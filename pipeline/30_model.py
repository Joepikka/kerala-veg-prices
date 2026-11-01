"""Spike early warning: will Kerala's price be >=30% higher in 14 days?

One row per crop and day. Every feature uses only information available that day (past values).
Label: 7-day median Kerala price at t+14 >= 1.30 x 7-day median at t (same rule as 23_spikes.py).

Chronological split (no shuffling):
  train       2021-01-01 .. 2024-06-30
  validation  2024-07-01 .. 2025-03-31   (choose the alert threshold here)
  test        2025-04-01 .. 2026-05-31   (reported once)
Labels look 14 days ahead, so the last 14 days before each split boundary are dropped from the
earlier set (a purge gap); otherwise training rows would contain the start of the next period.

Models: two rules a buyer could use without ML, logistic regression, gradient boosting.
Feature sets: market-only; + weather at hubs; + news intensity (if scraped). Each is evaluated so the
site can show whether the scraped data earns its place.
"""
import json
import re

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_fscore_support
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import CROPS, OUT, SCRAPED, connect

RISE, HORIZON, PURGE = 0.30, 14, 14
SPLITS = {"train": ("2021-01-01", "2024-06-30"), "valid": ("2024-07-01", "2025-03-31"), "test": ("2025-04-01", "2026-05-31")}


def daily(series):
    return series.asfreq("D").rolling(7, min_periods=4).median()


def crop_frame(con, crop, hubs):
    k = con.execute("SELECT date, price FROM series WHERE region='Kerala' AND commodity=? ORDER BY 1", [crop]).df()
    h = con.execute("""SELECT date, sum(price*greatest(arrival_t,0.01))/sum(greatest(arrival_t,0.01)) price,
                              sum(arrival_t) arrivals
                       FROM hub_day WHERE commodity=? GROUP BY 1 ORDER BY 1""", [crop]).df()
    k.date, h.date = pd.to_datetime(k.date), pd.to_datetime(h.date)
    kp = daily(k.set_index("date").price)
    hp = daily(h.set_index("date").price)
    ha = h.set_index("date").arrivals.asfreq("D").fillna(0)
    f = pd.DataFrame(index=kp.index)
    f["commodity"] = crop
    f["price"] = kp
    for d in (7, 14, 28):
        f[f"k_mom{d}"] = np.log(kp / kp.shift(d))
        f[f"h_mom{d}"] = np.log(hp / hp.shift(d)).reindex(f.index)
    f["k_vol14"] = np.log(kp).diff().rolling(14).std()
    f["k_vs_year"] = np.log(kp / kp.rolling(365, min_periods=180).median())
    f["h_vs_year"] = np.log(hp / hp.rolling(365, min_periods=180).median()).reindex(f.index)
    f["kerala_premium"] = np.log(kp / hp.reindex(f.index))
    arr7 = ha.rolling(7).sum()
    f["arr_vs_28"] = np.log1p(arr7) - np.log1p(ha.rolling(28).sum() / 4)
    f["arr_vs_year"] = (np.log1p(arr7) - np.log1p(arr7.rolling(365, min_periods=180).median())).reindex(f.index)
    doy = f.index.dayofyear
    f["season_sin"], f["season_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    f = f.join(weather(crop, hubs), how="left")
    f = f.join(news(crop), how="left")
    f["y"] = (kp.shift(-HORIZON) / kp - 1 >= RISE).astype(float).where(kp.shift(-HORIZON).notna())
    return f


def weather(crop, hubs):
    frames = []
    for h in [h for h in hubs if h["commodity"] == crop]:
        p = SCRAPED / "weather" / f"{re.sub(r'[^a-z0-9]+', '-', h['market_key'].lower())}.json"
        if p.exists():
            d = json.loads(p.read_text())["daily"]
            frames.append(pd.DataFrame({"rain": d["precipitation_sum"], "tmax": d["temperature_2m_max"]},
                                       index=pd.to_datetime(d["time"])))
    if not frames:
        return pd.DataFrame()
    w = pd.concat(frames).groupby(level=0).mean()
    out = pd.DataFrame(index=w.index)
    out["rain14"] = w.rain.rolling(14).sum()
    out["rain30"] = w.rain.rolling(30).sum()
    # Anomaly vs the same calendar window in the PREVIOUS year only (no future information).
    out["rain30_vs_lastyear"] = out.rain30 - out.rain30.shift(365)
    out["tmax14"] = w.tmax.rolling(14).mean()
    return out


def news(crop):
    p = SCRAPED / "gdelt" / f"timeline_{crop.lower()}.json"
    if not p.exists():
        return pd.DataFrame()
    pts = json.loads(p.read_text()).get("timeline", [{}])[0].get("data", [])
    s = pd.Series({pd.to_datetime(x["date"][:8]): x["value"] for x in pts}).asfreq("D").fillna(0)
    return pd.DataFrame({"news7": np.log1p(s.rolling(7).sum()),
                         "news_vs_28": np.log1p(s.rolling(7).sum()) - np.log1p(s.rolling(28).sum() / 4)})


def split(df, name):
    a, b = SPLITS[name]
    part = df.loc[a:b]
    if name != "test":  # purge: drop rows whose label window reaches into the next period
        part = part.loc[: pd.Timestamp(b) - pd.Timedelta(days=PURGE)]
    return part


def evaluate(y, score, threshold):
    pred = score >= threshold
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    return {"pr_auc": round(float(average_precision_score(y, score)), 3), "precision": round(float(p), 3),
            "recall": round(float(r), 3), "f1": round(float(f), 3), "alerts": int(pred.sum()),
            "base_rate": round(float(y.mean()), 3)}


def best_threshold(y, score):
    grid = np.unique(np.quantile(score, np.linspace(0.5, 0.995, 120)))
    return float(max(grid, key=lambda t: precision_recall_fscore_support(y, score >= t, average="binary", zero_division=0)[2]))


def main():
    con = connect(read_only=True)
    hubs = json.loads((OUT / "hubs.json").read_text())
    df = pd.concat([crop_frame(con, c, hubs) for c in CROPS]).sort_index()
    con.close()
    for c in CROPS:
        df[f"is_{c.lower()}"] = (df.commodity == c).astype(float)
    df = df.dropna(subset=["y", "k_mom28", "h_mom28", "arr_vs_28"])

    market = ["k_mom7", "k_mom14", "k_mom28", "h_mom7", "h_mom14", "h_mom28", "k_vol14", "k_vs_year", "h_vs_year",
              "kerala_premium", "arr_vs_28", "arr_vs_year", "season_sin", "season_cos"] + [f"is_{c.lower()}" for c in CROPS]
    sets = {"market": market}
    if "rain14" in df:
        sets["market+weather"] = market + ["rain14", "rain30", "rain30_vs_lastyear", "tmax14"]
    if "news7" in df:
        sets["market+weather+news"] = sets.get("market+weather", market) + ["news7", "news_vs_28"]

    tr, va, te = (split(df, s) for s in ("train", "valid", "test"))
    results = {"rows": {s: int(len(x)) for s, x in (("train", tr), ("valid", va), ("test", te))},
               "positives": {s: int(x.y.sum()) for s, x in (("train", tr), ("valid", va), ("test", te))},
               "rules": {}, "models": {}}

    # Rules a buyer could apply without a model; thresholds also chosen on validation.
    for name, col in (("Kerala price already rising (7-day momentum)", "k_mom7"),
                      ("Hub price rising (14-day momentum)", "h_mom14")):
        t = best_threshold(va.y, va[col].fillna(-9))
        results["rules"][name] = {"threshold": round(t, 4), "valid": evaluate(va.y, va[col].fillna(-9), t),
                                  "test": evaluate(te.y, te[col].fillna(-9), t)}

    test_scores = {}
    for set_name, cols in sets.items():
        for model_name, model in (
            ("logistic", make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))),
            ("gradient_boosting", HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                                 l2_regularization=1.0, class_weight="balanced",
                                                                 random_state=7)),
        ):
            fill = tr[cols].median()  # training medians only, so no information from later periods
            X = lambda part: part[cols].fillna(fill) if model_name == "logistic" else part[cols]
            model.fit(X(tr), tr.y)
            sv, st = model.predict_proba(X(va))[:, 1], model.predict_proba(X(te))[:, 1]
            t = best_threshold(va.y, sv)
            key = f"{model_name} | {set_name}"
            results["models"][key] = {"threshold": round(t, 4), "valid": evaluate(va.y, sv, t),
                                      "test": evaluate(te.y, st, t),
                                      "test_brier": round(float(brier_score_loss(te.y, st)), 4)}
            test_scores[key] = st

    best = max(results["models"], key=lambda k: results["models"][k]["valid"]["pr_auc"])
    results["selected_on_validation"] = best
    out = te[["commodity", "price", "y"]].copy()
    out["score"] = test_scores[best]
    out["alert"] = out.score >= results["models"][best]["threshold"]

    # Event level, the question a buyer asks: was each test-period spike flagged before its peak?
    events = [e for e in json.loads((OUT / "spike_events.json").read_text()) if e["start"] >= SPLITS["test"][0]]
    warned = []
    for e in events:
        a = out[(out.commodity == e["commodity"])]
        window = a.loc[pd.Timestamp(e["start"]) - pd.Timedelta(days=14): pd.Timestamp(e["peak"])]
        first = window.index[window.alert].min() if window.alert.any() else None
        warned.append({**e, "warned": first is not None,
                       "days_before_peak": (pd.Timestamp(e["peak"]) - first).days if first is not None else None})
    alert_days = out[out.alert]
    false_alerts = alert_days[alert_days.y == 0]
    months = (te.index.max() - te.index.min()).days / 30.4
    results["events_test"] = {"events": len(warned), "warned": sum(w["warned"] for w in warned),
                              "median_days_before_peak": float(pd.Series([w["days_before_peak"] for w in warned if w["warned"]]).median()) if any(w["warned"] for w in warned) else None,
                              "false_alert_days_per_month": round(len(false_alerts) / months / len(CROPS), 2),
                              "detail": warned}
    out.reset_index(names="date").to_csv(OUT / "csv" / "test_predictions.csv", index=False)
    (OUT / "model_results.json").write_text(json.dumps(results, indent=1))

    print(f"rows {results['rows']}, positives {results['positives']}")
    for k, v in {**results["rules"], **results["models"]}.items():
        print(f"  {k:52s} valid PR-AUC {v['valid']['pr_auc']:.3f} | test PR-AUC {v['test']['pr_auc']:.3f} "
              f"P {v['test']['precision']:.2f} R {v['test']['recall']:.2f} F1 {v['test']['f1']:.2f}")
    print("selected on validation:", best)
    ev = results["events_test"]
    print(f"test events warned before peak: {ev['warned']}/{ev['events']}, median {ev['median_days_before_peak']} days ahead; "
          f"{ev['false_alert_days_per_month']} false-alert days per crop per month")


if __name__ == "__main__":
    main()
