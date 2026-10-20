"""Synthetic lookback day files for the lab v2 dry run and tests (SYSTEM_V2_PREREG.md §4). OPS/test.

No lab outcome is ever computed on real data before the freeze; the v2 dry run uses this synthetic lookback with v1's
synthetic forward world (analysis/system/synth.py, unchanged).

Each UTC day 2026-01-01 .. 2026-08-31 gets a BID and an ASK file in the real Dukascopy bi5 format (LZMA-alone,
big-endian '>5if' records (sec, open, close, low, high, volume), 1,440 per day, prices x1000 as int32) under
<lookback>/raw/YYYY/MM/DD/{BID,ASK}.bi5, and a days.csv row whose fetched_utc is the day + 26 h 30 min.

Model (seed 11): a mid random walk in whole cents with per-minute sd (bp) by model-clock session (Asia 0.9, London
1.2, New York 1.6, as v1's synth); minutes in the model-clock daily break (00:00-01:00) and on model weekends are flats
(volume 0, price unchanged), and 5% of the other minutes too; the half-spread is $0.15, $0.20 or $0.25; open minutes
have volume 1.0. The whole walk is shifted so the last close is exactly $4,200.000, v1's synthetic start price. No
drift, so no seed has an edge.
"""
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
