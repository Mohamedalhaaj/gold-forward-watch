"""Lab v2 settles a day only when v1's forecast store covers it (xauusd-quant research/system/IMPLEMENTATION_REGISTER.md
R-V2-27, R-V2-16; lab review MF1). Synthetic data only.

The sequence: v1 + v2 through the 2026-11-07 run, then a job at 2026-11-14 03:20 whose v1 run fetches (its days.csv
rows are there) but halts on its forecast tripwire, so it appends no forecast row after 2026-11-06; lab v2 runs in the
same job. Before the fix v2 settled 2026-11-09 .. 11-13 then, with every signal recorded as abstain_U for ever, and the
v2 tripwire halted once v1 recovered. Now nothing is settled until v1 writes those days; the recovery job at 09:20
settles them exactly as the complete world (the committed judge fixture) did, apart from the run time it records.
"""
import shutil
from pathlib import Path

import pandas as pd
import pytest

import run_v2
import v2_data
import v2_ledger

FIXTURE = Path(__file__).resolve().parents[2] / "judge_fixtures" / "synthetic_world"
DAYS = [f"2026-11-{d:02d}" for d in range(9, 14)]
LEDGERS = ("audit.csv", "decisions.csv", "trades.csv", "twins.csv", "eproc.csv")
TIME_COLS = ("recorded_utc", "settled_utc")


def v1_run(P, t, halt=False):
    """v1's run of the job (synthetic); halt=True: its forecast tripwire reports a difference, after its fetch."""
    import run as v1run
    real = v1run.forecasts.tripwire
    if halt:
        v1run.forecasts.tripwire = lambda store, grid: ["simulated forecast tripwire"]
    try:
        info, _ = v1run.one_run(v1run.Paths(P.base), t, "synthetic", "dry", "dry-placeholder", fetch_on=False,
                                log=lambda *a: None)
    finally:
        v1run.forecasts.tripwire = real
    v1run.write_status(v1run.Paths(P.base), info)
    return info


def v2_run(P, t):
    return run_v2.guarded_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=lambda *a: None)


def rows(base, name):
    return v2_ledger.read(Path(base) / "reports/system/lab_v2" / name)


def strip(rs):
    return [{k: v for k, v in r.items() if k not in TIME_COLS} for r in rs]


@pytest.fixture(scope="module")
def through_11_07(world, tmp_path_factory):
    base = tmp_path_factory.mktemp("cover")
    P = run_v2.Paths(base / "w")
    shutil.copytree(world.base, P.base)
    run_v2.synthetic_runs(P, times=run_v2.SYNTH_TIMES[:4], log=lambda *a: None)    # v2 START 2026-11-09
    return P


def test_store_covers_and_pending_days_stop_at_the_first_uncovered_day():
    sts = {"S2": {"state": "PAPER", "first_day": "2026-11-09"}}
    complete = pd.Timestamp("2026-11-14 00:00", tz="UTC")
    full = {(d, s): (1.0, 1.0) for d in DAYS for s in range(23)}
    assert [d.strftime("%Y-%m-%d") for d in v2_ledger.pending_days("/nonexistent", sts, complete, full)] == DAYS
    part = {k: v for k, v in full.items() if not (k[0] == "2026-11-11" and k[1] == 22)}
    assert not v2_ledger.store_covers(part, pd.Timestamp("2026-11-11"))
    assert [d.strftime("%Y-%m-%d") for d in v2_ledger.pending_days("/nonexistent", sts, complete, part)] == DAYS[:2]
    nothing = {k: v for k, v in full.items() if k[0] < "2026-11-09"}
    assert v2_ledger.pending_days("/nonexistent", sts, complete, nothing) == []
    # a weekday without any store row is not waited for (it is settled) only when the store holds a later day
    gap = {k: v for k, v in full.items() if k[0] != "2026-11-11"}
    assert [d.strftime("%Y-%m-%d") for d in v2_ledger.pending_days("/nonexistent", sts, complete, gap)] == DAYS
    gap_last = {k: v for k, v in full.items() if k[0] != "2026-11-13"}
    assert [d.strftime("%Y-%m-%d") for d in v2_ledger.pending_days("/nonexistent", sts, complete, gap_last)] == (
        DAYS[:4])
    nan_f = dict(full) | {("2026-11-12", 5): (float("nan"), float("nan"))}    # an empty F_S row is present
    assert [d.strftime("%Y-%m-%d") for d in v2_ledger.pending_days("/nonexistent", sts, complete, nan_f)] == DAYS


def test_a_v1_halt_after_its_fetch_leaves_the_days_pending(through_11_07, tmp_path):
    P = run_v2.Paths(tmp_path / "w")
    shutil.copytree(through_11_07.base, P.base)
    t1 = pd.Timestamp("2026-11-14 03:20", tz="UTC")
    info1 = v1_run(P, t1, halt=True)
    assert any("forecast tripwire" in h for h in info1["halt"])
    store = pd.read_csv(P.v1data / "forecasts.csv", dtype=str)
    assert store.day.max() == "2026-11-06"                          # v1 wrote nothing new
    assert v2_data.v1_complete_utc(P.v1data, t1) >= pd.Timestamp("2026-11-14 00:00", tz="UTC")   # but the data are
    code, info = v2_run(P, t1)
    assert code == 0 and info["halt"] == [] and info["settled_now"] == []
    assert not rows(P.base, "lab_days.csv") and not rows(P.base, "decisions.csv")   # no abstain_U, nothing settled
    # the recovery job: v1 appends the missing slots, then v2 settles 11-09 .. 11-13 as the complete world did
    t2 = pd.Timestamp("2026-11-14 09:20", tz="UTC")
    info1 = v1_run(P, t2)
    assert info1["halt"] == []
    code, info = v2_run(P, t2)
    assert code == 0 and info["halt"] == [] and info["settled_now"] == DAYS
    assert [r["day"] for r in rows(P.base, "lab_days.csv")] == DAYS
    assert {r["settled_utc"] for r in rows(P.base, "lab_days.csv")} == {"2026-11-14T09:20:00Z"}
    for name in LEDGERS:
        want = [r for r in rows(FIXTURE, name) if r["day"] in DAYS]
        got = rows(P.base, name)
        assert strip(got) == strip(want) and want, name
    assert not any(r["outcome"] == "abstain_U" for r in rows(P.base, "decisions.csv"))
    # a later run in the same state re-derives 11-13 and finds no difference
    code, info = v2_run(P, t2)
    assert code == 0 and info["halt"] == [] and info["settled_now"] == []
