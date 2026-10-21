"""One-off download of the lab v2 input-only lookback (SYSTEM_V2_PREREG.md §0): Dukascopy XAUUSD M1 BID/ASK day files
for every UTC day 2026-01-01 .. 2026-08-31, written untouched to data/system/lab_v2/lookback/raw/YYYY/MM/DD/{BID,ASK}.bi5
(MM = calendar month; the URL month is 0-based). Runs on GitHub because the feed throttles the client's Mac.
It is a transport only: it decodes each body to validate it, never computes anything else, and writes a manifest with
sha256 so the Mac side can import the bytes into the lab v2 store with the store's own functions.
"""
import csv
import datetime as dt
import hashlib
import lzma
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("data/system/lab_v2/lookback/raw")
MANIFEST = Path("data/system/lab_v2/lookback/github_manifest.csv")
URL = "https://datafeed.dukascopy.com/datafeed/XAUUSD/{y}/{m0:02d}/{d:02d}/{side}_candles_min_1.bi5"
FIRST, LAST = dt.date(2026, 1, 1), dt.date(2026, 8, 31)


def get(url):
    wait = 2.0
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
            code = e.code
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            code = 0
        print(f"  retry {attempt + 1} after http {code}, sleeping {wait:.0f}s", flush=True)
        time.sleep(wait)
        wait = min(wait * 2, 120)
    return code, b""


def records(body):
    raw = lzma.decompress(body, format=lzma.FORMAT_ALONE)
    if len(raw) % 24:
        raise ValueError("record size")
    vol = sum(1 for i in range(0, len(raw), 24) if struct.unpack(">5if", raw[i:i + 24])[5] > 0)
    return len(raw) // 24, vol


def main():
    rows, ok, bad = [], 0, 0
    day = FIRST
    while day <= LAST:
        for side in ("BID", "ASK"):
            p = ROOT / f"{day:%Y/%m/%d}" / f"{side}.bi5"
            code, body = get(URL.format(y=day.year, m0=day.month - 1, d=day.day, side=side))
            now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if code == 200 and body:
                try:
                    n, vol = records(body)
                except Exception as e:  # noqa: BLE001
                    rows.append([day.isoformat(), side, code, len(body), "", "", "", now, f"invalid: {e}"])
                    bad += 1
                    continue
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(body)
                rows.append([day.isoformat(), side, code, len(body), hashlib.sha256(body).hexdigest(), n, vol, now, "ok"])
                ok += 1
            else:
                rows.append([day.isoformat(), side, code, len(body), "", "", "", now, "not fetched"])
                bad += 1
            time.sleep(0.3)
        day += dt.timedelta(days=1)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "side", "http", "bytes", "sha256", "records", "vol_minutes", "fetched_utc", "result"])
        w.writerows(rows)
    print(f"ok {ok}, not ok {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
