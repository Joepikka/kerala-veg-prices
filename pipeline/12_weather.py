"""Daily rainfall and maximum temperature at each origin hub, from the Open-Meteo historical archive.

Hubs come from reports/hubs.json (written by 20_hubs.py from arrival volumes, not assumed).
Open-Meteo's archive API is free and needs no key; one call per hub covers the whole period.
"""
import json
import re
import time
from urllib.parse import urlencode

from scrapling.fetchers import Fetcher

from common import END, OUT, SCRAPED, START, USER_AGENT

API = "https://archive-api.open-meteo.com/v1/archive"


def main():
    hubs = json.loads((OUT / "hubs.json").read_text())
    out_dir = SCRAPED / "weather"
    out_dir.mkdir(parents=True, exist_ok=True)
    for h in hubs:
        path = out_dir / f"{re.sub(r'[^a-z0-9]+', '-', h['market_key'].lower())}.json"
        if path.exists():
            continue
        params = {"latitude": round(h["lat"], 4), "longitude": round(h["lon"], 4), "start_date": START,
                  "end_date": END, "daily": "precipitation_sum,temperature_2m_max", "timezone": "Asia/Kolkata"}
        page = Fetcher.get(f"{API}?{urlencode(params)}", timeout=90, stealthy_headers=False,
                           headers={"User-Agent": USER_AGENT})
        if page.status != 200:
            raise RuntimeError(f"Open-Meteo {page.status} for {h['market']}")
        body = page.body.decode() if isinstance(page.body, bytes) else str(page.body)
        path.write_text(body, encoding="utf-8")
        print(f"  {h['commodity']:7s} {h['market']}: {len(json.loads(body)['daily']['time'])} days")
        time.sleep(2)


if __name__ == "__main__":
    main()
