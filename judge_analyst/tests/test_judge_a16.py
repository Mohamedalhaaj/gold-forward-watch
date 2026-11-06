"""§16.18 A16 (R-AN-5, R-AN-39, R-AN-67, R-AN-89; judge decision J-D66): R-AN-89 step 2's cap is 10 on or after
MODE.json `a16_from` and 6 before it, wherever the judge rebuilds the rule; A16 `a16_from` is R-AN-5's rule with the
pinned A16 build commit, plus a15_from set and a16_from >= a15_from."""
import datetime as dt

from jlib import config, watch
from jlib.clock import Window, check_grid, scheduled_checks
from jlib.common import VIOLATION, Findings
from jlib.judge import OPERATIONAL, Judge, operational

D = dt.date(2026, 11, 18)                         # a Wednesday
ALL = dict.fromkeys(watch.CONDITIONS, True)


def a_check():
    """A check of D that is not a scheduled one."""
    sched = scheduled_checks(D)
    return next(t for t in check_grid(D)[4:] if t not in sched)


def wakes(n, T):
    return [(T - dt.timedelta(minutes=30 * (i + 3)), "trigger", None) for i in range(n)]


def test_the_rule_takes_the_cap_of_its_day():
    T = a_check()
    assert (watch.DAY_CAP, watch.DAY_CAP_A16) == (6, 10)
    assert watch.rule(D, T, wakes(6, T), 0, False, ALL)[0] == "day_cap"
    assert watch.rule(D, T, wakes(6, T), 0, False, ALL, watch.DAY_CAP_A16)[0] == "window"
    assert watch.rule(D, T, wakes(9, T), 0, False, ALL, watch.DAY_CAP_A16)[0] == "window"
    assert watch.rule(D, T, wakes(10, T), 0, False, ALL, watch.DAY_CAP_A16)[0] == "day_cap"


def test_a16_from_is_operational_and_the_build_is_pinned_apart():
    assert OPERATIONAL["A16"] == {"a16_from"} and operational("A16|a16_from|analyst/MODE.json|x")
    assert hasattr(config, "A16_BUILD_COMMIT")


def judge(a15=None, a16=None, n=0):
    j = Judge.__new__(Judge)
    j.F = Findings()
    j.a14_day = dt.date(2026, 10, 29)
    j.a15_day, j.a16_day = a15, a16
    j.mode_cfg = {"a15_from": a15.isoformat() if a15 else None}
    j.e_o = lambda mode, d, t_check: (wakes(n, t_check), [])
    return j


def test_the_day_cap_and_the_closer_gate_from_a16_from():
    a15, a16 = dt.date(2026, 11, 2), dt.date(2026, 11, 16)
    j = judge(a15, a16, n=6)
    assert j.day_cap(dt.date(2026, 11, 13)) == 6 and j.day_cap(D) == 10
    assert j.day_cap(a16) == 10 and j.day_cap(a16 - dt.timedelta(days=1)) == 6       # the boundary day itself
    assert judge(a15, None).day_cap(D) == 6
    w2b = Window(D, "W2b")
    assert j.closer_gates("canary", w2b) == {}                                   # six wakes: no gate from a16_from
    assert judge(a15, a16, n=10).closer_gates("canary", w2b) == {"skipped:day_cap": 10}
    before = Window(dt.date(2026, 11, 13), "W2b")
    assert j.closer_gates("canary", before) == {"skipped:day_cap": 6}            # a day before a16_from keeps 6
    assert judge(a15, None, n=6).closer_gates("canary", w2b) == {"skipped:day_cap": 6}


def test_A16_a16_from_needs_a15_from_and_not_earlier():
    def run(a15, a16):
        j = judge(a15, a16)
        j.a16_commit = "b"
        j.check_from_value = lambda check, key, day, b, unpinned: "s"
        j.check_a16_from()
        return [f.key for f in j.F.items if f.severity == VIOLATION]
    assert run(dt.date(2026, 11, 2), dt.date(2026, 11, 9)) == []
    assert run(dt.date(2026, 11, 2), dt.date(2026, 11, 2)) == []
    assert run(dt.date(2026, 11, 9), dt.date(2026, 11, 2)) == ["A16|a16_from|analyst/MODE.json|s"]
    assert run(None, dt.date(2026, 11, 9)) == ["A16|a16_from|analyst/MODE.json|s"]
    assert run(dt.date(2026, 11, 2), None) == []


class _Hol:
    def any_exchange(self, d):
        return False


def rebuilt(monkeypatch, a16, n):
    """A judge whose model day D holds n earlier wakes, with the rule's inputs stubbed (every condition true)."""
    j = judge(dt.date(2026, 11, 2), a16, n=n)
    j.holidays = _Hol()
    j.commit_of = lambda p: "c"
    j.cross_check_m30 = lambda *a: None
    j.m30 = None                                   # no judge fetch: the bars comparison is skipped
    monkeypatch.setattr(watch, "wake_problems", lambda rec, win: [])
    monkeypatch.setattr(watch, "recorded_bars", lambda wk: [])
    monkeypatch.setattr(watch, "values_at", lambda bars, d, t: {})
    monkeypatch.setattr(watch, "conditions", lambda v, d, t: dict(ALL))
    return j


def with_attempt(j, win, reason=None):
    acc = [type("Wit", (), {"rec": {"path": "analyst/canary/attempts/x_1.json"}})()]
    j.watch_day = lambda mode, d: [(win, acc, "called")]
    j.attempt_record = lambda w: {"schema": "analyst-attempt/2", "n": 1, "wake": {"kind": win.kind, "reason": reason}}


def test_a14_day_cap_and_not_triggered_take_the_cap_of_the_day(monkeypatch):
    """The A14 checks of an accepted attempt rebuild R(T) with the day's cap: six earlier wakes are no `day_cap` and
    no `not_triggered` from a16_from on; the same day without a16_from (cap 6) gives both."""
    from jlib.clock import trigger_wid
    w2b = Window(D, "W2b")
    T = a_check()
    trig = Window(D, trigger_wid(T))
    for a16, expect in ((dt.date(2026, 11, 16), set()), (None, {"day_cap", "not_triggered"})):
        j = rebuilt(monkeypatch, a16, n=6)
        with_attempt(j, w2b)
        j.check_wake_window("canary", w2b)
        with_attempt(j, trig, reason="asia_up")
        j.check_wake_window("canary", trig)
        assert {f.code for f in j.F.items if f.check == "A14"} == expect, a16


def test_wake_missed_takes_the_cap_of_the_day(monkeypatch):
    """`wake_missed` rebuilds R(T) on the judge's own bars with the day's cap: six earlier wakes still leave a due
    trigger from a16_from on (a missed wake), none without a16_from."""
    for a16, missed in ((dt.date(2026, 11, 16), True), (None, False)):
        j = rebuilt(monkeypatch, a16, n=6)
        j.m30 = type("M30", (), {"get": lambda self, d: {"bars": []}})()
        j.watch_day = lambda mode, d: []
        j._pauses = []
        j.mode_off_at = lambda t: False
        j.check_wake_missed("canary", D)
        assert bool([f for f in j.F.items if f.code == "wake_missed"]) is missed, a16
