"""Government price interventions for tomato, onion and potato, from Press Information Bureau releases.

Discovery: one GDELT query per crop restricted to pib.gov.in (GDELT indexes PIB releases).
Scraping: Scrapling fetches each release page (pib.gov.in has no robots.txt rules), extracts the title,
release date and body text, and a transparent keyword rule labels the intervention type.
Polite: own User-Agent, no fake headers, 3 s between pages, every page cached in data/scraped/pib/.
"""
import hashlib
import json
import re
import time
from urllib.parse import urlencode

import pandas as pd
from scrapling.fetchers import Fetcher

from common import CROPS, END, OUT, SCRAPED, START, USER_AGENT

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
CACHE = SCRAPED / "pib"

# Checked in order; the first match labels the release. Patterns are on lowercased text.
INTERVENTIONS = [
    ("export restriction", r"export (duty|ban|prohibit)|minimum export price|\bmep\b"),
    ("buffer stock release", r"buffer"),
    ("subsidised retail sale", r"subsidi[sz]ed|retail (sale|price) of rs|rs\.? ?\d+ ?(/|per) ?kg|nafed|nccf|kendriya bhandar"),
    ("stock limit", r"stock limit"),
    ("import", r"\bimport"),
]


def fetch(url, **kw):
    for attempt in range(6):
        page = Fetcher.get(url, timeout=60, stealthy_headers=False, headers={"User-Agent": USER_AGENT}, **kw)
        if page.status == 200:
            return page
        time.sleep(30 * 2 ** attempt)
    raise RuntimeError(f"{page.status} for {url}")


def discover(crop):
    path = CACHE / f"gdelt_{crop.lower()}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    params = {"query": f"{crop.lower()} domain:pib.gov.in", "mode": "artlist", "maxrecords": 250, "format": "json",
              "startdatetime": START.replace("-", "") + "000000", "enddatetime": END.replace("-", "") + "235959"}
    page = fetch(f"{GDELT}?{urlencode(params)}")
    body = page.body.decode("utf-8", "replace") if isinstance(page.body, bytes) else str(page.body)
    arts = json.loads(body).get("articles", []) if body.strip().startswith("{") else []
    path.write_text(json.dumps(arts, ensure_ascii=False), encoding="utf-8")
    time.sleep(8)
    return arts


def scrape_release(url):
    path = CACHE / "pages" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    page = fetch(url)
    title = " ".join(t.strip() for t in page.css("h2::text").getall() if t.strip())[:300]
    text = " ".join(t.strip() for t in page.css("#PdfDiv ::text, .innner-page-main-about-us-content-right-part ::text").getall() if t.strip())
    if not text:  # layout fallback: all paragraph text
        text = " ".join(t.strip() for t in page.css("p ::text").getall() if t.strip())
    stamp = re.search(r"Posted On:\s*([0-9]{1,2} [A-Z]{3} [0-9]{4})", " ".join(page.css("::text").getall()))
    rec = {"url": url, "title": title, "posted": stamp.group(1) if stamp else None, "text": text[:20000]}
    path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    time.sleep(3)
    return rec


def label(text):
    t = text.lower()
    return next((name for name, pat in INTERVENTIONS if re.search(pat, t)), "other mention")


def main():
    (CACHE / "pages").mkdir(parents=True, exist_ok=True)
    rows = []
    for crop in CROPS:
        arts = discover(crop)
        print(f"  {crop}: {len(arts)} PIB releases found via GDELT")
        for a in arts:
            rec = scrape_release(a["url"])
            body = f"{rec['title']} {rec['text']}"
            if crop.lower() not in body.lower():
                continue  # GDELT match not about this crop
            rows.append({"commodity": crop, "seen": a.get("seendate", "")[:8], "posted": rec["posted"],
                         "title": rec["title"] or a.get("title", ""), "type": label(body), "url": a["url"]})
    if not rows:
        print("no PIB releases found; interventions.csv not written")
        return
    df = pd.DataFrame(rows).drop_duplicates(subset=["commodity", "url"])
    df["date"] = pd.to_datetime(df.posted, format="%d %b %Y", errors="coerce").fillna(pd.to_datetime(df.seen, format="%Y%m%d"))
    df = df.sort_values("date")
    df.drop(columns=["seen"]).to_csv(OUT / "csv" / "interventions.csv", index=False)
    print(df.groupby(["commodity", "type"]).size().to_string())


if __name__ == "__main__":
    (OUT / "csv").mkdir(parents=True, exist_ok=True)
    main()
