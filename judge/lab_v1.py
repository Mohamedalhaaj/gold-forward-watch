"""The judge's own v1 lab recomputation: grammar L2G-1 decisions, execution, P4 twins (SYSTEM_V1_PREREG.md §3; L2 §5,
§6; IMPLEMENTATION_REGISTER R-V1-28 .. R-V1-33)."""
import hashlib
import math

import pandas as pd

from . import execution
from .common import K10_H, K10_S, hhmm, rnum

FEATS = ("MOVE", "ABSMOVE", "RANGE", "POS", "LWICK", "UWICK")


def tmin(s):
    """'HHMM' -> minutes."""
    return int(s[:2]) * 60 + int(s[2:])


def coin_side(day):
    return 1 if int(hashlib.sha256(f"L2-C1|{day}".encode()).hexdigest()[:8], 16) % 2 == 0 else -1


class DayBars:
    """The M15 lab bars of one model day, keyed by bar start minute."""

    def __init__(self, m15, day):
        d0 = pd.Timestamp(day)
        sub = m15[(m15.index >= d0) & (m15.index < d0 + pd.Timedelta(days=1))]
        self.b = {}
        for ts, r in sub.iterrows():
            self.b[int((ts - d0) / pd.Timedelta(minutes=1))] = r

    def valid(self, start):
        r = self.b.get(start)
        return r is not None and bool(r["valid"])

    def get(self, start, col):
        return float(self.b[start][col])


def window_ok(db, a, b):
    return all(db.valid(s) for s in range(a, b, 15))


def feature(db, f, a, b, U):
    O = db.get(a, "o")
    C = db.get(b - 15, "c")
    hs = [db.get(s, "h") for s in range(a, b, 15)]
    ls = [db.get(s, "l") for s in range(a, b, 15)]
    hi, lo = max(hs), min(ls)
    if f == "MOVE":
        return (C - O) / U
    if f == "ABSMOVE":
        return abs((C - O) / U)
    if f == "RANGE":
        return (hi - lo) / U
    if f == "POS":
        rng = hi - lo
        return None if rng <= 0 else (C - lo) / rng
    if f == "LWICK":
        return (min(O, C) - lo) / U
    if f == "UWICK":
        return (hi - max(O, C)) / U
    raise ValueError(f)


def decide(rec, day, db, store_row, hol, event_days, first_day):
    """R-V1-29: (outcome, side, U, feats, F_H1, F_S)."""
    spec = rec["spec"]
    d = pd.Timestamp(day)
    T = tmin(spec["T"])
    hold = int(spec["hold"])
    FH = store_row["F_H1"] if store_row else float("nan")
    FS = store_row["F_S"] if store_row else float("nan")
    wd = d.dayofweek
    nfe = len(spec["when"])
    blank = (0, float("nan"), [float("nan")] * nfe, FH, FS)
    if (not (int(spec["days"]) >> wd) & 1 or d in hol or (int(spec["skip_event"]) and d in event_days)
            or (first_day is not None and d < first_day) or (wd == 4 and T + 15 * hold > 22 * 60 + 45)):
        return ("abstain_day",) + blank
    wins = [(tmin(p[1]), tmin(p[2])) for p in spec["when"]]
    if spec["side"][0] in ("FOLLOW", "FADE"):
        wins.append((tmin(spec["side"][1]), tmin(spec["side"][2])))
    if not db.valid(T - 15) or not all(window_ok(db, a, b) for a, b in wins):
        return ("abstain_data",) + blank
    CT = db.get(T - 15, "c")
    U = CT * (math.exp(FH / 1e4) - 1)
    Fstop = FH if spec["stop"] == "H10" else FS
    if not (math.isfinite(U) and U > 0) or not (math.isfinite(Fstop) and Fstop > 0):
        return ("abstain_U", 0, U if math.isfinite(U) else float("nan"), [float("nan")] * nfe, FH, FS)
    feats, ok = [], True
    for p in spec["when"]:
        v = feature(db, p[0], tmin(p[1]), tmin(p[2]), U)
        if v is None:
            return ("abstain_data", 0, U, [float("nan")] * nfe, FH, FS)
        feats.append(v)
        th = float(p[4])
        ok = ok and (v >= th if p[3] == "GE" else v <= th)
    mode = spec["side"][0]
    if mode == "LONG":
        side = 1
    elif mode == "SHORT":
        side = -1
    elif mode == "COIN":
        side = coin_side(d.strftime("%Y-%m-%d"))
    else:
        mv = feature(db, "MOVE", tmin(spec["side"][1]), tmin(spec["side"][2]), U)
        sg = (mv > 0) - (mv < 0)
        side = sg if mode == "FOLLOW" else -sg
    if ok and side != 0:
        return ("trigger", side, U, feats, FH, FS)
    return ("no_trigger", 0, U, feats, FH, FS)


def trade(rec, dm, side, U, FH, FS):
    """R-V1-30 for one triggered decision. Returns the trade fields (status final or no_quote)."""
    spec = rec["spec"]
    T = tmin(spec["T"])
    delay = int(rec.get("entry_delay_min", 1))
    hold = int(spec["hold"])
    k, F = (K10_H, FH) if spec["stop"] == "H10" else (K10_S, FS)
    m_e = T + delay
    out = {"T": spec["T"], "side": side, "delay_min": delay, "entry_model": hhmm(m_e), "F_RAW_H1": FH,
           "F_RAW_S": FS, "U": U}
    ep = execution.entry_price(dm, side, m_e)
    if ep is None:
        out["status"] = "no_quote"
        return out
    P_e, m_used, kind = ep
    X = P_e * math.exp(-side * k * F / 1e4)
    D = abs(P_e - X)
    P_x, m_x, reason, xk = execution.path(dm, side, X, m_e, T + 15 * hold)
    half_in = execution._half(dm, m_used, kind)
    half_out = execution._half(dm, m_x, xk)
    out.update({"P_e": P_e, "X": X, "D": D, "exit_model": hhmm(m_x) if m_x is not None else "",
                "P_x": P_x, "reason": reason, "status": "final"})
    out.update(execution.money(side, P_e, P_x, D, half_in, half_out))
    return out


def twin(dm, T, delay, hold, k, F):
    """R-V1-31: a long on the mid with the rule's stop multiplier, no allowance and no cost. R_twin or None."""
    m_e = T + delay
    ep = execution.entry_price(dm, 1, m_e, mid=True)
    if ep is None:
        return None
    P_e = ep[0]
    X = P_e * math.exp(-k * F / 1e4)
    D = P_e - X
    P_x, _, _, _ = execution.path(dm, 1, X, m_e, T + 15 * hold, mid=True)
    return (P_x - P_e) / D


def twin_key(rec):
    s = rec["spec"]
    return f"{s['T']}|{s['hold']}|{s['stop']}|{int(rec.get('entry_delay_min', 1))}"


def fmt_decision(rid, day, dec, recorded):
    outcome, side, U, feats, FH, FS = dec
    f = list(feats) + [float("nan")] * (2 - len(feats))
    return {"id": rid, "day": day, "outcome": outcome, "side": str(side), "U": rnum(U), "feat1": rnum(f[0]),
            "feat2": rnum(f[1]), "F_RAW_H1": rnum(FH), "F_RAW_S": rnum(FS), "recorded_utc": recorded}
