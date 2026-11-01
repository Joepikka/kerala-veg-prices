"""Export tidy CSVs shaped for Flourish templates (one file per chart) and site data.

Flourish wants wide tables for line charts (date column + one column per series) and long tables for
maps and scatters. Every file here is written from warehouse tables or analysis outputs, never typed in.
"""
import json

import pandas as pd

from common import OUT, connect

CHARTS = OUT / "flourish"


def main():
    CHARTS.mkdir(parents=True, exist_ok=True)
    con = connect(read_only=True)

    # 1. Kerala vs India weekly price per crop (Rs/kg): the "Kerala premium" line chart.
    w = con.execute("""
        SELECT date_trunc('week', date)::DATE AS week, commodity, region, avg(price) / 100 AS rs_per_kg
        FROM series GROUP BY ALL
    """).df()
    w["series"] = w.region + " " + w.commodity.str.lower()
    w.pivot_table(index="week", columns="series", values="rs_per_kg").round(2).to_csv(CHARTS / "01_kerala_vs_india_weekly.csv")

    # 1b. Same series, one row per week and crop: the site's line chart with a crop filter (Flourish 30761381).
    long = w.pivot_table(index=["week", "commodity"], columns="region", values="rs_per_kg").round(2).reset_index()
    long.rename(columns={"commodity": "crop", "Kerala": "Kerala markets", "India": "All-India (arrival-weighted)"}) \
        .sort_values(["crop", "week"], key=lambda c: c.map({"Tomato": 0, "Onion": 1, "Potato": 2}) if c.name == "crop" else c) \
        [["week", "crop", "Kerala markets", "All-India (arrival-weighted)"]].to_csv(CHARTS / "05_price_by_crop_long.csv", index=False)

    # 2. Premium: Kerala price / India price, monthly.
    m = con.execute("""
        WITH x AS (SELECT date_trunc('month', date)::DATE AS month, commodity, region, avg(price) p FROM series GROUP BY ALL)
        SELECT k.month, k.commodity, round(k.p / i.p, 3) AS kerala_to_india
        FROM x k JOIN x i ON k.month = i.month AND k.commodity = i.commodity AND i.region = 'India'
        WHERE k.region = 'Kerala' ORDER BY 1
    """).df()
    m.pivot(index="month", columns="commodity", values="kerala_to_india").to_csv(CHARTS / "02_kerala_premium_monthly.csv")

    # 3. Map: Kerala markets with median tomato/onion/potato price (Rs/kg) and reporting days.
    con.execute("""
        COPY (
            SELECT arg_max(market, date) AS market, arg_max(district, date) AS district,
                   round(arg_max(lat, date), 5) lat, round(arg_max(lon, date), 5) lon, commodity,
                   round(median(price) / 100, 1) AS median_rs_per_kg, count(*) AS days_reported
            FROM market_day WHERE state = 'Kerala' AND lat IS NOT NULL AND date >= DATE '2025-06-01'
            GROUP BY market_key, commodity HAVING count(*) >= 30 ORDER BY commodity, market
        ) TO '""" + (CHARTS / "03_kerala_markets_map.csv").as_posix() + "' (HEADER)")

    # 3b. Each market against the Kerala median for its crop (the map's colour), and a tomato-only map file.
    mp = pd.read_csv(CHARTS / "03_kerala_markets_map.csv")
    gap = mp.median_rs_per_kg / mp.groupby("commodity").median_rs_per_kg.transform("median") - 1
    mp.insert(5, "vs_kerala_median", pd.cut(gap, [-9, -0.10, 0.10, 9], labels=[
        "10%+ cheaper than the Kerala median", "Within 10% of the median", "10%+ dearer than the Kerala median"]).astype(str))
    mp.insert(7, "pct_vs_median", (gap * 100).round(0))
    mp.to_csv(CHARTS / "03_kerala_markets_map.csv", index=False)
    mp[mp.commodity == "Tomato"].drop(columns="commodity").to_csv(CHARTS / "06_kerala_tomato_markets_map.csv", index=False)

    # 4. Hubs: where Kerala's supply prices are set.
    hubs = pd.DataFrame(json.loads((OUT / "hubs.json").read_text()))
    hubs.to_csv(CHARTS / "04_origin_hubs.csv", index=False)
    con.close()
    print(f"wrote {len(list(CHARTS.glob('*.csv')))} chart files to {CHARTS.relative_to(OUT.parent)}")


if __name__ == "__main__":
    main()
