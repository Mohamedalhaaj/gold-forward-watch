"""Grammar L2G-1 (features, decisions, canonical form) and the execution model (§3 items 2-4, §9)."""
import numpy as np
import pandas as pd
import pytest

import bars
from lab import execution, grammar, registry

DAY = pd.Timestamp("2026-11-04")          # a Wednesday


def m1_day(day=DAY, mid=None, spread=0.4, novol=(), missing=(), lows=None, highs=None, opens=None):
    """A model-clock M1 day: mid path (1440 closes), bid/ask = mid -/+ spread/2, volume except at `novol`."""
    rng = np.random.default_rng(0)
    if mid is None:
        mid = 4000 + np.cumsum(rng.standard_normal(1440)) * 0.3
    c = np.asarray(mid, dtype=float)
    o = np.r_[c[0], c[:-1]] if opens is None else np.asarray(opens, dtype=float)
    h = np.maximum(o, c) + 0.05 if highs is None else np.asarray(highs, dtype=float)
    l = np.minimum(o, c) - 0.05 if lows is None else np.asarray(lows, dtype=float)
    idx = pd.date_range(day, periods=1440, freq="min")
    f = pd.DataFrame({"o": o, "h": h, "l": l, "c": c}, index=idx)
    for side, sg in (("bid", -1), ("ask", 1)):
        for k in "ohlc":
            f[f"{side}_{k}"] = f[k] + sg * spread / 2
    vol = np.ones(1440)
    vol[list(novol)] = 0
    f["bid_vol"] = vol
    f["ask_vol"] = vol
    return f.drop(index=idx[list(missing)])


def md_db(f):
    md = execution.Minutes(f)
    lb = bars.lab_bars(f)
    return md, grammar.DayBars(lb[lb.day == f.index[0].normalize()])


# ---------------------------------------------------------------- grammar: validation and canonical form
@pytest.mark.parametrize("patch, msg", [
    ({"T": "0130"}, "T must"), ({"T": "2330"}, "T must"), ({"T": "1507"}, "T must"),
    ({"side": ["FADE", "2300", "2245"]}, "window"), ({"side": ["FADE", "2245", "2315"]}, "window"),
    ({"side": ["FADE", "0115", "0145"]}, "window"), ({"hold": 3}, "hold"), ({"hold": 0}, "hold"),
    ({"when": [["SPEED", "2245", "2300", "GE", "0.50"]]}, "unknown feature"),
    ({"when": [["MOVE", "2245", "2300", "GE", "0.5"]] * 3}, "0, 1 or 2"),
    ({"when": [["MOVE", "2245", "2300", "GE", "0.505"]]}, "theta"),
    ({"when": [["MOVE", "2245", "2300", "GE", "10.00"]]}, "theta"),
    ({"stop": "X10"}, "unknown stop"), ({"days": 0}, "days"), ({"skip_event": 2}, "skip_event"),
    ({"side": ["COIN"]}, "COIN"),
])
def test_rejections(patch, msg):
    spec = dict(registry.S1_SPEC) | patch
    with pytest.raises(grammar.SpecError, match=msg):
        grammar.validate(spec)


def test_canonical_json_and_golden_hash():
    a = grammar.canonical_json(registry.S1_SPEC)
    b = grammar.canonical_json(dict(reversed(list(registry.S1_SPEC.items()))) | {"when": [["ABSMOVE", "2245", "2300",
                                                                                         "GE", "0.5"]]})
    assert a == b == ('{"T":"2300","days":15,"hold":2,"side":["FADE","2245","2300"],"skip_event":0,"stop":"H10",'
                      '"when":[["ABSMOVE","2245","2300","GE","0.50"]]}')
    assert grammar.spec_sha256(registry.S1_SPEC) == "6ffaa67288d4725be2899d18ebcca0cf1eaae96e7d02959487867aecb67c6b08"


def test_question_key_ignores_side_mode():
    fade = registry.S1_SPEC
    follow = dict(fade) | {"side": ["FOLLOW", "2245", "2300"]}
    assert grammar.question_key(fade) == grammar.question_key(follow)
    longs = dict(fade) | {"side": ["LONG"]}
    assert grammar.question_key(longs) == grammar.question_key(dict(fade) | {"side": ["SHORT"]})
    assert grammar.question_key(longs) != grammar.question_key(fade)


def test_coin_side_is_the_hash_parity():
    import hashlib
    for d in ("2026-11-02", "2026-11-03", "2027-01-05"):
        h = int(hashlib.sha256(f"L2-C1|{d}".encode()).hexdigest()[:8], 16)
        assert grammar.coin_side(d) == (1 if h % 2 == 0 else -1)


# ---------------------------------------------------------------- features and decisions
def test_features_by_hand():
    mid = np.full(1440, 4000.0)
    mid[1350:1365] = np.linspace(4000.5, 4003.0, 15)    # the 22:30 bar rises
    mid[1365:1380] = np.linspace(4002.0, 3999.0, 15)    # the 22:45 bar falls
    f = m1_day(mid=mid)
    md, db = md_db(f)
    U = 2.0
    o, c = db.O(1365), db.C(1380)
    hi, lo = db.hilo(1365, 1380)
    assert o == f.o.iloc[1365] and c == f.c.iloc[1379]
    assert hi == f.h.iloc[1365:1380].max() and lo == f.l.iloc[1365:1380].min()
    assert grammar.feature(db, "MOVE", 1365, 1380, U) == pytest.approx((c - o) / U)
    assert grammar.feature(db, "ABSMOVE", 1365, 1380, U) == pytest.approx(abs(c - o) / U)
    assert grammar.feature(db, "RANGE", 1350, 1380, U) == pytest.approx(
        (f.h.iloc[1350:1380].max() - f.l.iloc[1350:1380].min()) / U)
    assert grammar.feature(db, "POS", 1365, 1380, U) == pytest.approx((c - lo) / (hi - lo))
    assert grammar.feature(db, "LWICK", 1365, 1380, U) == pytest.approx((min(o, c) - lo) / U)
    assert grammar.feature(db, "UWICK", 1365, 1380, U) == pytest.approx((hi - max(o, c)) / U)


def _decide(f, spec=registry.S1_SPEC, day=DAY, first="2026-11-02", holiday=False, event=False, F=10.0, FS=12.0):
    md, db = md_db(f)
    return grammar.decide(spec, db, day, day.dayofweek, first, holiday, event, F, FS)


def test_s1_triggers_and_fades():
    mid = np.full(1440, 4000.0)
    mid[1365:1380] = np.linspace(4000.2, 4004.0, 15)     # strong rise in the 22:45 bar
    f = m1_day(mid=mid)
    rec = _decide(f)
    U = f.c.iloc[1379] * (np.exp(10 / 1e4) - 1)
    assert rec["outcome"] == "trigger" and rec["side"] == -1
    assert rec["U"] == pytest.approx(U) and rec["feats"][0] >= 0.5
    flat = m1_day(mid=np.full(1440, 4000.0))
    assert _decide(flat)["outcome"] == "no_trigger"


def test_abstentions():
    mid = np.full(1440, 4000.0)
    mid[1365:1380] = np.linspace(4000.2, 4004.0, 15)
    f = m1_day(mid=mid)
    assert _decide(f, holiday=True)["outcome"] == "abstain_day"
    assert _decide(f, first="2026-11-05")["outcome"] == "abstain_day"
    assert _decide(f, first=None)["outcome"] == "abstain_day"
    fri = pd.Timestamp("2026-11-06")
    assert _decide(m1_day(day=fri, mid=mid), day=fri)["outcome"] == "abstain_day"     # days = Mon-Thu
    ev = dict(registry.S1_SPEC) | {"skip_event": 1}
    assert _decide(f, spec=ev, event=True)["outcome"] == "abstain_day"
    assert _decide(f, spec=ev, event=False)["outcome"] == "trigger"
    assert _decide(f, F=np.nan)["outcome"] == "abstain_U"
    nov = m1_day(mid=mid, novol=range(1365, 1369))                # 11 of 15 minutes with volume: invalid bar
    assert _decide(nov)["outcome"] == "abstain_data"
    gone = m1_day(mid=mid, missing=range(1365, 1380))
    assert _decide(gone)["outcome"] == "abstain_data"


def test_friday_eligibility():
    """On a Friday a rule abstains unless T + 15h <= 22:45 (§3 item 4)."""
    fri = pd.Timestamp("2026-11-06")
    f = m1_day(day=fri, mid=np.full(1440, 4000.0))
    ok = {"T": "2200", "side": ["LONG"], "when": [], "hold": 3, "stop": "H10", "days": 31, "skip_event": 0}
    late = ok | {"hold": 4}
    assert _decide(f, spec=ok, day=fri)["outcome"] == "trigger"
    assert _decide(f, spec=late, day=fri)["outcome"] == "abstain_day"
    wed = m1_day(mid=np.full(1440, 4000.0))
    assert _decide(wed, spec=late)["outcome"] == "trigger"


# ---------------------------------------------------------------- execution
K = grammar.STOPS["H10"]


def loop_trade(md, side, T, hold, k, F, delay=1):
    """Plain minute loop of the §3 execution rules (the reference for the vectorised trade())."""
    t0, t1 = T + delay, T + 15 * hold
    r0 = md.row(t0)
    P_e = (md.ask_o if side > 0 else md.bid_o)[r0]
    X = P_e * np.exp(-side * k * F / 1e4)
    run, last = 0, None
    for m in range(t0, t1):
        r = md.row(m)
        run = run + 1 if (r < 0 or not md.vol[r]) else 0
        if r >= 0:
            o = (md.bid_o if side > 0 else md.ask_o)[r]
            lo = (md.bid_l if side > 0 else md.ask_h)[r]
            if (side > 0 and o <= X) or (side < 0 and o >= X):
                return P_e, X, o, "stop", m
            if (side > 0 and lo <= X) or (side < 0 and lo >= X):
                return P_e, X, X, "stop", m
            last = (m, (md.bid_c if side > 0 else md.ask_c)[r])
        if run >= 15:
            return P_e, X, X, "gap", m
    return P_e, X, last[1], "time", last[0]


def test_entry_is_one_minute_after_T_on_the_executable_side():
    f = m1_day()
    md, _ = md_db(f)
    t = execution.trade(md, 1, 1380, 2, K, 10.0, delay=1)
    assert t["entry_min"] == 1381 and t["P_e"] == f.ask_o.iloc[1381]
    s = execution.trade(md, -1, 1380, 2, K, 10.0, delay=1)
    assert s["P_e"] == f.bid_o.iloc[1381]
    r = execution.trade(md, 1, 1380, 2, K, 10.0, delay=0)              # S1R: entry at T
    assert r["entry_min"] == 1380 and r["P_e"] == f.ask_o.iloc[1380]


def test_time_exit_and_money():
    f = m1_day(mid=np.full(1440, 4000.0))
    md, _ = md_db(f)
    t = execution.trade(md, 1, 900, 2, K, 10.0)
    assert t["reason"] == "time" and t["exit_min"] == 929
    assert t["P_x"] == f.bid_c.iloc[929]
    assert t["net_usd"] == pytest.approx(f.bid_c.iloc[929] - f.ask_o.iloc[901] - 0.10)
    assert t["net_stress_usd"] == pytest.approx(t["net_usd"] - 0.25)
    assert t["D"] == pytest.approx(t["P_e"] * (1 - np.exp(-K * 10 / 1e4)))
    assert t["R"] == pytest.approx(t["net_usd"] / t["D"])
    assert t["gross_usd"] == pytest.approx(t["net_usd"] + 0.10 + 0.2 + 0.2)      # half spreads at entry and exit


def test_stop_wins_a_tie_in_the_last_minute():
    mid = np.full(1440, 4000.0)
    lows = mid - 0.05
    lows[929] = 3990.0                                      # only the last minute of the path reaches the stop
    f = m1_day(mid=mid, lows=lows)
    md, _ = md_db(f)
    t = execution.trade(md, 1, 900, 2, K, 10.0)
    assert t["reason"] == "stop" and t["exit_min"] == 929 and t["P_x"] == pytest.approx(t["X"])


def test_gap_through_the_stop_fills_at_the_open():
    mid = np.full(1440, 4000.0)
    mid[910:] = 3980.0
    f = m1_day(mid=mid)                                     # minute 910 opens at 4000 -> closes 3980; 911 opens 3980
    md, _ = md_db(f)
    t = execution.trade(md, 1, 900, 2, K, 10.0)
    assert t["reason"] == "stop" and t["exit_min"] == 910 and t["P_x"] == pytest.approx(t["X"])
    opens = np.r_[mid[0], mid[:-1]].copy()
    opens[911] = 3975.0                                     # a gap at the open of 911, below X
    lows = np.minimum(opens, mid) - 0.05
    lows[910] = 3999.9
    mid2 = mid.copy()
    mid2[910] = 4000.0
    f2 = m1_day(mid=mid2, opens=opens, lows=lows)
    md2, _ = md_db(f2)
    t2 = execution.trade(md2, 1, 900, 2, K, 10.0)
    assert t2["exit_min"] == 911 and t2["P_x"] == pytest.approx(3975.0 - 0.2) and t2["P_x"] < t2["X"]


def test_spread_wider_than_the_stop_exits_at_the_entry_minute_bid():
    f = m1_day(mid=np.full(1440, 4000.0), spread=10.0)
    md, _ = md_db(f)
    t = execution.trade(md, 1, 900, 2, K, 10.0)
    assert t["exit_min"] == 901 and t["P_x"] == f.bid_o.iloc[901] and t["P_x"] < t["X"]


def test_short_is_the_mirror():
    mid = np.full(1440, 4000.0)
    highs = mid + 0.05
    highs[915] = 4010.0
    f = m1_day(mid=mid, highs=highs)
    md, _ = md_db(f)
    t = execution.trade(md, -1, 900, 2, K, 10.0)
    assert t["reason"] == "stop" and t["exit_min"] == 915 and t["X"] > t["P_e"]
    assert t["net_usd"] == pytest.approx(-(t["X"] - t["P_e"]) - 0.10)


def test_conservative_settlement_on_data_gaps():
    f = m1_day(mid=np.full(1440, 4000.0), novol=range(905, 920))      # 15 minutes without volume
    md, _ = md_db(f)
    t = execution.trade(md, 1, 900, 2, K, 10.0)
    assert t["reason"] == "gap" and t["exit_min"] == 919 and t["P_x"] == pytest.approx(t["X"])
    f14 = m1_day(mid=np.full(1440, 4000.0), novol=range(905, 919))    # 14: not a gap
    t14 = execution.trade(execution.Minutes(f14), 1, 900, 2, K, 10.0)
    assert t14["reason"] == "time"
    fm = m1_day(mid=np.full(1440, 4000.0), missing=range(905, 912), novol=range(912, 920))   # rows missing count
    tm = execution.trade(execution.Minutes(fm), 1, 900, 2, K, 10.0)
    assert tm["reason"] == "gap" and tm["exit_min"] == 919


def test_vectorised_trade_equals_the_minute_loop():
    rng = np.random.default_rng(42)
    for i in range(300):
        mid = 4000 + np.cumsum(rng.standard_normal(1440)) * rng.uniform(0.1, 1.0)
        novol = rng.choice(1440, size=int(rng.integers(0, 300)), replace=False)
        if i % 7 == 0:
            s = int(rng.integers(300, 1300))
            novol = np.r_[novol, np.arange(s, s + 20)]
        f = m1_day(mid=mid, novol=novol, spread=float(rng.uniform(0.1, 2.0)))
        md = execution.Minutes(f)
        T = int(rng.integers(7, 92)) * 15
        h = int(rng.integers(1, 9))
        if T + 15 * h > 1410:
            continue
        side = int(rng.choice([-1, 1]))
        F = float(rng.uniform(5, 40))
        t = execution.trade(md, side, T, h, K, F)
        P_e, X, px, reason, m = loop_trade(md, side, T, h, K, F)
        assert (t["P_e"], t["X"], t["P_x"], t["reason"], t["exit_min"]) == (P_e, X, px, reason, m)
