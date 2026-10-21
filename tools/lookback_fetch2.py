"""Parallel one-off download of the lab v2 input-only lookback: one calendar month of 2026 per GitHub runner
(--month 1..8), Dukascopy XAUUSD M1 BID/ASK day files written untouched to
data/system/lab_v2/lookback/raw/YYYY/MM/DD/{BID,ASK}.bi5, plus github_manifest_MM.csv with sha256.
Transport only: each body is decoded to validate it; nothing else is computed. A file that keeps failing is listed as
'not fetched' and the job still saves everything it got.
"""
import argparse
import calendar
import csv
import datetime as dt
import hashlib
import lzma
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("data/system/lab_v2/lookback")
URL = "https://datafeed.dukascopy.com/datafeed/XAUUSD/{y}/{m0:02d}/{d:02d}/{side}_candles_min_1.bi5"


def get(url, tries=6):
    wait, code = 3.0, 0
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
            code = e.code
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            code = 0
        time.sleep(wait)
        wait = min(wait * 2, 60)
    return code, b""


def check(body):
    raw = lzma.decompress(body, format=lzma.FORMAT_ALONE)
    if len(raw) != 1440 * 24:
        raise ValueError(f"{len(raw) // 24} records")
    return 1440, sum(1 for i in range(0, len(raw), 24) if struct.unpack(">5if", raw[i:i + 24])[5] > 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", type=int, required=True)
    a = ap.parse_args()
    rows = []
    for dd in range(1, calendar.monthrange(2026, a.month)[1] + 1):
        day = dt.date(2026, a.month, dd)
        for side in ("BID", "ASK"):
            code, body = get(URL.format(y=2026, m0=a.month - 1, d=dd, side=side))
            now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            res, sha, n, vol = "not fetched", "", "", ""
            if code == 200 and body:
                try:
                    n, vol = check(body)
                    p = ROOT / "raw" / f"{day:%Y/%m/%d}" / f"{side}.bi5"
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(body)
                    res, sha = "ok", hashlib.sha256(body).hexdigest()
                except Exception as e:  # noqa: BLE001
                    res = f"invalid: {e}"
            rows.append([day.isoformat(), side, code, len(body), sha, n, vol, now, res])
            print(day, side, code, res, flush=True)
            time.sleep(0.3)
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / f"github_manifest_{a.month:02d}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "side", "http", "bytes", "sha256", "records", "vol_minutes", "fetched_utc", "result"])
        w.writerows(rows)
    print("ok", sum(r[-1] == "ok" for r in rows), "of", len(rows))


if __name__ == "__main__":
    main()
