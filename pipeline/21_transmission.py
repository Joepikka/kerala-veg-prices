"""How price changes at origin hubs reach Kerala: lag, pass-through, and asymmetry.

Weekly data (Mon-Sun means) because markets do not report every day.
For each crop, the origin signal is the arrival-weighted price across that crop's hubs.

1. Lead-lag: correlation of Kerala's weekly log change with the hub's change 0-4 weeks earlier.
2. Granger test: do past hub changes help predict Kerala's change beyond Kerala's own past (lags 1-2)?
3. Pass-through, split by direction (Houck-style asymmetric distributed lag):
     dK_t = a + sum_{j=0..2} b+_j * max(dH_{t-j},0) + sum_{j=0..2} b-_j * min(dH_{t-j},0) + c * dK_{t-1} + e
   Cumulative pass-through of a rise = sum b+_j; of a fall = sum b-_j; Wald test that they are equal.
   Newey-West (HAC) standard errors because weekly changes are autocorrelated.
"""
import json

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import grangercausalitytests

from common import CROPS, OUT, connect

LAGS = 2


def weekly(con, crop):
    k = con.execute("""SELECT date_trunc('week', date) wk, avg(price) kerala FROM series
                       WHERE region='Kerala' AND commodity=? GROUP BY 1""", [crop]).df()
    h = con.execute("""SELECT date_trunc('week', date) wk,
                              sum(price*greatest(arrival_t,0.01))/sum(greatest(arrival_t,0.01)) hub,
                              sum(arrival_t) hub_arrivals
                       FROM hub_day WHERE commodity=? GROUP BY 1""", [crop]).df()
    df = k.merge(h, on="wk").sort_values("wk").set_index("wk")
    df = df.asfreq("W-MON")  # explicit gaps stay NaN; no interpolation
    df["dK"] = np.log(df.kerala).diff()
    df["dH"] = np.log(df.hub).diff()
    return df


def analyse(df):
    d = df[["dK", "dH"]].copy()
    out = {"weeks": int(d.dropna().shape[0])}
    out["lead_lag"] = {f"{lag}": round(float(d.dK.corr(d.dH.shift(lag))), 3) for lag in range(0, 5)}
    out["best_lag_weeks"] = int(max(range(0, 5), key=lambda l: d.dK.corr(d.dH.shift(l))))

    g = grangercausalitytests(d[["dK", "dH"]].dropna(), maxlag=LAGS)
    out["granger_p"] = {str(l): round(float(g[l][0]["ssr_ftest"][1]), 4) for l in g}

    X = pd.DataFrame(index=d.index)
    for j in range(LAGS + 1):
        X[f"up{j}"] = d.dH.shift(j).clip(lower=0)
        X[f"down{j}"] = d.dH.shift(j).clip(upper=0)
    X["dK_lag1"] = d.dK.shift(1)
    data = pd.concat([d.dK, X], axis=1).dropna()
    model = sm.OLS(data.dK, sm.add_constant(data.drop(columns="dK"))).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    up = [f"up{j}" for j in range(LAGS + 1)]
    down = [f"down{j}" for j in range(LAGS + 1)]
    up_sum, down_sum = model.params[up].sum(), model.params[down].sum()
    # Standard errors of the sums from the coefficient covariance matrix.
    cov = model.cov_params()
    se = lambda names: float(np.sqrt(cov.loc[names, names].values.sum()))
    wald = model.wald_test(" + ".join(up) + " = " + " + ".join(down), scalar=True)
    out["pass_through"] = {
        "rise": round(float(up_sum), 3), "rise_se": round(se(up), 3),
        "fall": round(float(down_sum), 3), "fall_se": round(se(down), 3),
        "equal_p": round(float(wald.pvalue), 4), "r2": round(float(model.rsquared), 3), "n": int(model.nobs),
    }
    return out


def main():
    con = connect(read_only=True)
    results, weekly_rows = {}, []
    for crop in CROPS:
        df = weekly(con, crop)
        results[crop] = analyse(df)
        weekly_rows.append(df[["kerala", "hub", "hub_arrivals"]].assign(commodity=crop).reset_index())
        r = results[crop]
        pt = r["pass_through"]
        print(f"  {crop:7s} best lag {r['best_lag_weeks']} wk, corr {r['lead_lag']}, granger p {r['granger_p']}")
        print(f"          pass-through rise {pt['rise']} (se {pt['rise_se']}) vs fall {pt['fall']} (se {pt['fall_se']}), equal p={pt['equal_p']}")
    con.close()
    (OUT / "transmission.json").write_text(json.dumps(results, indent=1))
    pd.concat(weekly_rows).to_csv(OUT / "csv" / "weekly_kerala_vs_hubs.csv", index=False)


if __name__ == "__main__":
    (OUT / "csv").mkdir(parents=True, exist_ok=True)
    main()
