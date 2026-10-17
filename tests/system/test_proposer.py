"""The proposer (L2 §10 as amended): space, null, selection, schedule, and its calibration under a synthetic null."""
import numpy as np
import pandas as pd
import pytest

import bars
from lab import execution, grammar, ledger, proposer, registry

SD_BP = np.where(np.arange(1440) // 60 < 10, 0.9, np.where(np.arange(1440) // 60 < 15, 1.2, 1.6))


def rw_days(n_days, seed, start="2026-11-02"):
    """Synthetic random-walk model-clock days (no drift): DayInputs with constant per-slot forecasts."""
    rng = np.random.default_rng(seed)
    days = [d for d in pd.date_range(start, periods=n_days * 2, freq="D") if d.dayofweek < 5][:n_days]
    p = 4200.0
    hours = np.arange(23) + 1
    sd_h = np.where(hours < 10, 0.9, np.where(hours < 15, 1.2, 1.6))
    F_H1 = 1.6 * sd_h * np.sqrt(60)                                    # about the expected hour range, bp
    rest = np.array([(10 if h < 10 else 15 if h < 15 else 24) - h for h in hours])
    F_S = F_H1 * np.sqrt(rest)
    out = []
    for d in days:
        flat = (np.arange(1440) < 60) | (rng.uniform(size=1440) < 0.05)
        step = np.where(flat, 0.0, rng.standard_normal(1440) * SD_BP * 1e-4)
        c = p * np.exp(np.cumsum(step))
        o = np.r_[p, c[:-1]]
        wig = np.where(flat, 0.0, np.abs(rng.standard_normal(1440)) * SD_BP * 0.5e-4)
        h = np.maximum(o, c) * np.exp(wig)
        l = np.minimum(o, c) * np.exp(-wig)
        p = c[-1]
        idx = pd.date_range(d, periods=1440, freq="min")
        half = (0.30 + 0.20 * rng.uniform(size=1440)) / 2
        f = pd.DataFrame({"o": o, "h": h, "l": l, "c": c}, index=idx)
        for side, sg in (("bid", -1), ("ask", 1)):
            for k in "ohlc":
                f[f"{side}_{k}"] = f[k] + sg * half
        f["bid_vol"] = f["ask_vol"] = np.where(flat, 0.0, 1.0)
        lb = bars.lab_bars(f)
        out.append(ledger.DayInputs(day=d, weekday=d.dayofweek, holiday=False, event_day=False,
                                    db=grammar.DayBars(lb), md=execution.Minutes(f), F_H1=F_H1, F_S=F_S))
    return out


def test_space_has_exactly_1920_valid_rules():
    sp = proposer.space()
    assert len(sp) == 1920
    assert len({grammar.canonical_json(s) for s in sp}) == 1920
    for s in sp:
        v = grammar.validate(s)
        T = grammar.minutes(v["T"])
        assert 180 <= T <= 1380 and T % 30 == 0
        assert T + 15 * v["hold"] <= 1410 and v["stop"] == ("H10" if v["hold"] <= 4 else "S10")
    pairs = {(s["T"], s["hold"]) for s in sp}
    assert len(pairs) == 160
    assert len({grammar.question_key(s) for s in sp}) == 960                  # FOLLOW and FADE share a question


def test_null_is_deterministic_for_its_seed():
    rng = np.random.default_rng(1)
    G = np.where(rng.uniform(size=(50, 60)) < 0.4, rng.normal(size=(50, 60)), np.nan)
    C = np.where(np.isfinite(G), 0.1, np.nan)
    a = proposer.null_max(G, C, 20270102, B=200)
    b = proposer.null_max(G, C, 20270102, B=200)
    c = proposer.null_max(G, C, 20270130, B=200)
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    # the vectorised t* equals a direct computation for one replicate
    S = np.random.default_rng(20270102).choice(np.array([-1.0, 1.0]), size=(200, 60))
    Rs = S[0] * G - C
    t, _, _ = proposer.tstats(Rs)
    assert np.nanmax(t) == pytest.approx(a[0], rel=1e-9)


def test_selection_rules():
    sp = proposer.space()
    t = np.full(len(sp), np.nan)
    mean = np.full(len(sp), 0.1)
    same_hour = [j for j, s in enumerate(sp) if s["T"] in ("1500", "1530")][:3]
    other = next(j for j, s in enumerate(sp) if s["T"] == "1800")
    t[same_hour], t[other] = [5.0, 4.9, 4.8], 4.7
    chosen = proposer.select(sp, t, mean, 3.0, [], 0)
    assert chosen == [same_hour[0], other]                       # at most 2, distinct floor-hour(T)
    assert proposer.select(sp, t, mean, 3.0, [grammar.question_key(sp[same_hour[0]])], 0)[0] != same_hour[0]
    assert proposer.select(sp, t, mean, 3.0, [], 9) == [same_hour[0]]          # the cap of 10 active
    assert proposer.select(sp, t, mean, 3.0, [], 10) == []
    assert proposer.select(sp, t, np.full(len(sp), -0.1), 3.0, [], 0) == []     # mean R must be > 0


def test_training_days_never_precede_the_lab():
    days = rw_days(3, 1)
    with pytest.raises(AssertionError):
        proposer.run(days, "2026-11-07", "2026-11-03", [], 0, specs=proposer.space()[:10], B=10)


def test_schedule():
    assert proposer.due("2027-01-02", 40, []) == "2027-01-02"
    assert proposer.due("2027-01-02", 39, []) is None
    assert proposer.due("2027-01-05", 45, []) is None                           # not a Saturday
    done = ["2027-01-02"]
    assert proposer.due("2027-01-23", 60, done) is None
    assert proposer.due("2027-01-30", 60, done) == "2027-01-30"
    assert proposer.due("2027-02-02", 60, done) == "2027-01-30"                 # a missed Saturday runs late
    assert proposer.due("2027-02-02", 60, done + ["2027-01-30"]) is None


def indicator_accepts(title):
    """A1 item 3, as the indicator's CleanTitle applies it (xauusd-quant 6b5dc99): 1..31 characters, each an Arabic
    letter (U+0621..U+064A without U+0640), a digit or a space; the first an Arabic letter, the last not a space."""
    def letter(c):
        return "\u0621" <= c <= "\u064a" and c != "\u0640"
    if not 1 <= len(title) <= 31:
        return False
    if not all(letter(c) or c == " " or "0" <= c <= "9" or "\u0660" <= c <= "\u0669" for c in title):
        return False
    return letter(title[0]) and title[-1] != " "


def test_every_title_passes_the_indicator_rule_and_names_its_hour():
    """A1 item 3: every proposer title of the space, and every seed title, is shown by the indicator, and proposer
    titles carry their decision time, so two rules at different times never share a title."""
    prefix = "قاعدة اتجاه اجتازت الاختبار: "
    sp = proposer.space()
    by_title = {}
    for s in sp:
        t = proposer.title_for(s)
        assert indicator_accepts(t) and registry.title_ok(t), t
        assert len(prefix + t) <= 60 and not any("a" <= ch.lower() <= "z" for ch in t)
        T = grammar.minutes(s["T"])
        assert t.endswith(f"قبل {T // 60}" + (f" و{T % 60}" if T % 60 else "")), t
        by_title.setdefault(t, set()).add((s["side"][0], s["side"][1], s["T"]))
    assert len(by_title) == 246 and all(len(v) == 1 for v in by_title.values())     # 41 times x 3 windows x 2
    assert proposer.title_for({"T": "1500", "side": ["FADE", "1445", "1500"]}) == "عكس حركة ربع الساعة قبل 15"
    assert proposer.title_for({"T": "2230", "side": ["FOLLOW", "2200", "2230"]}) == "تتبع حركة نصف الساعة قبل 22 و30"
    assert proposer.title_for({"T": "0300", "side": ["FADE", "0200", "0300"]}) == "عكس حركة الساعة قبل 3"
    for r in registry.seed_records():
        assert indicator_accepts(r["title_ar"]) and len(prefix + r["title_ar"]) <= 60, r["id"]


def test_proposals_get_their_gamma_D_and_E_star_from_the_frozen_code(tmp_path):
    """A1 item 9: numbering k, γ_k, D and E*_k of new proposals come from proposer.new_records."""
    recs = registry.seed_records()
    sp = proposer.space()
    rep = {"run_date": "2027-01-02", "chosen_specs": [sp[0], sp[500]], "chosen_t": [4.1, 3.9], "q95": 3.5}
    events = [{"event": "PROMOTED", "id": "S1"}]
    new = proposer.new_records(rep, recs, events)
    assert [r["id"] for r in new] == ["P001", "P002"]
    assert [r["gamma"] for r in new] == [0.70 / 2, 0.70 / 6]
    assert [r["D_at_arrival"] for r in new] == [1, 1]
    assert new[0]["E_star"] == pytest.approx(1 / (0.04 * 0.35 * 2))
    later = proposer.new_records(rep | {"chosen_specs": [sp[900]], "chosen_t": [5.0]}, recs + new, [])
    assert later[0]["id"] == "P003" and later[0]["gamma"] == pytest.approx(0.70 / 12)


def test_plan_schedule_and_training_days():
    sts = {"S1": {"first_day": "2026-11-02", "state": "PAPER"}, "C1": {"first_day": "2026-11-02", "state": "REF"}}
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-11-02", periods=70)]
    assert proposer.plan("2027-01-02", days[:39], sts, [], True) is None              # fewer than 40 days
    pl = proposer.plan("2027-01-02", days[:45], sts, [], True)
    assert pl["date"] == "2027-01-02" and pl["first"] == "2026-11-02" and pl["train_days"] == days[:45]
    pl = proposer.plan("2027-01-30", days, sts, ["2027-01-02"], True)
    assert pl["date"] == "2027-01-30" and len(pl["train_days"]) == 60
    assert all(d < "2027-01-30" for d in pl["train_days"]) and pl["train_days"] == [
        d for d in days if d < "2027-01-30"][-60:]
    assert proposer.plan("2027-01-02", days[:45], sts, [], False) is None              # lab paused


@pytest.mark.slow
def test_proposer_null_calibration():
    """200 random-walk worlds of 60 days: the proposal rate is 5% +- 3.1% (L2 §16.1)."""
    sp = proposer.space()
    proposals = 0
    for w in range(200):
        days = rw_days(60, 1000 + w)
        rep = proposer.run(days, "2027-01-02", "2026-11-02", [], 0, specs=sp)
        proposals += bool(rep["chosen"])
    rate = proposals / 200
    assert abs(rate - 0.05) <= 0.031, rate
