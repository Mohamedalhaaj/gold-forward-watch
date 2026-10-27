"""§16.18 A14 (2026-10-27), continuous watching, as the judge sees it. Written from the register text (R-AN-4, R-AN-5,
R-AN-8, R-AN-9, R-AN-11, R-AN-12, R-AN-23, R-AN-25, R-AN-33, R-AN-34, R-AN-36, R-AN-37, R-AN-39, R-AN-40, R-AN-47,
R-AN-53, R-AN-60, R-AN-66, R-AN-67 check A14, R-AN-68 and the new R-AN-89, R-AN-90; decisions A14-D1..D20) without
reading the analyst or its watcher: the new windows and ids, the check grid, the trigger rule, the gates, the `wake`
record, `analyst-context/4` paired with the pinned A14 build commit, the judge's own 30-minute fetch, and the A14
findings on a world that runs R-AN-89 day by day.
"""
import copy
import datetime as dt
import json

import pytest

from jlib import stats, td, ticks, watch
from jlib.clock import (Holidays, Window, check_grid, last_check, parse_call_id, scheduled_checks, tday,
                        trigger_valid, windows_between)
from jlib.common import VIOLATION, WARNING, fmt_utc, sha256_bytes
from jlib.context import KEY_ORDER_V3, KEY_ORDER_V4, SCHEMA_V4, sources_block
from jlib.judge import CALL_ID_RE, OPERATIONAL, TERMINAL_STATUSES, classify_path, operational
from world import PLAN_BUY, PLAN_SELL, PLAN_STAY, World

U = dt.timezone.utc


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def keys(res, check=None, severity=None, code=None, path=None):
    return [f.key for f in res.findings.items if (not check or f.check == check) and
            (not severity or f.severity == severity) and (not code or f.code == code) and
            (not path or f.path == path)]


# ---------------------------------------------------------------- R-AN-4, R-AN-8, R-AN-89: windows and checks (unit)

@pytest.mark.parametrize("day,w1b,w2b,last", [
    ("2026-10-23", ("09:00", "13:00"), ("15:30", "19:30"), "16:30"),
    ("2026-10-27", ("10:00", "14:00"), ("15:30", "19:30"), "16:30"),
    ("2026-11-03", ("10:00", "14:00"), ("16:30", "20:30"), "17:30"),
    ("2027-03-16", ("10:00", "14:00"), ("15:30", "19:30"), "16:30"),
    ("2027-04-06", ("09:00", "13:00"), ("15:30", "19:30"), "16:30"),
    ("2027-11-02", ("10:00", "14:00"), ("15:30", "19:30"), "16:30"),
    ("2027-11-09", ("10:00", "14:00"), ("16:30", "20:30"), "17:30"),
])
def test_second_looks_follow_the_register_table(day, w1b, w2b, last):
    d = dt.date.fromisoformat(day)
    for wid, (e, x) in (("W1b", w1b), ("W2b", w2b)):
        w = Window(d, wid)
        assert (w.entry.strftime("%H:%M"), w.exit.strftime("%H:%M")) == (e, x)
        assert w.entry == Window(d, wid[:2]).entry + dt.timedelta(minutes=120)
        assert w.deadline == w.entry - dt.timedelta(minutes=15) and w.span_lo == w.entry - dt.timedelta(minutes=30)
        assert w.check == w.span_lo and w.kind == "second_look" and w.w == wid
    assert Window(d, "W1b").exchange == "LSE" and Window(d, "W2b").exchange == "NYSE"
    assert last_check(d).strftime("%H:%M") == last
    g = check_grid(d)
    assert g[0] == dt.datetime(d.year, d.month, d.day, 22, 30, tzinfo=U) - dt.timedelta(days=1)
    assert g[-1] == last_check(d) and len(g) == (37 if last == "16:30" else 39)
    assert set(scheduled_checks(d)) <= set(g)
    w1 = Window(d, "W1")
    assert w1.span_lo == w1.entry - dt.timedelta(minutes=45) and w1.check == w1.entry - dt.timedelta(minutes=30)


def test_trigger_ids_times_and_validity():
    w = Window(dt.date(2026, 11, 3), "T2230")              # R-AN-4's example: the check at 2026-11-02 22:30Z
    assert w.check == T("2026-11-02T22:30:00Z") and w.entry == T("2026-11-02T23:00:00Z")
    assert w.exit == T("2026-11-03T03:00:00Z") and w.deadline == T("2026-11-02T22:45:00Z")
    assert w.span_lo == w.check and w.w == "T" and w.kind == "trigger" and w.exchange is None
    assert w.slot == 0 and tday(w.check) == dt.date(2026, 11, 3)
    assert w.call_id == "2026-11-03_T2230" and trigger_valid(w)
    assert Window(dt.date(2026, 11, 3), "T1530").slot == to_slot("2026-11-03T16:00:00Z")
    assert not trigger_valid(Window(dt.date(2026, 11, 3), "T0730"))        # W1's scheduled check
    assert not trigger_valid(Window(dt.date(2026, 11, 3), "T0930"))        # W1b's
    assert not trigger_valid(Window(dt.date(2026, 11, 3), "T2200"))        # before 22:30 of d - 1
    assert not trigger_valid(Window(dt.date(2026, 11, 3), "T1800"))        # after L_d (17:30 on EST)
    assert trigger_valid(Window(dt.date(2026, 11, 3), "T1730"))
    assert not trigger_valid(Window(dt.date(2026, 10, 27), "T1700"))       # after L_d (16:30 on EDT)
    for ok in ("2026-11-03_W1b", "2026-11-03_W2b", "2026-11-03_T0000", "2026-11-03_T2330"):
        assert parse_call_id(ok) is not None
    for bad in ("2026-11-03_W3", "2026-11-03_T0015", "2026-11-03_T2400", "2026-11-07_T1000", "2026-11-03_W1c"):
        assert parse_call_id(bad) is None
    assert classify_path("analyst/attempts/2026-11-03_T2330_1.json") == ("live", "attempt")
    assert classify_path("analyst/canary/calls/2026-11-03_W2b.json") == ("canary", "call")
    assert classify_path("analyst/calls/2026-11-03_T2345.json") is None
    assert "_(?:W[12]b?|T" in CALL_ID_RE


def to_slot(s):
    from jlib.clock import slot_of
    return slot_of(T(s))


def test_window_order_and_expected_kinds():
    ws = windows_between(dt.date(2026, 11, 2), dt.date(2026, 11, 3), dt.date(2026, 11, 3))
    assert [w.call_id for w in ws] == ["2026-11-02_W1", "2026-11-02_W2", "2026-11-03_W1", "2026-11-03_W1b",
                                       "2026-11-03_W2", "2026-11-03_W2b"]
    assert [w.call_id for w in windows_between(dt.date(2026, 11, 2), dt.date(2026, 11, 3))] == \
        ["2026-11-02_W1", "2026-11-02_W2", "2026-11-03_W1", "2026-11-03_W2"]
    t = Window(dt.date(2026, 11, 3), "T2230")
    assert t.order < Window(dt.date(2026, 11, 3), "W1").order < Window(dt.date(2026, 11, 3), "T0800").order


def test_holidays_by_kind():
    h = Holidays(None)
    lse_only = dt.date(2026, 12, 28)                # LSE full, NYSE open
    early = dt.date(2026, 11, 27)                   # NYSE early close
    assert h.window_holiday(Window(lse_only, "W1b")) and not h.window_holiday(Window(lse_only, "W2b"))
    assert h.window_holiday(Window(lse_only, "T1200"))                    # either exchange, full or early (A14-D7)
    assert h.window_holiday(Window(early, "T1200")) and h.window_holiday(Window(early, "W2b"))
    assert not h.window_holiday(Window(early, "W1b"))


def test_new_statuses_and_operational_keys():
    assert {"skipped:trade_open", "skipped:day_cap"} <= TERMINAL_STATUSES
    assert OPERATIONAL["A14"] == {"skipped_wrong", "a14_from"}
    assert operational("A14|skipped_wrong|analyst/terminal/x.json|c") and operational("A14|a14_from|analyst/MODE.json|c")
    for k in ("not_triggered", "trade_open", "day_cap", "wake_record"):
        assert not operational(f"A14|{k}|p|c")                           # integrity keys
    assert stats.WINDOW_TYPES == ("W1", "W2", "W1b", "W2b", "T")


# ---------------------------------------------------------------- R-AN-89: values, conditions, the rule (unit)

D = dt.date(2026, 11, 3)                  # a Tuesday on EST: Asia [22:00 d-1, 07:00 d), L_d 17:30


def _bar(t, o, h, low, c):
    return {"t_utc": t if isinstance(t, str) else fmt_utc(t), "o": o, "h": h, "l": low, "c": c}


def prior_bars(n_days=20, rng_of=lambda k: 10.0 + k):
    """n_days prior model weekdays before D, one bar each at 12:00 UTC: day k's range rng_of(k), centred on 4000."""
    out, d, k = [], D, 0
    days = []
    while len(days) < n_days:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            days.append(d)
    for k, e in enumerate(reversed(days)):
        r = rng_of(k)
        out.append(_bar(dt.datetime(e.year, e.month, e.day, 12, tzinfo=U), 4000.0, 4000 + r / 2, 4000 - r / 2, 4000.0))
    return out, list(reversed(days))


def test_values_r20_yesterday_and_asia():
    bars, days = prior_bars()                                 # ranges 10..29 → median of 20 = 19.5
    today = [_bar("2026-11-02T22:00:00Z", 4000, 4003, 3999, 4001), _bar("2026-11-03T06:30:00Z", 4001, 4005, 3990, 4002),
             _bar("2026-11-03T07:00:00Z", 4002, 4004, 4000, 4003), _bar("2026-11-03T07:30:00Z", 4003, 4010, 4002, 4009)]
    v = watch.values_at(bars + today, D, T("2026-11-03T08:00:00Z"))
    assert v["r20"] == 19.5 and v["y_day"] == "2026-11-02" and (v["y_h"], v["y_l"]) == (4000 + 29 / 2, 4000 - 29 / 2)
    assert (v["asia_h"], v["asia_l"]) == (4005, 3990)          # bars with t_utc < 07:00 of d
    assert v["c_t"] == 4009 and v["c_prev"] == 4002 and v["c_prev_utc"] == "2026-11-03T06:30:00Z"   # <= T - 90 min
    assert [b["t_utc"] for b in v["_today"]] == [b["t_utc"] for b in today]
    assert len(v["_r20_days"]) == 20 and v["_r20_days"][0]["day"] == days[0].isoformat() and v["_r20_days"][-1]["day"] == days[-1].isoformat()
    v7 = watch.values_at(bars + today, D, T("2026-11-03T07:30:00Z"))   # the 07:30 bar has not closed
    assert v7["c_t"] == 4003 and v7["c_prev"] == 4001 and v7["_bar_t"]["t_utc"] == "2026-11-03T07:00:00Z"
    v19 = watch.values_at(prior_bars(19)[0] + today, D, T("2026-11-03T08:00:00Z"))
    assert v19["r20"] is None and not any(watch.conditions(v19, D, T("2026-11-03T08:00:00Z")).values())


def _cond(today, t):
    bars, _ = prior_bars(rng_of=lambda k: 20.0)               # R20 = 20 exactly, yesterday h/l = 4010/3990
    v = watch.values_at(bars + today, D, T(t))
    return watch.conditions(v, D, T(t))


def test_conditions_strictness():
    asia = [_bar("2026-11-03T06:30:00Z", 4000, 4005, 3995, 4000)]
    # asia_up is strict: c_T == asia_h is false, above it true; never before 07:00 UTC
    eq = _cond(asia + [_bar("2026-11-03T07:00:00Z", 4000, 4005, 4000, 4005)], "2026-11-03T07:30:00Z")
    assert not eq["asia_up"]
    up = _cond(asia + [_bar("2026-11-03T07:00:00Z", 4000, 4005.5, 4000, 4005.5)], "2026-11-03T07:30:00Z")
    assert up["asia_up"] and not up["asia_dn"]
    early = _cond([_bar("2026-11-03T05:30:00Z", 4000, 4005, 3995, 4000),
                   _bar("2026-11-03T06:00:00Z", 4000, 4007, 4000, 4006)], "2026-11-03T06:30:00Z")
    assert not early["asia_up"]
    # y_high is >=: bar_T.h == y_h - 0.1 R20 (4008) counts; y_low likewise
    yh = _cond([_bar("2026-11-03T09:00:00Z", 4000, 4008, 3999, 4001)], "2026-11-03T09:30:00Z")
    assert yh["y_high"] and not yh["y_low"]
    assert not _cond([_bar("2026-11-03T09:00:00Z", 4000, 4007.99, 3999, 4001)], "2026-11-03T09:30:00Z")["y_high"]
    assert _cond([_bar("2026-11-03T09:00:00Z", 4000, 4001, 3992, 4000)], "2026-11-03T09:30:00Z")["y_low"]
    # move: |c_T - c_prev| >= 0.3 R20 = 6, c_prev the latest bar of d closing at or before T - 60 min
    mv = [_bar("2026-11-03T09:00:00Z", 4000, 4001, 3999, 4000), _bar("2026-11-03T09:30:00Z", 4000, 4003, 3999, 4003),
          _bar("2026-11-03T10:00:00Z", 4003, 4006, 4003, 4006)]
    assert _cond(mv, "2026-11-03T10:30:00Z")["move"]                       # 4006 - 4000 == 6
    mv[-1]["c"] = 4005.99
    assert not _cond(mv, "2026-11-03T10:30:00Z")["move"]
    assert not _cond(mv[2:], "2026-11-03T10:30:00Z")["move"]               # no c_prev
    assert not any(_cond(mv[:2], "2026-11-03T10:30:00Z").values())         # no bar closing at T


def test_rule_order_gap_consumption_and_cap():
    t = T("2026-11-03T11:00:00Z")
    allc = dict.fromkeys(watch.CONDITIONS, True)
    assert watch.rule(D, t, [], 0, False, allc) == ("window", "T1100", "trigger", "asia_up")
    assert watch.rule(D, t, [], 1, False, allc)[0] == "trade_open"
    six = [(t - dt.timedelta(hours=k + 1), "trigger", None) for k in range(6)]
    assert watch.rule(D, t, six, 0, False, allc)[0] == "day_cap"
    assert watch.rule(D, t, [], 0, True, allc)[0] == "none"                 # a holiday-table day
    near = [(t - dt.timedelta(minutes=30), "fixed", None)]
    assert watch.rule(D, t, near, 0, False, allc)[0] == "none"              # g(T) < 60
    used = [(t - dt.timedelta(minutes=60), "trigger", "asia_up"), (t - dt.timedelta(minutes=90), "trigger", "asia_dn")]
    assert watch.rule(D, t, used, 0, False, allc) == ("window", "T1100", "trigger", "y_high")
    only_move = dict.fromkeys(watch.CONDITIONS, False, ) | {"move": True}
    assert watch.rule(D, t, [(t - dt.timedelta(minutes=60), "fixed", None)], 0, False, only_move)[0] == "none"
    assert watch.rule(D, t, [(t - dt.timedelta(minutes=120), "fixed", None)], 0, False, only_move)[3] == "move"
    sched = T("2026-11-03T09:30:00Z")                                      # W1b's check: scheduled, holiday or not
    assert watch.rule(D, sched, near, 0, True, allc) == ("window", "W1b", "second_look", None)
    assert watch.rule(D, T("2026-11-03T07:30:00Z"), [], 0, False, None) == ("window", "W1", "fixed", None)
    assert watch.rule(D, sched, [], 1, False, None)[0] == "trade_open"     # the gates come first
    assert watch.rule(D, T("2026-11-03T18:00:00Z"), [], 0, False, allc)[0] == "outside"


# ---------------------------------------------------------------- R-AN-90: the wake record (unit)

def _m30_prov(win, bars, **kw):
    f = {"src": "td", "req": "XAUUSD_M30", "url": watch.m30_url(win.day, win.check), "http": 200, "td_code": 200,
         "status": "ok", "reason": None, "bytes": 5000, "sha256": "a" * 64, "values_n": len(bars), "bars": bars,
         "fetched_utc": fmt_utc(win.check + dt.timedelta(seconds=131)), "tries": 1}
    f.update(kw)
    return f


def test_m30_url_is_the_register_form():
    assert watch.m30_url(D, T("2026-11-03T11:00:00Z")) == (
        "https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=30min&start_date=2026-10-01T22:00:00"
        "&end_date=2026-11-03T11:00:00&timezone=UTC&order=asc&outputsize=5000&dp=5")


def test_wake_problems():
    win = Window(D, "T1100")
    bars = [_bar("2026-11-03T10:00:00Z", 4000, 4001, 3999, 4000), _bar("2026-11-03T10:30:00Z", 4000, 4002, 3999, 4001)]
    good = {"wake": {"kind": "trigger", "reason": "move", "check_utc": "2026-11-03T11:00:00Z",
                     "td": _m30_prov(win, bars)}}
    assert watch.wake_problems(good, win) == []
    assert watch.wake_problems(json.loads(json.dumps(good, sort_keys=True)), win) == []      # key-sorted records
    late = copy.deepcopy(good)
    late["wake"]["td"]["bars"].append(_bar("2026-11-03T11:00:00Z", 4001, 4002, 4000, 4001))  # not closed at T
    late["wake"]["td"]["values_n"] = 3
    assert "td.bars.range" in watch.wake_problems(late, win)
    short = copy.deepcopy(good)
    short["wake"]["td"]["values_n"] = 4                                    # an element left out
    assert watch.wake_problems(short, win) == ["td.bars.elements"]
    plus1 = copy.deepcopy(good)
    plus1["wake"]["td"]["values_n"] = 3                                    # the element at T itself (end_date)
    assert watch.wake_problems(plus1, win) == []
    url = copy.deepcopy(good)
    url["wake"]["td"]["url"] = watch.m30_url(D, win.check + dt.timedelta(minutes=30))
    assert watch.wake_problems(url, win) == ["td.url"]
    assert watch.wake_problems({"wake": dict(good["wake"], reason="trend")}, win) == ["wake.reason"]
    assert watch.wake_problems({"wake": dict(good["wake"], check_utc="2026-11-03T10:30:00Z")}, win) == \
        ["wake.check_utc"]
    w1b = Window(D, "W1b")
    fixed = {"wake": {"kind": "second_look", "reason": None, "check_utc": "2026-11-03T09:30:00Z", "td": None}}
    assert watch.wake_problems(fixed, w1b) == []
    assert watch.wake_problems({"wake": dict(fixed["wake"], kind="fixed")}, w1b) == ["wake.kind"]
    assert watch.wake_problems({"wake": dict(fixed["wake"], reason="move")}, w1b) == ["wake.reason"]
    assert watch.wake_problems({"wake": dict(fixed["wake"], td=good["wake"]["td"])}, w1b) == ["wake.td"]
    assert watch.wake_problems({"wake": None}, w1b) == ["wake.keys"]
    err = _m30_prov(win, [], status="error", reason="credits", http=429, td_code=429, values_n=0, bytes=80)
    assert watch.wake_problems({"wake": dict(good["wake"], td=err)}, win) == []      # a provenance, not ok
    bad_err = dict(err, reason="server")
    assert watch.wake_problems({"wake": dict(good["wake"], td=bad_err)}, win) == ["td.reason"]


def test_context_4_shape():
    assert KEY_ORDER_V4.index("wake") == KEY_ORDER_V4.index("levels") + 1
    assert [k for k in KEY_ORDER_V4 if k != "wake"] == list(KEY_ORDER_V3)
    n = sources_block(SCHEMA_V4)["note"]
    assert n == td.SOURCES_V3["note"] + " wake values and wake.bars_m30 come from Twelve Data 30-minute bars in UTC, " \
                                        "labelled by their start."
    win = Window(D, "W2")
    blk = watch.wake_block({"kind": "fixed", "reason": None, "check_utc": "2026-11-03T14:00:00Z", "td": None}, win)
    assert blk == {"kind": "fixed", "reason": None, "check_utc": "2026-11-03T14:00:00Z", "values": None,
                   "r20_days": None, "bars_m30": None}
    tw = Window(D, "T1100")
    bars, _ = prior_bars()
    bars += [_bar("2026-11-03T10:00:00Z", 4000, 4001, 3999, 4000), _bar("2026-11-03T10:30:00Z", 4000, 4002, 3999, 4001)]
    blk = watch.wake_block({"kind": "trigger", "reason": "move", "check_utc": "2026-11-03T11:00:00Z",
                            "td": _m30_prov(tw, bars)}, tw)
    assert set(blk["values"]) == set(watch.VALUE_KEYS) and blk["values"]["r20"] == 19.5
    assert len(blk["r20_days"]) == 20 and [b["t_utc"] for b in blk["bars_m30"]] == \
        ["2026-11-03T10:00:00Z", "2026-11-03T10:30:00Z"]
    rec = copy.deepcopy(blk)
    assert watch.compare_wake(blk, rec) == []
    rec["values"]["r20"] = 19.5 * (1 + 1e-12)
    assert watch.compare_wake(blk, rec) == []                              # r20: relative 1e-9
    rec["values"]["c_t"] = 4001.0001
    rec["bars_m30"][0]["c"] = 4000.5
    assert watch.compare_wake(blk, rec) == ["wake.bars_m30", "wake.values.c_t"]


# ---------------------------------------------------------------- R-AN-66: the judge's own fetch (unit)

def _body(values, status="ok"):
    return json.dumps({"meta": {}, "values": values, "status": status}).encode()


def _el(t, o="4000.1", h="4001.0", low="3999.5", c="4000.5"):
    return {"datetime": t, "open": o, "high": h, "low": low, "close": c}


def test_classify_m30():
    st, reason, code, bars, n = watch.classify_m30(200, _body([_el("2026-11-03 10:00:00"), _el("2026-11-03 10:30:00")]))
    assert (st, reason, code, n) == ("ok", None, 200, 2)
    assert bars[0] == {"t_utc": "2026-11-03T10:00:00Z", "o": 4000.1, "h": 4001.0, "l": 3999.5, "c": 4000.5}
    assert watch.classify_m30(200, _body([_el("2026-11-03 10:15:00")]))[:3] == ("error", "invalid", 200)
    assert watch.classify_m30(200, _body([_el("2026-11-03 10:00:00")] * 2))[:2] == ("error", "invalid")
    assert watch.classify_m30(200, _body([_el("2026-11-03 10:00:00", low="4000.2")]))[:2] == ("error", "invalid")
    assert watch.classify_m30(200, _body([_el("2026-11-03 10:00:00", o="4e3")]))[:2] == ("error", "invalid")
    err = json.dumps({"code": 429, "message": "x", "status": "error"}).encode()
    assert watch.classify_m30(200, err)[:3] == ("error", "credits", 429)
    assert watch.classify_m30(0, None)[:3] == ("error", "server", 0)
    assert watch.classify_m30(200, b"x" * (td.MAX_BODY + 1))[:2] == ("error", "invalid")
    assert watch.classify_m30(200, _body([]))[0] == "ok"


def test_m30_source_transport_and_store(tmp_path):
    d = D
    end = T("2026-11-03T22:00:00Z")
    url = watch.m30_url(d, end)
    good = _body([_el("2026-11-03 10:00:00")])
    sleeps = []

    class Seq:
        available = True

        def __init__(self, answers):
            self.answers, self.calls = list(answers), []

        def get(self, u):
            self.calls.append(u)
            return self.answers.pop(0)

    f = Seq([(503, b""), (200, good)])                       # the second try only after 0 or 5xx
    src = watch.M30Source(f, str(tmp_path / "m30"), sleep=sleeps.append, clock=lambda: T("2026-11-04T01:00:00Z"))
    rec, ev = src.fetch(d, end)
    assert rec["status"] == "ok" and rec["tries"] == 2 and f.calls == [url, url] and sleeps == [8.0]
    assert ev == {"ref": "2026-11-03", "push_after": rec["sha256"], "activity_type": "ok",
                  "activity_utc": "2026-11-04T01:00:00Z", "run_id": 1}
    src.flush()
    again = watch.M30Source(Seq([]), str(tmp_path / "m30"))
    assert again.get(d)["bars"] == rec["bars"]                # kept, never fetched again
    f2 = Seq([(429, json.dumps({"code": 429, "status": "error"}).encode())])
    rec2, ev2 = watch.M30Source(f2, None, sleep=sleeps.append).fetch(d, end)
    assert rec2 is None and ev2["activity_type"] == "td_credits" and len(f2.calls) == 1   # never after 429
    assert "apikey" not in url and "Authorization" not in json.dumps(ev)


def test_m30_compare():
    lo, hi = T("2026-10-01T22:00:00Z"), T("2026-11-03T10:30:00Z")
    rec = [_bar("2026-11-03T10:00:00Z", 4000, 4001, 3999, 4000.5), _bar("2026-11-03T10:30:00Z", 4000, 4002, 3999, 4001)]
    own = copy.deepcopy(rec) + [_bar("2026-11-03T11:00:00Z", 4001, 4003, 4000, 4002)]   # after T - 30: not compared
    assert watch.m30_compare(rec, own, lo, hi) == []
    own[0]["h"] = 4001 * 1.0011
    assert watch.m30_compare(rec, own, lo, hi) == [f"2026-11-03T10:00:00Z h rec=4001 own={4001 * 1.0011!r}"]
    assert watch.m30_compare(rec[:1], own[:2], lo, hi)[-1] == "2026-11-03T10:30:00Z only_judge"
    assert watch.m30_compare(rec, [own[1]], lo, hi)[0] == "2026-11-03T10:00:00Z only_recorded"


def test_half_hour_ticks():
    from world import _TICK, lzma_alone
    raw = _TICK.pack(1000, 4_000_200, 4_000_000, 1, 1) + _TICK.pack(1_799_999, 4_000_400, 4_000_200, 1, 1) + \
        _TICK.pack(1_800_000, 4_000_600, 4_000_400, 1, 1)
    st, s = ticks.classify_halves(200, lzma_alone(raw))
    assert st == "present" and (s["lo_first_ask"], s["lo_last_ask"], s["hi_first_ask"], s["hi_last_ask"]) == \
        (4_000_200, 4_000_400, 4_000_600, 4_000_600)
    st, s = ticks.classify_halves(200, lzma_alone(_TICK.pack(10, 4_000_200, 4_000_000, 1, 1)))
    assert s["hi_first_ask"] is None and s["lo_first_bid"] == 4_000_000


# ---------------------------------------------------------------- the world: R-AN-89 day by day from a14_from

A14_WORLD = dict(canary_days=(), live_from="2026-11-30", live_to="2026-12-04", now="2026-12-05T12:00:00Z",
                 store_first="2026-10-19", a12_from="2026-11-30", a14_from="2026-12-02")
PLANS = {"2026-11-30_W1": ("call", PLAN_STAY), "2026-11-30_W2": ("call", PLAN_BUY),
         "2026-12-01_W1": ("call", PLAN_STAY), "2026-12-01_W2": ("call", PLAN_SELL),
         "2026-12-02_W1": ("call", PLAN_STAY), "2026-12-02_W1b": ("call", PLAN_STAY),
         "2026-12-02_W2": ("call", PLAN_BUY), "2026-12-03_W1": ("call", PLAN_BUY),
         "2026-12-03_W2": ("call", PLAN_STAY), "2026-12-03_W2b": ("call", PLAN_SELL)}


def a14_world(root, hooks=None):
    return World(root, plans=dict(PLANS), hooks=hooks or {}, **A14_WORLD).build()


@pytest.fixture(scope="module")
def a14(tmp_path_factory):
    return a14_world(str(tmp_path_factory.mktemp("a14") / "w"))


def term(w, cid):
    return w.terminals[("live", cid)]


def test_a14_world_runs_the_rule(a14):
    trig = [x.call_id for x in a14.trigger_wins]
    assert len(trig) >= 4 and all(trigger_valid(x) for x in a14.trigger_wins)
    reasons = {a14.wakes[("live", c)]["reason"] for c in trig}
    assert reasons <= set(watch.CONDITIONS) and len(reasons) >= 2
    sts = {cid: t["status"] for (_m, cid), t in a14.terminals.items()}
    assert "skipped:trade_open" in sts.values()
    assert all(f"2026-12-0{k}_{w}" in sts for k in (2, 3, 4) for w in ("W1", "W1b", "W2", "W2b"))
    assert "2026-12-01_W1b" not in sts                          # before a14_from: W1 and W2 only
    ctx = a14.context_of(trig[0])
    assert ctx["schema"] == SCHEMA_V4 and ctx["window"] == "T" and ctx["wake"]["kind"] == "trigger"
    assert set(ctx["wake"]["values"]) == set(watch.VALUE_KEYS) and len(ctx["wake"]["r20_days"]) == 20
    assert ctx["store"]["slots_sha256"] == sha256_bytes(a14.src_forecasts)        # mirror/system/forecasts.csv
    assert a14.context_of("2026-12-01_W2")["schema"] == SCHEMA_V4             # after the A14 build commit
    assert a14.context_of("2026-12-01_W2")["wake"]["kind"] == "fixed"
    assert a14.context_of("2026-11-30_W2")["schema"] == "analyst-context/3"


def test_a14_world_is_sound(a14):
    res = a14.judge()
    assert keys(res) == []
    assert res.summary["contexts_rebuilt"] == len(a14.calls)
    assert res.summary["m30_compared"] == len(a14.trigger_wins)
    assert res.summary["td_compared"] > 0 and res.summary.get("td_outside", 0) == 0
    ev = [r for r in res.evidence_new if r["source"] == "td_m30"]
    assert sorted(r["ref"] for r in ev) == ["2026-12-02", "2026-12-03", "2026-12-04"]
    assert all(r["activity_type"] == "ok" and len(r["push_after"]) == 64 for r in ev)


def test_A4_and_A0_unpinned_a14(a14):
    res = a14.judge(a14_commit=None)
    v4 = sorted(c for (_m, c) in a14.calls if a14.context_of(c)["schema"] == SCHEMA_V4)
    assert sorted(k.split("|")[2] for k in keys(res, "A4", VIOLATION, "context_schema")) == \
        [f"analyst/calls/{c}.json" for c in v4]
    assert keys(res, "A0", WARNING, "a14_unpinned") == ["A0|a14_unpinned|judge_analyst/jlib/config.py|-"]


def test_A14_wake_missed_and_m30_mismatch_from_the_judges_fetch(a14):
    """The judge's own bars differ: a due wake the watcher did not fire (WARNING `wake_missed`) and recorded bars
    beyond 1e-3 of the judge's (WARNING `m30_mismatch`)."""
    first = a14.trigger_wins[0]
    t_bar = fmt_utc(first.check - dt.timedelta(minutes=30))

    def edit(d, bars):
        if d == first.day:
            for b in bars:
                if b["t_utc"] == t_bar:
                    b["h"] = round(b["h"] * 1.002, 5)
        return bars
    src = watch.M30Source(watch.FakeM30Fetcher(a14.m30_responses(edit)), None, max_fetch=50, sleep=lambda _s: None)
    res = a14.judge(m30=src)
    ks = keys(res, "A14", WARNING, "m30_mismatch")
    assert f"A14|m30_mismatch|analyst/attempts/{first.call_id}_1.json|" in ks[0] if ks else False
    assert not keys(res, severity=VIOLATION)

    # a check with no window: the judge's bars give a move there (and nothing else differs)
    d = a14.trigger_wins[-1].day
    wins = [w for w in a14.world_windows() if w.day == d]
    have = {w.check for w in wins}
    cands = [t for t in check_grid(d) if t not in have and t not in scheduled_checks(d)]
    hit = None
    for t in cands:
        def edit2(dd, bars, t=t):
            if dd == d:
                for b in bars:
                    if b["t_utc"] == fmt_utc(t - dt.timedelta(minutes=30)):
                        b["c"] = b["h"] = round(b["c"] + 500.0, 5)
            return bars
        src = watch.M30Source(watch.FakeM30Fetcher(a14.m30_responses(edit2)), None, max_fetch=50,
                              sleep=lambda _s: None)
        res = a14.judge(m30=src)
        wm = keys(res, "A14", WARNING, "wake_missed")
        if wm:
            hit = (t, wm)
            break
    assert hit is not None
    t, wm = hit
    assert f"A14|wake_missed|{d.isoformat()}|T{t.hour:02d}{t.minute:02d}" in wm


def test_A14_m30_unchecked_and_failed_fetch(a14):
    src = watch.M30Source(watch.FakeM30Fetcher({}), None, max_fetch=50, sleep=lambda _s: None)
    res = a14.judge(m30=src)
    ev = [r for r in res.evidence_new if r["source"] == "td_m30"]
    assert ev and all(r["activity_type"] == "td_server" for r in ev)
    assert not keys(res, "A14", code="m30_unchecked")             # at most 3 weekdays old
    res = a14.judge(m30=None, now="2026-12-09T12:00:00Z")
    assert "A14|m30_unchecked|2026-12-02|-" in keys(res, "A14", WARNING, "m30_unchecked")


def test_A14_a14_from_changed_and_pushes_before_it(a14, tmp_path):
    w = a14.clone(str(tmp_path / "c"))
    import os
    m = json.loads(open(os.path.join(w.repo.path, "analyst/MODE.json"), encoding="utf-8").read())
    m["a14_from"] = "2026-12-03"
    from jlib.common import record_form
    sha = w.owner_commit({"analyst/MODE.json": record_form(m)}, T("2026-12-05T09:00:00Z"), "owner: a14_from moved")
    res = w.judge()
    ks = keys(res, "A14", VIOLATION, "a14_from")
    assert f"A14|a14_from|analyst/MODE.json|{sha}" in ks                     # a change after it was set
    pushed = [k for k in ks if k.split("|")[3] != sha]
    assert pushed                                                          # the 12-02 W1b, W2b and trigger pushes


# ---------------------------------------------------------------- the world with faults, each on its own record

def _bad_hooks():
    def wake(world, win, n, wk):
        if win.call_id == "2026-12-02_W1b":
            wk["check_utc"] = "2026-12-02T09:00:00Z"                         # not from its call_id
        if win.call_id == "2026-12-02_T0430" and wk["reason"] == "move":
            wk["reason"] = "y_low"                                           # not what R(T) gives

    def terminal(world, t):
        if t["call_id"] == "2026-12-02_W2b" and t["status"] == "skipped:trade_open":
            t["status"], t["detail"] = "missed:trigger", None                # while the gate holds

    def watcher_config(world, wc):
        wc["deployed_utc"] = "2026-12-01T22:30:00Z"                          # after 22:00Z of the day before
    return {"wake": wake, "terminal": terminal, "watcher_config": watcher_config,
            "force": {"2026-12-03_W1b"}, "drop_trigger": {"2026-12-04_T0030"}}


@pytest.fixture(scope="module")
def a14_bad(tmp_path_factory):
    return a14_world(str(tmp_path_factory.mktemp("a14bad") / "w"), hooks=_bad_hooks())


def test_A14_faults(a14_bad):
    w = a14_bad
    assert term(w, "2026-12-03_W1").get("status") == "called" and "2026-12-02_T0430" in \
        [x.call_id for x in w.trigger_wins]
    res = w.judge()
    a14v = sorted(keys(res, "A14", VIOLATION))
    assert [k.rsplit("|", 1)[0] for k in a14v] == sorted([
        "A14|a14_from|analyst/MODE.json",
        "A14|not_triggered|analyst/attempts/2026-12-02_T0430_1.json",
        "A14|skipped_wrong|analyst/terminal/2026-12-02_W2b.json",
        "A14|trade_open|analyst/attempts/2026-12-03_W1b_1.json",
        "A14|wake_record|analyst/attempts/2026-12-02_W1b_1.json"])
    assert "A14|wake_missed|2026-12-04|T0030" in keys(res, "A14", WARNING, "wake_missed")
    others = [k for k in keys(res, severity=VIOLATION) if not k.startswith("A14|")]
    assert others == []
