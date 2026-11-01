"""Shared paths and settings."""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
STAGING = ROOT / "data" / "staging"
SCRAPED = ROOT / "data" / "scraped"
WAREHOUSE_DB = ROOT / "data" / "warehouse.duckdb"
SQL = ROOT / "sql"
OUT = ROOT / "reports"

CROPS = ["Tomato", "Onion", "Potato"]
START, END = "2021-01-01", "2026-05-31"  # mandi data: old source 2021-Oct 2025, new source 27 Oct 2025-May 2026

# Identify ourselves honestly to every site we fetch from.
USER_AGENT = "kerala-veg-prices research scraper (student project; github.com/Joepikka)"


def connect(read_only=False):
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE_DB), read_only=read_only)
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = '{(ROOT / 'data' / 'tmp').as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET enable_progress_bar = false")
    return con
