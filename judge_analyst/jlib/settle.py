"""Independent settlement of a call (R-AN-40..R-AN-47): entry, path rule, money, void/no_quote, the opposite side,
the path summary and the drift twin. Integer points throughout (1 point = $0.001); every level comparison is exact."""
from __future__ import annotations

import datetime as dt

from .clock import Window, model_to_utc
from .common import UTC, fmt_utc
from .m1 import Store

MIN = 60


def _clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class Minutes:
    """The store minutes of UTC days d−1 and d for one window (R-AN-41). (§16.18 A17-R9) t1: the end of the path,
    x_exit (epoch): day_end(d) for an extended trade; by default the window's exit_utc."""

    def __init__(self, store: Store, win: Window, t1: int | None = None):
        self.store = store
        self.win = win
        self.t0 = int(win.entry.timestamp())
        self.t1 = int(win.exit.timestamp()) if t1 is None else int(t1)
        d = win.day
        self.mds = int(model_to_utc(dt.datetime(d.year, d.month, d.day)).timestamp())

    def row(self, side, t):
        return self.store.side(side, t)

    def live(self, t):
        b = self.store.side("BID", t)
        a = self.store.side("ASK", t)
        return b is not None and a is not None and b[4] > 0 and a[4] > 0

    def half_spread(self, t, field):
        """Half spread in $ at minute t on field 'o' or 'c'; 0 without both sides."""
        b = self.store.side("BID", t)
        a = self.store.side("ASK", t)
        if b is None or a is None:
            return 0.0
        i = 0 if field == "o" else 3
        return (a[i] - b[i]) / 2000.0


def _null_outcome(status, S):
    o = {k: None for k in ("P_e", "P_e_src", "P_e_minute_utc", "X", "Tg", "exit_minute_utc", "P_x", "reason", "fill",
                           "gross_usd")}
    o.update({"status": status, "cost_usd": 0.0, "net_usd": -S, "stress_net_usd": -S, "R": -1.0, "R_stress": -1.0,
              "y": -1.0})
    return o


def settle_side(mins: Minutes, s: int, S_dimes: int, T_dimes: int, void: bool, m: int | None = None):
    """Outcome dict of R-AN-46 for side s, plus private keys `_exit_t` (epoch) and `_pe_pts`. (§16.18 A15, R-AN-93)
    m: the managed minute (epoch of the closing review's entry), or None: R-AN-42's loop then runs for t0 .. m − 1,
    and without an exit there the trade exits at m (the exit side's open of m, reason `managed`, fill `open`), else
    at the latest quoted close in [t0, m) (`managed`, `close`), else at X (`gap`, `level`, exit minute null)."""
    S = S_dimes / 10
    if void:
        o = _null_outcome("void", S)
        o["_exit_t"] = None
        return o
    entry_side = "ASK" if s == 1 else "BID"
    exit_side = "BID" if s == 1 else "ASK"
    t0, t1 = mins.t0, mins.t1
    r = mins.row(entry_side, t0)
    if r is not None:
        pe, pe_src, pe_t, pe_field = r[0], "open", t0, "o"
    else:
        pe = None
        for t in range(t0 - MIN, mins.mds - 1, -MIN):
            rr = mins.row(entry_side, t)
            if rr is not None:
                pe, pe_src, pe_t, pe_field = rr[3], "fallback_close", t, "c"
                break
        if pe is None:
            o = _null_outcome("no_quote", S)
            o["_exit_t"] = None
            return o
    S_pts = 100 * S_dimes
    T_pts = 100 * T_dimes
    X = pe - s * S_pts
    Tg = pe + s * T_pts
    run = 0
    exit_t = px = reason = fill = None
    end = t1 if m is None else m
    for t in range(t0, end, MIN):
        q = mins.row(exit_side, t)
        if q is not None:
            o_, h_, l_, _c = q[0], q[1], q[2], q[3]
            if s == 1:
                if o_ <= X:
                    exit_t, px, reason, fill = t, o_, "stop", "open"
                elif l_ <= X:
                    exit_t, px, reason, fill = t, X, "stop", "level"
                elif h_ >= Tg:
                    exit_t, px, reason, fill = t, Tg, "target", "level"
            else:
                if o_ >= X:
                    exit_t, px, reason, fill = t, o_, "stop", "open"
                elif h_ >= X:
                    exit_t, px, reason, fill = t, X, "stop", "level"
                elif l_ <= Tg:
                    exit_t, px, reason, fill = t, Tg, "target", "level"
            if exit_t is not None:
                break
        run = 0 if mins.live(t) else run + 1
        if run >= 15:
            exit_t, px, reason, fill = t, X, "gap", "level"
            break
    where = "loop"
    no_minute = False
    if exit_t is None and m is not None:
        where = "managed"
        q = mins.row(exit_side, m)
        if q is not None:
            exit_t, px, reason, fill = m, q[0], "managed", "open"
        else:
            for t in range(m - MIN, t0 - 1, -MIN):
                q = mins.row(exit_side, t)
                if q is not None:
                    exit_t, px, reason, fill = t, q[3], "managed", "close"
                    break
            if exit_t is None:
                exit_t, px, reason, fill, no_minute = m, X, "gap", "level", True
    if exit_t is None:
        where = "time"
        last = t1 - MIN
        q = mins.row(exit_side, last)
        if q is not None:
            exit_t, px, reason, fill = last, q[3], "time", "close"
        else:
            for t in range(t1 - 2 * MIN, t0 - 1, -MIN):
                q = mins.row(exit_side, t)
                if q is not None:
                    exit_t, px, reason, fill = t, q[3], "time", "close"
                    break
            if exit_t is None:
                exit_t, px, reason, fill = last, X, "gap", "level"
    net = s * (px - pe) / 1000 - 0.10
    stress = net - 0.25
    cost = 0.10 + mins.half_spread(pe_t, pe_field) + \
        (0.0 if no_minute else mins.half_spread(exit_t, "o" if fill == "open" else "c"))
    return {"status": "final", "P_e": pe / 1000, "P_e_src": pe_src,
            "P_e_minute_utc": fmt_utc(dt.datetime.fromtimestamp(pe_t, UTC)), "X": X / 1000, "Tg": Tg / 1000,
            "exit_minute_utc": None if no_minute else fmt_utc(dt.datetime.fromtimestamp(exit_t, UTC)),
            "P_x": px / 1000, "reason": reason, "fill": fill, "cost_usd": cost, "gross_usd": net + cost,
            "net_usd": net, "stress_net_usd": stress, "R": net / S, "R_stress": stress / S,
            "y": _clip(stress / S, -2.0, 2.0), "_exit_t": exit_t, "_pe_pts": pe, "_where": where}


def x_end(outcome: dict, mins: Minutes, m: int | None = None) -> int:
    """R-AN-93's x_end_utc (epoch): an exit inside the loop at minute i: i for an open fill, i + 1 min for a level
    fill; a time exit (reason `time`, or `gap` at X after the loop): exit_utc; a managed exit (reason `managed`, or
    the managed case's `gap` at X): m; status `void` or `no_quote`: m when a review closed the trade, else
    exit_utc. (§16.18 A17-R9) x_exit in place of exit_utc: mins.t1."""
    if outcome.get("status") != "final":
        return m if m is not None else mins.t1
    if outcome["_where"] == "managed":
        return m
    if outcome["_where"] == "time":
        return mins.t1
    i = outcome["_exit_t"]
    return i if outcome["fill"] == "open" else i + MIN


def path_summary(mins: Minutes, s: int, outcome: dict, m: int | None = None):
    """(§16.18 A15, R-AN-93) for reason `managed`, mfe_usd and mae_usd run from t0 through minute m − 1; the buckets
    and range_mid_usd keep the full [t0, t1). (§16.18 A17-R9, judge decision J-D73) [t0, t1) is [t0, x_exit): the
    15-minute buckets cover it, 16 for a 4-hour trade and (x_exit − t0) / 15 min for an extended one."""
    if outcome["status"] != "final":
        return None
    st = mins.store
    t0, t1 = mins.t0, mins.t1
    buckets = []
    hi_all = lo_all = None
    for k in range((t1 - t0) // (15 * MIN)):
        ms = []
        for t in range(t0 + 15 * MIN * k, t0 + 15 * MIN * (k + 1), MIN):
            mb = st.mid_bar(t)
            if mb is not None:
                ms.append(mb)
        if ms:
            b = {"k": k, "o": ms[0][0], "h": max(m[1] for m in ms), "l": min(m[2] for m in ms), "c": ms[-1][3],
                 "n": len(ms)}
            hi_all = b["h"] if hi_all is None else max(hi_all, b["h"])
            lo_all = b["l"] if lo_all is None else min(lo_all, b["l"])
        else:
            b = {"k": k, "o": None, "h": None, "l": None, "c": None, "n": 0}
        buckets.append(b)
    exit_side = "BID" if s == 1 else "ASK"
    pe = outcome["_pe_pts"]
    hs, ls = [], []
    last = m - MIN if outcome.get("_where") == "managed" else outcome["_exit_t"]
    for t in range(t0, last + MIN, MIN):
        q = st.side(exit_side, t)
        if q is not None:
            hs.append(q[1])
            ls.append(q[2])
    if hs:
        if s == 1:
            mfe, mae = (max(hs) - pe) / 1000, (min(ls) - pe) / 1000
        else:
            mfe, mae = (pe - min(ls)) / 1000, (pe - max(hs)) / 1000
    else:
        mfe = mae = None
    return {"buckets": buckets, "mfe_usd": mfe, "mae_usd": mae,
            "exit_after_min": None if outcome["exit_minute_utc"] is None else (outcome["_exit_t"] - t0) // MIN,
            "range_mid_usd": None if hi_all is None else hi_all - lo_all}


def is_void(days, d: dt.date) -> bool:
    """R-AN-44: both sides of UTC day d have `missing` rows."""
    b = days.row(d, "BID")
    a = days.row(d, "ASK")
    return b is not None and a is not None and b["status"] == "missing" and a["status"] == "missing"


def twin(mins: Minutes, void: bool):
    """(mid_entry, mid_entry_src, mid_exit, mid_exit_src, d_W, status) of R-AN-47."""
    if void:
        return None, None, None, None, None, "void"
    st = mins.store
    t0, t1 = mins.t0, mins.t1
    e_sum = e_src = None
    x = st.both(t0)
    if x is not None:
        e_sum, e_src = x[0][0] + x[1][0], "open"
    else:
        for t in range(t0 - MIN, mins.mds - 1, -MIN):
            x = st.both(t)
            if x is not None:
                e_sum, e_src = x[0][3] + x[1][3], "fallback_close"
                break
    x_sum = x_src = None
    x = st.both(t1 - MIN)
    if x is not None:
        x_sum, x_src = x[0][3] + x[1][3], "close"
    else:
        for t in range(t1 - 2 * MIN, t0 - 1, -MIN):
            x = st.both(t)
            if x is not None:
                x_sum, x_src = x[0][3] + x[1][3], "fallback_close"
                break
    if e_sum is None or x_sum is None:
        return (None if e_sum is None else e_sum / 2000, e_src, None if x_sum is None else x_sum / 2000, x_src, None,
                "no_quote")
    return e_sum / 2000, e_src, x_sum / 2000, x_src, (x_sum - e_sum) / 2000, "final"


def public(outcome: dict) -> dict:
    return {k: v for k, v in outcome.items() if not k.startswith("_")}
