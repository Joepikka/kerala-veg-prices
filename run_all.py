"""Rebuild everything from the raw files: ingest, warehouse, tests, analyses, model, chart data.

Scrapers are separate (they call outside services and are cached):
  python pipeline/00_download.py           mandi CSVs (5 GB)
  python pipeline/10_scrape_news.py        GDELT news-volume timelines
  python pipeline/12_weather.py            Open-Meteo weather at the hubs (after 02_build picks hubs)
"""
import runpy
import sys
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent / "pipeline"
STEPS = ["01_ingest.py", "02_build.py", "03_tests.py", "21_transmission.py", "22_dispersion.py",
         "23_spikes.py", "30_model.py", "50_export.py",
         "55_bi_export.py", "60_excel.py"]

sys.path.insert(0, str(PIPELINE))
for step in STEPS:
    print(f"== {step}", flush=True)
    start = time.time()
    runpy.run_path(str(PIPELINE / step), run_name="__main__")
    print(f"   {time.time() - start:,.0f}s", flush=True)
