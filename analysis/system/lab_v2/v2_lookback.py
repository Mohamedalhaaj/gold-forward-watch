"""The lab v2 input-only lookback store (SYSTEM_V2_PREREG.md §0 and §2.5 item 3). OPS (transport); the store rules
are v1 §1's.

- Range: every UTC day 2026-01-01 .. 2026-08-31 (2026-01-01 because the seed input starts at 2026-01-02 00:00 model =
  2026-01-01 22:00 UTC; v1's committed raw store covers 2026-09-01 on, and lab v2 reads those days from there).
- Each raw file is written once, untouched, to data/system/lab_v2/lookback/raw/YYYY/MM/DD/{BID,ASK}.bi5 (MM = calendar
  month), and its row is appended to data/system/lab_v2/lookback/days.csv right after it (columns as v1's days.csv:
  day, side, status, bytes, sha256, records, vol_minutes, fetched_utc). Never in data/system/raw or days.csv.
- A body is valid iff it decodes to exactly 1,440 one-minute records (v1 A1 item 11); anything else is a failed
  attempt, logged in data/system/lab_v2/lookback/attempts.csv and retried on later runs. A (day, side) still failing 3
  days after its first failed attempt gets a permanent `missing` row and is never fetched again.
- An orphan raw file (written by a run that died before its row): a valid orphan is adopted (its own bytes, its own
  row; the new body is not used and the attempt is logged); an invalid one is replaced.
- No re-check fetches (the days are history; the independent judge re-downloads them, J1).
- Request budget: one request at a time, 1.5 s apart (--pace-s for a slower manual fetch), up to 4 attempts with
  5/20/60 s backoff on connection errors, 429 and 5xx; at most `max_requests` requests and `budget_s` seconds per call
  (cloud runs: 60 and 180 s; the next run continues). A 404 is not retried within the call.

Usage (the pre-freeze fetch, outside the sandbox):
  uv run --frozen python -I analysis/system/lab_v2/v2_lookback.py [--dir DIR] [--max-requests N] [--budget-s S]
      [--pace-s S]
"""
import argparse
import csv
import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2paths  # noqa: E402

import pandas as pd  # noqa: E402

import bi5  # noqa: E402
import v2_data  # noqa: E402

UA = "Mozilla/5.0 (gold-forward-watch lab-v2 lookback)"
PACE_S = 1.5
BACKOFF_S = (5, 20, 60)
MISSING_AFTER = pd.Timedelta(days=3)
RECORDS_PER_DAY = 1440
ATTEMPT_COLS = ["utc", "day", "side", "result"]
CLOUD_MAX_REQUESTS = 60
CLOUD_BUDGET_S = 180
DEFAULT_DIR = v2paths.ROOT / "data" / "system" / "lab_v2" / "lookback"


def iso(t):
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_csv(path, cols, rows):
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerows(rows)


def http_get(url, sleep=time.sleep):
    last = 0
    for k in range(len(BACKOFF_S) + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            last = e.code
            if e.code == 404 or (400 <= e.code < 500 and e.code != 429):
                return e.code, b""
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            last = 0
        if k < len(BACKOFF_S):
            sleep(BACKOFF_S[k])
    return last, b""


def validate(body, day):
    df = bi5.decode(body, day)
    if len(df) != RECORDS_PER_DAY:
        raise ValueError(f"{len(df)} records, not {RECORDS_PER_DAY}")
    return df


def days():
    return list(pd.date_range(v2_data.LOOKBACK_FIRST, v2_data.LOOKBACK_LAST, freq="D"))


def _row(key, side, body, df, now):
    return {"day": key, "side": side, "status": "ok", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "records": len(df), "vol_minutes": int((df.volume > 0).sum()), "fetched_utc": iso(now)}


def run(lookback_dir=DEFAULT_DIR, now=None, max_requests=CLOUD_MAX_REQUESTS, budget_s=CLOUD_BUDGET_S, get=http_get,
        sleep=time.sleep, clock=time.monotonic, pace_s=PACE_S):
    """One fetch pass over the (day, side) pairs that are not final yet. Returns a summary."""
    d0 = Path(lookback_dir)
    t_end = clock() + budget_s
    now = v2_data.to_utc(now) if now is not None else pd.Timestamp.now(tz="UTC").floor("s")
    st = v2_data.final_status(v2_data.read_days(d0 / "days.csv"))
    first_fail = {}
    att = d0 / "attempts.csv"
    if att.exists():
        for r in pd.read_csv(att, dtype=str, keep_default_na=False).itertuples():
            first_fail.setdefault((r.day, r.side), v2_data.to_utc(r.utc))
    s = {"fetched": 0, "failed": 0, "missing_new": 0, "adopted": 0, "requests": 0, "pending": 0}
    for d in days():
        for side in v2_data.SIDES:
            key = (d.strftime("%Y-%m-%d"), side)
            if key in st:
                continue
            if s["requests"] >= max_requests or clock() > t_end:
                s["pending"] += 1
                continue
            s["requests"] += 1
            code, body = get(bi5.url(d, side))
            sleep(pace_s)
            result = f"http {code}"
            if code == 200:
                try:
                    df = validate(body, d)
                except Exception as e:  # noqa: BLE001 - any decode failure is a failed fetch
                    result = f"bad body: {e}"[:120]
                else:
                    p = v2_data.raw_path(d0 / "raw", d, side)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    row = _write_or_adopt(d0, p, key, side, body, df, now, s)
                    append_csv(d0 / "days.csv", v2_data.DAYS_COLS, [row])
                    st[key] = ("ok", row["sha256"])
                    s["fetched"] += 1
                    continue
            s["failed"] += 1
            append_csv(att, ATTEMPT_COLS, [{"utc": iso(now), "day": key[0], "side": side, "result": result}])
            since = first_fail.setdefault(key, now)
            if now >= since + MISSING_AFTER:
                append_csv(d0 / "days.csv", v2_data.DAYS_COLS,
                           [{"day": key[0], "side": side, "status": "missing", "bytes": "", "sha256": "",
                             "records": "", "vol_minutes": "", "fetched_utc": iso(now)}])
                st[key] = ("missing", "")
                s["missing_new"] += 1
    return s


def _write_or_adopt(d0, p, key, side, body, df, now, s):
    if p.exists():
        old = p.read_bytes()
        try:
            odf = validate(old, key[0])
        except Exception:  # noqa: BLE001 - an invalid orphan is replaced
            odf = None
        if odf is not None:
            note = "adopted an orphan raw file" + ("" if old == body else "; the new body differs and is not used")
            append_csv(d0 / "attempts.csv", ATTEMPT_COLS, [{"utc": iso(now), "day": key[0], "side": side,
                                                            "result": note}])
            s["adopted"] += 1
            return _row(key[0], side, old, odf, now)
        append_csv(d0 / "attempts.csv", ATTEMPT_COLS, [{"utc": iso(now), "day": key[0], "side": side,
                                                        "result": "replaced an invalid orphan raw file"}])
    p.write_bytes(body)
    return _row(key[0], side, body, df, now)


def verify(lookback_dir=DEFAULT_DIR):
    """Every ok row's raw file exists with its recorded sha256; returns the problems."""
    d0 = Path(lookback_dir)
    bad = []
    for (day, side), (status, sha) in v2_data.final_status(v2_data.read_days(d0 / "days.csv")).items():
        if status != "ok":
            continue
        p = v2_data.raw_path(d0 / "raw", day, side)
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            bad.append(f"lookback {day} {side}")
    return bad


def complete(lookback_dir=DEFAULT_DIR):
    """True when every (day, side) of the range has a final row."""
    st = v2_data.final_status(v2_data.read_days(Path(lookback_dir) / "days.csv"))
    return all((d.strftime("%Y-%m-%d"), s) in st for d in days() for s in v2_data.SIDES)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--max-requests", type=int, default=CLOUD_MAX_REQUESTS)
    ap.add_argument("--budget-s", type=float, default=CLOUD_BUDGET_S)
    ap.add_argument("--pace-s", type=float, default=PACE_S)
    a = ap.parse_args(argv)
    s = run(a.dir, max_requests=a.max_requests, budget_s=a.budget_s, pace_s=a.pace_s)
    print(s)
    print("complete:", complete(a.dir), "store problems:", verify(a.dir) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
