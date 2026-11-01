"""Find price-spike events in Kerala and when each one started at the origin hubs.

A spike day: the 7-day median Kerala price 14 days later is at least 30% above today's 7-day median.
Consecutive spike days (gaps under 10 days) form one event. For each event we also find the first day
the hub price crossed the same +30%-in-14-days rule, within 30 days before the Kerala start: the lag
between the two is how long Kerala buyers had to act.
Writes reports/spike_events.json (also read by the news scraper) and the label used by the model.
"""
import json

import pandas as pd

from common import CROPS, OUT, connect

RISE, HORIZON = 0.30, 14


def smooth_daily(df, col):
    s = df.set_index("date")[col].asfreq("D")
    return s.rolling(7, min_periods=4).median()


def spike_days(s):
    return (s.shift(-HORIZON) / s - 1) >= RISE


def main():
    con = connect(read_only=True)
    events = []
    for crop in CROPS:
        k = con.execute("SELECT date, price FROM series WHERE region='Kerala' AND commodity=? ORDER BY date", [crop]).df()
        h = con.execute("""SELECT date, sum(price*greatest(arrival_t,0.01))/sum(greatest(arrival_t,0.01)) price
                           FROM hub_day WHERE commodity=? GROUP BY 1 ORDER BY 1""", [crop]).df()
        k["date"], h["date"] = pd.to_datetime(k.date), pd.to_datetime(h.date)
        ks, hs = smooth_daily(k, "price"), smooth_daily(h, "price")
        kd, hd = spike_days(ks), spike_days(hs)
        days = kd[kd].index
        groups, current = [], []
        for d in days:
            if current and (d - current[-1]).days >= 10:
                groups.append(current)
                current = []
            current.append(d)
        if current:
            groups.append(current)
        for g in groups:
            start = g[0]
            window = ks[start: start + pd.Timedelta(days=HORIZON + len(g))]
            peak_day = window.idxmax()
            hub_window = hd[start - pd.Timedelta(days=30): start + pd.Timedelta(days=7)]
            hub_start = hub_window[hub_window].index.min() if hub_window.any() else None
            events.append({
                "commodity": crop, "start": start.date().isoformat(), "peak": peak_day.date().isoformat(),
                "price_start": round(float(ks[start]), 0), "price_peak": round(float(window.max()), 0),
                "rise_pct": round(float(window.max() / ks[start] - 1) * 100, 1),
                "hub_start": hub_start.date().isoformat() if hub_start is not None else None,
                "hub_lead_days": (start - hub_start).days if hub_start is not None else None,
            })
    con.close()
    (OUT / "spike_events.json").write_text(json.dumps(events, indent=1))
    df = pd.DataFrame(events)
    df.to_csv(OUT / "csv" / "spike_events.csv", index=False)
    print(df.to_string(index=False))
    led = df.hub_lead_days.dropna()
    print(f"{len(df)} events; hub spike came first in {(led > 0).sum()} of {len(df)}; median lead {led[led > 0].median()} days")


if __name__ == "__main__":
    main()
