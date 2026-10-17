"""Dukascopy day candle files (SYSTEM_V1_PREREG.md §1). FROZEN: bar rules.

`{YYYY}/{MM0}/{DD}/{BID|ASK}_candles_min_1.bi5`, MM0 = 0-based month. LZMA-alone; 24-byte big-endian records
(int32 sec, int32 open, int32 close, int32 low, int32 high, float32 volume); prices / 1000; sec from 00:00 UTC.

`decode` returns the columns of a dukascopy-node CSV (timestamp in ms, open, high, low, close, volume), so the
mid builder in bars.py can apply pipeline/build_parquet.py's logic line for line.
"""
import datetime as dt
import lzma

import numpy as np
import pandas as pd

URL = "https://datafeed.dukascopy.com/datafeed/XAUUSD/{y:04d}/{m0:02d}/{d:02d}/{side}_candles_min_1.bi5"
SIDES = ("BID", "ASK")
RECORD = np.dtype([("sec", ">i4"), ("open", ">i4"), ("close", ">i4"), ("low", ">i4"), ("high", ">i4"),
                   ("volume", ">f4")])
PRICE_SCALE = 1000.0
COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def url(day, side):
    day = pd.Timestamp(day)
    if side not in SIDES:
        raise ValueError(side)
    return URL.format(y=day.year, m0=day.month - 1, d=day.day, side=side)


def decode(raw, day):
    """Records of one UTC day file. An empty body is a day without records."""
    day = pd.Timestamp(day).normalize()
    if len(raw) == 0:
        return pd.DataFrame({c: pd.Series(dtype="int64" if c == "timestamp" else "float64") for c in COLUMNS})
    data = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
    if len(data) % RECORD.itemsize:
        raise ValueError(f"{day.date()}: {len(data)} bytes is not a whole number of 24-byte records")
    rec = np.frombuffer(data, dtype=RECORD)
    sec = rec["sec"].astype("int64")
    if len(sec) and (sec.min() < 0 or sec.max() >= 86400 or (np.diff(sec) <= 0).any()):
        raise ValueError(f"{day.date()}: record seconds out of range or not increasing")
    base_ms = int((day - pd.Timestamp("1970-01-01")) // pd.Timedelta("1ms"))
    out = pd.DataFrame({
        "timestamp": base_ms + sec * 1000,
        "open": rec["open"].astype("float64") / PRICE_SCALE,
        "high": rec["high"].astype("float64") / PRICE_SCALE,
        "low": rec["low"].astype("float64") / PRICE_SCALE,
        "close": rec["close"].astype("float64") / PRICE_SCALE,
        "volume": rec["volume"].astype("float64"),
    })
    return out


def utc_day(d):
    return dt.date.fromisoformat(str(d)[:10])
