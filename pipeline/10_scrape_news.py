"""News coverage of tomato, onion and potato prices in India, from the GDELT DOC 2.0 API.

GDELT is built for programmatic access. Google News RSS and The Hindu BusinessLine are not used:
their robots.txt disallows them (BusinessLine names AI crawlers explicitly).

Two passes, kept small because GDELT throttles bursts (HTTP 429):
  timeline  one call per crop: daily count of matching Indian English articles over the whole period
            (the news-intensity feature).
  articles  article titles only for the windows around price spikes found in the data
            (python 10_scrape_news.py articles), used to classify each spike's stated cause.
Responses are cached in data/scraped/gdelt/, so reruns fetch only what is missing.
"""
import json
import sys
import time
from datetime import date, timedelta
from urllib.parse import urlencode

from scrapling.fetchers import Fetcher

from common import CROPS, END, OUT, SCRAPED, START, USER_AGENT

API = "https://api.gdeltproject.org/api/v2/doc/doc"
PAUSE_S = 8.0
CACHE = SCRAPED / "gdelt"


def query(crop):
    return f'("{crop.lower()} price" OR "{crop.lower()} prices") sourcecountry:india sourcelang:english'


def get_json(params, path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), False
    body, status = "", None
    for attempt in range(6):
        # stealthy_headers=False: no fake browser headers or Google referer; we say who we are.
        page = Fetcher.get(f"{API}?{urlencode(params)}", timeout=90, stealthy_headers=False,
                           headers={"User-Agent": USER_AGENT})
        status = page.status
        body = page.body.decode("utf-8", "replace").strip() if isinstance(page.body, bytes) else str(page.body)
        if status == 200 and (not body or body.startswith("{")):
            data = json.loads(body) if body else {}
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data, True
        time.sleep(30 * 2 ** attempt)  # throttled: back off 30 s, 60 s, 120 s ...
    raise RuntimeError(f"GDELT failed: {status} {body[:120]}")


def timeline():
    for crop in CROPS:
        params = {"query": query(crop), "mode": "timelinevolraw", "format": "json",
                  "startdatetime": START.replace("-", "") + "000000", "enddatetime": END.replace("-", "") + "235959"}
        data, fetched = get_json(params, CACHE / f"timeline_{crop.lower()}.json")
        series = data.get("timeline", [{}])[0].get("data", [])
        print(f"  timeline {crop}: {len(series)} days, {sum(p['value'] for p in series):,} articles")
        if fetched:
            time.sleep(PAUSE_S)


def articles():
    """Titles for +-10 days around each spike listed in reports/spike_events.json."""
    events = json.loads((OUT / "spike_events.json").read_text())
    for ev in events:
        a = date.fromisoformat(ev["start"]) - timedelta(days=10)
        b = date.fromisoformat(ev["start"]) + timedelta(days=10)
        params = {"query": query(ev["commodity"]), "mode": "artlist", "maxrecords": 250, "format": "json",
                  "sort": "datedesc", "startdatetime": f"{a:%Y%m%d}000000", "enddatetime": f"{b:%Y%m%d}235959"}
        data, fetched = get_json(params, CACHE / f"articles_{ev['commodity'].lower()}_{a:%Y%m%d}.json")
        print(f"  {ev['commodity']} spike {ev['start']}: {len(data.get('articles', []))} articles")
        if fetched:
            time.sleep(PAUSE_S)


if __name__ == "__main__":
    CACHE.mkdir(parents=True, exist_ok=True)
    articles() if sys.argv[1:] == ["articles"] else timeline()
