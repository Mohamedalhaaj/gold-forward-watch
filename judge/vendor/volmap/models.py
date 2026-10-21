"""Targets, event dummies and the forecast models of VOLMAP_PREREG.md sections 2-4.

Targets T1 (next M15 range), T2 (next H1 range), T3 (rest of the session from each H1 boundary) and T4 (next day's
range), all in bp of log range. T3 rows align 1:1 with T2 (H1) rows; the base grid of T3 is H1.
Models: N1 last value, N2 ATR14, M1 static clock, M2 HAR without clock, M3 clock x recent ratio, M4 clock-HAR with
event and holiday dummies (M4noev = the ablation without dummies).
"""
from pathlib import Path

import numpy as np
import pandas as pd

import core

TARGETS = ("T1", "T2", "T3", "T4")
BASE = {"T1": "T1", "T2": "T2", "T3": "T2", "T4": "T4"}
BPD = {"T1": 92, "T2": 23, "T3": 23, "T4": 1}
NSLOT = {"T1": 92, "T2": 23, "T3": 23, "T4": 1}
MINUTES = {"T1": 15, "T2": 60}
EVENTS = ("NFP", "CPI", "FOMC")
DUMMIES = ["D_NFP", "D_CPI", "D_FOMC", "D_HOL"]
KS = (1, 5, 22)
SIMPLICITY = ("M1", "M3", "M2", "M4")
MODEL_COLS = ["N1", "N2", "M1", "M2", "M3", "M4", "M4noev"]


# ---------------------------------------------------------------- calendars
def load_events(cal_dir):
    cal_dir = Path(cal_dir)
    bls = pd.read_csv(cal_dir / "bls_2015_2024.csv")
    fomc = pd.read_csv(cal_dir / "fomc_2015_2024.csv")
    out = {k: core.to_server(pd.DatetimeIndex(pd.to_datetime(bls.ts_utc[bls.event == k], utc=True))).sort_values()
           for k in ("NFP", "CPI")}
    out["FOMC"] = core.to_server(pd.DatetimeIndex(pd.to_datetime(fomc.utc_timestamp, utc=True))).sort_values()
    return out


def nyse_holidays(start="2015-01-01", end="2024-12-31"):
    """NYSE full closures and early closes on weekdays (known in advance)."""
    import pandas_market_calendars as mcal
    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(start, end)
    closed = pd.bdate_range(start, end).difference(sched.index.normalize())
    early = cal.early_closes(sched).index.normalize()
    return closed.union(early)


def flag_windows(starts, ends, events):
    ev = np.sort(pd.DatetimeIndex(events).values)
    return (np.searchsorted(ev, pd.DatetimeIndex(ends).values, "left")
            - np.searchsorted(ev, pd.DatetimeIndex(starts).values, "left")) > 0


# ---------------------------------------------------------------- targets
def _per_slot(tf, fn):
    return tf.groupby("slot", group_keys=False).y.transform(lambda s: pd.Series(fn(s.values), index=s.index))


def build(m1, events, holidays):
    m15, h1, day = core.grid_bars(m1, 15), core.grid_bars(m1, 60), core.day_bars(m1)
    rs = core.rest_of_session(h1)

    def frame(g, minutes):
        f = g[["day", "wd", "slot", "start"]].copy()
        f["origin"] = g.start
        f["end"] = g.start + pd.Timedelta(minutes=minutes)
        f["y"] = g.r.values
        f["price"] = g.o.fillna(g.c.ffill()).values  # last known price where the origin bar is empty
        return f

    T1, T2, T3 = frame(m15, 15), frame(h1, 60), frame(h1, 60)
    T3["end"] = h1.start + pd.to_timedelta(rs.length_h.values, unit="h")
    T3["y"] = rs.r.values
    T3["length_h"] = rs.length_h.values
    T3["session"] = rs.session.values
    T3["hi"], T3["lo"] = rs.hi.values, rs.lo.values
    T4 = pd.DataFrame({"day": day.index, "wd": day.wd.values, "slot": 0,
                       "start": day.index + pd.Timedelta(hours=core.DAY_START_HOUR)})
    T4["origin"] = T4.start
    T4["end"] = T4.day + pd.Timedelta(hours=24)
    T4["y"] = day.r.values
    T4["price"] = day.o.values
    hol = pd.DatetimeIndex(holidays).normalize()
    T = {"T1": T1, "T2": T2, "T3": T3, "T4": T4}
    for t, f in T.items():
        for k in EVENTS:
            f[f"D_{k}"] = flag_windows(f.start, f.end, events.get(k, [])).astype(int)
        f["D_HOL"] = f.day.isin(hol).astype(int)
        if t == "T3":
            f["n1"] = _per_slot(f, core.last_valid_before)
            f["n2"] = _per_slot(f, lambda v: core.trailing_valid_mean(v, 14))
        else:
            f["n1"] = core.last_valid_before(f.y)
            f["n2"] = core.trailing_valid_mean(f.y, 14)
    return {"m15": m15, "h1": h1, "day": day, "rs": rs, "T": T}


# ---------------------------------------------------------------- models
def in_range(tf, a, b):
    return ((tf.day >= pd.Timestamp(a)) & (tf.day <= pd.Timestamp(b))).values


def seasonal(tf, mask, nslot=None):
    """Weekday x slot mean of the target, without event-dummy and holiday rows."""
    nslot = nslot or int(tf.slot.max()) + 1
    ok = np.asarray(mask) & tf.y.notna().values & (tf[DUMMIES].values.sum(1) == 0)
    m = tf[ok].groupby(["wd", "slot"]).y.mean()
    tab = np.full((5, nslot), np.nan)
    tab[m.index.get_level_values(0), m.index.get_level_values(1)] = m.values
    col = np.nanmean(tab, axis=0)
    tab = np.where(np.isnan(tab), col[None, :], tab)
    return np.where(np.isnan(tab), np.nanmean(tab), tab)


def _sv(tf, tab):
    return np.asarray(tab)[tf.wd.values, tf.slot.values]


def _base_feats(T, t, Sb):
    b = T[BASE[t]]
    r = b.y.values
    sb = _sv(b, Sb)
    bpd = BPD[t]
    f = {"last_ratio": core.last_valid_before(pd.Series(r / sb)), "r_last": core.last_valid_before(pd.Series(r))}
    for K in KS:
        f[f"rho{K}"] = core.rolling_ratio(r, sb, K * bpd)
        f[f"m{K}"] = core.trailing_rows_mean(r, K * bpd)
    return f


def _X_m4(t, tf, f, ev=True):
    cols = [np.log(f["last_ratio"])]
    if t != "T4":
        cols.append(np.log(f["rho1"]))
    cols += [np.log(f["rho5"]), np.log(f["rho22"])]
    if ev:
        cols += [tf[d].values.astype(float) for d in DUMMIES]
    return np.column_stack(cols)


def _X_m2(t, tf, f):
    cols = [np.log(f["r_last"])]
    if t != "T4":
        cols.append(np.log(f["m1"]))
    cols += [np.log(f["m5"]), np.log(f["m22"])]
    if t == "T3":
        cols.append(np.log(tf.length_h.values.astype(float)))
    return np.column_stack(cols)


def _ols(X, logy, mask):
    ok = mask & np.isfinite(X).all(1) & np.isfinite(logy)
    beta, smear = core.ols_fit(X[ok], logy[ok])
    return {"beta": beta.tolist(), "smear": smear, "n": int(ok.sum())}


def fit(T, a, b, K):
    """Fit every model on server days [a, b]. K: dict target -> M3 window in days. Returns JSON-able params."""
    S = {t: seasonal(T[t], in_range(T[t], a, b), NSLOT[t]) for t in TARGETS}
    params = {}
    for t in TARGETS:
        tf = T[t]
        Sb, St = S[BASE[t]], S[t]
        f = _base_feats(T, t, Sb)
        y = tf.y.values
        mask = in_range(tf, a, b) & np.isfinite(y) & (y > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            p = {"S": St.tolist(), "Sb": Sb.tolist(), "K": int(K[t]), "fit_days": [str(a)[:10], str(b)[:10]],
                 "M2": _ols(_X_m2(t, tf, f), np.log(y), mask),
                 "M4": _ols(_X_m4(t, tf, f), np.log(y / _sv(tf, St)), mask),
                 "M4noev": _ols(_X_m4(t, tf, f, ev=False), np.log(y / _sv(tf, St)), mask)}
        params[t] = p
    return params


def _pred_ols(X, p, scale=1.0):
    out = np.full(len(X), np.nan)
    ok = np.isfinite(X).all(1)
    out[ok] = core.ols_predict(np.array(p["beta"]), p["smear"], X[ok]) * (scale[ok] if np.ndim(scale) else scale)
    return out


def predict_m3(T, t, params, K):
    tf, p = T[t], params[t]
    return _sv(tf, p["S"]) * _base_feats(T, t, p["Sb"])[f"rho{K}"]


def predict(T, t, params):
    tf, p = T[t], params[t]
    f = _base_feats(T, t, p["Sb"])
    st = _sv(tf, p["S"])
    with np.errstate(divide="ignore", invalid="ignore"):
        F = pd.DataFrame({
            "N1": tf.n1.values, "N2": tf.n2.values, "M1": st,
            "M2": _pred_ols(_X_m2(t, tf, f), p["M2"]),
            "M3": st * f[f"rho{p['K']}"],
            "M4": _pred_ols(_X_m4(t, tf, f), p["M4"], st),
            "M4noev": _pred_ols(_X_m4(t, tf, f, ev=False), p["M4noev"], st),
        })
    return F.clip(lower=core.FORECAST_FLOOR)


def choose_champion(q):
    best = min(q[m] for m in SIMPLICITY)
    return next(m for m in SIMPLICITY if q[m] <= best * 1.005)


def select(T, inner_fit=("2015-01-01", "2018-12-31"), hold=("2019-01-01", "2020-12-31")):
    """Inner-split selection: M3's K per target, then the champion among M1-M4 (prereg section 4)."""
    params = fit(T, *inner_fit, K={t: 5 for t in TARGETS})
    out = {}
    for t in TARGETS:
        tf = T[t]
        y = tf.y.values
        h = in_range(tf, *hold) & np.isfinite(y)
        m3 = {K: predict_m3(T, t, params, K) for K in KS}
        okK = h & np.all([np.isfinite(v) for v in m3.values()], axis=0)
        qK = {K: float(core.qlike(y[okK], np.maximum(v[okK], core.FORECAST_FLOOR)).mean()) for K, v in m3.items()}
        params[t]["K"] = min(qK, key=qK.get)
        F = predict(T, t, params)
        ok = h & F.notna().all(axis=1).values
        q = {m: float(core.qlike(y[ok], F[m].values[ok]).mean()) for m in F.columns}
        out[t] = {"K_qlike": {str(k): v for k, v in qK.items()}, "K": params[t]["K"], "qlike": q,
                  "n": int(ok.sum()), "champion": choose_champion(q)}
    return out
