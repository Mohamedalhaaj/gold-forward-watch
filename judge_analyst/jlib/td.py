"""The judge's own reading of R-AN-87 (§16.18 A9): the session's Twelve Data requests, re-implemented from the
register text (never imported from gold-analyst). The judge never calls Twelve Data (R-AN-66: it holds no key, and a
record must stand on its own); these functions check the recorded provenance objects of an `analyst-context/2`
(A4) and name the values the Dukascopy cross-check compares (A11, R-AN-68).
"""
from __future__ import annotations

import datetime as dt
import math
import re

from .common import is_utc, parse_utc

BASE = "https://api.twelvedata.com/time_series"
SYMBOLS = {"XAUUSD": "XAU/USD", "EURUSD": "EUR/USD", "USDJPY": "USD/JPY", "GBPUSD": "GBP/USD", "USDCAD": "USD/CAD",
           "USDCHF": "USD/CHF"}
REQ_ORDER = ("XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF", "fresh")
FRESH_URL = f"{BASE}?symbol=XAU/USD&interval=1min&outputsize=1&timezone=UTC&dp=5"
PROV_KEYS = {"src", "req", "url", "http", "td_code", "status", "reason", "bytes", "sha256", "values_n", "bars",
             "fetched_utc", "tries"}
BAR_KEYS = {"t_utc", "o", "h", "l", "c"}
MAX_BODY = 262_144
SOURCES = {"history": "dukascopy_store", "today": "twelvedata_1h",
           "note": "bars_h1 entries with src td, p_ref when p_ref_src is td, and fx come from Twelve Data hourly bars "
                   "in UTC; bars_h1 entries with src store are Dukascopy mid; bars_d1 are built from bars_h1; Twelve "
                   "Data and Dukascopy levels can differ slightly; settlement uses Dukascopy."}
CROSS_TOL = 1e-3          # R-AN-68, decision A9-D10: |v_td / v_dk - 1| <= 1e-3
UNCHECKED_AFTER = 3       # R-AN-67 td_unchecked: the model day more than 3 weekdays old
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def td_time(t: dt.datetime) -> str:
    """R-AN-87's A and B: UTC `YYYY-MM-DDTHH:MM:SS`, no zone suffix."""
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def hourly_url(req: str, a: dt.datetime, b: dt.datetime) -> str:
    return (f"{BASE}?symbol={SYMBOLS[req]}&interval=1h&start_date={td_time(a)}&end_date={td_time(b)}"
            f"&timezone=UTC&order=asc&outputsize=5000&dp=5")


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def expected_reason(http, td_code, tries):
    """R-AN-87's reason of a request that is not `ok`: `budget` for a request with no try; by td_code otherwise."""
    if tries == 0:
        return "budget"
    if td_code == 401:
        return "key"
    if td_code == 403:
        return "plan"
    if td_code == 429:
        return "credits"
    if td_code == 0 or (_int(td_code) and 500 <= td_code <= 599):
        return "server"
    if http == 200 and td_code == 200:
        return "invalid"
    return "other"


def bar_problems(bars, hours, fresh: bool, values_n):
    """Problems of an `ok` provenance's `bars` (R-AN-87): keys and R-C4 times, the hours the request may hold
    (`hours`, a set of t_utc strings; None for `fresh`), strict time order, o, h, l, c > 0, l <= min(o, c),
    h >= max(o, c); `fresh` holds exactly its newest element when the response had one."""
    out = []
    if not isinstance(bars, list):
        return ["bars"]
    prev = None
    for b in bars:
        if not isinstance(b, dict) or set(b) != BAR_KEYS or not is_utc(b["t_utc"]):
            return out + ["bars.keys"]
        t = parse_utc(b["t_utc"])
        if t.second != 0 or (not fresh and t.minute != 0):
            return out + ["bars.keys"]
        if not fresh and b["t_utc"] not in hours:
            out.append("bars.hours")
        if prev is not None and b["t_utc"] <= prev:
            out.append("bars.order")
        prev = b["t_utc"]
        o, h, low, c = b["o"], b["h"], b["l"], b["c"]
        if not all(_num(v) and v > 0 for v in (o, h, low, c)) or not (low <= min(o, c) and h >= max(o, c)):
            out.append("bars.values")
    if fresh and values_n is not None:
        if len(bars) != (1 if _int(values_n) and values_n >= 1 else 0):
            out.append("bars.fresh")
    elif _int(values_n) and len(bars) > values_n:
        out.append("bars.values_n")
    return sorted(set(out))


def provenance_problems(f, req: str, url: str, hours, asof: dt.datetime):
    """A4 problems of one recorded provenance object at its position: `req` and `url` are what R-AN-87 sends there;
    `hours` the t_utc strings its bars may hold (None for `fresh`)."""
    if not isinstance(f, dict) or set(f) != PROV_KEYS:
        return ["keys"]
    out = []
    if f["src"] != "td":
        out.append("src")
    if f["req"] != req:
        out.append("req")
    if f["url"] != url:
        out.append("url")
    if not all(_int(f[k]) for k in ("http", "td_code", "bytes", "values_n", "tries")) or \
            not isinstance(f["sha256"], str):
        return out + ["types"]
    tries, status = f["tries"], f["status"]
    if tries not in (0, 1, 2):
        out.append("tries")
    if f["sha256"] and not _HEX64.match(f["sha256"]):
        out.append("sha256")
    if tries == 0:
        if f["fetched_utc"] is not None or f["bytes"] != 0 or f["sha256"] != "":
            out.append("fetched_utc")
    elif not is_utc(f["fetched_utc"]) or parse_utc(f["fetched_utc"]) < asof:
        out.append("fetched_utc")
    if status == "ok":
        if f["reason"] is not None or tries == 0:
            out.append("reason")
        if f["http"] != 200 or f["td_code"] != 200 or not (0 < f["bytes"] <= MAX_BODY) or \
                not _HEX64.match(f["sha256"]):
            out.append("ok_fields")
        out += bar_problems(f["bars"], hours, hours is None, f["values_n"])
    elif status == "error":
        if f["reason"] != expected_reason(f["http"], f["td_code"], tries):
            out.append("reason")
        if f["values_n"] != 0:
            out.append("values_n")
        if f["bars"] != []:
            out.append("bars")
    else:
        out.append("status")
    return out


def ok_bars(f):
    """The bars of an `ok` provenance whose bars are well formed (keys, R-C4 times, order, values), as
    {t_utc: bar}; None otherwise. Their placement is A4's (provenance_problems); the rebuild uses only the bars at
    the hours R-AN-87 names."""
    if not isinstance(f, dict) or f.get("status") != "ok" or f.get("src") != "td":
        return None
    bars = f.get("bars")
    if not isinstance(bars, list):
        return None
    hrs = {b.get("t_utc") for b in bars if isinstance(b, dict)}
    if bar_problems(bars, hrs, f.get("req") == "fresh", None):
        return None
    return {b["t_utc"]: b for b in bars}


def probe_outcome(files):
    """R-AN-84 `net.twelvedata` in a canary `context`: read from the context's first R-AN-87 request (XAUUSD, or
    `fresh` when there is no XAUUSD request): 200 iff `ok`; −1 for `invalid`; else its td_code (0: no response);
    −2 when the context made no such request."""
    fs = [f for f in (files or []) if isinstance(f, dict) and f.get("src") == "td"]
    first = next((f for f in fs if f.get("req") == "XAUUSD"), None) or \
        next((f for f in fs if f.get("req") == "fresh"), None)
    if first is None:
        return -2
    if first.get("status") == "ok":
        return 200
    if expected_reason(first.get("http"), first.get("td_code"), first.get("tries")) == "invalid":
        return -1
    return first.get("td_code")


def weekdays_since(d: dt.date, today: dt.date) -> int:
    """Weekdays in [d, today) (numpy.busday_count's convention; holidays not removed)."""
    n, x = 0, d
    while x < today:
        if x.weekday() < 5:
            n += 1
        x += dt.timedelta(days=1)
    return n


def rel_diff(v_td: float, v_dk: float) -> float:
    return abs(v_td / v_dk - 1)
