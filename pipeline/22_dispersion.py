"""Same-day price gaps between Kerala markets: how much a buyer saves by choosing the market.

For each day and crop with at least 5 Kerala markets reporting:
  spread  = (90th percentile - 10th percentile) / median   (robust to one odd report)
Pairs of Kerala markets within 40 km of each other: median absolute same-day price gap, in %.
"""
import json

from common import OUT, connect


def main():
    con = connect(read_only=True)
    con.execute("""
        CREATE TEMP TABLE daily_spread AS
        SELECT date, commodity, count(*) n_markets,
               (quantile_cont(price, 0.9) - quantile_cont(price, 0.1)) / median(price) AS spread
        FROM market_day WHERE state = 'Kerala'
        GROUP BY ALL HAVING count(*) >= 5
    """)
    monthly = con.execute("""
        SELECT commodity, date_trunc('month', date)::DATE AS month, median(spread) spread, median(n_markets) markets
        FROM daily_spread GROUP BY ALL ORDER BY commodity, month
    """).df()
    pairs = con.execute("""
        WITH k AS (SELECT * FROM market_day WHERE state='Kerala' AND lat IS NOT NULL),
        p AS (
            SELECT a.commodity, a.date, a.market m1, b.market m2,
                   abs(a.price - b.price) / ((a.price + b.price) / 2) AS gap,
                   6371 * 2 * asin(sqrt(pow(sin(radians(b.lat - a.lat) / 2), 2)
                        + cos(radians(a.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - a.lon) / 2), 2))) AS km
            FROM k a JOIN k b ON a.commodity = b.commodity AND a.date = b.date AND a.market < b.market
        )
        SELECT commodity, count(*) pair_days, median(gap) median_gap, quantile_cont(gap, 0.9) p90_gap,
               avg(CASE WHEN gap >= 0.2 THEN 1 ELSE 0 END) share_gap_20pct
        FROM p WHERE km <= 40 GROUP BY commodity ORDER BY commodity
    """).df()
    con.close()
    summary = {r.commodity: {k: (round(float(v), 4) if isinstance(v, float) else int(v))
                             for k, v in r._asdict().items() if k != "commodity"}
               for r in pairs.itertuples(index=False)}
    summary["daily_spread_median"] = {c: round(float(g.spread.median()), 4) for c, g in monthly.groupby("commodity")}
    (OUT / "dispersion.json").write_text(json.dumps(summary, indent=1))
    monthly.to_csv(OUT / "csv" / "kerala_price_spread_monthly.csv", index=False)
    print(pairs.to_string(index=False))
    print("median daily spread (p90-p10)/median:", summary["daily_spread_median"])


if __name__ == "__main__":
    main()
