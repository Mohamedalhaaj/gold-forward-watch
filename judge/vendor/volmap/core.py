"""Volatility map: pure building blocks (bars, sessions, causal trailing features, losses, tests, rule helpers).

Pre-registration: research/volmap/VOLMAP_PREREG.md. Nothing here reads market data; see guard.py for loading.
Every trailing feature uses rows strictly before the current one.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

SERVER_SHIFT = pd.Timedelta(hours=7)  # MT5 server = America/New_York + 7h
DAY_START_HOUR = 1                    # trading day runs 01:00 -> 24:00 server
SESSIONS = {"asia": (1, 10), "london": (10, 15), "ny": (15, 24)}
VALID_FRAC = 0.8
DAY_MIN_BARS = 1104                   # 80% of 1,380 minutes
FORECAST_FLOOR = 0.1                  # bp


# ---------------------------------------------------------------- clock and units
def to_server(idx):
    return idx.tz_convert("America/New_York").tz_localize(None) + SERVER_SHIFT


def range_bps(h, l):
    return 1e4 * np.log(np.asarray(h, dtype=float) / np.asarray(l, dtype=float))


def session_of_hour(hour):
    for name, (a, b) in SESSIONS.items():
        if a <= hour < b:
            return name
    raise ValueError(hour)


# ---------------------------------------------------------------- bars
def grid_bars(m1, minutes):
    """Complete grid of `minutes` bars for every weekday present in the server-indexed M1 frame (o, h, l, c).

    Missing bars stay as rows with n = 0. A bar is valid with >= 80% of its minutes present."""
    m1 = m1[m1.index.dayofweek < 5]
    key = m1.index.floor(f"{minutes}min")
    g = m1.groupby(key)
    agg = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "n": g.o.size()})
    agg["tfirst"] = pd.Series(m1.index, index=m1.index).groupby(key).min()
    days = pd.DatetimeIndex(m1.index.normalize().unique()).sort_values()
    per_day = (24 - DAY_START_HOUR) * 60 // minutes
    offs = pd.to_timedelta(DAY_START_HOUR * 60 + np.arange(per_day) * minutes, unit="min")
    starts = pd.DatetimeIndex((days.values[:, None] + offs.values[None, :]).ravel())
    out = agg.reindex(starts)
    out["n"] = out.n.fillna(0).astype(int)
    out["t0"] = (out.tfirst - starts).dt.total_seconds().values / 60
    out = out.drop(columns="tfirst")
    out.insert(0, "start", starts)
    out.insert(0, "slot", np.tile(np.arange(per_day), len(days)))
    out.insert(0, "wd", np.repeat(days.dayofweek, per_day))
    out.insert(0, "day", np.repeat(days, per_day))
    out["valid"] = out.n >= math.ceil(VALID_FRAC * minutes)
    r = range_bps(out.h, out.l)
    out["r"] = np.where(out.valid & (r > 0), r, np.nan)
    return out.reset_index(drop=True)


def day_bars(m1):
    m1 = m1[m1.index.dayofweek < 5]
    key = m1.index.normalize()
    g = m1.groupby(key)
    d = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "n": g.o.size()})
    d.index.name = "day"
    d["wd"] = d.index.dayofweek
    d["valid"] = d.n >= DAY_MIN_BARS
    r = range_bps(d.h, d.l)
    d["r"] = np.where(d.valid & (r > 0), r, np.nan)
    return d


def rest_of_session(h1):
    """For every H1 grid row (origin h), the range of [h, end of h's session) from the H1 bars' extremes."""
    per_day = 24 - DAY_START_HOUR
    if len(h1) % per_day or (h1.slot.values.reshape(-1, per_day) != np.arange(per_day)).any():
        raise ValueError("rest_of_session needs a complete H1 grid")
    H = h1.h.values.reshape(-1, per_day)
    L = h1.l.values.reshape(-1, per_day)
    N = h1.n.values.reshape(-1, per_day).astype(float)
    hi, lo, n = np.full_like(H, np.nan), np.full_like(L, np.nan), np.zeros_like(N)
    length, sess = np.zeros(per_day, dtype=int), np.empty(per_day, dtype=object)
    for name, (a, b) in SESSIONS.items():
        sl = slice(a - DAY_START_HOUR, b - DAY_START_HOUR)
        hi[:, sl] = np.fmax.accumulate(H[:, sl][:, ::-1], axis=1)[:, ::-1]
        lo[:, sl] = np.fmin.accumulate(L[:, sl][:, ::-1], axis=1)[:, ::-1]
        n[:, sl] = np.cumsum(N[:, sl][:, ::-1], axis=1)[:, ::-1]
        hours = np.arange(a, b)
        length[sl] = b - hours
        sess[sl] = name
    out = pd.DataFrame({"hi": hi.ravel(), "lo": lo.ravel(), "n": n.ravel(),
                        "length_h": np.tile(length, len(H)), "session": np.tile(sess, len(H))}, index=h1.index)
    out["valid"] = out.n >= VALID_FRAC * 60 * out.length_h
    r = range_bps(out.hi, out.lo)
    out["r"] = np.where(out.valid & (r > 0), r, np.nan)
    return out


# ---------------------------------------------------------------- trailing features (strictly before)
def last_valid_before(s):
    return pd.Series(s).ffill().shift(1).values


def trailing_valid_mean(s, n):
    s = pd.Series(s).reset_index(drop=True)
    v = s.dropna().rolling(n).mean()
    return v.reindex(s.index).ffill().shift(1).values


def rolling_ratio(r, S, window, min_frac=0.5):
    """(sum of valid r over the previous `window` rows) / (sum of S over the same valid rows)."""
    r = pd.Series(r).reset_index(drop=True)
    S = pd.Series(S).reset_index(drop=True)
    ok = r.notna()
    num = r.where(ok, 0.0).rolling(window, min_periods=1).sum().shift(1)
    den = S.where(ok, 0.0).rolling(window, min_periods=1).sum().shift(1)
    cnt = ok.astype(float).rolling(window, min_periods=1).sum().shift(1)
    out = num / den
    return out.where((cnt >= math.ceil(min_frac * window)) & (den > 0)).values


def trailing_rows_mean(r, window, min_frac=0.5):
    r = pd.Series(r).reset_index(drop=True)
    return r.rolling(window, min_periods=math.ceil(min_frac * window)).mean().shift(1).values


# ---------------------------------------------------------------- losses and tests
def qlike(y, f):
    q = np.asarray(y, dtype=float) / np.asarray(f, dtype=float)
    return q - np.log(q) - 1


def newey_west_se(x, lag):
    x = np.asarray(x, dtype=float)
    e = x - x.mean()
    n = len(e)
    var = e @ e / n
    for k in range(1, lag + 1):
        var += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return math.sqrt(max(var, 0.0) / n)


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def dm_test(loss_base, loss_model, lag):
    """Diebold-Mariano on d = base - model; positive stat = model better. One-sided p."""
    d = np.asarray(loss_base, dtype=float) - np.asarray(loss_model, dtype=float)
    se = newey_west_se(d, lag)
    if se == 0:
        return 0.0, 0.5
    stat = d.mean() / se
    return stat, norm_sf(stat)


def _with_const(X):
    X = np.asarray(X, dtype=float)
    return np.column_stack([np.ones(len(X)), X.reshape(len(X), -1)])


def ols_fit(X, logy):
    """OLS of log y on X with intercept. Returns (beta, Duan smearing factor)."""
    Z = _with_const(X)
    beta, *_ = np.linalg.lstsq(Z, logy, rcond=None)
    resid = logy - Z @ beta
    return beta, float(np.mean(np.exp(resid)))


def ols_predict(beta, smear, X):
    return np.exp(_with_const(X) @ beta) * smear


def logistic_fit(X, y, lam=1.0, iters=100):
    """Ridge logistic regression by IRLS; the intercept is not penalised."""
    Z = _with_const(X)
    y = np.asarray(y, dtype=float)
    b = np.zeros(Z.shape[1])
    P = lam * np.eye(Z.shape[1])
    P[0, 0] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Z @ b)))
        W = p * (1 - p)
        grad = Z.T @ (y - p) - P @ b
        H = (Z * W[:, None]).T @ Z + P
        step = np.linalg.solve(H, grad)
        b = b + step
        if np.max(np.abs(step)) < 1e-10:
            break
    return b


def logistic_predict(b, X):
    return 1 / (1 + np.exp(-(_with_const(X) @ b)))


def auc(y, p):
    y = np.asarray(y).astype(bool)
    ranks = pd.Series(np.asarray(p, dtype=float)).rank(method="average").values
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def brier(y, p):
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


# ---------------------------------------------------------------- rule helpers
def excursions(E, lo, hi):
    """Adverse excursions in bp from entry E: below (long stop side) and above (short stop side)."""
    E = np.asarray(E, dtype=float)
    return 1e4 * np.log(E / np.asarray(lo, dtype=float)), 1e4 * np.log(np.asarray(hi, dtype=float) / E)


def unevenness(hits, n, p):
    hits, n = np.asarray(hits, dtype=float), np.asarray(n, dtype=float)
    ok = n > 0
    return float(np.mean(np.abs(hits[ok] / n[ok] - p)))


def week_bootstrap_counts(n_weeks, reps=2000, seed=20261016):
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_weeks, np.full(n_weeks, 1 / n_weeks), size=reps)


def day_labels(day, asia_hi, asia_lo, atr14):
    o, c, h, l = (np.asarray(day[k], dtype=float) for k in ("o", "c", "h", "l"))
    er = np.abs(c - o) / (h - l)
    r = range_bps(h, l)
    ok = np.isfinite(er)
    out = pd.DataFrame(index=day.index)
    out["er"] = er
    out["trend"] = np.where(ok, (er >= 0.5).astype(float), np.nan)
    okb = ok & np.isfinite(asia_hi) & np.isfinite(asia_lo)
    out["breakout"] = np.where(okb, ((c > asia_hi) | (c < asia_lo)).astype(float), np.nan)
    okg = ok & np.isfinite(atr14)
    out["big"] = np.where(okg, (r > 1.25 * np.asarray(atr14, dtype=float)).astype(float), np.nan)
    return out


def flag_events(starts, minutes, events):
    """True where at least one event timestamp falls inside [start, start + minutes)."""
    ev = np.sort(pd.DatetimeIndex(events).values)
    s = pd.DatetimeIndex(starts).values
    e = s + np.timedelta64(minutes, "m")
    return (np.searchsorted(ev, e, "left") - np.searchsorted(ev, s, "left")) > 0


# ---------------------------------------------------------------- quarantine and client hold
def quarantine_dates(manifest_path):
    """Server dates [cut - 30 days, cut + 1 day] around every eye-test cut."""
    charts = json.loads(Path(manifest_path).read_text())["charts"]
    out = set()
    for ch in charts:
        c = pd.Timestamp(ch["cut_server"]).normalize()
        out.update(pd.date_range(c - pd.Timedelta(days=30), c + pd.Timedelta(days=1)))
    return out


def client_release_allowed(verdict_path):
    """Nothing from this study goes to the client before the eye test's verdict.json exists."""
    return Path(verdict_path).exists()
