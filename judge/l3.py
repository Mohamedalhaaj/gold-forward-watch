"""The judge's own L3 estimator (SYSTEM_V1_PREREG.md §4 with Amendment A1 item 6; IMPLEMENTATION_REGISTER R-V1-25 ..
R-V1-27). Observations: hours from START with a defined RAW F_H1 > 0 and a realised mid range (>= 48 minutes)."""
import math

import numpy as np
import pandas as pd

from .common import BUCKETS, model_to_utc

EVENT_BUCKETS = ("CPI", "FOMC", "NFP")
SESS = {"asia": "N_ASIA", "london": "N_LONDON", "ny": "N_NY"}


def bucket(slot, nfp, cpi, fomc, session_of_hour):
    """First match wins: CPI, FOMC, NFP, REOPEN (slot 0), then the session of the model hour (slot + 1)."""
    if cpi:
        return "CPI"
    if fomc:
        return "FOMC"
    if nfp:
        return "NFP"
    if slot == 0:
        return "REOPEN"
    return SESS[session_of_hour(slot + 1)]


def observations(store, grid_y, start, cu, session_of_hour):
    """R-V1-25 rows: day, slot, r, bucket, week."""
    out = []
    s0 = pd.Timestamp(start)
    for (day, slot), r in sorted(store.items()):
        d = pd.Timestamp(day)
        F = r["F_H1"]
        if d < s0 or not (math.isfinite(F) and F > 0):
            continue
        if model_to_utc(pd.Timestamp(r["origin"]) + pd.Timedelta(hours=1)) > cu:
            continue
        y = grid_y.get((day, slot), float("nan"))
        if not math.isfinite(y):
            continue
        iso = d.isocalendar()
        out.append({"day": d, "slot": slot, "r": y / F,
                    "bucket": bucket(slot, r["nfp"], r["cpi"], r["fomc"], session_of_hour),
                    "week": iso[0] * 100 + iso[1]})
    return out


def update(obs, month, prev_active, zstar):
    """One monthly update (R-V1-26) for month M (Timestamp of M-01): observations with day < M-01."""
    rows = []
    cut = pd.Timestamp(month)
    for b in BUCKETS:
        rs = [o for o in obs if o["bucket"] == b and o["day"] < cut]
        n = len(rs)
        weeks = sorted({o["week"] for o in rs})
        G = len(weeks)
        r = np.array([o["r"] for o in rs], dtype=float)
        mean = float(r.mean()) if n else float("nan")
        if b in EVENT_BUCKETS:
            se = float(np.std(r, ddof=1) / math.sqrt(n)) if n >= 2 else float("nan")
        else:
            wm = np.array([np.mean([o["r"] for o in rs if o["week"] == w]) for w in weeks], dtype=float)
            se = float(np.std(wm, ddof=1) / math.sqrt(G)) if G >= 2 else float("nan")
        z = (mean - 1) / se if (math.isfinite(se) and se > 0) else float("nan")
        eligible = ((n >= 6) if b in EVENT_BUCKETS else (G >= 8)) and math.isfinite(z)
        was = bool(prev_active.get(b, False))
        if not eligible:
            act = False
        elif was:
            act = abs(z) >= zstar / 2
        else:
            act = abs(z) >= zstar
        w = (n / (n + 6)) if b in EVENT_BUCKETS else (G / (G + 8))
        m = min(max(1 + (mean - 1) * w, 0.80), 1.25) if act else 1.0
        rows.append({"month": cut.strftime("%Y-%m"), "bucket": b, "n": n, "G": G, "mean_r": mean, "se": se,
                     "z": z, "eligible": int(eligible), "active_before": int(was), "active_after": int(act),
                     "m": m, "zstar": zstar})
    return rows
