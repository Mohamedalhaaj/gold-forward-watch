"""The synthetic end-to-end dry run (§4): v1 + v2 on the synthetic world, byte-identical across two runs and equal to
the committed judge fixture (tests/judge_fixtures/synthetic_world), with the registration, START, ledger and publish
contracts checked on its output."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import numpy as np

import publish
import run_v2
import v2_data
import v2_exec
import v2_ledger
import v2_lookback
import v2_synth

FIXTURE = Path(__file__).resolve().parents[2] / "judge_fixtures" / "synthetic_world"
FIXTURE_DOCS = {"README.md", "MANIFEST.sha256"}


def tree(base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(base).rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def dry(tmp_path_factory):
    out = tmp_path_factory.mktemp("dry_a")
    assert run_v2.main(["--dry", "--synthetic", "--out", str(out)]) == 0
    return out


def test_two_runs_are_byte_identical(dry, tmp_path):
    out_b = tmp_path / "dry_b"
    assert run_v2.main(["--dry", "--synthetic", "--out", str(out_b)]) == 0
    a, b = tree(dry), tree(out_b)
    assert a == b and len(a) > 700


def test_the_committed_judge_fixture_is_this_run(dry):
    got = {k: v for k, v in tree(FIXTURE).items() if k not in FIXTURE_DOCS}
    assert got == tree(dry)
    man = dict(line.split("  ", 1)[::-1] for line in (FIXTURE / "MANIFEST.sha256").read_text().splitlines())
    assert man == got


def test_registration_start_and_first_day(dry):
    P = run_v2.Paths(dry)
    s1 = json.loads((dry / "reports/system/START.json").read_text())
    s2 = json.loads((P.rep / "START.json").read_text())
    assert s1["start"] == "2026-11-02" and s2["v1_start"] == "2026-11-02"
    assert s2["first_cloud_run_utc"] == "2026-11-03T03:20:00Z" and s2["start"] == "2026-11-09"
    ev = pd.read_csv(P.reg / "events.csv")
    reg = ev[ev.event == "REGISTERED"]
    assert list(reg.id) == ["S2", "S3", "S4", "S5"] and set(reg.utc) == {"2026-11-03T03:20:00Z"}
    assert set(reg.run_id) == {"dry"} and set(reg.head_sha) == {"dry-placeholder"}
    s = json.loads((P.rep / "summary.json").read_text())
    assert {r["first_day"] for r in s["rules"]} == {"2026-11-09"}


def test_ledgers(dry):
    P = run_v2.Paths(dry)
    days = pd.read_csv(P.rep / "lab_days.csv")
    assert days.day.min() == "2026-11-09" and days.day.max() == "2026-12-04" and len(days) == 20
    dec = pd.read_csv(P.rep / "decisions.csv")
    tr = pd.read_csv(P.rep / "trades.csv")
    assert (dec.day >= "2026-11-09").all() and set(dec.outcome) <= set(v2_ledger.OUTCOMES)
    assert len(tr) == (dec.outcome == "trade").sum() and set(tr.status) == {"final"}
    assert (dec[dec.day.isin(["2026-11-26", "2026-11-27"])].outcome == "abstain_day").all()   # NYSE holidays
    ep = pd.read_csv(P.rep / "eproc.csv")
    tw = pd.read_csv(P.rep / "twins.csv")
    assert len(ep) == len(tr) == len(tw)
    for sid, g in ep.groupby("id"):
        assert list(g.trade_no) == list(range(1, len(g) + 1))
    au = pd.read_csv(P.rep / "audit.csv")
    assert len(au) == 4 * len(days) and set(au.result) == {"ok"}
    assert au.n_mismatch_window.sum() == 0 and au.n_mismatch_outside.sum() == 0
    assert (pd.to_datetime(tr.day + " " + tr.entry_model) - pd.to_datetime(tr.day + " " + tr["T"])).eq(
        pd.Timedelta(minutes=1)).all()
    assert v2_ledger.ledger_consistent(P.rep) == []
    assert not (P.rep / "HALT.md").exists()


def test_publish(dry):
    P = run_v2.Paths(dry)
    s = json.loads((P.rep / "summary.json").read_text())
    assert s["state"] == "RUNNING" and s["days"] == 20 and s["n_paper"] == 4
    assert {r["id"]: r.get("warmup") for r in s["rules"]}["S3"] is True
    kv = publish.parse_system_csv((dry / "reports/forward_site/system/VolMapSystem.csv").read_text())
    assert kv["lab2_state"] == "RUNNING" and kv["lab2_n_paper"] == "4" and kv["lab2_days"] == "15"   # previous run's
    html = (P.site / "index.html").read_text()
    assert "المختبر، الإصدار الثاني" in html and "في مرحلة الإحماء حتى تكتمل بياناتها" in html
    assert json.loads((P.site / "lab_v2.json").read_text())["c1"]["n"] > 0
    assert v2_lookback.complete(P.lb)


def _minutes(dry, day):
    """The model day's M1 (execution.Minutes) of the dry run's synthetic store, as lab v2 reads it."""
    P = run_v2.Paths(dry)
    now = pd.Timestamp("2026-12-05 03:20", tz="UTC")
    cu = v2_data.v1_complete_utc(P.v1data, now)
    mf = v2_data.model_frame(v2_data.load_m1(P.lb, P.v1data, now, cu))
    return v2_ledger.execution.Minutes(v2_data.minutes_of_day(mf, day))


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def test_the_fixture_reaches_every_reachable_branch(dry):
    """Register R-FX (lab review MF9): the edge edits (v2_synth.EDGES) make the dry run, and so the judge fixture,
    reach every reachable decision and execution branch of R-V2-16..19 at least once."""
    P = run_v2.Paths(dry)
    dec = pd.read_csv(P.rep / "decisions.csv", dtype=str, keep_default_na=False)
    tr = pd.read_csv(P.rep / "trades.csv", dtype=str, keep_default_na=False)
    tw = pd.read_csv(P.rep / "twins.csv", dtype=str, keep_default_na=False)
    assert set(dec.outcome) == set(v2_ledger.OUTCOMES)
    assert (dec[dec.outcome == "abstain_U"].F_RAW_S == "").all()                 # an empty F_S of the entry slot
    win = dec[dec.outcome == "abstain_window"]
    assert ((win["T"].map(hm) < 90) | (win["T"].map(hm) + 120 > 1410)).all()   # S2 (hold 120 min) at 22:15
    ign = dec[dec.outcome == "ignored_open"].iloc[0]
    prev = tr[(tr.id == ign.id) & (tr.day == ign.day)].iloc[0]
    assert hm(prev["T"]) < hm(ign["T"]) < hm(prev["T"]) + 120
    assert set(tr.status) == {"final"} and set(tr.reason) == {"time", "stop", "gap"}
    assert set(tw.reason) == {"time", "stop", "gap"}
    stop = tr[tr.reason == "stop"]
    at_x = stop[stop.P_x == stop.X]
    at_open = stop[stop.P_x != stop.X]
    assert len(at_x) and len(at_open)                                          # intrabar at X, and a gap at an open
    assert (stop.exit_model == stop.entry_model).any()                         # stopped in its entry minute
    hold = {"S2": 120, "S3": 120, "S4": 240, "S5": 210}
    sched = stop.apply(lambda r: hm(r["T"]) + hold[r["id"]] - 1, axis=1)
    assert (stop.exit_model.map(hm) == sched).any()                            # the stop wins a tie at the exit minute
    gap = tr[tr.reason == "gap"]
    assert (gap.P_x == gap.X).all() and len(gap) >= 2
    key = ["id", "day", "T"]
    both = tr.merge(tw, on=key, suffixes=("", "_twin"))
    assert (both.exit_model != both.exit_model_twin).any()                     # a twin exits differently
    # the entry fallback and one-sided minutes: S2 2026-12-01 (the ASK of UTC 2026-12-01 is missing)
    days = pd.read_csv(P.v1data / "days.csv", dtype=str, keep_default_na=False)
    assert ((days.day == "2026-12-01") & (days.side == "ASK")).sum() == 1
    assert days[(days.day == "2026-12-01") & (days.side == "ASK")].status.iloc[0] == "missing"
    fb = tr[(tr.id == "S2") & (tr.day == "2026-12-01")].iloc[0]
    md = _minutes(dry, "2026-12-01")
    e = hm(fb.entry_model)
    assert e == hm(fb["T"]) + 1 and int(fb.side) == 1
    assert md.row(e) >= 0 and not np.isfinite(md.ask_o[md.row(e)])            # no ask at the entry minute
    assert float(fb.P_e) == float(md.ask_c[md.row(e - 2)])                     # the ask close of 01:59
    assert fb.reason == "gap" and np.isnan(md.c[md.row(e)])                   # one-sided (NaN mid) path minutes
    # each branch is reproduced by v2_exec on the stored minutes (so the fixture rows are what the code computes)
    re_ = v2_exec.trade(md, 1, hm(fb["T"]), 120, F_S=float(fb.F_RAW_S))
    assert re_["reason"] == "gap" and re_["P_e"] == float(fb.P_e) and re_["exit_min"] == hm(fb.exit_model)
    assert len(v2_synth.EDGES) == 11
