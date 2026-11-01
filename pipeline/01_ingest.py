"""Step 1: the two India Data Portal CSVs -> one typed Parquet file with a single schema.

Old source (2021 on) and new source (to Oct 2025) name columns differently; both are mapped here.
Prices are Rs/quintal and arrivals are tonnes in both (checked in 03_tests.py).
A manifest records each file's size and row count so the tests can reconcile them.
"""
import json

from common import RAW, STAGING, connect

OUT = STAGING / "mandi.parquet"
MANIFEST = STAGING / "manifest.json"

OLD = f"""
SELECT
    try_cast(report_date AS DATE)           AS date,
    trim(state_name)                        AS state,
    trim(district_name)                     AS district,
    trim(market_center)                     AS market,
    try_cast(market_code AS INTEGER)        AS market_code,
    try_cast(latitude AS DOUBLE)            AS lat,
    try_cast(longitude AS DOUBLE)           AS lon,
    trim(commodity_name)                    AS commodity,
    trim(variety)                           AS variety,
    NULL::VARCHAR                           AS grade,
    try_cast(arrival_quantity AS DOUBLE)    AS arrival_qty,
    trim(arrivals_unit)                     AS arrival_unit,
    try_cast(min_price AS DOUBLE)           AS min_price,
    try_cast(max_price AS DOUBLE)           AS max_price,
    try_cast(modal_price AS DOUBLE)         AS modal_price,
    trim(price_unit)                        AS price_unit,
    'old'                                   AS source
FROM read_csv('{(RAW / "old-source.csv").as_posix()}', header = true, all_varchar = true)
"""

NEW = f"""
SELECT
    try_cast(date AS DATE) AS date, trim(state_name) AS state, trim(district_name) AS district,
    trim(market_center_name) AS market, try_cast(market_center_code AS INTEGER) AS market_code,
    try_cast(latitude AS DOUBLE) AS lat, try_cast(longitude AS DOUBLE) AS lon, trim(commodity_name) AS commodity,
    trim(variety) AS variety, trim(grade) AS grade, try_cast(arrival_quantity AS DOUBLE) AS arrival_qty,
    trim(arrival_units) AS arrival_unit, try_cast(min_price AS DOUBLE) AS min_price,
    try_cast(max_price AS DOUBLE) AS max_price, try_cast(modal_price AS DOUBLE) AS modal_price,
    trim(price_unit) AS price_unit, 'new' AS source
FROM read_csv('{(RAW / "new-source.csv").as_posix()}', header = true, all_varchar = true)
"""


def main():
    STAGING.mkdir(parents=True, exist_ok=True)
    con = connect()
    manifest = {}
    for name in ["old-source.csv", "new-source.csv"]:
        path = RAW / name
        rows = con.execute(f"SELECT count(*) FROM read_csv('{path.as_posix()}', header=true, all_varchar=true)").fetchone()[0]
        manifest[name] = {"bytes": path.stat().st_size, "rows": rows}
        print(f"  {name}: {rows:,} rows")
    tmp = OUT.with_suffix(".parquet.tmp")
    con.execute(f"COPY ({OLD} UNION ALL {NEW}) TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    tmp.replace(OUT)
    manifest["staged_rows"] = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}'").fetchone()[0]
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"  staged {manifest['staged_rows']:,} rows -> {OUT.name}")
    con.close()


if __name__ == "__main__":
    main()
