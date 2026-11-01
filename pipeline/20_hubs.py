"""Choose origin hubs from the data: the markets that move the most volume of each crop.

Two kinds per crop: the 4 largest markets nationally, and the 3 largest in the states that border
and supply Kerala (Tamil Nadu, Karnataka). Kerala markets are destinations, never hubs.
Writes reports/hubs.json and the hub_day table (daily price and arrivals per hub).
"""
import json

from common import OUT, connect


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    hubs = con.execute("""
        WITH vol AS (
            SELECT commodity, state, market_key, any_value(market) market, any_value(lat) lat, any_value(lon) lon,
                   sum(arrival_t) AS tonnes, count(DISTINCT date) AS days
            FROM market_day WHERE state <> 'Kerala' AND lat IS NOT NULL
            GROUP BY commodity, state, market_key HAVING count(DISTINCT date) >= 500        -- reports most days of the period
        ), national AS (
            SELECT *, 'national' AS kind, row_number() OVER (PARTITION BY commodity ORDER BY tonnes DESC) rk FROM vol
        ), neighbour AS (
            SELECT *, 'neighbour' AS kind, row_number() OVER (PARTITION BY commodity ORDER BY tonnes DESC) rk
            FROM vol WHERE state IN ('Tamil Nadu', 'Karnataka')
        )
        SELECT commodity, kind, state, market, market_key, lat, lon, round(tonnes) tonnes, days
        FROM (SELECT * FROM national WHERE rk <= 4 UNION ALL SELECT * FROM neighbour WHERE rk <= 3)
        ORDER BY commodity, kind, tonnes DESC
    """).fetchall()
    cols = ["commodity", "kind", "state", "market", "market_key", "lat", "lon", "tonnes", "days"]
    rows = [dict(zip(cols, h)) for h in hubs]
    # A market can be both a national and a neighbour hub; keep it once, as national.
    seen, unique = set(), []
    for r in rows:
        key = (r["commodity"], r["market_key"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    (OUT / "hubs.json").write_text(json.dumps(unique, indent=1))
    con.execute("CREATE OR REPLACE TABLE hubs AS SELECT * FROM read_json_auto(?)", [str(OUT / "hubs.json")])
    con.execute("""
        CREATE OR REPLACE TABLE hub_day AS
        SELECT m.date, m.commodity, h.kind, m.market, m.market_key, m.state, m.price, m.arrival_t
        FROM market_day m JOIN hubs h USING (commodity, market_key)
    """)
    for r in unique:
        print(f"  {r['commodity']:7s} {r['kind']:9s} {r['market']:28s} {r['state']:15s} {r['tonnes']:>12,.0f} t  {r['days']} days")
    con.close()


if __name__ == "__main__":
    main()
