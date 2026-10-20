"""Lab v2 execution edge cases (§2.2, §4): entry at T + 1 on the executable side and its fallback, the S10 unit D, the
3·D disaster stop (stop-first, gap fills), the 15-minute no-quote run, the exit minute T + HOLD·TF − 1, costs and the
stress case, the P4 mid twin, and the decision outcomes (window, day, U, one open trade)."""
import numpy as np
import pandas as pd
import pytest

from lab import execution
import v2_exec
import v2_ledger
import v2_signals

DAY = pd.Timestamp("2026-11-04")          # a Wednesday
FS = 20.0                                 # bp
K_S = 1.0540339626212611


def m1_day(day=DAY, mid=None, spread=0.4, novol=(), missing=(), lows=None, highs=None, opens=None, nan_bid=()):
    rng = np.random.default_rng(0)
    if mid is None:
        mid = 4000 + np.cumsum(rng.standard_normal(1440)) * 0.3
    c = np.asarray(mid, dtype=float)
    o = np.r_[c[0], c[:-1]] if opens is None else np.asarray(opens, dtype=float)
    h = np.maximum(o, c) + 0.05 if highs is None else np.asarray(highs, dtype=float)
    lo = np.minimum(o, c) - 0.05 if lows is None else np.asarray(lows, dtype=float)
    idx = pd.date_range(day, periods=1440, freq="min")
    f = pd.DataFrame({"o": o, "h": h, "l": lo, "c": c}, index=idx)
    for side, sg in (("bid", -1), ("ask", 1)):
        for k in "ohlc":
            f[f"{side}_{k}"] = f[k] + sg * spread / 2
    vol = np.ones(1440)
    vol[list(novol)] = 0
    f["bid_vol"] = vol
    f["ask_vol"] = vol
    for i in nan_bid:
        f.iloc[i, [f.columns.get_loc(f"bid_{k}") for k in "ohlc"]] = np.nan
        f.iloc[i, [f.columns.get_loc(k) for k in "ohlc"]] = np.nan
    return f.drop(index=idx[list(missing)])


def md(f):
    return execution.Minutes(f)


T = 15 * 60          # 15:00
HOLD = 120           # minutes


def test_entry_is_the_open_of_T_plus_1_on_the_executable_side_and_D_is_the_s10_distance():
    f = m1_day()
    long_, short = v2_exec.trade(md(f), 1, T, HOLD, F_S=FS), v2_exec.trade(md(f), -1, T, HOLD, F_S=FS)
    assert long_["entry_min"] == T + 1 and long_["P_e"] == f.ask_o.iloc[T + 1]
    assert short["P_e"] == f.bid_o.iloc[T + 1]
    for t in (long_, short):
        assert t["D"] == t["P_e"] * (1 - np.exp(-K_S * FS / 1e4))
    assert long_["X"] == long_["P_e"] - 3 * long_["D"] and short["X"] == short["P_e"] + 3 * short["D"]


def test_time_exit_is_the_close_of_minute_T_plus_hold_minus_1_and_money():
    f = m1_day()
    t = v2_exec.trade(md(f), 1, T, HOLD, F_S=FS)
    assert t["reason"] == "time" and t["exit_min"] == T + HOLD - 1 and t["P_x"] == f.bid_c.iloc[T + HOLD - 1]
    assert t["net_usd"] == pytest.approx(t["P_x"] - t["P_e"] - 0.10, abs=1e-12)
    assert t["net_stress_usd"] == t["net_usd"] - 0.25
    assert t["R"] == t["net_usd"] / t["D"] and t["y"] == np.clip(t["R"], -2, 2)
    assert t["cost_usd"] == pytest.approx(0.10 + 0.2 + 0.2, abs=1e-9)                   # half spreads 0.2 + 0.2
    assert t["gross_usd"] == pytest.approx(t["net_usd"] + t["cost_usd"], abs=1e-12)


def test_disaster_stop_wins_a_tie_in_the_exit_minute_and_gaps_fill_at_the_open():
    mid = np.full(1440, 4000.0)
    f = m1_day(mid=mid, spread=0.0)
    D = 4000 * (1 - np.exp(-K_S * FS / 1e4))
    lows = f.l.to_numpy().copy()
    lows[T + HOLD - 1] = 4000 - 3 * D - 0.01                       # the exit minute's low reaches X
    t = v2_exec.trade(md(m1_day(mid=mid, spread=0.0, lows=lows)), 1, T, HOLD, F_S=FS)
    assert t["reason"] == "stop" and t["P_x"] == pytest.approx(4000 - 3 * D) and t["exit_min"] == T + HOLD - 1
    assert t["y"] == -2.0 and t["R"] < -3                         # R = (−3D − 0.10)/D, y clipped
    opens = f.o.to_numpy().copy()
    opens[T + 30] = 4000 - 3 * D - 5                               # a gap through X at an open
    lows2 = np.minimum(opens, f.c.to_numpy()) - 0.05
    t = v2_exec.trade(md(m1_day(mid=mid, spread=0.0, opens=opens, lows=lows2)), 1, T, HOLD, F_S=FS)
    assert t["reason"] == "stop" and t["P_x"] == opens[T + 30] and t["exit_min"] == T + 30
    # the entry minute itself: a spread wider than 3·D puts the bid open through X
    t = v2_exec.trade(md(m1_day(mid=mid, spread=7 * D)), 1, T, HOLD, F_S=FS)
    assert t["reason"] == "stop" and t["exit_min"] == T + 1


def test_short_is_the_mirror():
    mid = np.full(1440, 4000.0)
    D = 4000 * (1 - np.exp(-K_S * FS / 1e4))
    highs = np.full(1440, 4000.05)
    highs[T + 10] = 4000 + 3 * D + 0.01
    t = v2_exec.trade(md(m1_day(mid=mid, spread=0.0, highs=highs)), -1, T, HOLD, F_S=FS)
    assert t["reason"] == "stop" and t["P_x"] == pytest.approx(4000 + 3 * D) and t["side"] == -1


def test_a_15_minute_no_quote_run_settles_at_the_disaster_stop():
    f = m1_day(novol=range(T + 20, T + 35))
    t = v2_exec.trade(md(f), 1, T, HOLD, F_S=FS)
    assert t["reason"] == "gap" and t["P_x"] == t["X"] and t["exit_min"] == T + 34
    f = m1_day(missing=range(T + 20, T + 34))                     # 14 minutes: not a run
    assert v2_exec.trade(md(f), 1, T, HOLD, F_S=FS)["reason"] == "time"
    f = m1_day(nan_bid=range(T + 40, T + 55))                     # non-finite exit quotes count too
    assert v2_exec.trade(md(f), 1, T, HOLD, F_S=FS)["reason"] == "gap"


def test_entry_falls_back_to_the_last_finite_executable_close():
    f = m1_day(missing=[T + 1])
    t = v2_exec.trade(md(f), 1, T, HOLD, F_S=FS)
    assert t["P_e"] == f.ask_c.loc[DAY + pd.Timedelta(minutes=T)]
    f = m1_day(nan_bid=[T + 1, T])
    t = v2_exec.trade(md(f), -1, T, HOLD, F_S=FS)
    assert t["P_e"] == f.bid_c.iloc[T - 1]


def test_time_exit_uses_the_last_finite_close_and_no_quote_at_all():
    f = m1_day(missing=[T + HOLD - 1, T + HOLD - 2])
    t = v2_exec.trade(md(f), 1, T, HOLD, F_S=FS)
    assert t["reason"] == "time" and t["exit_min"] == T + HOLD - 3
    empty = m1_day(missing=range(0, T + 2))
    t = v2_exec.trade(md(empty), 1, T, HOLD, F_S=FS)
    assert t["status"] == "no_quote" and np.isnan(t["P_e"])
    with pytest.raises(ValueError):
        v2_exec.trade(md(m1_day()), 1, T, HOLD, F_S=np.nan)


def test_the_twin_is_a_long_on_the_mid_with_the_trades_D_and_no_cost():
    f = m1_day()
    tr = v2_exec.trade(md(f), -1, T, HOLD, F_S=FS)
    tw = v2_exec.trade(md(f), 1, T, HOLD, twin_D=tr["D"])
    assert tw["side"] == 1 and tw["P_e"] == f.o.iloc[T + 1] and tw["D"] == tr["D"]
    assert tw["X"] == tw["P_e"] - 3 * tr["D"] and tw["P_x"] == f.c.iloc[T + HOLD - 1]
    assert tw["R"] == (tw["P_x"] - tw["P_e"]) / tr["D"] and tw["cost_usd"] == 0.0


# ---------------------------------------------------------------- decisions of one seed on one day
def sigs(T_list, vals, hold_min=HOLD, tf_min=15, day=DAY):
    s = v2_signals.DaySignals(sid="S5", day=day, tf_min=tf_min, hold_min=hold_min)
    for Tm, v in zip(T_list, vals):
        s.start.append(Tm - tf_min)
        s.T.append(Tm)
        s.online.append(v)
        s.full.append(v)
        s.window.append(v2_signals.in_window(Tm, hold_min, day.dayofweek))
    return s


def di(f, holiday=False, F=FS):
    FS_ = np.full(23, F)
    return v2_ledger.DayInputs(day=f.index[0].normalize(), weekday=int(f.index[0].dayofweek), holiday=holiday,
                               md=md(f), F_S=FS_)


REC = {"id": "S5"}


def test_window_rule():
    assert v2_signals.in_window(90, 120, 2) and not v2_signals.in_window(75, 120, 2)
    assert v2_signals.in_window(1290, 120, 2) and not v2_signals.in_window(1305, 120, 2)    # exit ends 23:30
    assert v2_signals.in_window(1245, 120, 4) and not v2_signals.in_window(1260, 120, 4)    # Friday 22:45


def test_outcomes_in_order_and_one_open_trade():
    f = m1_day()
    s = sigs([60, 900, 960, 1020, 1035, 1350], [1, -1, 1, 1, -1, 1])
    decs, trades, twins = v2_ledger.rule_day(REC, di(f), s, "now", "c0de")
    assert [d["outcome"] for d in decs] == ["abstain_window", "trade", "ignored_open", "trade", "ignored_open",
                                            "abstain_window"]
    assert [d["T"] for d in decs] == ["01:00", "15:00", "16:00", "17:00", "17:15", "22:30"]
    assert [t["T"] for t in trades] == ["15:00", "17:00"] and [t["side"] for t in trades] == [-1, 1]
    assert [t["entry_model"] for t in trades] == ["15:01", "17:01"] and len(twins) == 2
    assert all(t["exit_model"] == v2_ledger.hhmm(v2_exec.trade(md(f), t["side"], int(t["T"][:2]) * 60, HOLD,
                                                               F_S=FS)["exit_min"]) for t in trades)
    decs, trades, _ = v2_ledger.rule_day(REC, di(f, holiday=True), s, "now", "c0de")
    assert [d["outcome"] for d in decs] == ["abstain_window", "abstain_day", "abstain_day", "abstain_day",
                                            "abstain_day", "abstain_window"] and trades == []
    decs, trades, _ = v2_ledger.rule_day(REC, di(f, F=np.nan), s, "now", "c0de")
    assert [d["outcome"] for d in decs][1:5] == ["abstain_U"] * 4 and trades == []
    decs, _, _ = v2_ledger.rule_day(REC, di(f, F=0.0), s, "now", "c0de")
    assert decs[1]["outcome"] == "abstain_U" and decs[1]["F_RAW_S"] == "0.0"


def test_the_entry_slot_is_the_hour_of_T_plus_1():
    f = m1_day()
    d = di(f)
    d.F_S[:] = np.nan
    d.F_S[14] = FS                     # slot 14 = the 15:00 hour
    s = sigs([900, 1020], [1, 1])      # T 15:00 -> entry 15:01 (slot 14); T 17:00 -> entry 17:01 (slot 16)
    decs, trades, _ = v2_ledger.rule_day(REC, d, s, "now", "c0de")
    assert [x["outcome"] for x in decs] == ["trade", "abstain_U"]


def test_zero_signals_make_no_rows_and_full_values_are_used_only_by_the_tripwire():
    f = m1_day()
    s = sigs([900, 1020], [0, 0])
    assert v2_ledger.rule_day(REC, di(f), s, "now", "c0de") == ([], [], [])
    s.full = [1, 0]
    decs, trades, _ = v2_ledger.rule_day(REC, di(f), s, "now", "c0de", values="full")
    assert len(decs) == 1 and len(trades) == 1
