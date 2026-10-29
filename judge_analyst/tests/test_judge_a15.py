"""§16.18 A15 (2026-10-29), trade management and learning in the canary, as the judge sees it. Written from the register
text (R-AN-5, R-AN-11, R-AN-22, R-AN-23, R-AN-26..R-AN-29, R-AN-33, R-AN-36, R-AN-39, R-AN-40, R-AN-42, R-AN-45..R-AN-56,
R-AN-58, R-AN-66..R-AN-68, R-AN-71, R-AN-89..R-AN-91 as marked, and the new R-AN-92..R-AN-95; decisions A15-D1..D21)
without reading the analyst or its watcher: the open set, the options and the `review` block, the managed exits,
x_end, the overlap weights and clusters, the weighted statistics, `analyst-plan/3`, `analyst-context/5` paired with
A15_BUILD_COMMIT, and the check A15 findings on a world whose days from a15_from run reviews in both modes.
"""
import copy
import datetime as dt
import json
import os

import pytest

from jlib import config, derive, review, settle, stats
from jlib.clock import Window
from jlib.common import VIOLATION, WARNING, fmt_utc, record_form
from jlib.context import KEY_ORDER_V4, KEY_ORDER_V5, SCHEMA_V4, SCHEMA_V5, context_keys, sources_block
from jlib.judge import CALL_STATUSES, OPERATIONAL, TERMINAL_STATUSES, operational
from jlib.m1 import Store

U = dt.timezone.utc


def T(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def keys(res, check=None, severity=None, code=None, path=None):
    return [f.key for f in res.findings.items if (not check or f.check == check) and
            (not severity or f.severity == severity) and (not code or f.code == code) and
            (not path or f.path == path)]


# ---------------------------------------------------------------- statuses, keys, pins (unit)

def test_statuses_keys_and_pin():
    assert {"review_hold", "review_close"} <= TERMINAL_STATUSES and {"review_hold", "review_close"} <= CALL_STATUSES
    assert OPERATIONAL["A15"] == {"review_open", "open_cap", "a15_from", "lesson_source"}
    for k in ("review_open", "open_cap", "a15_from", "lesson_source"):
        assert operational(f"A15|{k}|p|c")
    assert config.A15_BUILD_COMMIT is None or (isinstance(config.A15_BUILD_COMMIT, str) and len(config.A15_BUILD_COMMIT) == 40)  # pinned at the build
    assert KEY_ORDER_V5 == KEY_ORDER_V4[:KEY_ORDER_V4.index("wake") + 1] + ("review",) + \
        KEY_ORDER_V4[KEY_ORDER_V4.index("wake") + 1:]
    assert context_keys(SCHEMA_V5) == KEY_ORDER_V5
    assert sources_block(SCHEMA_V5)["note"] == sources_block(SCHEMA_V4)["note"] + (
        " review prices come from Twelve Data 30-minute bars in UTC and are indicative; settlement uses Dukascopy "
        "minutes, where an open trade may already have reached its stop or target.")
    assert review.M30R_REQ == "XAUUSD_M30R"


def test_options():
    assert review.options(0) is None
    assert review.options(1) == ["hold", "close", "reverse", "add"]
    assert review.options(2) == ["hold", "close"]


# ---------------------------------------------------------------- R-AN-26: analyst-plan/3 (unit)

HOLD = {"action": "hold", "confidence": "low", "reason_ar": "انتظار", "key_risks_ar": ""}
CLOSE = dict(HOLD, action="close")
ADD = {"action": "add", "stop_mult": 1.0, "target_mult": 2.0, "confidence": "medium", "reason_ar": "زيادة",
       "key_risks_ar": ""}
REVERSE = dict(ADD, action="reverse")


def test_plan_v3_actions_and_keys():
    for p in (HOLD, CLOSE, ADD, REVERSE):
        assert derive.plan_errors(p, v3=True, v5=True) == []
        assert derive.plan_errors(p, v3=True) == ["action"]                    # analyst-plan/2 has no such action
    assert derive.plan_errors(dict(HOLD, stay_out_reason="no_setup"), v3=True, v5=True) == ["keys"]
    assert derive.plan_errors(dict(HOLD, stop_mult=1.0), v3=True, v5=True) == ["keys"]
    bad = dict(ADD)
    del bad["target_mult"]
    assert "keys" in derive.plan_errors(bad, v3=True, v5=True)
    assert derive.plan_errors(dict(ADD, stop_mult=2.5), v3=True, v5=True) == ["stop_mult"]
    stay = {"action": "stay_out", "stay_out_reason": "no_setup", "confidence": "low", "reason_ar": "x",
            "key_risks_ar": ""}
    assert derive.plan_errors(stay, v3=True, v5=True) == []
    assert derive.status_of_action("reverse") == "called" and derive.status_of_action("add") == "called"
    assert derive.status_of_action("hold") == "review_hold" and derive.status_of_action("close") == "review_close"
    assert derive.status_of_action("stay_out") == "stay_out" and derive.status_of_action("buy") == "called"


# ---------------------------------------------------------------- R-AN-92: the open set (unit)

def W(cid, entry, status, action=None, names=None, hours=4):
    e = T(f"2026-12-02T{entry}:00Z")
    return {"cid": cid, "entry": e, "exit": e + dt.timedelta(hours=hours), "status": status, "action": action,
            "names": names}


def test_open_set_add_then_close_both():
    wins = [W("W1", "08:00", "called", "buy"), W("W1b", "10:00", "called", "add", ["W1"]),
            W("T1030", "11:00", "review_close", "close", ["W1", "W1b"]), W("T1130", "12:00", "stay_out", "stay_out")]
    r = review.open_sets(wins)
    assert r.open == {"W1": [], "W1b": ["W1"], "T1030": ["W1", "W1b"], "T1130": []}
    assert r.closed_by == {"W1": "T1030", "W1b": "T1030"}
    assert r.eff_exit["W1"] == r.eff_exit["W1b"] == T("2026-12-02T11:00:00Z")


def test_open_set_reverse_hold_and_no_decision():
    wins = [W("W1", "08:00", "called", "buy"), W("W1b", "10:00", "called", "reverse", ["W1"]),
            W("T1030", "11:00", "no_call:invalid"), W("T1100", "11:30", "missed:trigger"),
            W("T1130", "12:00", "review_hold", "hold", ["W1b"]), W("W2", "14:00", "stay_out", "stay_out")]
    r = review.open_sets(wins)
    assert r.open["W1b"] == ["W1"] and r.open["T1030"] == ["W1b"] and r.open["T1100"] == ["W1b"]
    assert r.open["T1130"] == ["W1b"]
    assert r.open["W2"] == []                         # entry 14:00 equals W1b's exit: not a review (A14-D4)
    assert r.closed_by == {"W1": "W1b"} and r.eff_exit["W1b"] == T("2026-12-02T14:00:00Z")


def test_open_set_late_lock_and_unshown_trade():
    # a late lock (no_call:late) opens no trade; a close never closes a trade its context did not name
    wins = [W("W1", "08:00", "called", "buy"), W("T0830", "09:00", "no_call:late", "add", ["W1"]),
            W("T0930", "10:00", "called", "add", ["W1"]), W("T1000", "10:30", "review_close", "close", ["W1"])]
    r = review.open_sets(wins)
    assert r.open["T0930"] == ["W1"] and r.open["T1000"] == ["W1", "T0930"]
    assert r.closed_by == {"W1": "T1000"}
    assert r.eff_exit["T0930"] == T("2026-12-02T14:00:00Z")


def test_open_set_three_open_when_a_review_breaks_its_options():
    wins = [W("W1", "08:00", "called", "buy"), W("T0830", "09:00", "called", "add", ["W1"]),
            W("T0930", "10:00", "called", "buy"), W("T1030", "11:00", "review_hold", "hold")]
    r = review.open_sets(wins)
    assert len(r.open["T1030"]) == 3 and review.max_open(r) == 3


# ---------------------------------------------------------------- R-AN-92: the `review` block (unit)

def bar(t, o, h, low, c):
    return {"t_utc": f"2026-12-02T{t}:00Z", "o": o, "h": h, "l": low, "c": c}


BARS = [bar("10:00", 4000.0, 4003.0, 3998.0, 4002.0), bar("10:30", 4002.0, 4006.0, 4001.0, 4005.5),
        bar("11:00", 4005.5, 4012.0, 4004.0, 4009.25)]


def trade(cid, action, side, entry, S, Tt, sm=1.0, tm=2.0):
    e = T(f"2026-12-02T{entry}:00Z")
    return {"call_id": cid, "action": action, "side": side, "entry_utc": fmt_utc(e),
            "exit_utc": fmt_utc(e + dt.timedelta(hours=4)), "S": S, "T": Tt, "stop_mult": sm, "target_mult": tm}


def test_review_block_values():
    tr = [trade("2026-12-02_W1", "buy", 1, "10:00", 5.0, 10.0),
          trade("2026-12-02_T1030", "add", -1, "11:00", 4.0, 6.0, 1.5, 1.5),
          trade("2026-12-02_T1100", "sell", -1, "11:30", 4.0, 6.0)]
    b = review.review_block(tr[:2], T("2026-12-02T12:00:00Z"), BARS)
    assert b["options"] == ["hold", "close"] and b["ref_px"] == 4009.25 and b["ref_utc"] == "2026-12-02T11:30:00Z"
    o1, o2 = b["open"]
    assert list(o1) == list(review.OPEN_KEYS)
    assert o1 == {"call_id": "2026-12-02_W1", "action": "buy", "side": "buy", "entry_utc": "2026-12-02T10:00:00Z",
                  "exit_utc": "2026-12-02T14:00:00Z", "stop_usd": 5.0, "target_usd": 10.0, "stop_mult": 1.0,
                  "target_mult": 2.0, "entry_px": 4000.0, "move_usd": 9.25, "move_r": 1.85,
                  "high_since_entry": 4012.0, "low_since_entry": 3998.0, "stop_touched": False,
                  "target_touched": True, "minutes_left": 120}
    assert o2["side"] == "sell" and o2["entry_px"] == 4005.5 and o2["move_usd"] == -3.75
    assert o2["move_r"] == -0.9375 and (o2["high_since_entry"], o2["low_since_entry"]) == (4012.0, 4004.0)
    assert (o2["stop_touched"], o2["target_touched"], o2["minutes_left"]) == (True, False, 180)
    # an entry bar not closed by asof: no entry_px, no move, no extremes, no touches
    b = review.review_block(tr[2:], T("2026-12-02T12:00:00Z"), BARS)
    o = b["open"][0]
    assert b["options"] == ["hold", "close", "reverse", "add"]
    assert all(o[k] is None for k in ("entry_px", "move_usd", "move_r", "high_since_entry", "low_since_entry",
                                      "stop_touched", "target_touched"))
    # no request (or not ok): M empty, every price null
    b = review.review_block(tr[:1], T("2026-12-02T12:00:00Z"), [])
    assert b["ref_px"] is None and b["ref_utc"] is None and b["open"][0]["entry_px"] is None
    assert review.review_block([], T("2026-12-02T12:00:00Z"), BARS) is None


def test_m30r_request_rule():
    tr = [trade("2026-12-02_W1", "buy", 1, "10:00", 5.0, 10.0)]
    asof = T("2026-12-02T11:40:00Z")
    assert review.m30r_needed(tr, asof) and not review.m30r_needed(tr, T("2026-12-02T10:29:59Z"))
    assert not review.m30r_needed([], asof)
    assert review.m30r_bounds(tr, asof) == (T("2026-12-02T10:00:00Z"), T("2026-12-02T11:30:00Z"))
    url = review.m30r_url(T("2026-12-02T10:00:00Z"), T("2026-12-02T11:30:00Z"))
    assert url == ("https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=30min&start_date=2026-12-02T"
                   "10:00:00&end_date=2026-12-02T11:30:00&timezone=UTC&order=asc&outputsize=5000&dp=5")


def test_compare_review_tolerances():
    tr = [trade("2026-12-02_W1", "buy", 1, "10:00", 5.0, 10.0)]
    e = review.review_block(tr, T("2026-12-02T12:00:00Z"), BARS)
    r = copy.deepcopy(e)
    r["open"][0]["move_r"] = e["open"][0]["move_r"] * (1 + 1e-12)
    assert review.compare_review(e, r) == []
    r["open"][0]["entry_px"] = 4000.0000001                          # prices exact
    r["open"][0]["stop_touched"] = None
    assert review.compare_review(e, r) == ["review.open[0].entry_px", "review.open[0].stop_touched"]
    assert review.compare_review(None, None) == [] and review.compare_review(e, None) == ["review"]


# ---------------------------------------------------------------- R-AN-93: managed exits and x_end (unit)

WIN = Window(dt.date(2026, 12, 2), "W1")         # EST: entry 08:00Z, exit 12:00Z
T0 = int(WIN.entry.timestamp())
T1 = int(WIN.exit.timestamp())
M = T0 + 120 * 60                                 # a review at 10:00Z closes it


def store_of(bid_of, gap=()):
    """A store whose ASK opens the trade at 4000.000 and whose BID per minute is bid_of(k) (o, h, l, c points)."""
    st = Store.__new__(Store)
    st.side_rows = {"BID": {}, "ASK": {}}
    for k in range(0, 241):
        t = T0 + 60 * k
        b = bid_of(k)
        if k not in gap:
            st.side_rows["BID"][t] = b + (1,)
        st.side_rows["ASK"][t] = tuple(x + 200 for x in b) + (1,)
    st.side_rows["ASK"][T0] = (4_000_000, 4_000_100, 3_999_900, 4_000_000, 1)
    return st


def flat(k):
    return (4_001_000, 4_001_500, 4_000_500, 4_001_000) if k != 120 else (4_003_000, 4_003_500, 4_002_000, 4_003_200)


def test_managed_exit_at_the_review_minute():
    mins = settle.Minutes(store_of(flat), WIN)
    out = settle.settle_side(mins, 1, 50, 100, False, m=M)          # S $5, T $10: X 3995, Tg 4010
    assert (out["reason"], out["fill"], out["exit_minute_utc"], out["P_x"]) == \
        ("managed", "open", "2026-12-02T10:00:00Z", 4003.0)
    assert abs(out["net_usd"] - 2.9) < 1e-12 and settle.x_end(out, mins, M) == M
    un = settle.settle_side(mins, 1, 50, 100, False)
    assert un["reason"] == "time" and un["exit_minute_utc"] == "2026-12-02T11:59:00Z" and settle.x_end(un, mins) == T1
    ps = settle.path_summary(mins, 1, out, m=M)
    assert ps["mfe_usd"] == 1.5 and ps["mae_usd"] == 0.5 and ps["exit_after_min"] == 120   # bid t0..m-1 only
    assert len(ps["buckets"]) == 16 and ps["buckets"][15]["n"] == 15                       # the full [t0, t1)


def test_managed_exit_falls_back_to_the_last_quoted_close():
    mins = settle.Minutes(store_of(flat, gap=range(116, 121)), WIN)
    out = settle.settle_side(mins, 1, 50, 100, False, m=M)
    assert (out["reason"], out["fill"], out["exit_minute_utc"], out["P_x"]) == \
        ("managed", "close", "2026-12-02T09:55:00Z", 4001.0)
    assert settle.x_end(out, mins, M) == M


def test_a_stop_before_the_review_minute_wins():
    def stopped(k):
        return (4_001_000, 4_001_500, 3_994_000, 4_001_000) if k == 30 else flat(k)
    mins = settle.Minutes(store_of(stopped), WIN)
    out = settle.settle_side(mins, 1, 50, 100, False, m=M)
    assert (out["reason"], out["fill"], out["exit_minute_utc"]) == ("stop", "level", "2026-12-02T08:30:00Z")
    assert settle.public(out) == settle.public(settle.settle_side(mins, 1, 50, 100, False))   # no effect
    assert settle.x_end(out, mins, M) == T0 + 31 * 60                 # level fill: i + 1 min

    def gapped(k):
        return (3_994_000, 3_994_500, 3_993_000, 3_994_000) if k == 30 else flat(k)
    out = settle.settle_side(settle.Minutes(store_of(gapped), WIN), 1, 50, 100, False, m=M)
    assert (out["reason"], out["fill"]) == ("stop", "open") and settle.x_end(out, mins, M) == T0 + 30 * 60


def test_void_and_opposite_with_a_managed_exit():
    mins = settle.Minutes(store_of(flat), WIN)
    v = settle.settle_side(mins, 1, 50, 100, True, m=M)
    assert v["status"] == "void" and settle.x_end(v, mins, M) == M and settle.x_end(v, mins) == T1
    opp = settle.settle_side(mins, -1, 50, 100, False, m=M)
    assert opp["reason"] == "managed" and opp["exit_minute_utc"] == "2026-12-02T10:00:00Z"


# ---------------------------------------------------------------- R-AN-94: weights and clusters (unit)

def iv(cid, a, b):
    return (cid, T(f"2026-12-02T{a}:00Z"), T(f"2026-12-02T{b}:00Z"))


def test_weights_chain_is_one_cluster():
    w = review.overlap_weights([iv("a", "08:00", "12:00"), iv("b", "11:00", "15:00"), iv("c", "14:30", "18:30"),
                                iv("d", "19:00", "23:00")])
    assert w == {"a": (0.5, "a"), "b": (0.5, "a"), "c": (0.5, "a"), "d": (1.0, "d")}
    assert sum(x for x, _c in w.values()) == 2.5


def test_weights_touching_and_stopped_trades_do_not_overlap():
    w = review.overlap_weights([iv("a", "08:00", "10:00"), iv("b", "10:00", "14:00")])
    assert w == {"a": (1.0, "a"), "b": (1.0, "b")}
    w = review.overlap_weights([iv("a", "08:00", "08:31"), iv("b", "10:00", "14:00"), iv("c", "13:00", "17:00")])
    assert w == {"a": (1.0, "a"), "b": (0.5, "b"), "c": (0.5, "b")}


# ---------------------------------------------------------------- R-AN-94, R-AN-52..R-AN-55: weighted statistics

def tr(cid, day, y, wt=1.0, cl=None, R=None, side=1, stress=None, cost=0.1, net=None):
    R = y if R is None else R
    return {"call_id": cid, "model_day": dt.date.fromisoformat(day), "w": "W1", "side": side, "y": y, "R": R,
            "net": R if net is None else net, "stress": R if stress is None else stress, "cost": cost, "wt": wt,
            "cluster": cl or cid}


def test_e_process_takes_one_factor_per_cluster():
    ts = [tr("a", "2026-12-02", 1.0, 0.5, "a"), tr("b", "2026-12-02", -0.5, 0.5, "a"),
          tr("c", "2026-12-03", 0.2)]
    want = sum((1 + lam * 0.25) * (1 + lam * 0.2) for lam in stats.LAMBDAS) / len(stats.LAMBDAS)
    assert stats.e_trades(ts) == pytest.approx(want, rel=1e-12)
    assert stats.k_trades(ts) == pytest.approx(
        sum((1 - lam * 0.25) * (1 - lam * 0.2) for lam in stats.LAMBDAS) / len(stats.LAMBDAS), rel=1e-12)
    assert stats.n_weighted(ts) == 2.0
    assert [c for c, _ts in stats.clusters(ts)] == ["a", "c"]
    # unweighted trades of earlier days: each its own cluster, the old formulas exactly
    old = [tr("x", "2026-11-30", 0.3), tr("y", "2026-12-01", -1.0)]
    assert stats.e_trades(old) == stats.e_value([0.3, -1.0]) and stats.n_weighted(old) == 2


def test_promotion_p5_and_side_share_are_weighted():
    ts = [tr("a", "2026-12-02", 1.0, 0.5, "a", R=4.0), tr("b", "2026-12-02", 1.0, 0.5, "a", R=2.0, side=-1),
          tr("c", "2026-12-03", 1.0, 1.0, "c", R=2.5)]
    p = stats.promotion(ts, [], dt.date(2026, 12, 1), dt.date(2026, 12, 3))
    assert p["n"] == 2.0
    assert p["P5"] is True                     # 0.5·4 + 0.5·2 + 2.5 = 5.5; best cluster a = 3.0; 5.5 − 3.0 > 0
    ts[2]["R"] = 0.4
    assert stats.promotion(ts, [], dt.date(2026, 12, 1), dt.date(2026, 12, 3))["P5"] is True   # 3.4 − 3.0
    ts[2]["R"] = -0.1
    assert stats.promotion(ts, [], dt.date(2026, 12, 1), dt.date(2026, 12, 3))["P5"] is False
    assert stats.side_share(ts) == 0.75


def test_demotion_d2_d3_by_weight():
    post = [tr(f"p{i}", "2026-12-10", 0.0, 0.5, f"c{i // 2}", R=-0.01) for i in range(200)]
    reason, _K = stats.demotion(post)
    assert reason == "D3"                       # cumulative weight 100 at trade 200: Σ w·R = −1 <= 0
    assert stats.demotion(post[:150])[0] is None    # weight 75: no D3 yet (an unweighted count would give one)
    post = [tr(f"p{i}", "2026-12-10", 0.0, 0.5, f"c{i // 2}", R=-3.0) for i in range(4)]
    assert stats.demotion(post)[0] == "D2"      # Σ w·R = −6 <= −5
    post = [tr(f"p{i}", "2026-12-10", 0.0, 0.5, f"c{i // 2}", R=-3.0) for i in range(3)]
    assert stats.demotion(post)[0] is None      # −4.5


def test_replay_reports_weighted_n():
    ts = [tr("a", "2026-12-02", 0.1, 0.5, "a"), tr("b", "2026-12-02", 0.1, 0.5, "a"), tr("c", "2026-12-03", 0.1)]
    ev = stats.replay_states(ts, [], dt.date(2026, 12, 2), {dt.date(2026, 12, 2), dt.date(2026, 12, 3)})
    assert ev[0][:4] == ("TESTING", "first_day", dt.date(2026, 12, 2), 1.0)


# ---------------------------------------------------------------- the world: reviews in both modes from a15_from

from world import PLAN_ADD, PLAN_BUY, PLAN_CLOSE, PLAN_HOLD, PLAN_REVERSE, PLAN_SELL, PLAN_STAY, World  # noqa: E402

# canary 12-01 (A14 only), 12-02 and 12-03 (A15), live 12-04 (A15); the triggers are those R-AN-89 gives on the
# world's bars: 12-02 T2330, T0430 (05:00), T0630 (07:00); 12-03 T2330, T0130, T0330; 12-04 T0030, T0630, T1530
A15_WORLD = dict(canary_days=("2026-12-01", "2026-12-02", "2026-12-03"), live_from="2026-12-04",
                 live_to="2026-12-04", now="2026-12-07T12:00:00Z", store_first="2026-10-19", a12_from="2026-11-30",
                 a14_from="2026-12-01", a15_from="2026-12-02")
PLANS = {"2026-12-02_T0630": ("call", PLAN_ADD), "2026-12-02_W1": ("call", PLAN_CLOSE),
         "2026-12-02_W1b": ("call", PLAN_SELL), "2026-12-02_W2": ("call", PLAN_BUY),
         "2026-12-03_W1": ("call", PLAN_SELL), "2026-12-03_W1b": ("call", PLAN_REVERSE),
         "2026-12-03_W2": ("call", PLAN_BUY), "2026-12-03_W2b": ("call", PLAN_HOLD),
         "2026-12-04_W1": ("call", PLAN_ADD), "2026-12-04_W1b": ("call", PLAN_CLOSE),
         "2026-12-04_W2": ("call", PLAN_STAY)}


class _TreeGit:
    """A one-commit tree for R-AN-50 (path -> bytes)."""

    def __init__(self, files):
        self.files = {p: (b if isinstance(b, bytes) else b.encode()) for p, b in files.items()}

    def ls_tree(self, commit, prefix=""):
        return sorted(p for p in self.files if p.startswith(prefix))

    def show(self, commit, path):
        return self.files.get(path)


def test_canary_playbook_in_force_only_after_a15_from():
    """R-AN-50 (A15-D22): a canary revision effective on a15_from (written before a15_from was set, from the fixture's
    lesson) is never in force; one effective after a15_from is, from its effective_from."""
    from jlib.context import playbook_in_force
    a15 = dt.date(2026, 11, 2)
    files = {"analyst/playbooks/v0.md": "# playbook v0\n",
             "analyst/canary/playbooks/v1.md": "# playbook v1\nfixture\n",
             "analyst/canary/revisions/2026-W44.json": json.dumps({"status": "written", "version": 1,
                                                                   "effective_from": "2026-11-02"})}
    git = _TreeGit(files)
    for d in (dt.date(2026, 11, 2), dt.date(2026, 11, 3), dt.date(2026, 11, 9)):
        assert playbook_in_force(git, "c", "analyst/canary/", d, a15) == (0, "analyst/playbooks/v0.md",
                                                                           b"# playbook v0\n")
    git.files["analyst/canary/playbooks/v2.md"] = b"# playbook v2\n"
    git.files["analyst/canary/revisions/2026-W45.json"] = json.dumps(
        {"status": "written", "version": 2, "effective_from": "2026-11-09"}).encode()
    assert playbook_in_force(git, "c", "analyst/canary/", dt.date(2026, 11, 6), a15)[0] == 0
    assert playbook_in_force(git, "c", "analyst/canary/", dt.date(2026, 11, 9), a15) == (
        2, "analyst/canary/playbooks/v2.md", b"# playbook v2\n")


def a15_world(root, hooks=None):
    return World(root, plans=dict(PLANS), hooks=hooks or {}, **A15_WORLD).build()


@pytest.fixture(scope="module")
def a15(tmp_path_factory):
    return a15_world(str(tmp_path_factory.mktemp("a15") / "w"))


def rec(w, path):
    with open(os.path.join(w.repo.path, path), encoding="utf-8") as f:
        return json.load(f)


def test_a15_world_runs_reviews(a15):
    st = {(m, c): t["status"] for (m, c), t in a15.terminals.items()}
    assert st[("canary", "2026-12-02_T0630")] == "called" and st[("canary", "2026-12-02_W1")] == "review_close"
    rv = a15.calls[("canary", "2026-12-02_W1")]["context"]["review"]
    assert [o["call_id"] for o in rv["open"]] == ["2026-12-02_T0430", "2026-12-02_T0630"]
    assert rv["options"] == ["hold", "close"] and rv["ref_px"] is not None
    assert a15.calls[("canary", "2026-12-02_W1")]["context"]["schema"] == SCHEMA_V5
    assert a15.calls[("canary", "2026-12-01_W1")]["context"]["schema"] == SCHEMA_V4      # before the A15 build
    assert st[("canary", "2026-12-03_W1b")] == "called" and st[("live", "2026-12-04_W1b")] == "review_close"
    assert "skipped:trade_open" in {v for (m, c), v in st.items() if c.startswith("2026-12-01")}
    assert not any(v == "skipped:trade_open" for (m, c), v in st.items() if c >= "2026-12-02")
    files = [f["req"] for f in a15.calls[("canary", "2026-12-02_W1")]["context"]["files"]]
    assert files[-1] == "XAUUSD_M30R" and files[-2] == "fresh"
    # managed exits, weights and clusters (R-AN-93, R-AN-94)
    s1 = rec(a15, "analyst/canary/settled/2026-12-02_T0430.json")
    s2 = rec(a15, "analyst/canary/settled/2026-12-02_T0630.json")
    assert s1["schema"] == "analyst-settled/2" and s1["class"] == "canary" and s1["mode"] == "canary"
    assert s1["closed_by"] == s2["closed_by"] == "2026-12-02_W1"
    assert s1["managed_utc"] == "2026-12-02T08:00:00Z" and s1["unmanaged"] is not None
    assert (s1["weight"], s1["cluster"], s2["weight"], s2["cluster"]) == (0.5, "2026-12-02_T0430", 0.5,
                                                                         "2026-12-02_T0430")
    assert [r["call_id"] for r in s2["reviews"]] == ["2026-12-02_W1"] and s2["action"] == "add"
    assert [r["call_id"] for r in s1["reviews"]] == ["2026-12-02_T0630", "2026-12-02_W1"]
    w1b = rec(a15, "analyst/canary/settled/2026-12-03_W1b.json")
    assert w1b["action"] == "reverse" and w1b["side"] == 1 and w1b["closed_by"] is None
    assert rec(a15, "analyst/canary/settled/2026-12-03_W1.json")["closed_by"] == "2026-12-03_W1b"
    assert not os.path.exists(os.path.join(a15.repo.path, "analyst/canary/settled/2026-12-01_W1.json"))
    assert os.path.exists(os.path.join(a15.repo.path, "analyst/canary/twins/2026-12-02_W1.json"))   # a review
    live = rec(a15, "analyst/settled/2026-12-04_T0630.json")
    assert live["closed_by"] == "2026-12-04_W1b" and live["weight"] == 0.5
    # the canary's memory (R-AN-95) and `side` (R-AN-22, /5)
    mem = a15.calls[("canary", "2026-12-03_W1")]["context"]["memory"]
    assert mem is not None and {s["call_id"] for s in mem["settled"]} >= {"2026-12-02_T0430", "2026-12-02_W2"}
    assert all(set(s) >= {"side"} for s in mem["settled"]) and all("side" in p for p in mem["pending"])
    assert a15.calls[("canary", "2026-12-01_W1")]["context"]["memory"] is None
    assert a15.calls[("canary", "2026-12-02_W1")]["context"]["memory"]["settled"] == []
    led = (open(os.path.join(a15.repo.path, "analyst/ledger.csv"), encoding="utf-8").read().splitlines())
    assert led[0].endswith("n_w,weight,cluster,x_end_utc,closed_by")
    assert rec(a15, "analyst/STATE.json")["schema"] == "analyst-state/2"


def test_a15_world_is_sound(a15):
    res = a15.judge()
    assert keys(res) == []
    assert res.summary["contexts_rebuilt"] == len(a15.calls)
    assert res.summary["settled_checked"] == len(a15.a15_settled)
    assert res.summary["m30r_compared"] >= 4


def test_A4_and_A0_unpinned_a15(a15):
    res = a15.judge(a15_commit=None)
    v5 = sorted(f"{'analyst/' if m == 'live' else 'analyst/canary/'}calls/{c}.json" for (m, c) in a15.calls
                if a15.calls[(m, c)]["context"]["schema"] == SCHEMA_V5)
    assert sorted(k.split("|")[2] for k in keys(res, "A4", VIOLATION, "context_schema")) == v5
    assert keys(res, "A0", WARNING, "a15_unpinned") == ["A0|a15_unpinned|judge_analyst/jlib/config.py|-"]


def test_A15_m30r_mismatch_from_the_judges_fetch(a15):
    from jlib import watch
    rv = a15.calls[("canary", "2026-12-02_W1")]["context"]["review"]
    t_bar = rv["open"][0]["entry_utc"]

    def edit(d, bars):
        if d == dt.date(2026, 12, 2):
            for b in bars:
                if b["t_utc"] == t_bar:                  # the whole bar 0.2% higher (still a valid bar)
                    for k in ("o", "h", "l", "c"):
                        b[k] = round(b[k] * 1.002, 5)
        return bars
    src = watch.M30Source(watch.FakeM30Fetcher(a15.m30_responses(edit)), None, max_fetch=50, sleep=lambda _s: None)
    res = a15.judge(m30=src)
    ks = keys(res, "A15", WARNING, "m30r_mismatch")
    assert any(k.startswith("A15|m30r_mismatch|analyst/canary/calls/2026-12-02_W1.json|") for k in ks)
    assert not keys(res, "A15", VIOLATION)


def test_A15_unsettled_after_two_weekdays(tmp_path):
    w = a15_world(str(tmp_path / "w"), hooks={"skip_settle_day": {("canary", dt.date(2026, 12, 3))}})
    assert not keys(w.judge(), "A15", code="unsettled")             # 12-04 02:10Z final; Friday only
    res = w.judge(now="2026-12-10T12:00:00Z")
    ks = keys(res, "A15", WARNING, "unsettled")
    assert any(k.startswith("A15|unsettled|analyst/canary/terminal/2026-12-03_W1.json|") for k in ks)
    assert not any("2026-12-02_" in k for k in ks)


def _bad_hooks():
    def context(world, win, ctx):
        if win.call_id == "2026-12-04_W1b":           # names one of its two open trades (a late-lock-like race)
            m30r = next(f for f in ctx["files"] if f["req"] == "XAUUSD_M30R")
            first = world.review_trades("live", win)[:1]
            ctx["review"] = review.review_block(first, win.entry, m30r["bars"])
        if win.call_id == "2026-12-02_T0630" and ctx.get("review"):
            ctx["review"]["ref_px"] = ctx["review"]["ref_px"] + 0.5      # not what its bars give

    def call(world, win, c):
        if win.call_id == "2026-12-03_W1b":
            c["plan"]["action"] = "sell"                                  # not one of the review's options
            c["plan_sha256"] = None

    def terminal(world, t):
        if t["call_id"] == "2026-12-03_W2b" and t["status"] == "skipped:day_cap":
            t["status"], t["detail"] = "skipped:trade_open", "2026-12-03_W2"   # never from a15_from

    def settled(world, win, r):
        if r["call_id"] == "2026-12-04_T0630":
            r["weight"] = 1.0
    return {"context": context, "call": call, "terminal": terminal, "settled": settled}


@pytest.fixture(scope="module")
def a15_bad(tmp_path_factory):
    return a15_world(str(tmp_path_factory.mktemp("a15bad") / "w"), hooks=_bad_hooks())


def test_A15_faults(a15_bad):
    w = a15_bad
    res = w.judge()
    assert keys(res, "A15", VIOLATION, "review_open") == \
        [f"A15|review_open|analyst/calls/2026-12-04_W1b.json|{res_commit(w, 'analyst/calls/2026-12-04_W1b.json')}"]
    assert [k.rsplit("|", 1)[0] for k in keys(res, "A4", VIOLATION, "context_differs")] == \
        ["A4|context_differs|analyst/canary/calls/2026-12-02_T0630.json"]
    assert [k.rsplit("|", 1)[0] for k in keys(res, "A5", VIOLATION, "action_not_allowed")] == \
        ["A5|action_not_allowed|analyst/canary/calls/2026-12-03_W1b.json"]
    assert [k.rsplit("|", 1)[0] for k in keys(res, "A14", VIOLATION, "skipped_wrong")] == \
        ["A14|skipped_wrong|analyst/canary/terminal/2026-12-03_W2b.json"]
    # the weight, and W2's `reviews`: its review W2b is `skipped:trade_open` at main
    assert sorted(k.rsplit("|", 1)[0] for k in keys(res, "A11", WARNING, "settled_mismatch")) == \
        ["A11|settled_mismatch|analyst/canary/settled/2026-12-03_W2.json",
         "A11|settled_mismatch|analyst/settled/2026-12-04_T0630.json"]
    assert sorted(f.detail for f in res.findings.items if f.code == "settled_mismatch") == ["reviews", "weight"]
    assert not keys(res, "A15", code="open_cap") and not keys(res, "A15", code="a15_from")


def res_commit(w, path):
    from jlib.gitrepo import GitRepo
    g = GitRepo(w.repo.path)
    try:
        return g.run("log", "--diff-filter=A", "--format=%H", "--", path).split()[-1]
    finally:
        g.close()


def test_A15_a15_from_and_lesson_source(a15, tmp_path):
    from jlib.common import sha256_bytes
    w = a15.clone(str(tmp_path / "c"))
    fx = open(os.path.join(w.repo.path, "analyst/tests/fixtures/canary_settled.json"), "rb").read()
    les = {"schema": "analyst-lesson/1", "call_id": "2026-12-02_W2", "mode": "canary", "status": "ok",
           "text_ar": "درس", "settled_sha256": sha256_bytes(fx), "playbook_version": 0, "attempt_n": 1,
           "self_reported": {}}
    bad2 = dict(les, call_id="2026-12-02_W1", settled_sha256="0" * 64)      # a review: no canary settled record
    ok = dict(les, call_id="2026-12-02_T2330",
              settled_sha256=sha256_bytes(open(os.path.join(w.repo.path, "analyst/canary/settled/2026-12-02_T2330.json"),
                                               "rb").read()))
    tw = rec(w, "analyst/canary/twins/2026-12-02_W1.json")
    tw.update({"call_id": "2026-12-01_W1", "model_day": "2026-12-01"})
    w.owner_commit({"analyst/canary/lessons/2026-12-02_W2.json": record_form(les),
                    "analyst/canary/lessons/2026-12-02_W1.json": record_form(bad2),
                    "analyst/canary/lessons/2026-12-02_T2330.json": record_form(ok),
                    "analyst/canary/twins/2026-12-01_W1.json": record_form(tw)},
                   T("2026-12-05T10:00:00Z"), "planted canary records")
    m = rec(w, "analyst/MODE.json")
    m["a15_from"] = "2026-12-03"
    sha = w.owner_commit({"analyst/MODE.json": record_form(m)}, T("2026-12-05T11:00:00Z"), "owner: a15_from moved")
    res = w.judge()
    ls = sorted(k.split("|")[2] for k in keys(res, "A15", VIOLATION, "lesson_source"))
    assert ls == ["analyst/canary/lessons/2026-12-02_W1.json", "analyst/canary/lessons/2026-12-02_W2.json"]
    af = keys(res, "A15", VIOLATION, "a15_from")
    assert f"A15|a15_from|analyst/MODE.json|{sha}" in af                     # changed after it was set
    assert len(af) >= 2                                                    # and the 12-01 canary twin


def test_A15_a15_from_conditions(tmp_path):
    def wc(world, c):
        c["deployed_utc"] = "2026-12-01T22:30:00Z"                         # after 22:00Z of the day before
    w = a15_world(str(tmp_path / "w"), hooks={"watcher_config_a15": wc})
    res = w.judge()
    assert [k.rsplit("|", 1)[0] for k in keys(res, "A15", VIOLATION, "a15_from")] == ["A15|a15_from|analyst/MODE.json"]
    assert "deployed_utc" in [f for f in res.findings.items if f.code == "a15_from"][0].detail


def test_A15_open_cap_from_the_recomputed_sets():
    """open_cap and review_open on the judge's own reading (check_reviews), with a review that broke its options."""
    from jlib.common import Findings
    from jlib.judge import Judge, Rec
    j = Judge.__new__(Judge)
    j.F, j.open_info, j.a15_day = Findings(), {}, dt.date(2026, 12, 2)
    d = dt.date(2026, 12, 2)
    wins = [Window(d, w) for w in ("T0430", "T0630", "W1", "T0800")]
    j.windows = {"canary": wins, "live": []}
    plans = {"T0430": ("called", "buy", None), "T0630": ("called", "add", ["2026-12-02_T0430"]),
             "W1": ("called", "add", ["2026-12-02_T0430", "2026-12-02_T0630"]), "T0800": ("review_hold", "hold", None)}
    j.terminal_info = {}
    for w in wins:
        stt, act, names = plans[w.w if w.w != "T" else w.call_id[-5:]]
        rv = {"open": [{"call_id": c} for c in names], "options": review.options(len(names))} if names else None
        call = {"plan": {"action": act}, "context": {"review": rv}}
        j.terminal_info[("canary", w.call_id)] = {"status": stt, "call": call,
                                                  "call_raw": Rec(f"analyst/canary/calls/{w.call_id}.json", b"",
                                                                  None, "c1")}
    j.check_reviews()
    ks = [f.key for f in j.F.items]
    assert "A15|open_cap|2026-12-02|canary" in ks                         # T0800: three open trades
    assert "A15|review_open|analyst/canary/calls/2026-12-02_T0800.json|c1" in ks    # review null, three open
    assert len(ks) == 2
