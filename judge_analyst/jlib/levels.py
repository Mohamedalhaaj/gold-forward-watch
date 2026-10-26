"""The judge's own reading of R-AN-88 (§16.18 A12, decision A12-D6): the context's `levels`, re-implemented from the
register text (never imported from gold-analyst), and their comparison within R-AN-68 (decision A12-D9).

compute() gives the unrounded values; rounded() writes them as R-AN-88 does (rnd(x, k) = Python round on the
double); compare() judges a recorded `levels` against the unrounded values: prices exact (copied from bars), a rounded
field within 0.5·10^-k + 1e-9 of the unrounded value (k = 2 for dist_* and the ratios, 3 for ret_*), and a null must
be null in the judge's computation too, and the reverse.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics

from .clock import model_to_utc, to_server
from .common import fmt_utc, parse_utc, price_eq

LEVEL_KEYS = ("prev_day", "week_open", "asia", "ret_1d", "ret_5d", "ret_20d", "vol_ratio")
PREV_KEYS = ("day", "h", "l", "c", "dist_h", "dist_l", "dist_c")
WEEK_KEYS = ("t_utc", "o", "dist")
ASIA_KEYS = ("from_utc", "to_utc", "n_hours", "complete", "h", "l", "dist_h", "dist_l", "width_ratio", "hist")
HIST_KEYS = ("day", "h", "l")
ASIA_HOURS = range(1, 10)          # model hours 1 to 9: server 01:00-10:00 (VolMap Rule 3 L2)
HIST_DAYS = 20
RETS = (("ret_1d", 1), ("ret_5d", 5), ("ret_20d", 20))
DECIMALS = {"dist_h": 2, "dist_l": 2, "dist_c": 2, "dist": 2, "width_ratio": 2, "vol_ratio": 2,
            "ret_1d": 3, "ret_5d": 3, "ret_20d": 3}
HOUR = dt.timedelta(hours=1)


def _model(b):
    """A bar's model day and model hour (those of its t_server, here from its t_utc)."""
    m = to_server(parse_utc(b["t_utc"]))
    return m.date(), m.hour


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def compute(P, D, B, d1, d: dt.date, hist=None):
    """Unrounded R-AN-88 levels. P = p_ref.p_ref; D = d_ref.D_ref; B = the hourly bars over [start_lv, h_new] (or
    any list holding the bars it needs); d1 = bars_d1; `hist` (optional) replaces the hist computed from B, so that
    width_ratio follows from a recorded hist."""
    def dist(v):
        if not (_num(P) and _num(D) and D != 0 and _num(v)):
            return None
        return (v - P) / D

    B = sorted(B, key=lambda b: b["t_utc"])
    out = {}
    if d1:
        e = d1[-1]
        out["prev_day"] = {"day": e["day"], "h": e["h"], "l": e["l"], "c": e["c"], "dist_h": dist(e["h"]),
                           "dist_l": dist(e["l"]), "dist_c": dist(e["c"])}
    else:
        out["prev_day"] = None
    monday = d - dt.timedelta(days=d.weekday())
    wk = [b for b in B if monday <= _model(b)[0] <= d]
    out["week_open"] = {"t_utc": wk[0]["t_utc"], "o": wk[0]["o"], "dist": dist(wk[0]["o"])} if wk else None
    A = [b for b in B if _model(b)[0] == d and _model(b)[1] in ASIA_HOURS]
    if A:
        k_end = _model(A[-1])[1]
        if hist is None:
            hist = []
            for e in d1[-HIST_DAYS:]:
                day = dt.date.fromisoformat(e["day"])
                hb = [b for b in B if _model(b)[0] == day and 1 <= _model(b)[1] <= k_end]
                if hb:
                    hist.append({"day": e["day"], "h": max(b["h"] for b in hb), "l": min(b["l"] for b in hb)})
        ah, al = max(b["h"] for b in A), min(b["l"] for b in A)
        width = None
        if len(hist) >= 10:
            m = statistics.median([x["h"] - x["l"] for x in hist])
            if m > 0:
                width = (ah - al) / m
        out["asia"] = {"from_utc": fmt_utc(model_to_utc(dt.datetime(d.year, d.month, d.day, 1))),
                       "to_utc": fmt_utc(parse_utc(A[-1]["t_utc"]) + HOUR), "n_hours": len(A),
                       "complete": len(A) == 9, "h": ah, "l": al, "dist_h": dist(ah), "dist_l": dist(al),
                       "width_ratio": width, "hist": hist}
    else:
        out["asia"] = None
    c = [e["c"] for e in d1]
    n_c = len(c)
    for key, n in RETS:
        out[key] = 100 * (c[n_c - 1] / c[n_c - 1 - n] - 1) if n_c >= n + 1 else None
    vol = None
    if len(d1) >= 20:
        den = statistics.fmean([e["h"] - e["l"] for e in d1[-20:]])
        if den > 0:
            vol = statistics.fmean([e["h"] - e["l"] for e in d1[-5:]]) / den
    out["vol_ratio"] = vol
    return out


def _rnd(x, k):
    return None if x is None else round(x, k)


def rounded(u):
    """The levels as R-AN-88 writes them, in its key order."""
    if u is None:
        return None
    r = {}
    p = u["prev_day"]
    r["prev_day"] = None if p is None else {k: (_rnd(p[k], 2) if k.startswith("dist") else p[k]) for k in PREV_KEYS}
    w = u["week_open"]
    r["week_open"] = None if w is None else {"t_utc": w["t_utc"], "o": w["o"], "dist": _rnd(w["dist"], 2)}
    a = u["asia"]
    if a is None:
        r["asia"] = None
    else:
        r["asia"] = {k: (_rnd(a[k], 2) if k in DECIMALS else a[k]) for k in ASIA_KEYS}
        r["asia"]["hist"] = [{k: x[k] for k in HIST_KEYS} for x in a["hist"]]
    for key, _n in RETS:
        r[key] = _rnd(u[key], 3)
    r["vol_ratio"] = _rnd(u["vol_ratio"], 2)
    return r


def within(rec, exp, k: int) -> bool:
    """R-AN-68 (A12): |recorded − the judge's unrounded value| <= 0.5·10^−k + 1e-9; null iff null."""
    if exp is None or rec is None:
        return exp is None and rec is None
    if not _num(rec):
        return False
    return abs(rec - exp) <= 0.5 * 10 ** -k + 1e-9


def _hist_eq(rec, exp) -> bool:
    if not isinstance(rec, list) or not isinstance(exp, list) or len(rec) != len(exp):
        return False
    for r, e in zip(rec, exp):
        if not isinstance(r, dict) or set(r) != set(HIST_KEYS) or r["day"] != e["day"] or \
                not price_eq(r["h"], e["h"]) or not price_eq(r["l"], e["l"]):
            return False
    return True


def _cmp_obj(rec, exp, keys, out, base):
    if exp is None or rec is None:
        if not (exp is None and rec is None):
            out.append(base)
        return False
    if not isinstance(rec, dict) or set(rec) != set(keys):
        out.append(base + ".keys")
        return False
    for k in keys:
        if k == "hist":
            continue
        if k in DECIMALS:
            ok = within(rec[k], exp[k], DECIMALS[k])
        elif k in ("h", "l", "c", "o"):
            ok = price_eq(rec[k], exp[k])
        else:
            ok = rec[k] == exp[k] and type(rec[k]) is type(exp[k])
        if not ok:
            out.append(f"{base}.{k}")
    return True


def compare(rec, u, hist_rebuild):
    """Paths where a recorded `levels` differs from the judge's unrounded values `u` (None when the context's
    status is not ok) beyond R-AN-68; `hist_rebuild` is the judge's own asia.hist from the mirror (A4)."""
    out = []
    if u is None or rec is None:
        if not (u is None and rec is None):
            out.append("levels")
        return out
    if not isinstance(rec, dict) or set(rec) != set(LEVEL_KEYS):
        return ["levels.keys"]
    _cmp_obj(rec["prev_day"], u["prev_day"], PREV_KEYS, out, "levels.prev_day")
    _cmp_obj(rec["week_open"], u["week_open"], WEEK_KEYS, out, "levels.week_open")
    if _cmp_obj(rec["asia"], u["asia"], ASIA_KEYS, out, "levels.asia"):
        if not _hist_eq(rec["asia"]["hist"], hist_rebuild):
            out.append("levels.asia.hist")
    for key, _n in RETS:
        if not within(rec[key], u[key], 3):
            out.append(f"levels.{key}")
    if not within(rec["vol_ratio"], u["vol_ratio"], 2):
        out.append("levels.vol_ratio")
    return out
