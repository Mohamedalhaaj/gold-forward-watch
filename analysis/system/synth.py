"""Synthetic random-walk Dukascopy day files, for the lab dry run and the tests (SYSTEM_V1_PREREG.md §9). OPS/test.

The pre-freeze lab dry run uses these bars only; no lab outcome is ever computed on real data before the freeze.
Each UTC day gets a BID and an ASK file in the real bi5 format (LZMA-alone, big-endian 24-byte records, prices x1000),
written to <data>/raw/YYYY/MM/DD/{BID,ASK}.bi5 with a days.csv row whose fetched_utc is the day + 26 h 30 min, so a
run at time `now` sees exactly the days a real run would have fetched by then.

Model: the mid is a random walk with per-minute sd (bp) by model-clock session (Asia 0.9, London 1.2, New York 1.6);
minutes in the model-clock daily break (00:00-01:00) and on model weekends are flats (volume 0, price unchanged); 5%
of open minutes are flats too. The spread is $0.30-0.50 per minute. No drift, so no rule has an edge.
"""
import hashlib
import lzma

import numpy as np
import pandas as pd

import bars
import bi5
import fetch

SD_BP = {"asia": 0.9, "london": 1.2, "ny": 1.6}


def encode(sec, o, c, l, h, vol):
    rec = np.zeros(len(sec), dtype=bi5.RECORD)
    rec["sec"], rec["open"], rec["close"], rec["low"], rec["high"], rec["volume"] = sec, o, c, l, h, vol
    return lzma.compress(rec.tobytes(), format=lzma.FORMAT_ALONE)


def world(data_dir, first="2026-09-01", last="2027-02-26", seed=7, price0=4200.0):
    """Write the synthetic raw store. Returns the number of days written."""
    rng = np.random.default_rng(seed)
    p = price0
    rows = []
    for day in pd.date_range(first, last, freq="D"):
        utc = pd.date_range(day, periods=1440, freq="min", tz="UTC")
        mt = bars.to_model(utc)
        hour = mt.hour.values
        closed = (mt.dayofweek.values >= 5) | (hour == 0)
        sd = np.where(hour < 10, SD_BP["asia"], np.where(hour < 15, SD_BP["london"], SD_BP["ny"]))
        flat = closed | (rng.uniform(size=1440) < 0.05)
        step = rng.standard_normal(1440) * sd * 1e-4
        wig_h = np.abs(rng.standard_normal(1440)) * sd * 0.5e-4
        wig_l = np.abs(rng.standard_normal(1440)) * sd * 0.5e-4
        o = np.empty(1440)
        c = np.empty(1440)
        h = np.empty(1440)
        l = np.empty(1440)
        for i in range(1440):
            o[i] = p
            if flat[i]:
                c[i] = h[i] = l[i] = p
            else:
                c[i] = p * np.exp(step[i])
                h[i] = max(o[i], c[i]) * np.exp(wig_h[i])
                l[i] = min(o[i], c[i]) * np.exp(-wig_l[i])
                p = c[i]
        half = (0.30 + 0.20 * rng.uniform(size=1440)) / 2
        vol = np.where(flat, 0.0, 0.01 + rng.uniform(size=1440)).astype(np.float32)
        sec = np.arange(1440) * 60
        for side, sgn in (("BID", -1), ("ASK", 1)):
            q = {k: np.round((v + sgn * half) * 1000).astype(np.int64) for k, v in
                 (("o", o), ("c", c), ("l", l), ("h", h))}
            body = encode(sec, q["o"], q["c"], q["l"], q["h"], vol)
            path = bars.raw_path(f"{data_dir}/raw", day, side)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            rows.append({"day": day.strftime("%Y-%m-%d"), "side": side, "status": "ok", "bytes": len(body),
                         "sha256": hashlib.sha256(body).hexdigest(), "records": 1440,
                         "vol_minutes": int((vol > 0).sum()),
                         "fetched_utc": fetch.iso(day + pd.Timedelta(hours=26, minutes=30))})
    fetch.append_csv(f"{data_dir}/days.csv", fetch.DAYS_COLS, rows)
    return len(rows) // 2
