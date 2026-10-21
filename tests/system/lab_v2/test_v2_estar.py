"""Exact E* and the v2 statistics (§2.3, §4): α_v2 = 0.005 (A1 item 5), γ 0.30/0.30/0.20/0.20, E* = 1/(α·γ) stored
exactly; P1 against the exact rational; P4 with μ̄; promotion, demotion and retirement as v1."""
import json
from fractions import Fraction
from pathlib import Path

import numpy as np

import v2_ledger
import v2_registry
from lab import eproc

ROOT = Path(__file__).resolve().parents[3]


def test_alpha_and_gamma():
    assert v2_registry.ALPHA_V2 == Fraction(5, 1000)
    assert float(v2_registry.ALPHA_V2) == eproc.alpha_version(2) == 0.005
    assert eproc.ALPHA_V1 + eproc.alpha_version(2) <= 0.045 + 1e-15      # the program FDR stays <= 0.045 + 0.0
    assert v2_registry.GAMMA == {"S2": Fraction(3, 10), "S3": Fraction(3, 10), "S4": Fraction(1, 5),
                                 "S5": Fraction(1, 5)}
    assert sum(v2_registry.GAMMA.values()) == 1


def test_e_star_is_exact():
    assert v2_registry.e_star_exact(Fraction(3, 10)) == Fraction(2000, 3)
    assert v2_registry.e_star_exact(Fraction(1, 5)) == 1000
    for sid, exact, dbl in (("S2", "2000/3", 666.6666666666666), ("S3", "2000/3", 666.6666666666666),
                            ("S4", "1000", 1000.0), ("S5", "1000", 1000.0)):
        rec = json.loads((ROOT / v2_registry.REG_REL / f"{sid}.json").read_text())
        assert rec["E_star_exact"] == exact and rec["E_star"] == dbl == float(Fraction(exact))
        assert rec["alpha_exact"] == "1/200" and rec["D_at_arrival"] == 0
        assert Fraction(rec["gamma_exact"]) * Fraction(rec["alpha_exact"]) * Fraction(rec["E_star_exact"]) == 1
        assert rec["alpha_j"] == float(Fraction(rec["alpha_exact"]) * Fraction(rec["gamma_exact"]))


def test_p1_compares_with_the_exact_rational(monkeypatch):
    """E equal to the double nearest 2000/3 (just below it) does not reach E* = 2000/3 exactly; v2 passes the exact
    rational to v1's promotion_checks, whose `E >= E_star` is then an exact float/Fraction comparison."""
    es = Fraction(2000, 3)
    below = float(es)
    assert Fraction(below) < es
    tr = [{"day": "2027-01-04", "side": 1, "y": 0.5, "R": 0.5, "net_usd": 1.0, "net_stress_usd": 0.5}]
    monkeypatch.setattr(eproc, "e_value", lambda y, lambdas=eproc.LAMBDAS: below)
    assert eproc.promotion_checks(tr, es, 0.0, True)["P1"] is False
    assert eproc.promotion_checks(tr, below, 0.0, True)["P1"] is True          # the double alone would pass
    assert eproc.promotion_checks(tr, Fraction(1000), 0.0, True)["P1"] is False
    monkeypatch.setattr(eproc, "e_value", lambda y, lambdas=eproc.LAMBDAS: 1000.0)
    assert eproc.promotion_checks(tr, Fraction(1000), 0.0, True)["P1"] is True
    assert v2_ledger.e_star({"E_star_exact": "2000/3"}) == es


def test_p4_uses_the_mean_twin_over_the_seeds_final_trades(tmp_path):
    lab = tmp_path
    v2_ledger.append(lab / "trades.csv", v2_ledger.TRADE_COLS, [
        {"id": "S2", "day": "2027-01-04", "T": "10:00", "side": 1, "status": "final", "y": 0.1, "R": 0.1,
         "net_usd": 1, "net_stress_usd": 0.75, "recorded_utc": "a"},
        {"id": "S2", "day": "2027-01-05", "T": "10:00", "side": -1, "status": "final", "y": 0.3, "R": 0.3,
         "net_usd": 1, "net_stress_usd": 0.75, "recorded_utc": "a"},
        {"id": "S3", "day": "2027-01-05", "T": "14:30", "side": 1, "status": "final", "y": 9, "R": 9,
         "net_usd": 1, "net_stress_usd": 0.75, "recorded_utc": "a"}])
    v2_ledger.append(lab / "twins.csv", v2_ledger.TWIN_COLS, [
        {"id": "S2", "day": "2027-01-04", "T": "10:00", "status": "final", "R_twin": 0.4},
        {"id": "S2", "day": "2027-01-05", "T": "10:00", "status": "final", "R_twin": 0.2},
        {"id": "S3", "day": "2027-01-05", "T": "14:30", "status": "final", "R_twin": 5.0}])
    st = {"promoted_utc": None}
    s = v2_ledger.rule_stats(lab, {"id": "S2"}, st)
    assert s["mu_bar"] == np.mean([0.4, 0.2]) and s["n"] == 2
    # P4: Σ (R_i − side_i·μ̄) = (0.1 − 0.3) + (0.3 + 0.3) = 0.4 > 0
    chk = eproc.promotion_checks(s["trades"], Fraction(2000, 3), s["mu_bar"], True)
    assert chk["P4"] is True
    assert (np.array([0.1, 0.3]) - np.array([1, -1]) * 0.3).sum() > 0


def test_states_promote_demote_retire_as_v1(tmp_path):
    """A seed with a large synthetic edge is promoted only when every conjunct holds; then demoted by D2."""
    recs = [json.loads((ROOT / v2_registry.REG_REL / "S4.json").read_text())]
    lab = tmp_path
    rows, tw = [], []
    days = [d.strftime("%Y-%m-%d") for d in __import__("pandas").bdate_range("2027-01-04", periods=70)]
    for d in days:
        rows.append({"id": "S4", "day": d, "T": "16:25", "side": 1, "status": "final", "y": 1.2, "R": 1.2,
                     "net_usd": 5, "net_stress_usd": 4.75, "recorded_utc": "2027-01-01T00:00:00Z"})
        tw.append({"id": "S4", "day": d, "T": "16:25", "status": "final", "R_twin": 0.0})
    v2_ledger.append(lab / "trades.csv", v2_ledger.TRADE_COLS, rows)
    v2_ledger.append(lab / "twins.csv", v2_ledger.TWIN_COLS, tw)
    v2_ledger.append(lab / "lab_days.csv", v2_ledger.DAY_COLS, [{"day": d, "settled_utc": "x"} for d in days])
    sts = {"S4": {"state": "PAPER", "registered_utc": "2026-11-10T03:20:00Z", "first_day": "2027-01-04",
                  "promoted_utc": None, "demoted_utc": None, "retired_utc": None, "promotable": True}}
    import pandas as pd
    today = pd.Timestamp(days[-1])
    ev = v2_ledger.update_states(lab, recs, sts, [], "2027-04-10T03:20:00Z", True, "r", "h", today)
    assert [e["event"] for e in ev] == ["PROMOTED"] and sts["S4"]["state"] == "LIVE"
    assert eproc.e_value([1.2] * 70) >= 1000
    # post-promotion losses: D2 (Σ R <= −5)
    v2_ledger.append(lab / "trades.csv", v2_ledger.TRADE_COLS, [
        {"id": "S4", "day": "2027-04-12", "T": "16:25", "side": 1, "status": "final", "y": -2, "R": -3.05,
         "net_usd": -1, "net_stress_usd": -1.25, "recorded_utc": "2027-04-13T03:20:00Z"}] * 2)
    v2_ledger.append(lab / "lab_days.csv", v2_ledger.DAY_COLS, [{"day": "2027-04-12", "settled_utc": "x"}])
    ev = v2_ledger.update_states(lab, recs, sts, [{"event": "PROMOTED"}], "2027-04-13T03:20:00Z", True, "r", "h",
                                 pd.Timestamp("2027-04-12"))
    assert [(e["event"], e["reason"]) for e in ev] == [("DEMOTED", "D2")]
