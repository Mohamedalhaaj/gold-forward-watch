"""Dukascopy fetch transport and the raw store (SYSTEM_V1_PREREG.md §1). OPS (transport); the store rules are §1.

- A UTC day D is fetched only when complete: at or after D+1 02:00 UTC. Every calendar day from 2026-09-01 is
  fetched (Sunday evening UTC is Monday's model-clock open).
- A body is valid iff it decodes to exactly 1,440 one-minute records (Amendment A1 item 11); an empty or short body
  is a failed attempt, retried on later runs.
- Each raw file is written once, untouched, to data/system/raw/YYYY/MM/DD/{BID,ASK}.bi5 (MM = calendar month), and
  its row in data/system/days.csv (append-only) records size, sha256, record and volume counts. The row is appended
  right after its file is written. A raw file without a row (a run that died in between: an orphan) is adopted: if
  it is itself a valid body, it is the first fetch, gets its row, and a different new body is logged to
  revisions.csv and never used; an invalid orphan is replaced by the new body. Each adoption is logged in
  attempts.csv.
- A failed fetch is retried on later runs and logged in data/system/attempts.csv. A (day, side) still failing 3 days
  after it became complete, or after its first failed attempt if that is later (a backfill), is written to days.csv
  as a permanent `missing` and never fetched again.
- Re-check: once a file is at least 24 h old it is fetched one more time. A different body goes to
  data/system/revisions.csv and is never used (review fix L1-M6); every re-check is logged in rechecks.csv.
- Polite transport: one request at a time, 1.5 s apart, up to 4 attempts with 5/20/60 s backoff on connection
  errors, 429 and 5xx; at most 150 requests and 20 minutes a run (the next run continues). A 404 (file not
  published yet) is not retried within the run.
- Lag (A1 item 11): lag_trading_days counts the UTC weekdays between the end of the complete data and the end it
  should have reached (the last day that is complete by the 02:00 UTC rule); run.py fails the run above 2.

Usage: uv run --frozen python -I analysis/system/fetch.py [--data DIR] [--now ISO] [--max-requests N]
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
import syspath  # noqa: E402

import pandas as pd  # noqa: E402

import bars  # noqa: E402
import bi5  # noqa: E402

FIRST_DAY = pd.Timestamp("2026-09-01")
COMPLETE_AFTER = pd.Timedelta(hours=26)        # D+1 02:00 UTC
MISSING_AFTER = pd.Timedelta(days=3)           # after the day became complete
RECHECK_AFTER = pd.Timedelta(hours=24)
RECORDS_PER_DAY = 1440
UA = "Mozilla/5.0 (gold-forward-watch system-v1)"
PACE_S = 1.5
BACKOFF_S = (5, 20, 60)
DAYS_COLS = ["day", "side", "status", "bytes", "sha256", "records", "vol_minutes", "fetched_utc"]
ATTEMPT_COLS = ["utc", "day", "side", "result"]
RECHECK_COLS = ["utc", "day", "side", "same", "bytes", "sha256"]
REVISION_COLS = ["utc", "day", "side", "committed_sha256", "refetch_sha256", "committed_bytes", "refetch_bytes"]


def utcnow():
    return pd.Timestamp.now(tz="UTC").floor("s")


def to_utc(t):
    """Timestamp (string, naive = UTC, or aware) -> tz-aware UTC."""
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def iso(t):
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_csv(path, cols):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=cols)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


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
    """(status, body). status 200 with the body, 404 for a file not published yet, or 0/5xx/429 after retries."""
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
    """Decoded frame of a fetched body, or raise: exactly 1,440 one-minute records (A1 item 11)."""
    df = bi5.decode(body, day)
    if len(df) != RECORDS_PER_DAY:
        raise ValueError(f"{len(df)} records, not {RECORDS_PER_DAY}")
    return df


def complete_days(now, first=FIRST_DAY):
    last = (to_utc(now).tz_localize(None) - COMPLETE_AFTER).normalize()
    if last < first:
        return []
    return list(pd.date_range(first, last, freq="D"))


def final_status(days_df, now=None):
    """{(day, side): status} for rows already written (ok or missing), as of `now` (None = all rows)."""
    if now is not None and len(days_df):
        days_df = days_df[[to_utc(t) <= to_utc(now) for t in days_df.fetched_utc]]
    return {(r.day, r.side): r.status for r in days_df.itertuples()}


def complete_through_utc(data_dir, now):
    """End (exclusive, UTC) of the longest run of days from 2026-09-01 whose both sides are final (ok or missing)."""
    st = final_status(read_csv(Path(data_dir) / "days.csv", DAYS_COLS), now)
    end = FIRST_DAY
    for d in complete_days(now):
        key = d.strftime("%Y-%m-%d")
        if all((key, s) in st for s in bi5.SIDES):
            end = d + pd.Timedelta(days=1)
        else:
            break
    return end.tz_localize("UTC")


def expected_through_utc(now):
    """Where complete_through_utc should be at `now`: the end of the last day complete by the 02:00 UTC rule."""
    days = complete_days(now)
    return (days[-1] + pd.Timedelta(days=1) if days else FIRST_DAY).tz_localize("UTC")


def lag_trading_days(data_dir, now):
    """UTC weekdays (Monday-Friday) from the end of the complete data to where it should be (0 = up to date)."""
    end, want = complete_through_utc(data_dir, now), expected_through_utc(now)
    if end >= want:
        return 0
    days = pd.date_range(end.tz_localize(None), want.tz_localize(None) - pd.Timedelta(days=1), freq="D")
    return int(sum(1 for d in days if d.dayofweek < 5))


def _row(key, side, body, df, now):
    return {"day": key, "side": side, "status": "ok", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "records": len(df), "vol_minutes": int((df.volume > 0).sum()), "fetched_utc": iso(now)}


def run(data_dir, now=None, max_requests=150, get=http_get, sleep=time.sleep, recheck=True, budget_s=1200,
        clock=time.monotonic):
    """One fetch pass, at most `max_requests` requests and `budget_s` seconds of transport. Returns a summary."""
    data_dir = Path(data_dir)
    t_end = clock() + budget_s
    now = to_utc(now) if now is not None else utcnow()
    days_df = read_csv(data_dir / "days.csv", DAYS_COLS)
    st = final_status(days_df)
    first_fail = {}
    for r in read_csv(data_dir / "attempts.csv", ATTEMPT_COLS).itertuples():
        first_fail.setdefault((r.day, r.side), to_utc(r.utc).tz_localize(None))
    summary = {"fetched": 0, "failed": 0, "missing_new": 0, "rechecked": 0, "revisions": 0, "requests": 0,
               "adopted": 0}
    for d in complete_days(now):
        for side in bi5.SIDES:
            key = (d.strftime("%Y-%m-%d"), side)
            if key in st:
                continue
            if summary["requests"] >= max_requests or clock() > t_end:
                summary["stopped_early"] = True
                break
            summary["requests"] += 1
            code, body = get(bi5.url(d, side))
            sleep(PACE_S)
            result = f"http {code}"
            if code == 200:
                try:
                    df = validate(body, d)
                except Exception as e:  # noqa: BLE001 - any decode failure is a failed fetch
                    result = f"bad body: {e}"[:120]
                else:
                    p = bars.raw_path(data_dir / "raw", d, side)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    row, _ = _adopt_or_write(data_dir, p, key, side, body, df, now, summary)
                    append_csv(data_dir / "days.csv", DAYS_COLS, [row])          # right after its file
                    st[key] = "ok"
                    summary["fetched"] += 1
                    continue
            summary["failed"] += 1
            append_csv(data_dir / "attempts.csv", ATTEMPT_COLS,
                       [{"utc": iso(now), "day": key[0], "side": side, "result": result}])
            # permanent only after 3 days of retries: from completion, or from the first failed attempt if later
            since = max(d + COMPLETE_AFTER, first_fail.get(key, now.tz_localize(None)))
            if now.tz_localize(None) >= since + MISSING_AFTER:
                append_csv(data_dir / "days.csv", DAYS_COLS,
                           [{"day": key[0], "side": side, "status": "missing", "bytes": "", "sha256": "",
                             "records": "", "vol_minutes": "", "fetched_utc": iso(now)}])
                st[key] = "missing"
                summary["missing_new"] += 1
    if recheck and clock() <= t_end:
        _recheck(data_dir, now, summary, get, sleep, limit=4)
    return summary


def _adopt_or_write(data_dir, p, key, side, body, df, now, summary):
    """Write a new raw file, or adopt an orphan (a raw file without a days.csv row). Returns (days.csv row, path)."""
    if p.exists():
        old = p.read_bytes()
        if old == body:
            note = "adopted an orphan raw file (same bytes)"
        else:
            try:
                odf = validate(old, key[0])
            except Exception:  # noqa: BLE001 - an invalid orphan (e.g. a cut write) is replaced
                odf = None
            if odf is not None:
                append_csv(data_dir / "revisions.csv", REVISION_COLS,
                           [{"utc": iso(now), "day": key[0], "side": side,
                             "committed_sha256": hashlib.sha256(old).hexdigest(),
                             "refetch_sha256": hashlib.sha256(body).hexdigest(), "committed_bytes": len(old),
                             "refetch_bytes": len(body)}])
                summary["revisions"] += 1
                summary["adopted"] += 1
                append_csv(data_dir / "attempts.csv", ATTEMPT_COLS, [{"utc": iso(now), "day": key[0], "side": side,
                                                                      "result": "adopted an orphan raw file; the "
                                                                                "new body differs (revisions.csv)"}])
                return _row(key[0], side, old, odf, now), p
            note = "replaced an invalid orphan raw file"
            p.write_bytes(body)
        summary["adopted"] += 1
        append_csv(data_dir / "attempts.csv", ATTEMPT_COLS,
                   [{"utc": iso(now), "day": key[0], "side": side, "result": note}])
        return _row(key[0], side, body, df, now), p
    p.write_bytes(body)
    return _row(key[0], side, body, df, now), p


def _recheck(data_dir, now, summary, get, sleep, limit):
    days_df = read_csv(data_dir / "days.csv", DAYS_COLS)
    done = read_csv(data_dir / "rechecks.csv", RECHECK_COLS)
    seen = set(zip(done.day, done.side))
    rows, revs = [], []
    for r in days_df[days_df.status == "ok"].itertuples():
        if len(rows) >= limit:
            break
        if (r.day, r.side) in seen:
            continue
        if to_utc(now) - to_utc(r.fetched_utc) < RECHECK_AFTER:
            continue
        code, body = get(bi5.url(r.day, r.side))
        sleep(PACE_S)
        summary["requests"] += 1
        if code != 200:
            continue
        sha = hashlib.sha256(body).hexdigest()
        same = sha == r.sha256
        rows.append({"utc": iso(now), "day": r.day, "side": r.side, "same": int(same), "bytes": len(body),
                     "sha256": sha})
        summary["rechecked"] += 1
        if not same:
            revs.append({"utc": iso(now), "day": r.day, "side": r.side, "committed_sha256": r.sha256,
                         "refetch_sha256": sha, "committed_bytes": r.bytes, "refetch_bytes": len(body)})
            summary["revisions"] += 1
    append_csv(data_dir / "rechecks.csv", RECHECK_COLS, rows)
    append_csv(data_dir / "revisions.csv", REVISION_COLS, revs)


def verify_store(data_dir):
    """Every ok row's raw file exists with its recorded sha256 (the derived files depend only on these)."""
    bad = []
    for r in read_csv(Path(data_dir) / "days.csv", DAYS_COLS).itertuples():
        if r.status != "ok":
            continue
        p = bars.raw_path(Path(data_dir) / "raw", r.day, r.side)
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != r.sha256:
            bad.append(f"{r.day} {r.side}")
    return bad


def ok_days(data_dir, now=None, before=None):
    """UTC days with at least one side ok (as of `now`), optionally only days before the UTC time `before`."""
    st = final_status(read_csv(Path(data_dir) / "days.csv", DAYS_COLS), now)
    days = {d for (d, _), v in st.items() if v == "ok"}
    if before is not None:
        days = {d for d in days if pd.Timestamp(d).tz_localize("UTC") < to_utc(before)}
    return sorted(days)


def missing(data_dir):
    df = read_csv(Path(data_dir) / "days.csv", DAYS_COLS)
    return [f"{r.day} {r.side}" for r in df.itertuples() if r.status == "missing"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(syspath.ROOT / "data" / "system"))
    ap.add_argument("--now")
    ap.add_argument("--max-requests", type=int, default=150)
    a = ap.parse_args(argv)
    now = to_utc(a.now) if a.now else None
    s = run(a.data, now=now, max_requests=a.max_requests)
    print(s)
    print("complete through (UTC, exclusive):", complete_through_utc(a.data, now or utcnow()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
