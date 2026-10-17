"""The lab state machine on synthetic ledger rows: promotion, demotion, retirement, suspension (L2 §9.3-§9.5)."""
import numpy as np
import pandas as pd
import pytest

import run
from lab import ledger, registry


def setup_lab(tmp_path, R, start_day="2026-11-02", recorded="2027-01-10T03:20:00Z"):
    P = run.Paths(tmp_path)
    for r in registry.seed_records():
        registry.write(P.reg, r)
    recs = registry.load(P.reg)
    ev = registry.register_new(recs, [], "2026-10-27T03:20:00Z", "1", "h", {"S1", "S1R", "C1"})
    registry.append_events(P.reg / "events.csv", ev)
    days = [d for d in pd.date_range(start_day, periods=400, freq="D") if d.dayofweek < 4][:len(R)]
    rows = [{"id": "S1", "day": d.strftime("%Y-%m-%d"), "T": "2300", "side": -1, "status": "final", "R": r,
             "y": float(np.clip(r, -2, 2)), "net_usd": r * 5, "net_stress_usd": r * 5 - 0.25, "recorded_utc": recorded}
            for d, r in zip(days, R)]
    ledger.append(P.lab / "trades.csv", ledger.TRADE_COLS, rows)
    tw = [{"key": "2300|2|H10|1", "day": d.strftime("%Y-%m-%d"), "R_twin": 0.0, "recorded_utc": recorded}
          for d in days]
    ledger.append(P.lab / "twins.csv", ledger.TWIN_COLS, tw)
    ledger.append(P.lab / "lab_days.csv", ledger.DAY_COLS, [{"day": rows[-1]["day"], "settled_utc": recorded}])
    return P, recs, days


def states_now(P, recs):
    return registry.states(recs, registry.read_events(P.reg / "events.csv"), "2026-11-02")


def test_promotion_then_demotion_then_retirement(tmp_path):
    P, recs, days = setup_lab(tmp_path, [0.6] * 60)
    sts = states_now(P, recs)
    today = pd.Timestamp(days[-1]) + pd.Timedelta(days=1)
    ev = ledger.update_states(P.lab, recs, sts, registry.read_events(P.reg / "events.csv"), "2027-03-01T03:20:00Z",
                              True, "2", "h2", today)
    assert [(e["id"], e["event"]) for e in ev] == [("S1", "PROMOTED")]
    sts = states_now(P, recs)
    assert sts["S1"]["state"] == "LIVE" and sts["S1"]["promoted_utc"] == "2027-03-01T03:20:00Z"
    # post-promotion losses: K >= 10 (D1)
    post = [{"id": "S1", "day": "2027-03-0%d" % i, "T": "2300", "side": -1, "status": "final", "R": -2.0, "y": -2.0,
             "net_usd": -10.0, "net_stress_usd": -10.25, "recorded_utc": "2027-03-05T03:20:00Z"} for i in range(2, 9)]
    ledger.append(P.lab / "trades.csv", ledger.TRADE_COLS, post)
    ledger.append(P.lab / "lab_days.csv", ledger.DAY_COLS, [{"day": "2027-03-08", "settled_utc": "x"}])
    ev = ledger.update_states(P.lab, recs, sts, registry.read_events(P.reg / "events.csv"), "2027-03-09T03:20:00Z",
                              True, "3", "h3", pd.Timestamp("2027-03-09"))
    assert [(e["event"], e["reason"]) for e in ev] == [("DEMOTED", "D1")]
    sts = states_now(P, recs)
    ev = ledger.update_states(P.lab, recs, sts, registry.read_events(P.reg / "events.csv"), "2027-03-12T03:20:00Z",
                              True, "4", "h4", pd.Timestamp("2027-03-12"))
    assert ev == []                                                      # shown for 5 trading days
    ev = ledger.update_states(P.lab, recs, states_now(P, recs), registry.read_events(P.reg / "events.csv"),
                              "2027-03-16T03:20:00Z", True, "5", "h5", pd.Timestamp("2027-03-16"))
    assert [(e["event"], e["reason"]) for e in ev] == [("RETIRED", "demoted")]


def test_no_promotion_without_every_conjunct(tmp_path):
    P, recs, days = setup_lab(tmp_path, [0.6] * 60)
    sts = states_now(P, recs)
    ev = ledger.update_states(P.lab, recs, sts, registry.read_events(P.reg / "events.csv"), "2027-03-01T03:20:00Z",
                              False, "2", "h2", pd.Timestamp(days[-1]))           # P7: lab not running
    assert ev == []
    P2, recs2, days2 = setup_lab(tmp_path / "b", [0.6] * 39)                      # P2: n < 40
    ev = ledger.update_states(P2.lab, recs2, states_now(P2, recs2), [], "2027-03-01T03:20:00Z", True, "2", "h2",
                              pd.Timestamp(days2[-1]))
    assert ev == []


def test_paper_retirement_after_150_losing_trades(tmp_path):
    P, recs, days = setup_lab(tmp_path, [-0.1] * 150)
    ev = ledger.update_states(P.lab, recs, states_now(P, recs), registry.read_events(P.reg / "events.csv"),
                              "2027-12-01T03:20:00Z", True, "2", "h2", pd.Timestamp(days[-1]))
    assert [(e["id"], e["event"], e["reason"]) for e in ev] == [("S1", "RETIRED", "n150")]


def test_live_rule_is_suspended_when_stale_and_resumes(tmp_path):
    P, recs, days = setup_lab(tmp_path, [0.6] * 60)
    ledger.update_states(P.lab, recs, states_now(P, recs), registry.read_events(P.reg / "events.csv"),
                         "2027-03-01T03:20:00Z", True, "2", "h2", pd.Timestamp(days[-1]))
    late = pd.Timestamp(days[-1]) + pd.Timedelta(days=10)                        # > 5 trading days, no settled day
    ev = ledger.update_states(P.lab, recs, states_now(P, recs), registry.read_events(P.reg / "events.csv"),
                              "2027-03-10T03:20:00Z", True, "3", "h3", late)
    assert [(e["event"], e["reason"]) for e in ev] == [("SUSPENDED", "S-a: no settled day")]
    ledger.append(P.lab / "lab_days.csv", ledger.DAY_COLS, [{"day": late.strftime("%Y-%m-%d"), "settled_utc": "x"}])
    ev = ledger.update_states(P.lab, recs, states_now(P, recs), registry.read_events(P.reg / "events.csv"),
                              "2027-03-11T03:20:00Z", True, "4", "h4", late)
    assert [e["event"] for e in ev] == ["RESUMED"]


def test_a_halt_suspends_live_rules(tmp_path, monkeypatch):
    P, recs, days = setup_lab(tmp_path, [0.6] * 60)
    ledger.update_states(P.lab, recs, states_now(P, recs), registry.read_events(P.reg / "events.csv"),
                         "2027-03-01T03:20:00Z", True, "2", "h2", pd.Timestamp(days[-1]))
    monkeypatch.setattr(run.frozen_hashes, "check", lambda root=None: ["x: differs"])
    import synth
    synth.world(P.data, first="2026-09-01", last="2026-09-10")
    info, halted = run.one_run(P, pd.Timestamp("2027-03-02 03:20", tz="UTC"), "synthetic", "6", "h6", fetch_on=False)
    assert halted
    ev = registry.read_events(P.reg / "events.csv")
    assert (ev[-1]["id"], ev[-1]["event"], ev[-1]["reason"]) == ("S1", "SUSPENDED", "S-a: lab paused")


def test_live_rule_shows_its_post_promotion_record_only(tmp_path):
    """§3 item 11: status and dashboard show a LIVE rule's post-promotion record only."""
    P, recs, days = setup_lab(tmp_path, [0.6] * 60)
    ledger.update_states(P.lab, recs, states_now(P, recs), registry.read_events(P.reg / "events.csv"),
                         "2027-03-01T03:20:00Z", True, "2", "h2", pd.Timestamp(days[-1]))
    post = [{"id": "S1", "day": "2027-03-0%d" % i, "T": "2300", "side": -1, "status": "final", "R": 0.1, "y": 0.1,
             "net_usd": 0.5, "net_stress_usd": 0.25, "recorded_utc": "2027-03-05T03:20:00Z"} for i in (2, 3, 4)]
    ledger.append(P.lab / "trades.csv", ledger.TRADE_COLS, post)
    ev = registry.read_events(P.reg / "events.csv")
    lab = run.lab_summary(P, recs, states_now(P, recs), ev, "RUNNING", "2026-11-02")
    s1 = next(r for r in lab["rules"] if r["id"] == "S1")
    assert s1["state"] == "LIVE" and s1["n"] == 3 and s1["net_sum"] == pytest.approx(1.5)
    assert s1["record"] == "post-promotion" and lab["n_live"] == 1 and lab["live"][0]["n_post"] == 3
    lines = __import__("publish").system_csv("2027-03-05T03:20:00Z", {"green_ok": 1, "asof": "2027-03-05"},
                                             {"asof": None, "mult": {b: (1.0, 0) for b in
                                                                     __import__("system_common").BUCKETS}}, lab)
    assert "lab_live_1_npost,3" in lines and "lab_n_live,1" in lines
