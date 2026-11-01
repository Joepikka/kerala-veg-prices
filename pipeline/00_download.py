"""Step 0: download the two India Data Portal CSVs with parallel, resumable range requests.

Each part re-resolves the portal's download link (it redirects to a short-lived signed storage URL),
so parts can run for longer than one signed URL lives. An existing partial file is kept and only the
remaining bytes are fetched.
"""
import shutil
from concurrent.futures import ThreadPoolExecutor

import requests

from common import RAW, USER_AGENT

BASE = "https://ckandev.indiadataportal.com/dataset/1749d812-35b4-4635-ac29-dd3116ed31b0/resource"
FILES = {
    "old-source.csv": (f"{BASE}/21ecb9f0-7bf9-42d0-af24-df2e230e4a0a/download/apmc-arrivals-and-prices-old-source.csv", 4_233_268_613),
    "new-source.csv": (f"{BASE}/078fd1ea-dab6-4aca-aed9-3a4b8b2c761d/download/apmc-arrivals-and-prices-new-source.csv", 802_731_921),
}
PARTS = 8


def fetch_range(url, part_path, start, end):
    for _ in range(20):
        have = part_path.stat().st_size if part_path.exists() else 0
        if start + have > end:
            return
        try:
            with requests.get(url, headers={"Range": f"bytes={start + have}-{end}", "User-Agent": USER_AGENT},
                              stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(part_path, "ab") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
        except requests.RequestException as e:
            print(f"    {part_path.name}: retry after {e}", flush=True)
    raise RuntimeError(f"{part_path.name} incomplete")


def download(name, url, size):
    target = RAW / name
    have = target.stat().st_size if target.exists() else 0
    if have == size:
        print(f"  {name}: complete")
        return
    remaining = size - have
    chunk = -(-remaining // PARTS)
    ranges = [(have + i * chunk, min(size, have + (i + 1) * chunk) - 1) for i in range(PARTS)]
    parts = [RAW / f"{name}.part{i}" for i in range(PARTS)]
    print(f"  {name}: {have:,} bytes on disk, fetching {remaining:,} in {PARTS} parts", flush=True)
    with ThreadPoolExecutor(PARTS) as pool:
        list(pool.map(lambda a: fetch_range(url, *a), [(p, s, e) for p, (s, e) in zip(parts, ranges)]))
    with open(target, "ab") as out:
        for p in parts:
            with open(p, "rb") as f:
                shutil.copyfileobj(f, out)
            p.unlink()
    if target.stat().st_size != size:
        raise SystemExit(f"{name}: size {target.stat().st_size} != {size}")
    print(f"  {name}: complete", flush=True)


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    for name, (url, size) in FILES.items():
        download(name, url, size)
