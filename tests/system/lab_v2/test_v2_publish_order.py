"""OPS fix ops-v2-publish-order: the summary a lab v2 run publishes reflects that run's own registration and START.

Lab v2's first cloud run (78c13fa, 2026-10-22T08:42Z) registered S2-S5 and wrote reports/system/lab_v2/START.json,
but its summary.json showed first_day None for the lab and every seed: the states the summary was built from had been
computed while START was still unset (first_day(registered_utc, None) is None). The next run showed 2026-11-02. The
judge's J5 flagged it (J5-202610220842-1..5, adjudicated spec_gap). Here: the synthetic world's first lab v2 run (it
registers S2-S5 and writes START.json in the same run) must publish the first_day it registered.
"""
import json
import shutil

import pandas as pd
import pytest

import run_v2
import v2_ledger
import v2_registry
from lab import registry as v1reg

FIRST_V2 = pd.Timestamp(run_v2.SYNTH_V2_FROM, tz="UTC")


@pytest.fixture(scope="module")
def first_run(world, tmp_path_factory):
    """A copy of the synthetic world after v1's runs up to and including lab v2's first run (2026-11-03 03:20)."""
    P = run_v2.Paths(tmp_path_factory.mktemp("publish_order") / "w")
    shutil.copytree(world.base, P.base)
    times = [t for t in run_v2.SYNTH_TIMES if pd.Timestamp(t, tz="UTC") <= FIRST_V2]
    codes = run_v2.synthetic_runs(P, times=times, log=lambda *a: None)
    return P, codes


def test_the_first_run_registers_and_writes_start(first_run):
    P, codes = first_run
    assert codes == [(FIRST_V2, 0)]
    start = json.loads((P.rep / "START.json").read_text())
    assert start["first_cloud_run_utc"] == "2026-11-03T03:20:00Z" and start["start"] == "2026-11-09"
    ev = pd.read_csv(P.reg / "events.csv")
    assert list(ev.event) == ["REGISTERED"] * 4 and set(ev.utc) == {"2026-11-03T03:20:00Z"}


def test_the_registering_run_publishes_its_first_day(first_run):
    P, _ = first_run
    s = json.loads((P.rep / "summary.json").read_text())
    assert s["asof_utc"] == "2026-11-03T03:20:00Z" and s["start"] == "2026-11-09"
    assert s["first_day"] == "2026-11-09"
    assert {r["id"]: r["first_day"] for r in s["rules"]} == {sid: "2026-11-09" for sid in ("S2", "S3", "S4", "S5")}
    # the same first_day a reader recomputes from the files this run committed (registry, events, START.json)
    recs = v2_registry.load(P.reg)
    sts = v1reg.states(recs, v1reg.read_events(P.reg / "events.csv"),
                       json.loads((P.rep / "START.json").read_text())["start"])
    assert s["first_day"] == v2_ledger.lab_first_day(sts)
    assert all(r["first_day"] == sts[r["id"]]["first_day"] for r in s["rules"])


def test_the_page_and_status_show_it_too(first_run):
    P, _ = first_run
    site = json.loads((P.site / "lab_v2.json").read_text())
    assert site["first_day"] == "2026-11-09" and {r["first_day"] for r in site["rules"]} == {"2026-11-09"}
    status = (P.rep / "STATUS.md").read_text(encoding="utf-8")
    assert "| S2 | PAPER | 2026-11-09 |" in status
