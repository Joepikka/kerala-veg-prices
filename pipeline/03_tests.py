"""Step 3: data tests. Non-zero exit if anything fails."""
import json
import os
import sys

from common import ROOT, STAGING, connect


def check(con, name, sql):
    ok = bool(con.execute(sql).fetchone()[0])
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def main():
    os.chdir(ROOT)
    con = connect(read_only=True)
    m = json.loads((STAGING / "manifest.json").read_text())
    raw = m["old-source.csv"]["rows"] + m["new-source.csv"]["rows"]
    results = [
        check(con, "staged rows == rows in both CSVs", f"SELECT {m['staged_rows']} = {raw}"),
        check(con, "staged parquet has the manifest's row count",
              f"SELECT count(*) = {m['staged_rows']} FROM read_parquet('data/staging/mandi.parquet')"),
        check(con, "every TOP record is Rs/quintal or excluded and counted",
              "SELECT (SELECT count(*) FROM top_clean) + (SELECT dropped_units FROM dq_clean) <= (SELECT raw_rows FROM dq_clean)"),
        check(con, "clean prices inside 0-30,000 Rs/q", "SELECT bool_and(modal_price > 0 AND modal_price <= 30000) FROM top_clean"),
        check(con, "no overlap: old source ends before 27 Oct 2025",
              "SELECT coalesce(max(date) < DATE '2025-10-27', true) FROM top_clean WHERE source = 'old'"),
        check(con, "market_day unique per market, day, crop",
              "SELECT count(*) = count(DISTINCT (market_key, date, commodity)) FROM market_day"),
        check(con, "series covers all three crops for Kerala and India",
              "SELECT count(DISTINCT (commodity, region)) = 6 FROM series"),
        check(con, "Kerala series is a weighted mean of Kerala market prices (within min-max)",
              """SELECT bool_and(s.price BETWEEN m.lo - 0.01 AND m.hi + 0.01) FROM series s
                 JOIN (SELECT date, commodity, min(price) lo, max(price) hi FROM market_day WHERE state='Kerala' GROUP BY ALL) m
                 USING (date, commodity) WHERE s.region = 'Kerala'"""),
        check(con, "one record per market, day, crop, variety and grade after dedup",
              "SELECT count(*) = count(DISTINCT (market_key, date, commodity, variety, coalesce(grade, ''))) FROM top_clean"),
        check(con, "outlier filter dropped under 1% of market-days",
              "SELECT (SELECT count(*) FROM market_day_all) - (SELECT count(*) FROM market_day) < 0.01 * (SELECT count(*) FROM market_day_all)"),
        check(con, "Kerala series stays within Rs 2-150/kg (no reporting artefacts)",
              "SELECT bool_and(price BETWEEN 200 AND 15000) FROM series WHERE region = 'Kerala'"),
        check(con, "hubs are never Kerala markets", "SELECT count(*) = 0 FROM hubs WHERE state = 'Kerala'"),
        check(con, "every crop has at least 3 hubs", "SELECT min(n) >= 3 FROM (SELECT count(*) n FROM hubs GROUP BY commodity)"),
    ]
    con.close()
    print(f"  {sum(results)}/{len(results)} tests passed")
    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
