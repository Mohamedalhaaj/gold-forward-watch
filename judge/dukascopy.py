"""The judge's own Dukascopy fetch and bi5 decode (v1 §1, IMPLEMENTATION_REGISTER R-V1-1 .. R-V1-3, R-V1-9).

Decode: LZMA-alone; 24-byte big-endian records (int32 sec, int32 open, int32 close, int32 low, int32 high,
float32 volume); price = int32 / 1000.0 in IEEE double; UTC. A body is valid with exactly 1,440 records, seconds in
[0, 86400) strictly increasing.
"""
import lzma
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

URL = "https://datafeed.dukascopy.com/datafeed/XAUUSD/{y:04d}/{m0:02d}/{d:02d}/{side}_candles_min_1.bi5"
UA = "Mozilla/5.0 (gold-forward-watch judge-v1)"
REC = np.dtype([("sec", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("v", ">f4")])


class BadBody(Exception):
    pass


def url(day, side):
    d = pd.Timestamp(day)
    return URL.format(y=d.year, m0=d.month - 1, d=d.day, side=side)


def records(body):
    """Raw records array (big-endian structured) of a bi5 body; raises BadBody."""
    if len(body) == 0:
        return np.zeros(0, dtype=REC)
    try:
        raw = lzma.decompress(body, format=lzma.FORMAT_ALONE)
    except lzma.LZMAError as e:
        raise BadBody(f"not LZMA-alone: {e}") from None
    if len(raw) % REC.itemsize:
        raise BadBody(f"decompressed length {len(raw)} is not a multiple of 24")
    r = np.frombuffer(raw, dtype=REC)
    s = r["sec"].astype(np.int64)
    if len(s) and (s.min() < 0 or s.max() >= 86400 or (np.diff(s) <= 0).any()):
        raise BadBody("seconds out of range or not strictly increasing")
    return r


def valid(body):
    r = records(body)
    if len(r) != 1440:
        raise BadBody(f"{len(r)} records, 1440 required")
    return r


def frame(body, day):
    """Decoded frame of one UTC day: ts (UTC), o, h, l, c (double), vol (float32 as double)."""
    r = records(body)
    start = pd.Timestamp(day).tz_localize("UTC") if pd.Timestamp(day).tzinfo is None else pd.Timestamp(day)
    ts = start + pd.to_timedelta(r["sec"].astype(np.int64) * 1000, unit="ms")
    return pd.DataFrame({
        "ts": ts,
        "o": r["o"].astype(np.int64) / 1000.0,
        "h": r["h"].astype(np.int64) / 1000.0,
        "l": r["l"].astype(np.int64) / 1000.0,
        "c": r["c"].astype(np.int64) / 1000.0,
        "vol": r["v"].astype(np.float64),
    })


def arrays_equal(a, b):
    """Decoded records equal field by field (sec and int32 prices exact, float32 volume bit-equal)."""
    if len(a) != len(b):
        return False
    for f in ("sec", "o", "c", "l", "h"):
        if not np.array_equal(a[f], b[f]):
            return False
    return np.array_equal(a["v"].view(">u4"), b["v"].view(">u4"))


class Transport:
    """One request at a time, `pace_s` after each; up to 4 attempts with 5/20/60 s backoff on connection errors, 429
    and 5xx; another 4xx returns at once (R-V1-9). Budget: max_requests and budget_s per run."""

    def __init__(self, pace_s=1.5, max_requests=150, budget_s=1200.0, opener=None, sleep=time.sleep):
        self.pace_s, self.max_requests, self.budget_s = pace_s, max_requests, budget_s
        self.opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
        self.sleep = sleep
        self.n = 0
        self.t0 = time.monotonic()

    def exhausted(self):
        return self.n >= self.max_requests or time.monotonic() - self.t0 >= self.budget_s

    def get(self, u):
        """(status, body); status 0 = connection error after the retries; None when the budget is exhausted."""
        status, body = 0, b""
        for attempt, back in enumerate((5, 20, 60, None)):
            if self.exhausted():
                return None
            self.n += 1
            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA})
                with self.opener(req, 60) as resp:
                    status, body = resp.status, resp.read()
            except urllib.error.HTTPError as e:
                status, body = e.code, b""
            except Exception:   # noqa: BLE001  URLError, OSError, timeouts, http.client.HTTPException (IncompleteRead,
                status, body = 0, b""   # BadStatusLine, ...): a connection error, retried (§3.2 J1: unverified)
            self.sleep(self.pace_s)
            if status == 200:
                return status, body
            if not (status == 0 or status == 429 or 500 <= status < 600) or back is None:
                return status, body
            self.sleep(back)
        return status, body
