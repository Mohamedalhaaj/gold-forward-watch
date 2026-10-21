"""The judge's own lab v2 recomputation: online signals and the causality audit, decisions, execution with the
disaster stop, P4 twins (SYSTEM_V2_PREREG.md §2.2; IMPLEMENTATION_REGISTER R-V2-9 .. R-V2-19, R-V2-42).

The seeds are the vendored hunt files, called on the judge's own seed bars; nothing of the system is executed.
"""
import math

import numpy as np
import pandas as pd

from . import execution, vendored
from .common import K10_S, hhmm, rnum

TF_MIN = {"M5": 5, "M15": 15}


def normalise(sig, index):
    """R-V2-10: signal(df).reindex(df.index).fillna(0).clip(-1, 1).round().astype(int)."""
    return sig.reindex(index).fillna(0).clip(-1, 1).round().astype(int)


def hold_minutes(sid):
    tf, hold = vendored.SEED_SPEC[sid]
    return TF_MIN[tf] * hold


def in_window(T, hold_min, friday):
    return T >= 90 and T + hold_min <= (1365 if friday else 1410)


class SeedRun:
    """Seed bars B of one run (as of its data) and the full-data values of one seed."""

    def __init__(self, sid, inp):
        from .bars import seed_bars
        self.sid = sid
        self.mod = vendored.seed(sid)
        self.tf = TF_MIN[self.mod.TF]
        self.B = seed_bars(inp, self.tf)
        self.full = normalise(self.mod.signal(self.B), self.B.index).to_numpy()

    def day_positions(self, day):
        d0 = pd.Timestamp(day)
        idx = self.B.index
        a = idx.searchsorted(d0, "left")
        b = idx.searchsorted(d0 + pd.Timedelta(days=1), "left")
        return a, b

    def online(self, i):
        """Online value at bar position i: the normalised signal of B[: i + 1] read at i (R-V2-11)."""
        sub = self.B.iloc[: i + 1]
        return int(normalise(self.mod.signal(sub), sub.index).iloc[-1])


def audit_day(sr, day, hold_min):
    """R-V2-13 (strict, Amendment B2 item 4) for one (day, seed): (audit fields, [(bar position, online value)]).
    ANY bar whose online value differs from the full-data value fails the audit, in the window or outside it;
    first_mismatch is the bar start HH:MM of the first differing bar of the day."""
    a, b = sr.day_positions(day)
    d0 = pd.Timestamp(day)
    friday = d0.dayofweek == 4
    n_window = n_sig = mw = mo = 0
    first_mm = ""
    onl = []
    for i in range(a, b):
        start = sr.B.index[i]
        T = int((start - d0) / pd.Timedelta(minutes=1)) + sr.tf
        v = sr.online(i)
        onl.append((i, v))
        win = in_window(T, hold_min, friday)
        n_window += int(win)
        n_sig += int(v != 0)
        if v != sr.full[i]:
            if win:
                mw += 1
            else:
                mo += 1
            if not first_mm:
                first_mm = hhmm(T - sr.tf)
    return {"n_bars": b - a, "n_window": n_window, "n_signals": n_sig, "n_mismatch_window": mw,
            "n_mismatch_outside": mo, "first_mismatch": first_mm,
            "result": "ok" if mw == 0 and mo == 0 else "FAIL"}, onl


def decisions_day(sr, day, onl, hold_min, hol, fs_of_slot):
    """R-V2-16 rows for one (day, seed) from its online values: dicts with bar_start, T, signal, outcome,
    entry_model, F_RAW_S (float)."""
    d0 = pd.Timestamp(day)
    friday = d0.dayofweek == 4
    rows = []
    busy_until = -1
    for i, v in onl:
        if v == 0:
            continue
        start = sr.B.index[i]
        bs = int((start - d0) / pd.Timedelta(minutes=1))
        T = bs + sr.tf
        slot = (T + 1) // 60 - 1
        F = fs_of_slot(slot) if 0 <= slot <= 22 else float("nan")
        if not in_window(T, hold_min, friday):
            out = "abstain_window"
        elif d0 in hol:
            out = "abstain_day"
        elif not (math.isfinite(F) and F > 0):
            out = "abstain_U"
        elif T < busy_until:
            out = "ignored_open"
        else:
            out = "trade"
            busy_until = T + hold_min
        rows.append({"bar_start": hhmm(bs), "T": T, "signal": v, "outcome": out, "entry_model": hhmm(T + 1),
                     "F_RAW_S": F})
    return rows


def trade(dm, side, T, hold_min, F_S):
    """R-V2-17. Returns the trade fields (status final or no_quote)."""
    m_e = T + 1
    out = {"T": hhmm(T), "side": side, "entry_model": hhmm(m_e), "F_RAW_S": F_S}
    ep = execution.entry_price(dm, side, m_e)
    if ep is None:
        out["status"] = "no_quote"
        return out
    P_e, m_used, kind = ep
    D = P_e * (1 - math.exp(-K10_S * F_S / 1e4))
    X = P_e - side * 3 * D
    P_x, m_x, reason, xk = execution.path(dm, side, X, m_e, T + hold_min)
    half_in = execution._half(dm, m_used, kind)
    half_out = execution._half(dm, m_x, xk)
    out.update({"P_e": P_e, "D": D, "X": X, "exit_model": hhmm(m_x) if m_x is not None else "", "P_x": P_x,
                "reason": reason, "status": "final"})
    out.update(execution.money(side, P_e, P_x, D, half_in, half_out))
    return out


def twin(dm, T, hold_min, D):
    """R-V2-19: a long on the mid with the trade's D, X = P_e - 3 D, no cost."""
    m_e = T + 1
    out = {"T": hhmm(T), "entry_model": hhmm(m_e)}
    ep = execution.entry_price(dm, 1, m_e, mid=True)
    if ep is None:
        out["status"] = "no_quote"
        return out
    P_e = ep[0]
    X = P_e - 3 * D
    P_x, m_x, reason, _ = execution.path(dm, 1, X, m_e, T + hold_min, mid=True)
    out.update({"exit_model": hhmm(m_x) if m_x is not None else "", "P_e": P_e, "D": D, "X": X, "P_x": P_x,
                "reason": reason, "R_twin": (P_x - P_e) / D, "status": "final"})
    return out


def s3_flow_values(B15, before_day):
    """R-V2-15: finite trend-flip-flow values Ft preceding the given model date (display check only)."""
    mod = vendored.seed("S3")
    idx = B15.index
    hm = idx.hour * 60 + idx.minute
    day = idx.normalize()
    at = hm == mod.CLOSE_BAR
    p = pd.Series(B15.c.to_numpy()[at], index=day[at])
    p = p[~p.index.duplicated()].astype(float)
    lp = np.log(p)
    S = pd.concat([np.sign(lp - lp.shift(L)) for L in mod.LOOKS], axis=1).mean(axis=1, skipna=False)
    V = mod.TV / (lp.diff().rolling(mod.VOL_N, min_periods=mod.VOL_N).std() * np.sqrt(252))
    Ft = (S - S.shift(1)) * V.shift(1)
    Ft = Ft[Ft.index < pd.Timestamp(before_day)]
    return int(np.isfinite(Ft.to_numpy(dtype=float)).sum())


def fmt(x):
    if isinstance(x, str):
        return x
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    return rnum(x)
