"""Watching (§16.18 A14; R-AN-89, R-AN-90, R-AN-66, R-AN-68): the judge's own reading of the trigger rule, the gates,
the `wake` record and the 30-minute Twelve Data bars, re-implemented from the register text (never imported from
gold-analyst or its watcher).

- `values_at` / `conditions` / `rule`: R-AN-89 at a check T of model day d, on a set of 30-minute bars labelled by
  their start, with E(T) and O(T) given by the caller (the judge builds them from main: accepted attempt witnesses,
  their attempt records, terminals).
- `wake_problems`: R-AN-90's `wake` of an `analyst-attempt/2` record (A14 `wake_record`).
- `wake_block`: the `analyst-context/4` `wake` (R-AN-23) rebuilt from the attempt record's `wake`.
- `classify_m30` and `M30Source`: the judge's own fetch of the bars (R-AN-66), R-AN-87's transport and
  classification, kept under reports/judge_analyst/m30/ with an evidence row per try (R-AN-69).
- `m30_compare`: R-AN-68's comparison of a trigger attempt's bars with that fetch (A14 `m30_mismatch`).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import statistics
import time
import urllib.error
import urllib.request

from . import td
from .clock import HALF, check_grid, scheduled_checks, tday, trigger_wid
from .common import UTC, fmt_utc, is_utc, parse_utc, rel_eq, sha256_bytes

CONDITIONS = ("asia_up", "asia_dn", "y_high", "y_low", "move")
KINDS = ("fixed", "second_look", "trigger")
M30_REQ = "XAUUSD_M30"
DAY_CAP = 6                           # R-AN-89 step 2: |E(T)| >= 6
DAY_CAP_A16 = 10                      # §16.18 A16: from MODE.json a16_from on
R20_DAYS = 20
WAKE_KEYS = ("kind", "reason", "check_utc", "td")
CTX_WAKE_KEYS = ("kind", "reason", "check_utc", "values", "r20_days", "bars_m30")
VALUE_KEYS = ("c_t", "c_prev", "c_prev_utc", "asia_h", "asia_l", "y_day", "y_h", "y_l", "r20")
WAKE_NOTE = (" wake values and wake.bars_m30 come from Twelve Data 30-minute bars in UTC, labelled by their start.")
UA = "Mozilla/5.0 (gold-forward-watch analyst judge)"
_NUM = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_DT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


# ---------------------------------------------------------------- the request (R-AN-90, R-AN-66)


def m30_start(d: dt.date) -> dt.datetime:
    """A = 22:00:00 UTC of the calendar day d − 33 days (the start of model day d − 32)."""
    a = d - dt.timedelta(days=33)
    return dt.datetime(a.year, a.month, a.day, 22, tzinfo=UTC)


def m30_url(d: dt.date, b: dt.datetime) -> str:
    return (f"{td.BASE}?symbol=XAU/USD&interval=30min&start_date={td.td_time(m30_start(d))}"
            f"&end_date={td.td_time(b)}&timezone=UTC&order=asc&outputsize=5000&dp=5")


# ---------------------------------------------------------------- the rule (R-AN-89)


def _bars(bars, limit):
    out = []
    for b in bars or []:
        t = parse_utc(b["t_utc"])
        if t <= limit:
            out.append((t, b))
    out.sort(key=lambda x: x[0])
    return out


def values_at(bars, d: dt.date, t_check: dt.datetime) -> dict:
    """R-AN-89's values at check T: the bars used are those with t_utc <= T − 30 min. Returns the context's `values`
    keys plus `_bar_t` (bar_T), `_r20_days` and `_today` (the used bars of d)."""
    used = _bars(bars, t_check - HALF)
    by_day = {}
    for t, b in used:
        by_day.setdefault(tday(t), []).append((t, b))
    prior = sorted(e for e in by_day if e < d and e.weekday() < 5)
    ranges = [(e, max(b["h"] for _t, b in by_day[e]), min(b["l"] for _t, b in by_day[e])) for e in prior]
    last = ranges[-R20_DAYS:]
    r20 = statistics.median([h - lo for _e, h, lo in last]) if len(prior) >= R20_DAYS else None
    today = by_day.get(d, [])
    a7 = dt.datetime(d.year, d.month, d.day, 7, tzinfo=UTC)
    asia = [b for t, b in today if t < a7]
    bar_t = next((b for t, b in today if t == t_check - HALF), None)
    prev = [(t, b) for t, b in today if t <= t_check - 3 * HALF]
    y = ranges[-1] if ranges else None
    return {"c_t": bar_t["c"] if bar_t else None,
            "c_prev": prev[-1][1]["c"] if prev else None,
            "c_prev_utc": fmt_utc(prev[-1][0]) if prev else None,
            "asia_h": max(b["h"] for b in asia) if asia else None,
            "asia_l": min(b["l"] for b in asia) if asia else None,
            "y_day": y[0].isoformat() if y else None, "y_h": y[1] if y else None, "y_l": y[2] if y else None,
            "r20": r20, "_bar_t": bar_t,
            "_r20_days": [{"day": e.isoformat(), "h": h, "l": lo} for e, h, lo in last],
            "_today": [{k: b[k] for k in ("t_utc", "o", "h", "l", "c")} for _t, b in today]}


def conditions(v: dict, d: dt.date, t_check: dt.datetime) -> dict:
    """The five conditions at T, each evaluated exactly as R-AN-89 writes it (IEEE doubles); all false when bar_T is
    absent or R20 is undefined."""
    out = dict.fromkeys(CONDITIONS, False)
    bt, r20 = v["_bar_t"], v["r20"]
    if bt is None or r20 is None:
        return out
    c_t = bt["c"]
    after7 = t_check >= dt.datetime(d.year, d.month, d.day, 7, tzinfo=UTC)
    if after7 and v["asia_h"] is not None:
        out["asia_up"] = c_t > v["asia_h"]
        out["asia_dn"] = c_t < v["asia_l"]
    out["y_high"] = bt["h"] >= v["y_h"] - 0.1 * r20
    out["y_low"] = bt["l"] <= v["y_l"] + 0.1 * r20
    out["move"] = v["c_prev"] is not None and abs(c_t - v["c_prev"]) >= 0.3 * r20
    return out


def rule(d: dt.date, t_check: dt.datetime, earlier, n_open: int, holiday: bool, cond: dict | None,
         cap: int = DAY_CAP):
    """R(T), in R-AN-89's order. `earlier` = E(T) as [(check, kind, reason)], `n_open` = |O(T)|, `holiday` = a row of
    either exchange on d, `cond` = the conditions at T (None: no bars; only steps 1-5 can then decide), `cap` = step
    2's cap of d (10 from a16_from on, §16.18 A16).
    Returns (outcome, wid, kind, reason): outcome `trade_open` | `day_cap` | `window` | `none` | `outside`."""
    if t_check not in check_grid(d):
        return ("outside", None, None, None)
    if n_open:
        return ("trade_open", None, None, None)
    if len(earlier) >= cap:
        return ("day_cap", None, None, None)
    sched = scheduled_checks(d)
    if t_check in sched:
        w = sched[t_check]
        return ("window", w, "fixed" if w in ("W1", "W2") else "second_look", None)
    if holiday:
        return ("none", None, None, None)
    g = math.inf if not earlier else (t_check - max(c for c, _k, _r in earlier)).total_seconds() / 60
    if g < 60:
        return ("none", None, None, None)
    consumed = {r for _c, k, r in earlier if k == "trigger"}
    for c in CONDITIONS:
        if (cond or {}).get(c) and c not in consumed and (c != "move" or g >= 120):
            return ("window", trigger_wid(t_check), "trigger", c)
    return ("none", None, None, None)


# ---------------------------------------------------------------- the wake record (R-AN-90, R-AN-25)


def m30_bar_problems(bars, lo: dt.datetime, hi: dt.datetime, values_n) -> list:
    """`bars` of an `ok` XAUUSD_M30 provenance: keys, R-C4 times on a half hour in [lo, hi], strict time order,
    R-AN-87's value rules, and every element with t_utc <= hi kept (values_n − len(bars) is 0, or 1 for the element
    at T itself when end_date is inclusive)."""
    out = []
    if not isinstance(bars, list):
        return ["bars"]
    prev = None
    for b in bars:
        if not isinstance(b, dict) or set(b) != td.BAR_KEYS or not is_utc(b["t_utc"]):
            return out + ["bars.keys"]
        t = parse_utc(b["t_utc"])
        if t.second != 0 or t.minute not in (0, 30):
            return out + ["bars.keys"]
        if not (lo <= t <= hi):
            out.append("bars.range")
        if prev is not None and b["t_utc"] <= prev:
            out.append("bars.order")
        prev = b["t_utc"]
        o, h, low, c = b["o"], b["h"], b["l"], b["c"]
        if not all(td._num(x) and x > 0 for x in (o, h, low, c)) or not (low <= min(o, c) and h >= max(o, c)):
            out.append("bars.values")
    if not td._int(values_n) or values_n - len(bars) not in (0, 1):
        out.append("bars.elements")
    return sorted(set(out))


def td_problems(f, win) -> list:
    """R-AN-87's provenance rules for the trigger request of `win` (req XAUUSD_M30, R-AN-90's URL with B = T)."""
    t_check = win.check
    url = m30_url(win.day, t_check)
    if not isinstance(f, dict) or set(f) != td.PROV_KEYS:
        return ["td.keys"]
    out = [p for p in td.provenance_problems(dict(f, bars=[]), M30_REQ, url, set(), t_check)
           if not p.startswith("bars")]
    if f.get("status") == "ok":
        out += m30_bar_problems(f.get("bars"), m30_start(win.day), t_check - HALF, f.get("values_n"))
    return ["td." + p for p in out]


def wake_problems(rec, win) -> list:
    """A14 `wake_record` (R-AN-90) of one `analyst-attempt/2` call attempt of `win`: [] when its `wake` is right."""
    wk = rec.get("wake") if isinstance(rec, dict) else None
    if not isinstance(wk, dict) or set(wk) != set(WAKE_KEYS):           # records are key-sorted (R-AN-3)
        return ["wake.keys"]
    out = []
    if wk["kind"] != win.kind:
        out.append("wake.kind")
    if wk["check_utc"] != fmt_utc(win.check):
        out.append("wake.check_utc")
    if win.kind != "trigger":
        if wk["reason"] is not None:
            out.append("wake.reason")
        if wk["td"] is not None:
            out.append("wake.td")
        return out
    if wk["reason"] not in CONDITIONS:
        out.append("wake.reason")
    return out + td_problems(wk["td"], win)


def recorded_bars(wk):
    """The bars of a trigger wake's `ok` request, or None."""
    f = (wk or {}).get("td") if isinstance(wk, dict) else None
    if not isinstance(f, dict) or f.get("status") != "ok" or not isinstance(f.get("bars"), list):
        return None
    try:
        for b in f["bars"]:
            parse_utc(b["t_utc"])
            if not all(td._num(b[k]) for k in ("o", "h", "l", "c")):
                return None
    except (KeyError, TypeError, ValueError):
        return None
    return f["bars"]


# ---------------------------------------------------------------- the context's `wake` (R-AN-23, analyst-context/4)


def wake_block(wk, win) -> dict | None:
    """The `analyst-context/4` `wake` the attempt record's `wake` gives: kind, reason, check_utc copied; values,
    r20_days and bars_m30 by R-AN-89 at check_utc from `wake.td.bars` for a trigger, null otherwise."""
    if not isinstance(wk, dict):
        return None
    out = {"kind": wk.get("kind"), "reason": wk.get("reason"), "check_utc": wk.get("check_utc"), "values": None,
           "r20_days": None, "bars_m30": None}
    if wk.get("kind") != "trigger":
        return out
    bars = recorded_bars(wk)
    if bars is None:
        return out
    v = values_at(bars, win.day, win.check)
    out["values"] = {k: v[k] for k in VALUE_KEYS}
    out["r20_days"] = v["_r20_days"]
    out["bars_m30"] = v["_today"]
    return out


def compare_wake(exp, rec) -> list:
    """R-AN-68 (A14): kind, reason, check_utc, bars, days and prices exact; r20 relative 1e-9."""
    if exp is None or not isinstance(rec, dict):
        return [] if exp is None and rec is None else ["wake"]
    if set(rec) != set(CTX_WAKE_KEYS):
        return ["wake.keys"]
    out = [f"wake.{k}" for k in ("kind", "reason", "check_utc", "r20_days", "bars_m30") if rec[k] != exp[k]]
    ev, rv = exp["values"], rec["values"]
    if ev is None or rv is None:
        if not (ev is None and rv is None):
            out.append("wake.values")
    elif not isinstance(rv, dict) or set(rv) != set(VALUE_KEYS):
        out.append("wake.values")
    else:
        for k in VALUE_KEYS:
            if k == "r20":
                ok = (ev[k] is None and rv[k] is None) or (ev[k] is not None and rel_eq(rv[k], ev[k]))
            else:
                ok = rv[k] == ev[k] and type(rv[k]) is type(ev[k])
            if not ok:
                out.append(f"wake.values.{k}")
    return out


# ---------------------------------------------------------------- the judge's own fetch (R-AN-66)


def classify_m30(http: int, body: bytes | None):
    """R-AN-87's td_code and classification of one try for interval 30min: (status, reason, td_code, bars, values_n).
    bars = every element as {t_utc, o, h, l, c}, in time order."""
    obj = None
    if body:
        try:
            obj = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            obj = None
    code = http
    if isinstance(obj, dict) and obj.get("status") == "error" and td._int(obj.get("code")):
        code = obj["code"]
    ok = http == 200 and body is not None and len(body) <= td.MAX_BODY and isinstance(obj, dict) and \
        obj.get("status") == "ok" and isinstance(obj.get("values"), list)
    bars = []
    if ok:
        seen = set()
        for e in obj["values"]:
            if not isinstance(e, dict) or not isinstance(e.get("datetime"), str) or not _DT.match(e["datetime"]):
                ok = False
                break
            try:
                t = dt.datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            except ValueError:
                ok = False
                break
            if t.minute not in (0, 30) or t.second != 0 or e["datetime"] in seen:
                ok = False
                break
            seen.add(e["datetime"])
            vals = [e.get(k) for k in ("open", "high", "low", "close")]
            if not all(isinstance(x, str) and _NUM.match(x) for x in vals):
                ok = False
                break
            o, h, low, c = (float(x) for x in vals)
            if not (o > 0 and h > 0 and low > 0 and c > 0 and low <= min(o, c) and h >= max(o, c)):
                ok = False
                break
            bars.append({"t_utc": fmt_utc(t), "o": o, "h": h, "l": low, "c": c})
    if ok:
        bars.sort(key=lambda b: b["t_utc"])
        return "ok", None, 200, bars, len(bars)
    return "error", td.expected_reason(http, code, 1), code, [], 0


class HttpM30Fetcher:
    """GET with the key in an `Authorization: apikey` header (never printed or stored); (http, body), http 0 on a
    connection error or a timeout."""

    def __init__(self, key: str | None, timeout: int = 10):
        self._key = key
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self._key)

    def get(self, url: str):
        req = urllib.request.Request(url, headers={"Authorization": f"apikey {self._key}", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:   # noqa: S310 - fixed https host
                return r.status, r.read(td.MAX_BODY + 1)
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read(td.MAX_BODY + 1)
            except Exception:  # noqa: BLE001
                return e.code, b""
        except Exception:  # noqa: BLE001
            return 0, None


class FakeM30Fetcher:
    """Tests: {url: (http, body)}; any other URL answers a connection error."""

    def __init__(self, responses: dict, available: bool = True):
        self.responses = responses
        self.available = available
        self.calls = []

    def get(self, url: str):
        self.calls.append(url)
        return self.responses.get(url, (0, None))


class M30Source:
    """The judge's fetch per model day, kept in `<dir>/<day>.json` once `ok` (never repeated); a failed fetch is
    retried at a later run. Each fetch adds an evidence row (source `td_m30`, R-AN-69): ref = the model day,
    push_after = the response's sha256, activity_type = the status (`ok` or `td_<reason>`), activity_utc = the
    fetch time, run_id = values_n."""

    SCHEMA = "judge-m30/1"

    def __init__(self, fetcher, directory: str | None, max_fetch: int = 3, sleep=time.sleep, clock=None):
        self.fetcher = fetcher
        self.dir = directory
        self.max_fetch = max_fetch
        self.sleep = sleep
        self.clock = clock or (lambda: dt.datetime.now(UTC).replace(microsecond=0))
        self.memory = {}
        self.new_files = {}
        self.fetched = 0
        self._last_start = None

    def _path(self, d: dt.date):
        return os.path.join(self.dir, f"{d.isoformat()}.json") if self.dir else None

    def get(self, d: dt.date):
        """The kept `ok` fetch of d, or None."""
        if d in self.memory:
            return self.memory[d]
        p = self._path(d)
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    rec = json.load(f)
                if rec.get("schema") == self.SCHEMA and rec.get("status") == "ok":
                    self.memory[d] = rec
                    return rec
            except (OSError, ValueError):
                return None
        return None

    def fetch(self, d: dt.date, b: dt.datetime):
        """One fetch of d (R-AN-87's transport: at most 2 tries, the second only after td_code 0 or 500-599, 8.0 s
        between try starts). Returns (record or None, evidence fields)."""
        if self.fetcher is None or not getattr(self.fetcher, "available", True) or self.fetched >= self.max_fetch:
            return None, None
        self.fetched += 1
        url = m30_url(d, b)
        tries = 0
        while True:
            if self._last_start is not None:
                self.sleep(8.0)
            self._last_start = True
            tries += 1
            http, body = self.fetcher.get(url)
            status, reason, code, bars, n = classify_m30(http, body)
            if status == "ok" or tries >= 2 or not (code == 0 or (td._int(code) and 500 <= code <= 599)):
                break
        rec = {"schema": self.SCHEMA, "model_day": d.isoformat(), "url": url, "fetched_utc": fmt_utc(self.clock()),
               "http": http, "td_code": code, "status": status, "reason": reason, "bytes": len(body or b""),
               "sha256": sha256_bytes(body) if body else "", "values_n": n, "tries": tries, "bars": bars}
        ev = {"ref": d.isoformat(), "push_after": rec["sha256"], "activity_type": "ok" if status == "ok" else
              f"td_{reason}", "activity_utc": rec["fetched_utc"], "run_id": n}
        if status == "ok":
            self.memory[d] = rec
            self.new_files[d] = rec
        return (rec if status == "ok" else None), ev

    def flush(self):
        if not self.dir:
            return
        for d, rec in self.new_files.items():
            os.makedirs(self.dir, exist_ok=True)
            with open(self._path(d), "w", encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
        self.new_files = {}


def m30_compare(rec_bars, own_bars, lo: dt.datetime, hi: dt.datetime) -> list:
    """R-AN-68 (A14): every recorded bar's o, h, l and c against the judge's bar at the same t_utc (|v_rec / v_own −
    1| <= 1e-3), and every bar with t_utc in [lo, hi] present in one set and not the other. Returns the differences
    as short judge-formatted strings."""
    own = {b["t_utc"]: b for b in own_bars or []}
    rec = {b["t_utc"]: b for b in rec_bars or []}
    out = []
    for t in sorted(rec):
        if t not in own:
            if lo <= parse_utc(t) <= hi:
                out.append(f"{t} only_recorded")
            continue
        for k in ("o", "h", "l", "c"):
            a, b = rec[t][k], own[t][k]
            if not (b and abs(a / b - 1) <= td.CROSS_TOL):
                out.append(f"{t} {k} rec={a!r} own={b!r}")
    for t in sorted(own):
        if t not in rec and lo <= parse_utc(t) <= hi:
            out.append(f"{t} only_judge")
    return out
