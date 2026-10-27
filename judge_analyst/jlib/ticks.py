"""Dukascopy hour tick files (R-AN-16), decoded independently by the judge.

A summary keeps only integer points, so every price the context derives from a file can be recomputed exactly:
the first and last tick (ms, ask, bid), the max and min of ask + bid, and the tick count.
"""
from __future__ import annotations

import datetime as dt
import lzma
import struct

from .common import sha256_bytes

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
POINTS = {"XAUUSD": 1000, "USDJPY": 1000, "EURUSD": 100000, "GBPUSD": 100000, "USDCAD": 100000, "USDCHF": 100000,
          "AUDJPY": 1000}          # §16.18 A12 (R-AN-16): AUDJPY 1000, for the cross-check of `risk` (R-AN-68)
FX_PAIRS = ("EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF")
FX_EXPONENTS = (-0.576 / 0.958, 0.136 / 0.958, -0.119 / 0.958, 0.091 / 0.958, 0.036 / 0.958)
_TICK = struct.Struct(">IIIff")  # ms, ask, bid, ask_volume, bid_volume


def hour_url(sym: str, hour: dt.datetime) -> str:
    return f"{BASE_URL}/{sym}/{hour.year:04d}/{hour.month - 1:02d}/{hour.day:02d}/{hour.hour:02d}h_ticks.bi5"


def classify(http: int, body: bytes | None):
    """Return (status, summary|None) for one fetch result, by R-AN-16's rules.
    summary = {ticks, first_ms, first_ask, first_bid, last_ms, last_ask, last_bid, max_sum, min_sum}."""
    if http == 404 or (http == 200 and (body is None or len(body) == 0)):
        return "empty", None
    if http != 200:
        return "error", None
    try:
        raw = lzma.decompress(body, format=lzma.FORMAT_ALONE)
    except Exception:  # noqa: BLE001
        return "invalid", None
    if len(raw) == 0 or len(raw) % _TICK.size:
        return "invalid", None
    prev = -1
    n = 0
    first = last = None
    mx = None
    mn = None
    for ms, ask, bid, _av, _bv in _TICK.iter_unpack(raw):
        if not (0 <= ms < 3_600_000) or ms < prev or ask <= 0 or bid <= 0:
            return "invalid", None
        prev = ms
        n += 1
        s = ask + bid
        if first is None:
            first = (ms, ask, bid)
        last = (ms, ask, bid)
        mx = s if mx is None or s > mx else mx
        mn = s if mn is None or s < mn else mn
    return "present", {"ticks": n, "first_ms": first[0], "first_ask": first[1], "first_bid": first[2],
                       "last_ms": last[0], "last_ask": last[1], "last_bid": last[2], "max_sum": mx, "min_sum": mn}


def tick_mid(ask: int, bid: int, sym: str) -> float:
    """R-AN-16: (ask_pts + bid_pts) / (2·points), as a double."""
    return (ask + bid) / (2 * POINTS[sym])


def sum_mid(s: int, sym: str) -> float:
    return s / (2 * POINTS[sym])


def summary_sha(body: bytes) -> str:
    return sha256_bytes(body)


HALF_MS = 1_800_000
HALF_KEYS = ("lo_first_ask", "lo_first_bid", "lo_last_ask", "lo_last_bid", "hi_first_ask", "hi_first_bid",
             "hi_last_ask", "hi_last_bid")


def classify_halves(http: int, body: bytes | None):
    """§16.18 A14 (R-AN-68): `classify`'s status, and for a present file the first and the last tick of each half
    hour (`lo` = [0, 30) min, `hi` = [30, 60) min; None for a half without a tick)."""
    status, summ = classify(http, body)
    if status != "present":
        return status, None
    out = {"ticks": summ["ticks"]}
    out.update(dict.fromkeys(HALF_KEYS))
    raw = lzma.decompress(body, format=lzma.FORMAT_ALONE)
    for ms, ask, bid, _av, _bv in _TICK.iter_unpack(raw):
        h = "lo" if ms < HALF_MS else "hi"
        if out[h + "_first_ask"] is None:
            out[h + "_first_ask"], out[h + "_first_bid"] = ask, bid
        out[h + "_last_ask"], out[h + "_last_bid"] = ask, bid
    return "present", out
