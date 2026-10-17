"""Bars and clocks (SYSTEM_V1_PREREG.md §1, §3 item 1). FROZEN: bar rules.

- Mid M1 for the volmap: exactly pipeline/build_parquet.py (vendored byte-identically in vendor/pipeline/ and proved
  identical by tests/system/test_bars.py): per side concat, ts from ms, sort, drop duplicate ts keeping the first,
  outer join of bid and ask on ts, per-field mid. Flats (zero-volume minutes) are kept, as dukascopy-node -fl kept
  them for the validation data; rows present on one side only stay, with a NaN mid.
- Model (server) clock = America/New_York + 7 h through the vendored core.to_server, as guard.load_m1 maps the
  validation data. The volmap input is the model-clock frame with columns o, h, l, c = mid_o, mid_h, mid_l, mid_c.
- Lab M15 mid bars (§3 item 1): 15-minute model-clock bars from the M1 mid, OHLC over the minutes present (the
  standard aggregation, as core.grid_bars does); a bar is valid iff at least 12 of its minutes have volume on both
  sides (bid_vol > 0 and ask_vol > 0, review fix L1-M7).
- No timestamp before 2026-09-01 UTC is ever loaded (§0).
"""
from pathlib import Path

import numpy as np
import pandas as pd

import bi5
import core

FORWARD_FROM_UTC = pd.Timestamp("2026-09-01", tz="UTC")
NY = "America/New_York"
SEVEN = pd.Timedelta(hours=7)
LAB_OPEN = pd.Timedelta(hours=1, minutes=30)     # lab window [01:30, 23:30] model
LAB_CLOSE = pd.Timedelta(hours=23, minutes=30)
M15_MIN_VOL_MINUTES = 12


# ---------------------------------------------------------------- build_parquet.py, applied to decoded day files
def load_side(frames, side):
    """pipeline/build_parquet.load_side on in-memory dukascopy-node frames (side = "bid" or "ask")."""
    if not frames:
        msg = f"no CSVs found for side {side}"
        raise SystemExit(msg)
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp"]).sort_values("ts")
    df = df.drop_duplicates(subset="ts", keep="first").set_index("ts")
    return df.rename(
        columns={
            "open": f"{side}_o",
            "high": f"{side}_h",
            "low": f"{side}_l",
            "close": f"{side}_c",
            "volume": f"{side}_vol",
        }
    )


def build_m1(bid_frames, ask_frames):
    """pipeline/build_parquet.main without the file I/O: UTC-indexed frame with bid_*, ask_*, mid_*, spread_c."""
    bid, ask = load_side(bid_frames, "bid"), load_side(ask_frames, "ask")
    m = bid.join(ask, how="outer")
    for p in "ohlc":
        m[f"mid_{p}"] = (m[f"bid_{p}"] + m[f"ask_{p}"]) / 2
    m["spread_c"] = m["ask_c"] - m["bid_c"]
    if len(m) and m.index.min() < FORWARD_FROM_UTC:
        raise AssertionError("a bar before 2026-09-01 UTC must never be loaded")
    return m


# ---------------------------------------------------------------- clocks
def to_model(idx):
    """UTC (tz-aware) -> naive model clock (New York + 7 h), the vendored core.to_server."""
    return core.to_server(pd.DatetimeIndex(idx))


def model_to_utc(t):
    """Naive model time(s) -> tz-aware UTC. Weekday model times never fall on a repeated or skipped New York hour."""
    idx = pd.DatetimeIndex(np.atleast_1d(pd.to_datetime(t)))
    out = (idx - SEVEN).tz_localize(NY, ambiguous="raise", nonexistent="raise").tz_convert("UTC")
    return out if np.ndim(t) else out[0]


def model_frame(m):
    """Model-clock M1 frame: o, h, l, c (mid, as guard.load_m1 renames them) plus bid/ask and volumes."""
    f = m.copy()
    f.index = to_model(f.index)
    f = f.rename(columns={"mid_o": "o", "mid_h": "h", "mid_l": "l", "mid_c": "c"})
    return f.sort_index()


def volmap_input(mf):
    """Exactly the frame guard.load_m1 hands to models.build: model clock, columns o, h, l, c."""
    return mf[["o", "h", "l", "c"]]


# ---------------------------------------------------------------- raw store
def raw_path(raw_dir, day, side):
    day = pd.Timestamp(day)
    return Path(raw_dir) / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}" / f"{side}.bi5"


def load_store(raw_dir, days):
    """Mid M1 of the committed raw day files of `days` (UTC dates). Missing files are simply absent."""
    frames = {"BID": [], "ASK": []}
    for d in sorted(pd.Timestamp(x) for x in days):
        if d < FORWARD_FROM_UTC.tz_localize(None):
            raise AssertionError("a day before 2026-09-01 must never be loaded")
        for side in bi5.SIDES:
            p = raw_path(raw_dir, d, side)
            if p.exists():
                frames[side].append(bi5.decode(p.read_bytes(), d))
    if not frames["BID"] and not frames["ASK"]:
        return None
    empty = [bi5.decode(b"", "2026-09-01")]
    return build_m1(frames["BID"] or empty, frames["ASK"] or empty)


# ---------------------------------------------------------------- lab M15 mid bars
def has_volume(mf):
    return ((mf["bid_vol"] > 0) & (mf["ask_vol"] > 0)).values


def lab_bars(mf):
    """M15 mid bars on the model clock for every 15-minute start in the lab window of each weekday present.

    Columns: start, day, o, h, l, c, n (minutes present), nvol (minutes with volume on both sides), valid."""
    f = mf[mf.index.dayofweek < 5]
    if f.empty:
        return pd.DataFrame(columns=["start", "day", "o", "h", "l", "c", "n", "nvol", "valid"])
    key = f.index.floor("15min")
    vol = pd.Series(has_volume(f).astype(int), index=f.index)
    g = f.groupby(key)
    agg = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "n": g.o.size(),
                        "nvol": vol.groupby(key).sum()})
    days = pd.DatetimeIndex(f.index.normalize().unique()).sort_values()
    offs = pd.timedelta_range(LAB_OPEN, LAB_CLOSE - pd.Timedelta(minutes=15), freq="15min")
    starts = pd.DatetimeIndex((days.values[:, None] + offs.values[None, :]).ravel())
    out = agg.reindex(starts)
    out["n"] = out.n.fillna(0).astype(int)
    out["nvol"] = out.nvol.fillna(0).astype(int)
    out["valid"] = (out.nvol >= M15_MIN_VOL_MINUTES) & out.o.notna() & out.c.notna()
    out.insert(0, "day", starts.normalize())
    out.insert(0, "start", starts)
    return out.reset_index(drop=True)
