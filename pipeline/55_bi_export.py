"""Export a small star schema for Power BI and Excel (reports/bi/*.csv), prices in Rs/kg.

Facts:  daily_price (Kerala and all-India series), market_month (each Kerala market, monthly median),
        hub_week (Kerala vs origin hubs), test_predictions (the warning model's held-out scores).
Dims:   markets (Kerala markets with district and north/central/south band), spike_events, model_scores.
Power BI builds its own date table in DAX; Excel reads the same files.
"""
import json

import pandas as pd

from common import OUT, connect

BI = OUT / "bi"


def band(lat):
    # Same cut-offs the site uses for the north-south finding.
    return "North (above 11°N)" if lat > 11 else "South (below 9.5°N)" if lat < 9.5 else "Central"


def main():
    BI.mkdir(parents=True, exist_ok=True)
    con = connect(read_only=True)

    con.execute("""SELECT date, commodity, CASE region WHEN 'India' THEN 'All-India' ELSE region END AS region,
                          round(price / 100, 2) AS rs_per_kg, round(arrival_t, 1) AS arrival_t, n_markets
                   FROM series ORDER BY date, commodity, region""").df().to_csv(BI / "daily_price.csv", index=False)

    con.execute("""SELECT date_trunc('month', date)::DATE AS month, commodity, market_key,
                          round(median(price) / 100, 2) AS rs_per_kg, count(*) AS days_reported,
                          round(sum(arrival_t), 1) AS arrival_t
                   FROM market_day WHERE state = 'Kerala' GROUP BY ALL ORDER BY 1, 2, 3""").df() \
        .to_csv(BI / "market_month.csv", index=False)

    # Latest coordinates: older source rows put some markets at a same-named town elsewhere (Pala, Chala).
    m = con.execute("""SELECT market_key, arg_max(market, date) AS market, arg_max(district, date) AS district,
                              round(arg_max(lat, date), 5) AS lat, round(arg_max(lon, date), 5) AS lon
                       FROM market_day WHERE state = 'Kerala' GROUP BY market_key ORDER BY market""").df()
    m["band"] = [band(x) if pd.notna(x) else "Unknown" for x in m.lat]
    off = (m.lat - m.groupby("district").lat.transform("median")).abs()
    assert (off < 1).all(), f"market far from its district: {m[off >= 1].market.tolist()}"
    m.to_csv(BI / "markets.csv", index=False)

    w = pd.read_csv(OUT / "csv" / "weekly_kerala_vs_hubs.csv")
    w[["kerala", "hub"]] = (w[["kerala", "hub"]] / 100).round(2)
    w.rename(columns={"wk": "week", "kerala": "kerala_rs_per_kg", "hub": "hub_rs_per_kg"}).to_csv(BI / "hub_week.csv", index=False)

    s = pd.read_csv(OUT / "csv" / "spike_events.csv")
    s[["price_start", "price_peak"]] = (s[["price_start", "price_peak"]] / 100).round(2)
    s.insert(0, "event_id", range(1, len(s) + 1))
    s["hub_first"] = s.hub_lead_days > 0
    s.to_csv(BI / "spike_events.csv", index=False)

    p = pd.read_csv(OUT / "csv" / "test_predictions.csv")
    p["rs_per_kg"] = (p.price / 100).round(2)
    p["spike_ahead"] = p.y.astype(int)
    p[["date", "commodity", "rs_per_kg", "spike_ahead", "score", "alert"]].round({"score": 4}) \
        .to_csv(BI / "test_predictions.csv", index=False)

    res = json.loads((OUT / "model_results.json").read_text())
    rows = []
    for kind, block in (("Trader rule", res["rules"]), ("Model", res["models"])):
        for name, r in block.items():
            rows.append({"approach": name, "kind": kind, "selected": name == res["selected_on_validation"],
                         "threshold": r["threshold"], **{f"test_{k}": v for k, v in r["test"].items()},
                         "valid_pr_auc": r["valid"]["pr_auc"]})
    pd.DataFrame(rows).to_csv(BI / "model_scores.csv", index=False)

    con.close()
    print(f"wrote {len(list(BI.glob('*.csv')))} BI tables to {BI.relative_to(OUT.parent)}")


if __name__ == "__main__":
    main()
