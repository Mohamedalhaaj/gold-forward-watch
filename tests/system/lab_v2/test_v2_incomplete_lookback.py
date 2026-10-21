"""Lab v2 with an incomplete lookback store (SYSTEM_V2_PREREG.md §0, §2.2; xauusd-quant
research/system/IMPLEMENTATION_REGISTER.md R-V2-42): S3 waits until the store is complete, S2, S4 and S5 are
unaffected. Synthetic data only: the lookback days of May to August "arrive" late (their days rows get a later
fetched_utc), and the ledgers are compared with the committed judge fixture, the same sequence on the complete store.
"""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import run_v2
import v2_data
import v2_ledger
import v2_signals

FIXTURE = Path(__file__).resolve().parents[2] / "judge_fixtures" / "synthetic_world"
LATE_FROM, LATE_TO = "2026-05-01", "2026-08-31"
LATE_UTC = "2026-11-20T00:00:00Z"                 # after the 2026-11-14 run, before the 2026-11-21 run
FIRST_FULL_RUN = "2026-11-21T03:20:00Z"           # the first v2 run that sees the complete store
LEDGERS = ("audit.csv", "decisions.csv", "trades.csv", "twins.csv")
OTHERS = ("S2", "S4", "S5")


def make_late(lb, when=LATE_UTC):
    """Give the lookback days of May to August the fetched_utc `when` (a copy of the world, never the real store)."""
    days = pd.read_csv(lb / "days.csv", dtype=str, keep_default_na=False)
    late = (days.day >= LATE_FROM) & (days.day <= LATE_TO)
    assert late.sum() == 2 * len(pd.date_range(LATE_FROM, LATE_TO))
    days.loc[late, "fetched_utc"] = when
    days.to_csv(lb / "days.csv", index=False, lineterminator="\n")


def rows(base, name, ids=None):
    out = v2_ledger.read(Path(base) / "reports/system/lab_v2" / name)
    return [r for r in out if ids is None or r["id"] in ids]


def test_lookback_complete_counts_only_final_rows_fetched_by_now(world, tmp_path):
    lb = tmp_path / "lookback"
    shutil.copytree(world.lb, lb)
    assert v2_data.lookback_complete(lb, pd.Timestamp("2026-09-02 03:00", tz="UTC"))
    assert not v2_data.lookback_complete(lb, pd.Timestamp("2026-09-01 02:00", tz="UTC"))   # 08-31 fetched 02:30
    make_late(lb)
    for t, want in (("2026-11-14 03:20", False), ("2026-11-19 23:59:59", False), ("2026-11-20 00:00", True)):
        assert v2_data.lookback_complete(lb, pd.Timestamp(t, tz="UTC")) is want, t
    days = pd.read_csv(lb / "days.csv", dtype=str, keep_default_na=False)
    days.loc[0, ["status", "bytes", "sha256", "records", "vol_minutes"]] = ["missing", "", "", "", ""]
    days.to_csv(lb / "days.csv", index=False, lineterminator="\n")
    assert v2_data.lookback_complete(lb, pd.Timestamp("2026-11-20 00:00", tz="UTC"))       # missing is final
    days.iloc[1:].to_csv(lb / "days.csv", index=False, lineterminator="\n")
    assert not v2_data.lookback_complete(lb, pd.Timestamp("2026-12-05 03:20", tz="UTC"))   # a pair without a row
    assert not v2_data.lookback_complete(tmp_path / "nothing", pd.Timestamp("2026-12-05 03:20", tz="UTC"))
    assert v2_signals.LOOKBACK_SEEDS == ("S3",)


def bars_at(lb, v1data, now):
    cu = v2_data.v1_complete_utc(v1data, now)
    m_in = v2_data.seed_input(v2_data.model_frame(v2_data.load_m1(lb, v1data, now, cu)))
    return {"M5": v2_data.seed_bars(m_in, "M5"), "M15": v2_data.seed_bars(m_in, "M15")}


def test_only_s3_reads_the_lookback_on_forward_days(world, tmp_path):
    """Full-data values of every bar on or after 2026-11-02 (the earliest START) with the complete lookback and with
    no lookback at all: S2, S4 and S5 are identical, S3 is not."""
    now = pd.Timestamp("2026-12-05 03:20", tz="UTC")
    full, none = bars_at(world.lb, world.v1data, now), bars_at(tmp_path / "empty", world.v1data, now)
    for sid, _, tf, _ in v2_signals.SEEDS:
        mod = v2_signals.load_seed(sid)
        a = pd.Series(v2_signals.full_values(mod, full[tf]), index=full[tf].index)
        b = pd.Series(v2_signals.full_values(mod, none[tf]), index=none[tf].index)
        a, b = a[a.index >= "2026-11-02"], b[b.index >= "2026-11-02"]
        assert a.index.equals(b.index) and len(a) > 1000
        if sid in v2_signals.LOOKBACK_SEEDS:
            assert (a != 0).sum() > 0 and not a.equals(b), sid
        else:
            assert a.equals(b), (sid, int((a != b).sum()))


@pytest.fixture(scope="module")
def late_world(world, tmp_path_factory):
    """The synthetic sequence with the late lookback, run in two parts: through the 2026-11-14 run (the store is not
    complete: S3 waits), then the rest. Returns (Paths, the copy after the first part, the v2 exit codes)."""
    base = tmp_path_factory.mktemp("late")
    P = run_v2.Paths(base / "w")
    shutil.copytree(world.base, P.base)
    make_late(P.lb)
    codes = run_v2.synthetic_runs(P, times=run_v2.SYNTH_TIMES[:5], log=lambda *a: None)
    mid = run_v2.Paths(base / "after_11_14")
    shutil.copytree(P.base, mid.base)
    codes += run_v2.synthetic_runs(P, times=run_v2.SYNTH_TIMES[5:], log=lambda *a: None)
    return P, mid, codes


def test_s3_waits_while_the_store_is_incomplete(late_world):
    P, mid, codes = late_world
    assert [c for _, c in codes] == [0] * 6                                  # v2 runs 11-03 .. 12-05, no halt
    s = json.loads((mid.rep / "summary.json").read_text())
    s3 = {r["id"]: r for r in s["rules"]}["S3"]
    assert s3["waits_for_lookback"] is True and s3["warmup"] is True and s3["state"] == "PAPER" and s3["n"] == 0
    assert "S3 waits for the lookback store" in (mid.rep / "STATUS.md").read_text()
    assert "complete: False" in (mid.rep / "STATUS.md").read_text()
    for name in LEDGERS:
        assert not rows(mid.base, name, {"S3"}), name                       # 11-09 .. 11-13 settled without S3
    assert {r["day"] for r in rows(mid.base, "audit.csv")} == {f"2026-11-{d:02d}" for d in range(9, 14)}
    s = json.loads((P.rep / "summary.json").read_text())
    s3 = {r["id"]: r for r in s["rules"]}["S3"]
    assert s3["waits_for_lookback"] is False and s3["n"] > 0
    assert "S3 waits" not in (P.rep / "STATUS.md").read_text()


def test_s2_s4_s5_rows_equal_the_complete_world(late_world):
    P, _, _ = late_world
    assert rows(P.base, "lab_days.csv") == rows(FIXTURE, "lab_days.csv")
    for name in LEDGERS + ("eproc.csv",):
        got, want = rows(P.base, name, OTHERS), rows(FIXTURE, name, OTHERS)
        assert got == want and (want or name == "twins.csv"), name


def test_s3_rows_from_the_first_complete_run_equal_the_complete_world(late_world):
    P, _, _ = late_world
    settled = {r["day"]: r["settled_utc"] for r in rows(FIXTURE, "lab_days.csv")}
    for name in LEDGERS:
        got = rows(P.base, name, {"S3"})
        want = [r for r in rows(FIXTURE, name, {"S3"}) if settled[r["day"]] >= FIRST_FULL_RUN]
        assert got == want and want, name
    lost = [r for r in rows(FIXTURE, "trades.csv", {"S3"}) if settled[r["day"]] < FIRST_FULL_RUN]
    assert lost                                     # the complete world traded S3 on days the late world waited
    ep = rows(P.base, "eproc.csv", {"S3"})
    assert [int(r["trade_no"]) for r in ep] == list(range(1, len(ep) + 1)) and len(ep) == len(
        [r for r in rows(P.base, "trades.csv", {"S3"}) if r["status"] == "final"])


def test_the_tripwire_passes_when_the_store_completes_between_runs(late_world, tmp_path):
    """The copy after the 11-14 run, with the late days arriving before a second run at the same time: nothing new
    to settle, the tripwire re-derives 2026-11-13 for S2, S4, S5 on the now complete store and finds no difference;
    S3 (not audited that day) is not re-derived."""
    _, mid, _ = late_world
    P = run_v2.Paths(tmp_path / "w")
    shutil.copytree(mid.base, P.base)
    make_late(P.lb, when="2026-11-14T03:00:00Z")
    t = pd.Timestamp("2026-11-14 03:20", tz="UTC")
    code, info = run_v2.guarded_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=lambda *a: None)
    assert code == 0 and info["halt"] == [] and info["settled_now"] == [] and info["data"]["lookback_complete"]
    s3 = {r["id"]: r for r in json.loads((P.rep / "summary.json").read_text())["rules"]}["S3"]
    assert s3["waits_for_lookback"] is False and np.isfinite(s3["E"])
