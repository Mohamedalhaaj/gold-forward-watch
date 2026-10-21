"""The judge's own L1 (SYSTEM_V1_PREREG.md §2) and green suppression (§4; IMPLEMENTATION_REGISTER R-V1-21 .. R-V1-24).
"""
import math

import numpy as np
import pandas as pd

from .common import K10_H, model_to_utc

GREEN, YELLOW, RED, GREY = "GREEN", "YELLOW", "RED", "GREY"
R_UNDEF, R_CLOSED = 1 << 0, 1 << 1
R_CPI, R_WEEKOPEN, R_COSTHIGH, R_NFP, R_FOMC, R_REOPEN, R_COST, R_WEEKEND, R_DRIFT = (1 << b for b in range(2, 11))


def judge(ok, closed, w, slot, nfp, cpi, fomc, hour_usd, cost_usd, green_ok):
    """(state, reason bits) exactly as the §2 table: GREY undefined, GREY closed, then each reason sets its bit."""
    if not ok or not (hour_usd > 0 and hour_usd < 1e12):
        return GREY, R_UNDEF
    if closed:
        return GREY, R_CLOSED
    c = cost_usd / hour_usd
    bits = 0
    if cpi:
        bits |= R_CPI
    if w == 0 and slot == 0:
        bits |= R_WEEKOPEN
    if c >= 0.12:
        bits |= R_COSTHIGH
    if nfp:
        bits |= R_NFP
    if fomc:
        bits |= R_FOMC
    if slot == 0 and w >= 1:
        bits |= R_REOPEN
    if 0.06 <= c < 0.12:
        bits |= R_COST
    if w == 4 and slot >= 21:
        bits |= R_WEEKEND
    if green_ok == 0:
        bits |= R_DRIFT
    if bits & (R_CPI | R_WEEKOPEN):
        return RED, bits
    return (YELLOW if bits else GREEN), bits


def hour_trial(mf_day_rows, origin, F):
    """R-V1-22 on the model-frame rows of the hour. Returns None (no entry) or (long_hit, short_hit)."""
    sub = mf_day_rows
    t = sub.index
    first = sub[(t >= origin) & (t < origin + pd.Timedelta(minutes=5))
                & (sub["bid_vol"] > 0) & (sub["ask_vol"] > 0)]
    if first.empty:
        return None
    t0 = first.index[0]
    E = float(first["o"].iloc[0])
    win = sub[(t >= t0) & (t < origin + pd.Timedelta(minutes=60))]
    with np.errstate(all="ignore"):
        lo = np.nanmin(win["l"].to_numpy(dtype=float)) if len(win) else np.nan
        hi = np.nanmax(win["h"].to_numpy(dtype=float)) if len(win) else np.nan
    if not (math.isfinite(E) and math.isfinite(lo) and math.isfinite(hi)):
        return None
    return (1e4 * math.log(E / lo) >= K10_H * F, 1e4 * math.log(hi / E) >= K10_H * F)


def trials(store, mf, start, cu):
    """One trial per store row with model day >= START and a defined F_H1 whose hour is final (R-V1-21, R-V1-22).
    Returns rows: day, origin, state, entry (bool), long, short."""
    out = []
    starts = pd.Timestamp(start)
    iv = mf.index.values
    for (day, slot), r in sorted(store.items()):
        d = pd.Timestamp(day)
        if d < starts or not math.isfinite(r["F_H1"]):
            continue
        origin = pd.Timestamp(r["origin"])
        if model_to_utc(origin + pd.Timedelta(hours=1)) > cu:
            continue
        hour_usd = r["price"] * (math.exp(r["F_H1"] / 1e4) - 1)
        state, _ = judge(1, 0, d.dayofweek, slot, r["nfp"], r["cpi"], r["fomc"], hour_usd, 0.25, 1)
        a = np.searchsorted(iv, np.datetime64(origin), "left")
        b = np.searchsorted(iv, np.datetime64(origin + pd.Timedelta(minutes=60)), "left")
        rows = mf.iloc[a:b]
        tr = hour_trial(rows, origin, r["F_H1"])
        out.append({"day": d, "origin": origin, "state": state, "entry": tr is not None,
                    "long": bool(tr[0]) if tr else False, "short": bool(tr[1]) if tr else False})
    return out


def blocks(trs, start, cu, full_closures):
    """R-V1-23: 13-week blocks from START (numbered from 1) with the hysteresis of green_ok. Returns (rows, green_ok)."""
    start = pd.Timestamp(start)
    rows, green_ok, high, band = [], 1, 0, 0
    k = 0
    while True:
        bs, be = start + pd.Timedelta(days=91 * k), start + pd.Timedelta(days=91 * (k + 1))
        if model_to_utc(bs + pd.Timedelta(hours=1)) > cu:
            break
        ended = model_to_utc(be) <= cu
        inb = [t for t in trs if bs <= t["day"] < be]
        n_origins = sum(1 for t in inb if t["entry"])
        wd = pd.bdate_range(bs, be - pd.Timedelta(days=1))
        expected = 23 * int(len(wd.difference(full_closures)))
        greens = [t for t in inb if t["entry"] and t["state"] == "GREEN"]
        hits = sum(int(t["long"]) + int(t["short"]) for t in greens)
        ntr = 2 * len(greens)
        hr = hits / ntr if ntr else float("nan")
        complete = ended and n_origins >= 0.8 * expected
        if complete:
            if ntr and hr > 0.14:
                high, band = high + 1, 0
            elif ntr and 0.06 <= hr <= 0.14:
                band, high = band + 1, 0
            else:
                high, band = 0, 0
            if green_ok == 1 and high >= 2:
                green_ok = 0
            elif green_ok == 0 and band >= 2:
                green_ok = 1
        rows.append({"block": k + 1, "start": bs.strftime("%Y-%m-%d"), "end": be.strftime("%Y-%m-%d"),
                     "complete": int(complete), "n_origins": n_origins, "expected": expected,
                     "n_green": len(greens), "hits": hits, "trials": ntr, "hit_rate": hr,
                     "green_ok_after": green_ok})
        k += 1
    return rows, green_ok
