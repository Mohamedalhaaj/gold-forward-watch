"""§16.18 A17 (2026-11-06), the time decision, as the judge sees it. Written from the register text (A17-R1..A17-R12 and
A17-D1..A17-D8, and the items they mark: R-AN-4, R-AN-5, R-AN-8, R-AN-11, R-AN-23, R-AN-26, R-AN-29, R-AN-33, R-AN-36,
R-AN-39, R-AN-40, R-AN-55, R-AN-67, R-AN-89..R-AN-94) without reading the analyst or its watcher: the time windows
`<d>_X<hhmm>` and G_X(d), R(T)'s time step 4b and the subject, the `wake` of kind `time`, the open set with extensions,
`analyst-context/6`'s `review` block, `analyst-plan/4` and `review_extend`, settlement to day_end(d) with `at_4h` and
`to_day_end` (`analyst-settled/3`), check A17 (`a17_from`, `not_due`, `time_missed`) and A17_BUILD_COMMIT; days before
a17_from keep A16's rules (judge decisions J-D67..J-D75).
"""
import copy
import datetime as dt

import pytest

from jlib import config, derive, review, settle, watch
from jlib.clock import (Window, check_grid, check_grid_x, day_end, last_check, parse_call_id, scheduled_checks,
                        time_valid, time_wid)
from jlib.common import VIOLATION, WARNING, Findings, fmt_utc
from jlib.context import KEY_ORDER_V5, KEY_ORDER_V6, SCHEMA_V5, SCHEMA_V6, context_keys, sources_block
from jlib.judge import (ANSWERS, CALL_ID_RE, CALL_STATUSES, OPERATIONAL, TERMINAL_STATUSES, Judge, classify_path,
                        operational)
from jlib.m1 import Store

U = dt.timezone.utc
D = dt.date(2026, 12, 2)                  # a Wednesday on EST/GMT: W1 08:00-12:00Z, W2 14:30-18:30Z, day_end 22:00Z
E = dt.date(2026, 10, 28)                 # a Wednesday on EDT/GMT: day_end 21:00Z, L_d 16:30Z


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def keys(F, check=None, severity=None, code=None):
    return [f.key for f in F.items if (not check or f.check == check) and (not severity or f.severity == severity)
            and (not code or f.code == code)]


# ---------------------------------------------------------------- A17-R1: time windows and G_X(d) (unit)

def test_day_end_and_the_extended_grid():
    assert day_end(D) == T("2026-12-02T22:00:00Z") and day_end(E) == T("2026-10-28T21:00:00Z")
    for d in (D, E):
        g, gx = check_grid(d), check_grid_x(d)
        assert gx[:len(g)] == g and g[-1] == last_check(d) == day_end(d) - dt.timedelta(minutes=270)
        extra = gx[len(g):]
        assert extra == [last_check(d) + dt.timedelta(minutes=30 * k) for k in range(1, 7)]
        assert extra[-1] == day_end(d) - dt.timedelta(minutes=90)
    assert check_grid_x(dt.date(2026, 12, 5)) == []                       # a Saturday


def test_time_window_ids_times_and_validity():
    w = Window(D, "X1130")                                              # the time window of W1 (exit 12:00Z)
    assert (w.w, w.wid, w.kind, w.exchange) == ("X", "X1130", "time", None)
    assert w.check == T("2026-12-02T11:30:00Z") and w.entry == Window(D, "W1").exit
    assert w.exit == w.entry + dt.timedelta(minutes=240) and w.deadline == w.entry - dt.timedelta(minutes=15)
    assert w.span_lo == w.check and w.call_id == "2026-12-02_X1130"
    assert w.order > Window(D, "T1100").order and w.order < Window(D, "W2").order    # (model_day, entry_utc)
    assert time_wid(T("2026-12-02T20:00:00Z")) == "X2000"
    assert time_valid(w) and time_valid(Window(D, "X2030")) and time_valid(Window(D, "X1800"))   # beyond L_d
    assert not time_valid(Window(D, "X2100"))                          # after day_end - 90 min
    assert not time_valid(Window(D, "X0730")) and not time_valid(Window(D, "X1400"))   # W1's and W2's checks
    assert not time_valid(Window(E, "X2000")) and time_valid(Window(E, "X1930"))
    for ok in ("2026-12-02_X1130", "2026-12-02_X0000", "2026-12-02_X2330"):
        assert parse_call_id(ok) is not None
    for bad in ("2026-12-02_X1115", "2026-12-02_X2400", "2026-12-05_X1130", "2026-12-02_Y1130"):
        assert parse_call_id(bad) is None
    assert classify_path("analyst/canary/attempts/2026-12-02_X1130_1.json") == ("canary", "attempt")
    assert classify_path("analyst/calls/2026-12-02_X2000.json") == ("live", "call")
    assert classify_path("analyst/calls/2026-12-02_X2015.json") is None
    assert "X(?:" in CALL_ID_RE


def test_statuses_keys_and_the_unpinned_build():
    assert "review_extend" in TERMINAL_STATUSES and "review_extend" in CALL_STATUSES and "review_extend" in ANSWERS
    assert OPERATIONAL["A17"] == {"a17_from"} and operational("A17|a17_from|analyst/MODE.json|c")
    assert not operational("A17|not_due|analyst/attempts/x_1.json|c")         # an integrity key, as not_triggered
    assert hasattr(config, "A17_BUILD_COMMIT")
    pin = config.A17_BUILD_COMMIT
    assert isinstance(pin, str) and len(pin) == 40 and int(pin, 16) >= 0    # pinned (the A17 build commit)
    j = Judge.__new__(Judge)
    Judge.__init__(j, None, "2026-12-07T12:00:00Z")
    assert j.a17_commit == pin                                          # the judge's default is the pin
    Judge.__init__(j, None, "2026-12-07T12:00:00Z", a17_commit="PLACEHOLDER-A17-BUILD-COMMIT")
    assert j.a17_commit is None                                         # a placeholder is no pin
    Judge.__init__(j, None, "2026-12-07T12:00:00Z", a17_commit="ab" * 20)
    assert j.a17_commit == "ab" * 20
    assert KEY_ORDER_V6 == KEY_ORDER_V5 and context_keys(SCHEMA_V6) == KEY_ORDER_V6
    assert sources_block(SCHEMA_V6) == sources_block(SCHEMA_V5)          # every other field as for /5


# ---------------------------------------------------------------- A17-R2, A17-R3: the time step (unit)

ALL = dict.fromkeys(watch.CONDITIONS, True)
W1 = "2026-12-02_W1"


def test_the_time_step_in_its_order():
    t = T("2026-12-02T11:30:00Z")
    assert watch.rule(D, t, [], 0, False, ALL, 10, subject=W1, a17=True) == ("window", "X1130", "time", W1)
    assert watch.rule(D, t, [], 0, False, ALL, 10, subject=None, a17=True)[2] == "trigger"     # no subject
    assert watch.rule(D, t, [], 0, False, ALL, 10, subject=W1)[2] == "trigger"     # before a17_from: no step 4b
    near = [(t - dt.timedelta(minutes=30), "trigger", "asia_up")]
    assert watch.rule(D, t, near, 0, False, ALL, 10, subject=W1, a17=True)[2] == "time"    # no gap for it
    ten = [(t - dt.timedelta(minutes=30 * (k + 1)), "fixed", None) for k in range(10)]
    assert watch.rule(D, t, ten, 0, False, ALL, 10, subject=W1, a17=True)[0] == "day_cap"  # step 2 first
    assert watch.rule(D, t, [], 0, True, ALL, 10, subject=W1, a17=True)[0] == "none"       # a holiday-table day
    sched = T("2026-12-02T14:00:00Z")                                    # W2's check: the scheduled window wins
    assert watch.rule(D, sched, [], 0, False, ALL, 10, subject="2026-12-02_T0930", a17=True) == \
        ("window", "W2", "fixed", None)
    late = T("2026-12-02T18:00:00Z")                                     # beyond L_d: the time step only
    assert watch.rule(D, late, [], 0, False, ALL, 10, subject=None, a17=True)[0] == "none"
    assert watch.rule(D, late, [], 0, False, ALL, 10, subject="2026-12-02_W2", a17=True) == \
        ("window", "X1800", "time", "2026-12-02_W2")
    assert watch.rule(D, late, [], 0, False, ALL, 10, subject="2026-12-02_W2")[0] == "outside"
    assert watch.rule(D, T("2026-12-02T21:00:00Z"), [], 0, False, ALL, 10, subject=W1, a17=True)[0] == "outside"
    # a time window with an attempt is in E(T): the gaps and the cap count it, consumption does not
    after = [(t, "time", None)]
    assert watch.rule(D, t + dt.timedelta(minutes=30), after, 0, False, ALL, 10, a17=True)[0] == "none"   # g < 60
    assert watch.rule(D, t + dt.timedelta(minutes=60), after, 0, False, ALL, 10, a17=True)[3] == "asia_up"


def W(cid, entry, status, action=None, names=None, hours=4):
    e = T(f"2026-12-02T{entry}:00Z")
    return {"cid": cid, "entry": e, "exit": e + dt.timedelta(hours=hours), "status": status, "action": action,
            "names": names}


DE = T("2026-12-02T22:00:00Z")


def test_open_set_extension_and_a_later_close():
    wins = [W("2026-12-02_W1", "08:00", "called", "buy"),
            W("2026-12-02_X1130", "12:00", "review_extend", "extend", ["2026-12-02_W1"]),
            W("2026-12-02_W2", "14:30", "review_close", "close", ["2026-12-02_W1"]),
            W("2026-12-02_T1500", "15:30", "stay_out", "stay_out")]
    r = review.open_sets(wins, DE)
    assert r.open["2026-12-02_X1130"] == []                    # its subject is not in O(X)
    assert r.open["2026-12-02_W2"] == ["2026-12-02_W1"] and r.flags["2026-12-02_W2"] == [True]
    assert r.extended == {"2026-12-02_W1": "2026-12-02_X1130"}
    assert r.closed_by == {"2026-12-02_W1": "2026-12-02_W2"}                # a managed exit after exit_utc
    assert r.managed["2026-12-02_W1"] == T("2026-12-02T14:30:00Z") == r.eff_exit["2026-12-02_W1"]
    assert r.open["2026-12-02_T1500"] == []
    held = copy.deepcopy(wins)
    held[2].update(status="review_hold", action="hold")
    r = review.open_sets(held, DE)
    assert r.eff_exit["2026-12-02_W1"] == DE and r.open["2026-12-02_T1500"] == ["2026-12-02_W1"]
    assert r.flags["2026-12-02_T1500"] == [True]
    # no extension before a17_from (day_end None): A15's open set exactly
    assert review.open_sets(held).eff_exit["2026-12-02_W1"] == T("2026-12-02T12:00:00Z")


def test_a_time_window_closes_and_opens_nothing():
    base = [W("2026-12-02_W1", "08:00", "called", "buy"), W("2026-12-02_W1b", "10:00", "called", "add",
                                                           ["2026-12-02_W1"])]
    for st, act in (("review_close", "close"), ("no_call:invalid", None), ("missed:trigger", None),
                    ("called", "buy")):
        wins = base + [W("2026-12-02_X1130", "12:00", st, act, ["2026-12-02_W1", "2026-12-02_W1b"]),
                       W("2026-12-02_T1230", "13:00", "review_hold", "hold")]
        r = review.open_sets(wins, DE)
        assert r.closed_by == {} and r.extended == {}, st
        assert r.eff_exit["2026-12-02_W1"] == T("2026-12-02T12:00:00Z"), st
        assert r.open["2026-12-02_T1230"] == ["2026-12-02_W1b"], st      # the X window is never a trade
        # A17-R7 (amended): O(X) is empty by definition, though W1b is open at its entry (no review, no open_cap)
        assert r.open["2026-12-02_X1130"] == [] and r.flags["2026-12-02_X1130"] == [], st
    # an extension names only its own subject (the trade whose exit is its entry), once
    wins = base + [W("2026-12-02_X1130", "12:00", "review_extend", "extend", ["2026-12-02_W1b"])]
    assert review.open_sets(wins, DE).extended == {}
    closed = [W("2026-12-02_W1", "08:00", "called", "buy"),
              W("2026-12-02_W1b", "10:00", "called", "reverse", ["2026-12-02_W1"]),
              W("2026-12-02_X1130", "12:00", "review_extend", "extend", ["2026-12-02_W1"])]
    r = review.open_sets(closed, DE)
    assert r.extended == {} and r.eff_exit["2026-12-02_W1"] == T("2026-12-02T10:00:00Z")


def test_the_subject():
    w1 = W("2026-12-02_W1", "08:00", "called", "buy")
    assert review.subject_at([w1], T("2026-12-02T12:00:00Z"), DE) == "2026-12-02_W1"
    assert review.subject_at([w1], T("2026-12-02T12:30:00Z"), DE) is None           # no trade exits there
    hold = W("2026-12-02_W1b", "10:00", "review_hold", "hold", ["2026-12-02_W1"])
    rev = W("2026-12-02_W1b", "10:00", "called", "reverse", ["2026-12-02_W1"])
    assert review.subject_at([w1, hold], T("2026-12-02T12:00:00Z"), DE) == "2026-12-02_W1"
    assert review.subject_at([w1, rev], T("2026-12-02T12:00:00Z"), DE) is None      # closed before its exit
    assert review.subject_at([w1, rev], T("2026-12-02T14:00:00Z"), DE) == "2026-12-02_W1b"
    stay = W("2026-12-02_W1", "08:00", "stay_out", "stay_out")
    assert review.subject_at([stay], T("2026-12-02T12:00:00Z"), DE) is None
    # A17-D3: at least 60 minutes of extension
    t1630 = W("2026-12-02_T1630", "17:00", "called", "sell")
    t1700 = W("2026-12-02_T1700", "17:30", "called", "sell")
    assert review.subject_at([t1630], T("2026-12-02T21:00:00Z"), DE) == "2026-12-02_T1630"
    assert review.subject_at([t1700], T("2026-12-02T21:30:00Z"), DE) is None


# ---------------------------------------------------------------- A17-R4: the wake of kind `time` (unit)

def test_wake_problems_of_a_time_window():
    x = Window(D, "X1130")
    good = {"wake": {"kind": "time", "reason": W1, "check_utc": "2026-12-02T11:30:00Z", "td": None}}
    assert watch.wake_problems(good, x) == []
    assert watch.wake_problems({"wake": dict(good["wake"], kind="trigger")}, x) == ["wake.kind"]
    assert watch.wake_problems({"wake": dict(good["wake"], reason=None)}, x) == ["wake.reason"]
    w1b = dict(good["wake"], reason="2026-12-02_W1b")                  # W1b exits at 14:00, not at 12:00
    assert watch.wake_problems({"wake": w1b}, x) == ["wake.reason"]
    assert watch.wake_problems({"wake": dict(good["wake"], reason="2026-12-01_W1")}, x) == ["wake.reason"]
    assert watch.wake_problems({"wake": dict(good["wake"], reason="move")}, x) == ["wake.reason"]
    assert watch.wake_problems({"wake": dict(good["wake"], td={"req": "XAUUSD_M30"})}, x) == ["wake.td"]
    assert watch.wake_problems({"wake": dict(good["wake"], check_utc="2026-12-02T12:00:00Z")}, x) == \
        ["wake.check_utc"]
    blk = watch.wake_block(good["wake"], x)
    assert blk == {"kind": "time", "reason": W1, "check_utc": "2026-12-02T11:30:00Z", "values": None,
                   "r20_days": None, "bars_m30": None}


# ---------------------------------------------------------------- A17-R5: the `review` block of /6 (unit)

def bar(t, o, h, low, c):
    return {"t_utc": f"2026-12-02T{t}:00Z", "o": o, "h": h, "l": low, "c": c}


BARS = [bar("08:00", 4000.0, 4003.0, 3998.0, 4002.0), bar("08:30", 4002.0, 4006.0, 4001.0, 4005.5),
        bar("11:00", 4005.5, 4012.0, 4004.0, 4009.25)]


def trade(cid, action, side, entry, S, Tt, sm=1.0, tm=2.0):
    e = T(f"2026-12-02T{entry}:00Z")
    return {"call_id": cid, "action": action, "side": side, "entry_utc": fmt_utc(e),
            "exit_utc": fmt_utc(e + dt.timedelta(hours=4)), "S": S, "T": Tt, "stop_mult": sm, "target_mult": tm}


def test_review_block_v6_time_and_review_kinds():
    w1 = trade(W1, "buy", 1, "08:00", 5.0, 10.0)
    b = review.review_block_v6([w1], T("2026-12-02T12:00:00Z"), BARS, "time", DE, [False])
    assert list(b) == list(review.BLOCK_KEYS_V6) == ["kind", "open", "options", "ref_px", "ref_utc",
                                                      "extend_until_utc"]
    assert b["kind"] == "time" and b["options"] == ["extend", "close"] == review.TIME_OPTIONS
    assert b["extend_until_utc"] == "2026-12-02T22:00:00Z" and b["ref_px"] == 4009.25
    o = b["open"][0]
    assert list(o) == list(review.OPEN_KEYS_V6) and review.OPEN_KEYS_V6.index("extended") == \
        review.OPEN_KEYS_V6.index("exit_utc") + 1
    assert (o["extended"], o["exit_utc"], o["minutes_left"]) == (False, "2026-12-02T12:00:00Z", 0)
    assert o["entry_px"] == 4000.0 and o["move_usd"] == 9.25 and o["target_touched"] is True
    # a later review of the extended trade: its current exit is day_end(d)
    b = review.review_block_v6([w1], T("2026-12-02T14:30:00Z"), BARS, "review", DE, [True])
    o = b["open"][0]
    assert b["kind"] == "review" and b["options"] == ["hold", "close", "reverse", "add"]
    assert b["extend_until_utc"] is None
    assert (o["extended"], o["exit_utc"], o["minutes_left"]) == (True, "2026-12-02T22:00:00Z", 450)
    assert review.review_block_v6([], T("2026-12-02T14:30:00Z"), BARS, "review", DE, []) is None
    rec = copy.deepcopy(b)
    assert review.compare_review_v6(b, rec) == []
    rec["open"][0]["extended"] = False
    rec["extend_until_utc"] = "2026-12-02T22:00:00Z"
    assert review.compare_review_v6(b, rec) == ["review.extend_until_utc", "review.open[0].extended"]
    old = review.review_block([w1], T("2026-12-02T14:30:00Z"), BARS)                # a /5 block is not a /6 one
    assert review.compare_review_v6(b, old) == ["review.keys"]


# ---------------------------------------------------------------- A17-R6: analyst-plan/4 (unit)

EXTEND = {"action": "extend", "confidence": "medium", "reason_ar": "الاتجاه مستمر", "key_risks_ar": ""}


def test_plan_v4_extend():
    assert derive.status_of_action("extend") == "review_extend"
    assert derive.plan_errors(EXTEND, v3=True, v5=True, v6=True) == []
    assert derive.plan_errors(EXTEND, v3=True, v5=True) == ["action"]               # analyst-plan/3 has no extend
    assert derive.plan_errors(dict(EXTEND, stop_mult=1.0), v3=True, v5=True, v6=True) == ["keys"]
    hold = dict(EXTEND, action="hold")
    assert derive.plan_errors(hold, v3=True, v5=True, v6=True) == []
    assert derive.side_of("extend") == 0


# ---------------------------------------------------------------- A17-R9: settlement to day_end(d) (unit)

WIN = Window(D, "W1")                                  # entry 08:00Z, exit 12:00Z; day_end 22:00Z
T0 = int(WIN.entry.timestamp())


def long_store(bid_of):
    """A store from 08:00Z to 22:00Z whose ASK opens the trade at 4000.000 and whose BID per minute is bid_of(k)."""
    st = Store.__new__(Store)
    st.side_rows = {"BID": {}, "ASK": {}}
    for k in range(0, 14 * 60 + 1):
        t = T0 + 60 * k
        b = bid_of(k)
        st.side_rows["BID"][t] = b + (1,)
        st.side_rows["ASK"][t] = tuple(x + 200 for x in b) + (1,)
    st.side_rows["ASK"][T0] = (4_000_000, 4_000_100, 3_999_900, 4_000_000, 1)
    return st


def drift(k):
    """Flat at 4001 for four hours, then up 0.02 a minute: the bid high reaches the target 4010 at k = 685."""
    p = 4_001_000 + max(0, k - 240) * 20
    return (p, p + 100, p - 100, p)


def test_an_extended_trade_settles_to_day_end():
    end = int(DE.timestamp())
    four = settle.Minutes(long_store(drift), WIN)
    ext = settle.Minutes(long_store(drift), WIN, t1=end)
    assert (four.t1, ext.t1) == (int(WIN.exit.timestamp()), end)
    at_4h = settle.settle_side(four, 1, 50, 100, False)                   # S $5, T $10
    assert (at_4h["reason"], at_4h["exit_minute_utc"]) == ("time", "2026-12-02T11:59:00Z")
    out = settle.settle_side(ext, 1, 50, 100, False)
    assert out["reason"] == "target" and out["exit_minute_utc"] == "2026-12-02T19:25:00Z"
    assert settle.x_end(out, ext) == T0 + (685 + 1) * 60
    # A17-R9 (amended): R-AN-46's 16 buckets (the first 4 hours), range_mid_usd over [t0, x_exit), mfe, mae and
    # exit_after_min on the trade's own minutes
    ps, p4 = settle.path_summary(ext, 1, out), settle.path_summary(four, 1, at_4h)
    assert len(ps["buckets"]) == 16 and ps["buckets"] == p4["buckets"]
    assert ps["range_mid_usd"] == pytest.approx(12.78) and p4["range_mid_usd"] == pytest.approx(0.8)
    assert (ps["mfe_usd"], ps["mae_usd"], ps["exit_after_min"]) == (pytest.approx(10.0), pytest.approx(0.9), 685)
    assert (p4["mfe_usd"], p4["exit_after_min"]) == (pytest.approx(1.1), 239)
    # a review after exit_utc closes the extended trade: the managed minute lies after it
    m = int(T("2026-12-02T14:30:00Z").timestamp())
    man = settle.settle_side(ext, 1, 50, 100, False, m)
    assert (man["reason"], man["fill"], man["exit_minute_utc"]) == ("managed", "open", "2026-12-02T14:30:00Z")
    assert settle.x_end(man, ext, m) == m
    pm = settle.path_summary(ext, 1, man, m)
    assert (len(pm["buckets"]), pm["range_mid_usd"], pm["exit_after_min"]) == (16, pytest.approx(12.78), 390)
    assert pm["mfe_usd"] == pytest.approx(4.08)                            # t0 .. m − 1 (R-AN-93)
    flat_ext = settle.Minutes(long_store(lambda k: (4_001_000, 4_001_100, 4_000_900, 4_001_000)), WIN, t1=end)
    tim = settle.settle_side(flat_ext, 1, 50, 100, False)
    assert tim["reason"] == "time" and tim["exit_minute_utc"] == "2026-12-02T21:59:00Z"
    assert settle.x_end(tim, flat_ext) == end                              # x_end with x_exit for exit_utc


# ---------------------------------------------------------------- check A17 on the judge's own reading (stubs)

def judge(a15=dt.date(2026, 11, 2), a16=dt.date(2026, 11, 9), a17=dt.date(2026, 11, 9)):
    j = Judge.__new__(Judge)
    j.F = Findings()
    j.a14_day = dt.date(2026, 10, 29)
    j.a15_day, j.a16_day, j.a17_day = a15, a16, a17
    j.mode_cfg = {"a15_from": a15.isoformat() if a15 else None, "a16_from": a16.isoformat() if a16 else None,
                  "a17_from": a17.isoformat() if a17 else None}
    j.wit, j.terminal_info, j.windows = [], {}, {"canary": [], "live": []}
    return j


def test_A17_a17_from_needs_a16_from_and_not_earlier():
    def run(a16, a17):
        j = judge(a16=a16, a17=a17)
        j.a17_commit = "b"
        j.check_from_value = lambda check, key, day, b, unpinned: "s"
        j.git = type("G", (), {"ls_tree": lambda self, c, p: []})()
        j.head = "h"
        j.check_a17_from()
        return keys(j.F, severity=VIOLATION)
    nov9, nov16 = dt.date(2026, 11, 9), dt.date(2026, 11, 16)
    assert run(nov9, nov9) == [] and run(nov9, nov16) == []
    assert run(nov16, nov9) == ["A17|a17_from|analyst/MODE.json|s"]
    assert run(None, nov9) == ["A17|a17_from|analyst/MODE.json|s"]
    assert run(nov9, None) == []


def test_A17_a17_from_records_before_it_from_the_folders():
    """A `review_extend` terminal or an `analyst-settled/3` record of a model day before a17_from (or any while it is
    null), read from the folders: a time window before a17_from is no expected window."""
    files = {"analyst/canary/terminal/2026-11-06_X1130.json": {"status": "review_extend"},
             "analyst/terminal/2026-11-06_W1.json": {"status": "review_hold"},
             "analyst/settled/2026-11-06_W1b.json": {"schema": "analyst-settled/3"},
             "analyst/settled/2026-11-09_W1.json": {"schema": "analyst-settled/3"},
             "analyst/canary/settled/2026-11-06_W1.json": {"schema": "analyst-settled/2"}}

    class G:
        def ls_tree(self, c, prefix):
            return sorted(p for p in files if p.startswith(prefix) and "/" not in p[len(prefix):])
    for a17, want in ((dt.date(2026, 11, 9), {"t", "s"}), (None, {"t", "s", "s9"})):
        j = judge(a17=a17)
        j.a17_commit, j.git, j.head = "b", G(), "h"
        j.check_from_value = lambda check, key, day, b, unpinned: "set"
        j.json_at_head = lambda p: files[p]
        j.commit_of = {"analyst/canary/terminal/2026-11-06_X1130.json": "t", "analyst/settled/2026-11-06_W1b.json": "s",
                       "analyst/settled/2026-11-09_W1.json": "s9"}.get
        j.check_a17_from()
        assert {f.commit for f in j.F.items if f.code == "a17_from"} == want, a17


def test_A0_a17_unpinned_while_the_build_is_a_placeholder():
    j = judge()
    j.log = []
    j.check_from_value("A17", "a17_from", j.a17_day, None, "a17_unpinned")
    assert keys(j.F) == ["A0|a17_unpinned|judge_analyst/jlib/config.py|-"]
    assert [f.severity for f in j.F.items] == [WARNING]
    j = judge(a17=None)
    j.log = []
    j.check_from_value("A17", "a17_from", None, None, "a17_unpinned")
    assert keys(j.F) == []


class _Hol:
    def __init__(self, hol=False):
        self.hol = hol

    def any_exchange(self, d):
        return self.hol


def stubbed(subject_wins, n_e=0, hol=False, a16=dt.date(2026, 11, 9)):
    """A judge whose model day D has the windows `subject_wins` (R-AN-92's input) and n_e earlier wakes."""
    j = judge(a16=a16)
    j.holidays = _Hol(hol)
    j.commit_of = lambda p: "c"
    j.day_windows = lambda mode, d: subject_wins
    j.e_o = lambda mode, d, t: ([(t - dt.timedelta(minutes=30 * (i + 1)), "fixed", None) for i in range(n_e)], [])
    return j


def with_attempt(j, win, wake):
    acc = [type("Wit", (), {"rec": {"path": f"analyst/canary/attempts/{win.call_id}_1.json", "seq": 1}})()]
    j.watch_day = lambda mode, d: [(win, acc, "review_extend")]
    j.attempt_record = lambda w: {"schema": "analyst-attempt/2", "n": 1, "wake": wake}


def x_wake(win, subject):
    return {"kind": "time", "reason": subject, "check_utc": fmt_utc(win.check), "td": None}


def test_A17_not_due_rebuilds_the_time_step():
    x = Window(D, "X1130")
    w1 = dict(W(W1, "08:00", "called", "buy"), win=Window(D, "W1"))
    rev = dict(W("2026-12-02_W1b", "10:00", "called", "reverse", [W1]), win=Window(D, "W1b"))
    cases = [([w1], 0, False, W1, []),                                 # due: no finding
             ([w1, rev], 0, False, W1, ["not_due"]),                   # closed before its exit: no subject
             ([w1], 10, False, W1, ["not_due"]),                       # the cap of the day (10 from a16_from)
             ([w1], 0, True, W1, ["not_due"]),                         # a holiday-table day
             ([w1], 0, False, "2026-12-02_T0730", ["not_due"])]        # another subject in its wake
    for wins, n_e, hol, subj, want in cases:
        j = stubbed(wins, n_e, hol)
        with_attempt(j, x, x_wake(x, subj))
        j.check_wake_window("canary", x)
        assert [f.code for f in j.F.items] == want, (n_e, hol, subj)
        assert all(f.severity == VIOLATION and f.check == "A17" for f in j.F.items)
    j = stubbed([w1], 6, a16=None)                                      # the cap of 6 on a day before a16_from
    with_attempt(j, x, x_wake(x, W1))
    j.check_wake_window("canary", x)
    assert keys(j.F) == ["A17|not_due|analyst/canary/attempts/2026-12-02_X1130_1.json|c"]
    sched = Window(D, "X1400")                                           # W2's scheduled check: never a time window
    j = stubbed([dict(W("2026-12-02_T1000", "10:30", "called", "buy"), win=Window(D, "T1000"))])
    with_attempt(j, sched, x_wake(sched, "2026-12-02_T1000"))
    j.check_wake_window("canary", sched)
    assert [f.code for f in j.F.items] == ["not_due"]


def test_A17_time_missed_from_main(monkeypatch):
    """A due time window with no window at its check is the WARNING `time_missed` (pause intervals and mode off left
    out); a trigger due at the same check is not `wake_missed` from a17_from, since the time window beats it."""
    w1 = dict(W(W1, "08:00", "called", "buy"), win=Window(D, "W1"))
    j = stubbed([w1])
    j.watch_day = lambda mode, d: []
    j._pauses = []
    j.mode_off_at = lambda t: False
    j.now = T("2026-12-03T00:00:00Z")
    j.check_time_missed("canary", D)
    assert keys(j.F) == ["A17|time_missed|2026-12-02|X1130"] and j.F.items[0].severity == WARNING
    j = stubbed([w1])
    j.watch_day = lambda mode, d: []
    j._pauses = [(T("2026-12-02T11:00:00Z"), T("2026-12-02T12:00:00Z"))]
    j.mode_off_at = lambda t: False
    j.now = T("2026-12-03T00:00:00Z")
    j.check_time_missed("canary", D)
    assert keys(j.F) == []
    j.now, j._pauses = T("2026-12-02T22:30:00Z"), []                    # before day_end + 60 min: not yet
    j.check_time_missed("canary", D)
    assert keys(j.F) == []
    # wake_missed: the judge's bars give a trigger at 11:30, but the subject's time window wins there
    j = stubbed([w1])
    j.watch_day = lambda mode, d: []
    j._pauses = []
    j.mode_off_at = lambda t: False
    j.m30 = type("M30", (), {"get": lambda self, d: {"bars": []}})()
    monkeypatch.setattr(watch, "values_at", lambda bars, d, t: {})
    monkeypatch.setattr(watch, "conditions", lambda v, d, t: dict(ALL))
    j.check_wake_missed("canary", D)
    missed = {f.commit for f in j.F.items if f.code == "wake_missed"}
    assert "T1130" not in missed and "T1100" in missed


# ---------------------------------------------------------------- the world: time decisions in both modes from a17_from

from world import (PLAN_ADD, PLAN_BUY, PLAN_CLOSE, PLAN_EXTEND, PLAN_HOLD, PLAN_REVERSE, PLAN_SELL,  # noqa: E402
                   World)
import json  # noqa: E402
import os  # noqa: E402

# Canary 11-30 (A14), 12-01 (A15), 12-02 (A16: the day before a17_from keeps A16's rules), 12-03 (A17); live 12-04
# (A17). As A16-D3 and A17-D5 (amended) plan them, a16_from and a17_from are consecutive days, each with its own build,
# Worker and WATCHER_CONFIG.json the evening before; the A17 build is a --no-ff merge after 12-02's last lock.
# Canary 12-03: T2330 buy; T0130 adds; X0330 closes T2330 at its exit; X0530 extends T0130; W1 holds; W1b closes the
# extended T0130 at 10:00 (after its exit, 06:00); W2 buy; W2b holds; T1730 adds (exit 22:00, too late for a time
# window); X1800 extends W2 to 22:00. Live 12-04: T0030 buy; X0430 extends it; T0630 reverses it at 07:00 (after its
# exit, 05:00); W1 and W1b hold; X1030 closes T0630 at its exit; W2 sell; T1530 and W2b hold; X1800 closes W2.
A17_WORLD = dict(canary_days=("2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03"), live_from="2026-12-04",
                 live_to="2026-12-04", now="2026-12-07T12:00:00Z", store_first="2026-10-19", a12_from="2026-11-29",
                 a14_from="2026-11-30", a15_from="2026-12-01", a16_from="2026-12-02", a17_from="2026-12-03")
PLANS = {"2026-12-03_T0130": ("call", PLAN_ADD), "2026-12-03_X0330": ("call", PLAN_CLOSE),
         "2026-12-03_X0530": ("call", PLAN_EXTEND), "2026-12-03_W1": ("call", PLAN_HOLD),
         "2026-12-03_W1b": ("call", PLAN_CLOSE), "2026-12-03_W2": ("call", PLAN_BUY),
         "2026-12-03_W2b": ("call", PLAN_HOLD), "2026-12-03_T1730": ("call", PLAN_ADD),
         "2026-12-03_X1800": ("call", PLAN_EXTEND), "2026-12-04_X0430": ("call", PLAN_EXTEND),
         "2026-12-04_T0630": ("call", PLAN_REVERSE), "2026-12-04_W1": ("call", PLAN_HOLD),
         "2026-12-04_W1b": ("call", PLAN_HOLD), "2026-12-04_X1030": ("call", PLAN_CLOSE),
         "2026-12-04_W2": ("call", PLAN_SELL), "2026-12-04_T1530": ("call", PLAN_HOLD),
         "2026-12-04_W2b": ("call", PLAN_HOLD), "2026-12-04_X1800": ("call", PLAN_CLOSE)}


def a17_world(root, hooks=None, plans=None):
    return World(root, plans=dict(PLANS, **(plans or {})), hooks=hooks or {}, **A17_WORLD).build()


@pytest.fixture(scope="module")
def a17(tmp_path_factory):
    return a17_world(str(tmp_path_factory.mktemp("a17") / "w"))


def rkeys(res, check=None, severity=None, code=None):
    return keys(res.findings, check, severity, code)


def rec(w, path):
    with open(os.path.join(w.repo.path, path), encoding="utf-8") as f:
        return json.load(f)


def test_a17_world_runs_time_decisions(a17):
    st = {(m, c): t["status"] for (m, c), t in a17.terminals.items()}
    xs = sorted(x.call_id for x in a17.time_wins)
    assert xs == ["2026-12-03_X0330", "2026-12-03_X0530", "2026-12-03_X1800", "2026-12-04_X0430",
                  "2026-12-04_X1030", "2026-12-04_X1800"]
    assert [st[("canary", "2026-12-03_" + x)] for x in ("X0330", "X0530", "X1800")] == \
        ["review_close", "review_extend", "review_extend"]
    assert [st[("live", "2026-12-04_" + x)] for x in ("X0430", "X1030", "X1800")] == \
        ["review_extend", "review_close", "review_close"]
    assert not any("_X" in c for (_m, c) in st if c < "2026-12-03")           # the day before a17_from: A16's rules
    assert a17.calls[("canary", "2026-12-02_W1")]["context"]["schema"] == SCHEMA_V5
    assert a17.wakes[("canary", "2026-12-03_X0530")] == {"kind": "time", "reason": "2026-12-03_T0130",
                                                         "check_utc": "2026-12-03T05:30:00Z", "td": None}
    ctx = a17.calls[("canary", "2026-12-03_X0530")]["context"]
    assert ctx["schema"] == SCHEMA_V6 and ctx["window"] == "X" and ctx["wake"]["kind"] == "time"
    rv = ctx["review"]
    assert (rv["kind"], rv["options"], rv["extend_until_utc"]) == ("time", ["extend", "close"],
                                                                   "2026-12-03T22:00:00Z")
    assert [(o["call_id"], o["extended"], o["minutes_left"]) for o in rv["open"]] == [("2026-12-03_T0130", False, 0)]
    w1 = a17.calls[("canary", "2026-12-03_W1")]["context"]["review"]
    assert (w1["kind"], w1["open"][0]["extended"], w1["open"][0]["exit_utc"]) == ("review", True,
                                                                                 "2026-12-03T22:00:00Z")
    # settlement (A17-R9): x_exit, the managed exit after exit_utc, the `time` block; no record for a time window
    t0130 = rec(a17, "analyst/canary/settled/2026-12-03_T0130.json")
    assert t0130["schema"] == "analyst-settled/3" and t0130["exit_utc"] == "2026-12-03T06:00:00Z"
    assert (t0130["closed_by"], t0130["managed_utc"]) == ("2026-12-03_W1b", "2026-12-03T10:00:00Z")
    assert [r["call_id"] for r in t0130["reviews"]] == ["2026-12-03_W1", "2026-12-03_W1b"]      # no time window
    assert t0130["time"]["call_id"] == "2026-12-03_X0530" and t0130["time"]["status"] == "review_extend"
    assert t0130["time"]["extended"] is True and t0130["time"]["x_exit_utc"] == "2026-12-03T22:00:00Z"
    assert t0130["unmanaged"] is not None and t0130["time"]["at_4h"] is not None
    t2330 = rec(a17, "analyst/canary/settled/2026-12-03_T2330.json")
    assert t2330["time"]["extended"] is False and t2330["time"]["status"] == "review_close"
    # a close in a time window ends the trade at its exit, as planned: no managed exit, the 4-hour outcome itself
    assert t2330["closed_by"] is None and t2330["time"]["x_exit_utc"] == t2330["exit_utc"]
    assert t2330["time"]["at_4h"] == t2330["outcome"] and t2330["time"]["to_day_end"] is not None
    late = rec(a17, "analyst/canary/settled/2026-12-03_T1730.json")
    assert late["exit_utc"] == "2026-12-03T22:00:00Z" and late["time"] == {
        "call_id": None, "status": None, "extended": False, "x_exit_utc": "2026-12-03T22:00:00Z", "at_4h": None,
        "to_day_end": None}
    w2 = rec(a17, "analyst/canary/settled/2026-12-03_W2.json")
    assert w2["time"]["extended"] is True and len(w2["path_summary"]["buckets"]) == 16     # A17-R9: the first 4 h
    t0030 = rec(a17, "analyst/settled/2026-12-04_T0030.json")
    assert (t0030["closed_by"], t0030["managed_utc"], t0030["exit_utc"]) == \
        ("2026-12-04_T0630", "2026-12-04T07:00:00Z", "2026-12-04T05:00:00Z")
    assert rec(a17, "analyst/settled/2026-12-04_W2.json")["time"]["status"] == "review_close"
    for m, c in (("canary", "2026-12-03_X0530"), ("live", "2026-12-04_X1030")):
        pre = "analyst/" if m == "live" else "analyst/canary/"
        assert not os.path.exists(os.path.join(a17.repo.path, f"{pre}settled/{c}.json"))
        assert not os.path.exists(os.path.join(a17.repo.path, f"{pre}twins/{c}.json"))
    assert rec(a17, "analyst/canary/settled/2026-12-02_W2.json")["schema"] == "analyst-settled/2"
    led = open(os.path.join(a17.repo.path, "analyst/ledger.csv"), encoding="utf-8").read()
    assert "2026-12-04_X0430,2026-12-04,X," in led


def test_a17_world_is_sound(a17):
    res = a17.judge()
    assert rkeys(res) == []
    assert res.summary["contexts_rebuilt"] == len(a17.calls)
    assert res.summary["settled_checked"] == len(a17.a15_settled)


def test_A0_a17_unpinned_and_the_day_pairing(a17):
    """With A17_BUILD_COMMIT a placeholder, a17_from is unverified (A0 `a17_unpinned`), and `analyst-context/6`
    is still the schema of every call of a model day >= a17_from (paired with the day, not the commit)."""
    for pin in (None, "PLACEHOLDER-A17-BUILD-NOT-PINNED"):
        res = a17.judge(a17_commit=pin)
        assert rkeys(res) == ["A0|a17_unpinned|judge_analyst/jlib/config.py|-"], pin


def test_A17_a17_from_conditions(tmp_path):
    def wc(world, c):
        c["deployed_utc"] = "2026-12-02T22:30:00Z"                         # after 22:00Z of the day before
    w = a17_world(str(tmp_path / "w"), hooks={"watcher_config_a17": wc})
    res = w.judge()
    assert [k.rsplit("|", 1)[0] for k in rkeys(res, "A17", VIOLATION, "a17_from")] == ["A17|a17_from|analyst/MODE.json"]
    assert "deployed_utc" in [f for f in res.findings.items if f.code == "a17_from"][0].detail
    assert operational(rkeys(res, "A17", VIOLATION, "a17_from")[0])


def test_A17_a17_from_moved_and_records_before_it(a17, tmp_path):
    from jlib.common import record_form
    w = a17.clone(str(tmp_path / "c"))
    m = rec(w, "analyst/MODE.json")
    m["a17_from"] = "2026-12-04"
    sha = w.owner_commit({"analyst/MODE.json": record_form(m)}, T("2026-12-05T09:00:00Z"), "owner: a17_from moved")
    res = w.judge()
    af = rkeys(res, "A17", VIOLATION, "a17_from")
    assert f"A17|a17_from|analyst/MODE.json|{sha}" in af                      # a change after it was set
    det = " ".join(f.detail for f in res.findings.items if f.code == "a17_from")
    assert "accepted push before a17_from; 2026-12-03_X0530" in det             # time windows of 12-03
    # (their review_extend terminals share the call's commit, hence its key; the settle run's commit is its own)
    assert "analyst-settled/3; 2026-12-03_T0130" in det
    assert "A17 build before a17_from; 2026-12-03_W1" in det                  # A17-D5's order: 12-03 ran on it
    # 12-03 is a day before a17_from now: its calls are expected as /5 (A4)
    assert any("analyst/canary/calls/2026-12-03_W1.json" in k for k in rkeys(res, "A4", VIOLATION, "context_schema"))


def test_A17_build_merged_before_the_last_lock_of_the_day_before(tmp_path):
    """A17-D5 (amended): the A17 build reaches main after the last lock of the day before a17_from, so no window of
    an A16-only day runs on it. Merged on that morning instead (R-AN-5's rule still holds at 22:00Z), every window of
    12-02 runs on it: A17 `a17_from` on those records, and nothing else."""
    def day(world, d):
        if d == dt.date(2026, 12, 2):                  # after the day's 02:10 mirror run, before its windows
            world.make_a17_commits(T("2026-12-02T02:30:00Z"))
    w = a17_world(str(tmp_path / "w"), hooks={"day": day})
    res = w.judge()
    det = sorted(f.detail for f in res.findings.items if f.code == "a17_from")
    assert det and all(x.startswith("A17 build before a17_from; 2026-12-02_") for x in det)
    assert "A17 build before a17_from; 2026-12-02_W1" in det
    assert all(operational(k) for k in rkeys(res, "A17", VIOLATION, "a17_from"))
    assert [k for k in rkeys(res, severity=VIOLATION) if not k.startswith("A17|a17_from|")] == []


def _bad_hooks():
    def context(world, win, ctx):
        if win.call_id == "2026-12-03_W1":             # hides the extension of its open trade (a race-like read)
            m30r = next(f for f in ctx["files"] if f["req"] == "XAUUSD_M30R")
            trades, _flags = world.review_inputs("canary", win)
            ctx["review"] = review.review_block_v6(trades, win.entry, m30r["bars"], "review",
                                                   day_end(win.day), [False])
        if win.call_id == "2026-12-04_X0430":
            ctx["review"]["extend_until_utc"] = "2026-12-04T21:00:00Z"      # not day_end(d)

    def call(world, win, c):
        if win.call_id == "2026-12-04_W1b":            # extend in a review that is no time window
            c["plan"] = dict(PLAN_EXTEND)
            c["status"], c["plan_sha256"] = "review_extend", None
        if win.call_id == "2026-12-04_X1030":          # hold in a time window
            c["plan"] = dict(PLAN_HOLD)
            c["status"], c["plan_sha256"] = "review_hold", None

    def settled(world, win, r):
        if r["call_id"] == "2026-12-03_T2330":
            r["time"]["at_4h"] = None

    def terminal(world, t):
        if t["call_id"] == "2026-12-03_X0330" and t["status"] == "no_call:run":
            t["status"] = "missed:trigger"             # the closer writes no_call:run for a time window, never this
    return {"context": context, "call": call, "settled": settled, "terminal": terminal,
            "force_time": {"2026-12-03_X1130": "2026-12-03_W1"},           # W1 is a review hold: no trade
            "drop_time": {"2026-12-04_X1800"}, "time_twin": {"2026-12-04_X1030"}}


@pytest.fixture(scope="module")
def a17_bad(tmp_path_factory):
    return a17_world(str(tmp_path_factory.mktemp("a17bad") / "w"), hooks=_bad_hooks(),
                     plans={"2026-12-03_X0330": ("run_died",)})          # an attempt, no lock: the closer's


def test_A17_faults(a17_bad):
    w = a17_bad
    xs = [x.call_id for x in w.time_wins]
    assert "2026-12-03_X1130" in xs and "2026-12-04_X1800" not in xs
    assert "2026-12-03_X1800" not in xs                  # the forced X1130 is the tenth wake there: day_cap
    assert w.calls[("canary", "2026-12-03_X1130")]["context"]["detail"] == "time_subject"
    res = w.judge()
    base = sorted(k.rsplit("|", 1)[0] for k in rkeys(res, severity=VIOLATION))
    assert base == sorted([
        "A17|not_due|analyst/canary/attempts/2026-12-03_X1130_1.json",
        "A15|review_open|analyst/canary/calls/2026-12-03_W1.json",
        "A4|context_differs|analyst/calls/2026-12-04_X0430.json",
        "A5|call_status|analyst/calls/2026-12-04_W1b.json",
        "A5|action_not_allowed|analyst/calls/2026-12-04_W1b.json",
        "A5|call_status|analyst/calls/2026-12-04_X1030.json",
        "A5|action_not_allowed|analyst/calls/2026-12-04_X1030.json"])
    assert "A17|time_missed|2026-12-04|X1800" in rkeys(res, "A17", WARNING, "time_missed")
    assert sorted(k.rsplit("|", 1)[0] for k in rkeys(res, "A11", WARNING) if "_mismatch" in k) == \
        ["A11|settled_mismatch|analyst/canary/settled/2026-12-03_T2330.json",
         "A11|twin_mismatch|analyst/twins/2026-12-04_X1030.json"]
    # A17-R8: the closer's terminal of a time window is no_call:run; a missed:trigger there is A11 terminal_status
    assert rec(w, "analyst/canary/terminal/2026-12-03_X0330.json")["status"] == "missed:trigger"
    assert [k.rsplit("|", 1)[0] for k in rkeys(res, "A11", WARNING, "terminal_status")] == \
        ["A11|terminal_status|analyst/canary/terminal/2026-12-03_X0330.json"]
    det = {f.key.rsplit("|", 1)[0]: f.detail for f in res.findings.items}
    # T2330's `time`: at_4h dropped, and the status of its time window as main holds it (the world wrote the
    # closer's no_call:run before the tamper)
    assert set(det["A11|settled_mismatch|analyst/canary/settled/2026-12-03_T2330.json"].split("; ")) == \
        {"time.status", "time.at_4h.missing"}
    assert "extended" in det["A15|review_open|analyst/canary/calls/2026-12-03_W1.json"]
    assert "review.extend_until_utc" in det["A4|context_differs|analyst/calls/2026-12-04_X0430.json"]
    assert not operational(rkeys(res, "A17", VIOLATION, "not_due")[0])
