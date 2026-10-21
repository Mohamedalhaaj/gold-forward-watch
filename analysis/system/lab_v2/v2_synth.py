"""Synthetic lookback day files, and deterministic edge edits of v1's synthetic forward world, for the lab v2 dry run
and tests (SYSTEM_V2_PREREG.md §4). OPS/test.

No lab outcome is ever computed on real data before the freeze; the v2 dry run uses this synthetic lookback with v1's
synthetic forward world (analysis/system/synth.py, unchanged), to which apply_edges adds the edits in EDGES (2026-11-16
.. 2026-12-02, after the days the R-V2-42 and forecast-coverage tests rely on), so the dry run and the judge fixture
reach every reachable branch of the decisions and of the execution (register R-FX).

Each UTC day 2026-01-01 .. 2026-08-31 gets a BID and an ASK file in the real Dukascopy bi5 format (LZMA-alone,
big-endian '>5if' records (sec, open, close, low, high, volume), 1,440 per day, prices x1000 as int32) under
<lookback>/raw/YYYY/MM/DD/{BID,ASK}.bi5, and a days.csv row whose fetched_utc is the day + 26 h 30 min.

Model (seed 11): a mid random walk in whole cents with per-minute sd (bp) by model-clock session (Asia 0.9, London
1.2, New York 1.6, as v1's synth); minutes in the model-clock daily break (00:00-01:00) and on model weekends are flats
(volume 0, price unchanged), and 5% of the other minutes too; the half-spread is $0.15, $0.20 or $0.25; open minutes
have volume 1.0. The whole walk is shifted so the last close is exactly $4,200.000, v1's synthetic start price. No
drift, so no seed has an edge.
"""
import csv
import hashlib
import lzma
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2paths  # noqa: E402,F401

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import v2_data  # noqa: E402

SD_BP = {"asia": 0.9, "london": 1.2, "ny": 1.6}
END_PRICE_MILLI = 4_200_000
RECORD = np.dtype([("sec", ">i4"), ("open", ">i4"), ("close", ">i4"), ("low", ">i4"), ("high", ">i4"),
                   ("volume", ">f4")])


def encode(sec, o, c, lo, hi, vol):
    rec = np.zeros(len(sec), dtype=RECORD)
    rec["sec"], rec["open"], rec["close"], rec["low"], rec["high"], rec["volume"] = sec, o, c, lo, hi, vol
    return lzma.compress(rec.tobytes(), format=lzma.FORMAT_ALONE)


def lookback_world(lookback_dir, first="2026-01-01", last="2026-08-31", seed=11):
    """Write the synthetic lookback store. Returns the number of days written."""
    rng = np.random.default_rng(seed)
    days = list(pd.date_range(first, last, freq="D"))
    paths = []
    p = 0                                         # mid in milli-dollars, relative; shifted at the end
    for day in days:
        utc = pd.date_range(day, periods=1440, freq="min", tz="UTC")
        mt = v2_data.harness()._to_server(utc)
        hour = mt.hour.values
        closed = (mt.dayofweek.values >= 5) | (hour == 0)
        sd = np.where(hour < 10, SD_BP["asia"], np.where(hour < 15, SD_BP["london"], SD_BP["ny"]))
        flat = closed | (rng.uniform(size=1440) < 0.05)
        cents = np.rint(rng.standard_normal(1440) * sd * 1e-4 * 4200 * 100).astype(np.int64)
        wig_h = np.rint(np.abs(rng.standard_normal(1440)) * sd * 0.5e-4 * 4200 * 100).astype(np.int64)
        wig_l = np.rint(np.abs(rng.standard_normal(1440)) * sd * 0.5e-4 * 4200 * 100).astype(np.int64)
        half = rng.choice(np.array([150, 200, 250]), size=1440)
        o = np.empty(1440, np.int64)
        c = np.empty(1440, np.int64)
        for i in range(1440):
            o[i] = p
            if not flat[i]:
                p = p + 10 * cents[i]
            c[i] = p
        h = np.where(flat, o, np.maximum(o, c) + 10 * wig_h)
        lo = np.where(flat, o, np.minimum(o, c) - 10 * wig_l)
        vol = np.where(flat, 0.0, 1.0).astype(np.float32)
        paths.append((day, o, c, lo, h, half, vol))
    shift = END_PRICE_MILLI - p
    rows = []
    for day, o, c, lo, h, half, vol in paths:
        sec = np.arange(1440) * 60
        for side, sgn in (("BID", -1), ("ASK", 1)):
            body = encode(sec, o + shift + sgn * half, c + shift + sgn * half, lo + shift + sgn * half,
                          h + shift + sgn * half, vol)
            path = v2_data.raw_path(f"{lookback_dir}/raw", day, side)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            rows.append({"day": day.strftime("%Y-%m-%d"), "side": side, "status": "ok", "bytes": len(body),
                         "sha256": hashlib.sha256(body).hexdigest(), "records": 1440,
                         "vol_minutes": int((vol > 0).sum()),
                         "fetched_utc": (day + pd.Timedelta(hours=26, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    pd.DataFrame(rows, columns=v2_data.DAYS_COLS).to_csv(f"{lookback_dir}/days.csv", index=False,
                                                         lineterminator="\n")
    return len(days)


# ---------------------------------------------------------------- deterministic edge edits of the forward world
# Edits of v1's synthetic forward store (data/system, UTC days from 2026-11-13 on), so the synthetic dry run, and with
# it the judge fixture, reaches every reachable branch of lab v2's decisions and execution (register R-V2-16..19,
# R-FX). Every edited file stays a valid Dukascopy body: 1,440 records with increasing seconds, prices x1000 as int32.
# Times are model-clock minutes; prices are dollars on the named side, and every edit moves the bid and the ask by
# the same amount, so each minute keeps its own spread. Kinds:
# - wick_h / wick_l: that minute's high (low) on `side` becomes `level` (only ever further out than it was);
# - gap_open: that minute's open on `side` becomes `level`, and its high/low widen to include it (the close is kept);
# - flat: the minutes [at, until) become flats, as Dukascopy writes them: volume 0 and open = high = low = close = the
#   side's close of the minute before;
# - missing: the (UTC day, side) is `missing` in days.csv (no file; fetched_utc = the day + 26 h 30 min + 72 h, when
#   v1 declares a side missing after three days of retries).
EDGES = (
    # S5 2026-11-16 long: a gap through its stop at the 18:00 open (stop filled at the open; its twin stops too)
    {"kind": "gap_open", "at": "2026-11-16 18:00", "side": "BID", "level": 4088.7},
    # S3 2026-11-17 long: 21 flat minutes, so the 15th non-live minute (15:14) settles it at X ("gap"; twin too)
    {"kind": "flat", "at": "2026-11-17 15:00", "until": "2026-11-17 15:21"},
    # S2 2026-11-18: first touch of the $4,200 figure at 22:10, too late to trade (abstain_window)
    {"kind": "wick_h", "at": "2026-11-18 22:10", "side": "ASK", "level": 4201.5},
    # S2 2026-11-19: a short at 09:05 ($4,100 touched), then a long signal at 10:05 while it is open (ignored_open);
    # the 10:00 wick also stops the short at X intrabar, while its long twin runs to the time exit
    {"kind": "wick_l", "at": "2026-11-19 09:00", "side": "BID", "level": 4098.5},
    {"kind": "wick_h", "at": "2026-11-19 10:00", "side": "ASK", "level": 4201.5},
    # S3 2026-11-20 short: stopped at X inside its entry minute 14:31 (the entry minute is on the path)
    {"kind": "wick_h", "at": "2026-11-20 14:31", "side": "ASK", "level": 4179.0},
    # S3 2026-11-23 long: its exit minute 16:29 also reaches X: the stop wins the tie with the time exit
    {"kind": "wick_l", "at": "2026-11-23 16:29", "side": "BID", "level": 4141.0},
    # S5 2026-11-24 short: stopped at X intrabar at 18:30 (its long twin is not); S2 also fires on that wick
    {"kind": "wick_h", "at": "2026-11-24 18:30", "side": "ASK", "level": 4241.0},
    # S2 2026-12-01: a long signal at 02:00 (the 01:55 bar, UTC 2026-11-30 23:55), and the ASK of UTC 2026-12-01 is
    # missing: no ask at the entry minute 02:01 (entry at the ask close of 01:59), one-sided minutes on the whole path,
    # so the 15th non-live minute settles it at X ("gap"; its mid twin too); F of 12-01 and early 12-02 undefined
    {"kind": "wick_h", "at": "2026-12-01 01:55", "side": "ASK", "level": 4201.5},
    {"kind": "missing", "day": "2026-12-01", "side": "ASK"},
    # S2 2026-12-02: a short signal at 05:05 whose entry slot has no F_S (abstain_U)
    {"kind": "wick_l", "at": "2026-12-02 05:00", "side": "BID", "level": 4098.5},
)


def _decode_records(path):
    raw = lzma.decompress(Path(path).read_bytes(), format=lzma.FORMAT_ALONE)
    return np.frombuffer(raw, dtype=RECORD).copy()


def apply_edges(v1_data, edges=None):
    """Apply the edge edits to v1's synthetic store at `v1_data` (raw files and days.csv). Returns the edited
    (UTC day, side) keys."""
    import bars as v1bars
    edges = EDGES if edges is None else edges
    v1_data = Path(v1_data)
    days_path = v1_data / "days.csv"
    with open(days_path, newline="") as f:
        rows = list(csv.DictReader(f))
    index = {(r["day"], r["side"]): r for r in rows}
    cache, missing = {}, set()

    def rec(day, side):
        key = (day, side)
        if key not in cache:
            cache[key] = _decode_records(v2_data.raw_path(v1_data / "raw", day, side))
        return cache[key]

    def utc_minute(model_t):
        u = v1bars.model_to_utc(pd.Timestamp(model_t))
        return u.strftime("%Y-%m-%d"), u.hour * 60 + u.minute

    for e in edges:
        kind = e["kind"]
        if kind == "missing":
            missing.add((e["day"], e["side"]))
            continue
        day, m = utc_minute(e["at"])
        if kind == "flat":
            day2, m2 = utc_minute(e["until"])
            if day2 != day:
                raise ValueError(f"flat {e} crosses a UTC day")
            for side in ("BID", "ASK"):
                r = rec(day, side)
                last = int(r["close"][m - 1])
                for f in ("open", "high", "low", "close"):
                    r[f][m:m2] = last
                r["volume"][m:m2] = 0.0
            continue
        side = e["side"]
        r = rec(day, side)
        target = int(round(e["level"] * 1000))
        field = {"wick_h": "high", "wick_l": "low", "gap_open": "open"}[kind]
        delta = target - int(r[field][m])
        if (kind == "wick_h" and delta <= 0) or (kind == "wick_l" and delta >= 0):
            raise ValueError(f"edge {e} would not widen the bar ({delta / 1000:+.3f})")
        for s in ("BID", "ASK"):
            q = rec(day, s)
            q[field][m] += delta
            if kind == "gap_open":
                q["high"][m] = max(q["high"][m], q["open"][m])
                q["low"][m] = min(q["low"][m], q["open"][m])
    edited = set()
    for (day, side), r in cache.items():
        if (day, side) in missing:
            continue
        body = lzma.compress(r.tobytes(), format=lzma.FORMAT_ALONE)
        path = v2_data.raw_path(v1_data / "raw", day, side)
        path.write_bytes(body)
        row = index[(day, side)]
        row.update({"bytes": str(len(body)), "sha256": hashlib.sha256(body).hexdigest(),
                    "vol_minutes": str(int((r["volume"] > 0).sum()))})
        edited.add((day, side))
    for day, side in missing:
        v2_data.raw_path(v1_data / "raw", day, side).unlink()
        row = index[(day, side)]
        row.update({"status": "missing", "bytes": "", "sha256": "", "records": "", "vol_minutes": "",
                    "fetched_utc": (pd.Timestamp(day) + pd.Timedelta(hours=26 + 72, minutes=30)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ")})
        edited.add((day, side))
    with open(days_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=v2_data.DAYS_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return sorted(edited)


FIXTURE_DOCS = ("README.md", "MANIFEST.sha256")


def fixture_manifest(base):
    """`sha256  path` lines of every file under `base` (paths relative, sorted), the docs excluded."""
    base = Path(base)
    out = []
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base).as_posix()
        if p.is_file() and rel not in FIXTURE_DOCS:
            out.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
    return out


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--manifest":
        lines = fixture_manifest(sys.argv[2])
        with open(f"{sys.argv[2]}/MANIFEST.sha256", "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"{len(lines)} files")
    else:
        print("usage: v2_synth.py --manifest <fixture dir>")
