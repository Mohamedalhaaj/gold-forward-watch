"""L3 self-calibration and the green suppression (SYSTEM_V1_PREREG.md §4). FROZEN: L3 estimator.

Observations (one per model-clock origin hour from START): a defined RAW F_H1 (the write-once store) and a realised
mid range y_bp (the vendored T2 target: >= 48 M1 minutes, H > L) of an hour whose minutes are all final;
r = y_bp / F_H1; bucket = system_common.bucket(slot, nfp, cpi, fomc) from the hour's raw flags (first match:
CPI, FOMC, NFP, REOPEN, then N_ASIA / N_LONDON / N_NY by core.session_of_hour).

Monthly update for month M (from 2027-01; at the first run in M, or later, whose data before M are final; burn-in:
observations before START never count; monthly_updates chains the due months, each starting from the previous
month's active states), per bucket, over observations with model date < M:
- m = mean r; normal and REOPEN buckets: SE = sd of the ISO-week cluster means / √G (G weeks); event buckets
  (CPI, FOMC, NFP): SE = sd(r)/√n; z = (m − 1)/SE.
- eligible: G >= 8 (normal, REOPEN), n >= 6 (events). An inactive bucket turns active iff eligible and |z| >= z*;
  an active bucket turns inactive iff |z| < z*/2 (or it is no longer eligible).
- multiplier m_b = clamp(1 + (m − 1)·w, 0.80, 1.25), w = G/(G + 8) (normal, REOPEN) or n/(n + 6) (events);
  inactive buckets publish 1. z* comes from reports/system/L3_ZSTAR.json (the pre-START synthetic simulation).

Green suppression (L1 D1, owned here): 13-week blocks from START. Over origins that system_common.judge rates GREEN on
the raw inputs (ok = F defined, closed = 0, cost_usd = 0.25, the indicator default, green_ok = 1): the pooled k10
hour-stop hit rate on the mid. Entry at the hour open: the mid open of the first minute in [h, h + 5 min) with volume
on both sides (review fix L1-M7); a long hits if 1e4·ln(E / min mid low) >= k10·F, a short if
1e4·ln(max mid high / E) >= k10·F, over [entry, h + 60 min). A block is complete when it has ended and holds at least
80% of its expected origins (23 per weekday that is not an NYSE full closure); an incomplete block is skipped (it
neither counts nor breaks a run). Two consecutive complete blocks with a hit rate > 14% publish l1_green_ok = 0; two
consecutive complete blocks in [6%, 14%] restore it.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import bars
import system_common as sc

K10 = 1.049036930300697
COST_REF = 0.25
EVENT_BUCKETS = ("CPI", "FOMC", "NFP")
G_MIN = 8
N_MIN_EVENT = 6
SHRINK_G = 8
SHRINK_N = 6
M_LO, M_HI = 0.80, 1.25
FIRST_UPDATE = pd.Timestamp("2027-01-01")
BLOCK_DAYS = 91
BLOCK_COMPLETE_FRAC = 0.80
HR_HIGH, HR_LOW = 0.14, 0.06
UPDATE_COLS = ["month", "bucket", "n", "G", "mean_r", "se", "z", "eligible", "active_before", "active_after", "m",
               "zstar", "computed_utc"]
BLOCK_COLS = ["block", "start", "end", "complete", "n_origins", "expected", "n_green", "hits", "trials", "hit_rate",
              "green_ok_after"]


# ---------------------------------------------------------------- observations
def observations(store, grid, start, complete_utc):
    """One row per origin hour from START with defined F_H1 and y_bp, all minutes final.

    store: forecasts.read_store(); grid: forecasts.compute() on the raw files (gives y_bp)."""
    if start is None or not len(store):
        return pd.DataFrame(columns=["day", "slot", "F", "y", "r", "bucket", "week", "month"])
    s = store.copy()
    s = s[s.day >= str(pd.Timestamp(start).date())]
    s = s[pd.notna(s.F_H1) & (s.F_H1 != "")]
    if not len(s):
        return pd.DataFrame(columns=["day", "slot", "F", "y", "r", "bucket", "week", "month"])
    g = grid.assign(dkey=pd.DatetimeIndex(grid.day).strftime("%Y-%m-%d")).set_index(["dkey", "slot"])
    y = np.array([g.y_bp.get((d, int(sl)), np.nan) for d, sl in zip(s.day, s.slot)], dtype=float)
    end_utc = bars.model_to_utc(pd.to_datetime(s.origin_model) + pd.Timedelta(hours=1))
    final = np.asarray(end_utc <= complete_utc)
    F = s.F_H1.astype(float).values
    ok = final & np.isfinite(y) & np.isfinite(F) & (F > 0)
    s, y, F = s[ok], y[ok], F[ok]
    d = pd.to_datetime(s.day)
    iso = d.dt.isocalendar()
    return pd.DataFrame({
        "day": s.day.values, "slot": s.slot.astype(int).values, "F": F, "y": y, "r": y / F,
        "bucket": [sc.bucket(int(sl), int(nf), int(cp), int(fo)) for sl, nf, cp, fo in
                   zip(s.slot, s.nfp, s.cpi, s.fomc)],
        "week": (iso.year.astype(int) * 100 + iso.week.astype(int)).values,
        "month": d.dt.strftime("%Y-%m").values,
    })


# ---------------------------------------------------------------- estimator
def bucket_stats(obs_b, event):
    """(n, G, mean, se, z) of one bucket's observations."""
    n = len(obs_b)
    if n == 0:
        return 0, 0, np.nan, np.nan, np.nan
    r = obs_b.r.values.astype(float)
    m = float(r.mean())
    G = int(obs_b.week.nunique())
    if event:
        se = float(r.std(ddof=1) / np.sqrt(n)) if n >= 2 else np.nan
    else:
        wm = obs_b.groupby("week").r.mean().values
        se = float(wm.std(ddof=1) / np.sqrt(G)) if G >= 2 else np.nan
    z = (m - 1.0) / se if np.isfinite(se) and se > 0 else np.nan
    return n, G, m, se, z


def eligible(bucket, n, G):
    return n >= N_MIN_EVENT if bucket in EVENT_BUCKETS else G >= G_MIN


def multiplier(bucket, n, G, m):
    w = n / (n + SHRINK_N) if bucket in EVENT_BUCKETS else G / (G + SHRINK_G)
    return float(min(max(1.0 + (m - 1.0) * w, M_LO), M_HI))


def update(obs, month, active_before, zstar):
    """One monthly update: rows per bucket (observations with model date < the month's first day)."""
    cut = pd.Timestamp(month + "-01")
    o = obs[pd.to_datetime(obs.day) < cut]
    rows = []
    for b in sc.BUCKETS:
        ev = b in EVENT_BUCKETS
        n, G, m, se, z = bucket_stats(o[o.bucket == b], ev)
        el = eligible(b, n, G) and np.isfinite(z)
        was = bool(active_before.get(b, False))
        if not el:
            act = False
        elif was:
            act = abs(z) >= zstar / 2
        else:
            act = abs(z) >= zstar
        rows.append({"month": month, "bucket": b, "n": n, "G": G, "mean_r": m, "se": se, "z": z, "eligible": int(el),
                     "active_before": int(was), "active_after": int(act),
                     "m": multiplier(b, n, G, m) if act else 1.0, "zstar": zstar})
    return rows


def due_months(today_model, done_months):
    """Months from 2027-01 through the current one without an update row yet."""
    out = []
    m = FIRST_UPDATE
    while m <= pd.Timestamp(today_model).normalize():
        k = m.strftime("%Y-%m")
        if k not in done_months:
            out.append(k)
        m += pd.DateOffset(months=1)
    return out


def latest_active(updates):
    """{bucket: active} after the latest update (the hysteresis state; empty before the first update)."""
    if not len(updates):
        return {}
    last = updates[updates.month.astype(str) == str(updates.month.max())]
    return {r.bucket: bool(int(r.active_after)) for r in last.itertuples()}


def monthly_updates(obs, updates, today_model, complete_utc, zstar):
    """The update rows due at this run, in month order (§4; A1 item 9: the chaining and its state live here).

    updates: the l3_updates ledger so far. A due month is computed only once every minute before its first day is
    final (complete_utc); the first month that is not stops the chain until a later run. Each month starts from the
    previous month's active states."""
    done = set(updates.month.astype(str)) if len(updates) else set()
    before = latest_active(updates)
    out = []
    for month in due_months(today_model, done):
        if bars.model_to_utc(pd.Timestamp(month + "-01")) > complete_utc:
            break
        rows = update(obs, month, before, zstar)
        out += rows
        before = {r["bucket"]: bool(r["active_after"]) for r in rows}
    return out


def current_multipliers(updates):
    """{bucket: (m, n)} of the latest update (1.0 and 0 before the first)."""
    out = {b: (1.0, 0) for b in sc.BUCKETS}
    if not len(updates):
        return out, None
    last = updates.month.max()
    for r in updates[updates.month == last].itertuples():
        out[r.bucket] = (float(r.m), int(r.n))
    return out, last


def load_zstar(path):
    p = Path(path)
    if not p.exists():
        return float("inf")
    return float(json.loads(p.read_text())["zstar"])


# ---------------------------------------------------------------- green suppression
def hour_trials(mf, store, start, complete_utc):
    """Per origin hour from START: base state (judge on raw inputs) and the two k10 mid trials."""
    if start is None or not len(store):
        return pd.DataFrame()
    s = store[(store.day >= str(pd.Timestamp(start).date())) & pd.notna(store.F_H1) & (store.F_H1 != "")]
    if not len(s):
        return pd.DataFrame()
    vol = bars.has_volume(mf)
    t = mf.index
    rows = []
    for r in s.itertuples():
        h0 = pd.Timestamp(r.origin_model)
        if bars.model_to_utc(h0 + pd.Timedelta(hours=1)) > complete_utc:
            continue
        F = float(r.F_H1)
        price = float(r.price) if pd.notna(r.price) and r.price != "" else np.nan
        hour_usd = price * (np.exp(F / 1e4) - 1) if np.isfinite(price) else np.nan
        state, reasons, _ = sc.judge(1, 0, h0.dayofweek, int(r.slot), int(r.nfp), int(r.cpi), int(r.fomc), hour_usd,
                                     COST_REF, 1)
        i0, i5, i60 = t.searchsorted(h0), t.searchsorted(h0 + pd.Timedelta(minutes=5)), \
            t.searchsorted(h0 + pd.Timedelta(hours=1))
        ent = [i for i in range(i0, i5) if vol[i]]
        row = {"day": r.day, "slot": int(r.slot), "origin": r.origin_model, "state": state, "reasons": reasons,
               "entry": 0, "hit_long": 0, "hit_short": 0}
        if ent:
            e = ent[0]
            E = float(mf.o.iloc[e])
            lo, hi = float(np.nanmin(mf.l.values[e:i60])), float(np.nanmax(mf.h.values[e:i60]))
            if np.isfinite(E) and np.isfinite(lo) and np.isfinite(hi):
                row["entry"] = 1
                row["hit_long"] = int(1e4 * np.log(E / lo) >= K10 * F)
                row["hit_short"] = int(1e4 * np.log(hi / E) >= K10 * F)
        rows.append(row)
    return pd.DataFrame(rows)


def expected_origins(a, b, holidays_full):
    days = pd.date_range(a, b - pd.Timedelta(days=1), freq="D")
    return int(sum(23 for d in days if d.dayofweek < 5 and d not in holidays_full))


def green_blocks(trials, start, complete_utc, holidays_full):
    """Block table and the resulting l1_green_ok (D1 rule)."""
    if start is None:
        return [], 1
    start = pd.Timestamp(start)
    rows, green_ok, run_hi, run_band = [], 1, 0, 0
    k = 0
    while True:
        a, b = start + pd.Timedelta(days=BLOCK_DAYS * k), start + pd.Timedelta(days=BLOCK_DAYS * (k + 1))
        if bars.model_to_utc(a + pd.Timedelta(hours=1)) > complete_utc:
            break
        ended = bars.model_to_utc(b) <= complete_utc
        tb = trials[(pd.to_datetime(trials.day) >= a) & (pd.to_datetime(trials.day) < b)] if len(trials) else trials
        exp = expected_origins(a, b, holidays_full)
        n_or = int((tb.entry == 1).sum()) if len(tb) else 0
        g = tb[(tb.state == sc.GREEN) & (tb.entry == 1)] if len(tb) else tb
        hits = int(g.hit_long.sum() + g.hit_short.sum()) if len(g) else 0
        trials_n = 2 * len(g)
        hr = hits / trials_n if trials_n else np.nan
        complete = bool(ended and n_or >= BLOCK_COMPLETE_FRAC * exp)
        if complete and np.isfinite(hr):
            if hr > HR_HIGH:
                run_hi, run_band = run_hi + 1, 0
            elif HR_LOW <= hr <= HR_HIGH:
                run_band, run_hi = run_band + 1, 0
            else:
                run_hi, run_band = 0, 0
            if green_ok == 1 and run_hi >= 2:
                green_ok = 0
            elif green_ok == 0 and run_band >= 2:
                green_ok = 1
        rows.append({"block": k + 1, "start": a.strftime("%Y-%m-%d"), "end": b.strftime("%Y-%m-%d"),
                     "complete": int(complete), "n_origins": n_or, "expected": exp, "n_green": len(g), "hits": hits,
                     "trials": trials_n, "hit_rate": hr, "green_ok_after": green_ok})
        k += 1
    return rows, green_ok
