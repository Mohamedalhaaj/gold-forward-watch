"""Planted cases of blocker R6-2 of the sixth review of register §16.18 A6 (2026-10-23): retirement by time, not by
the order of analyst-settle runs (R-AN-55 step 2, R-AN-62, R-AN-67 A11, R-AN-70; prereg §8).

Written from the register text, not from the analyst code:
- the verdict (`analyst-verdict/1`) gains `violation_first_seen`: for each key of `violation_keys` that has a row in
  FINDINGS.csv, that row's `first_seen_utc` (a key first found in this run: the run's time). A0 keys and
  `system_error:` entries, which have no FINDINGS.csv row, have no entry;
- A11 `retire_unsupported` also for a RETIRED `violation` that no integrity key supports by time: a VIOLATION key of
  the judge's FINDINGS.csv, not operational, first seen strictly after the arming time A and no later than 10 min
  after the RETIRED event's utc (a fresh verdict's tolerance, R-AN-70), with no earlier PAUSED event for its subject
  and no clear of it in the judge's ADJUDICATIONS.csv dated at or before the RETIRED event. A is the earliest clear
  time among the live integrity pauses an earlier RESUMED `clear:` event closed; a pause's clear time is the `utc` of
  its earliest analyst/ADJUDICATIONS.csv clear row dated at or after its PAUSED event (the RESUMED event's utc when
  there is none).

The verifier's probe (scratchpad verify5/r6/probes_ga/test_r6_ga.py, a late settle run that applies the owner's
clear of K1 and retires on K2, which the judge had published before that clear) is the first case below, as the
judge sees its events.
"""
import json
import os

import pytest

from jlib import report
from jlib.common import Findings
from jlib.judge import Result
from test_judge_fourth_review import (K_INT, K_OP, K_PROBE, key_of, m, pause_row, plant,  # noqa: F401
                                      small_base, state_keys)

JV = "judge_violation:"
K2 = "A10|in_span_without_attempt|analyst/runs/2026-W49.json|" + "b" * 40


def out_with(tmp_path, rows, adj=()):
    """The judge's out folder: FINDINGS.csv rows (first_seen_utc, severity, check, key) and its ADJUDICATIONS.csv."""
    out = tmp_path / "out"
    os.makedirs(out, exist_ok=True)
    report.append_csv(str(out / "FINDINGS.csv"), report.FINDINGS_HEADER,
                      [{"first_seen_utc": t, "severity": sev, "check": key.split("|")[0], "key": key}
                       for (t, sev, key) in rows])
    report.append_csv(str(out / "ADJUDICATIONS.csv"), report.ADJ_HEADER,
                      [{"utc": u, "ref": "latch", "check": k.split("|")[0], "subject": k, "decision": "clear",
                        "note": "owner"} for (u, k) in adj])
    return str(out)


# ---------------------------------------------------------------- the sixth review's probe, as the judge sees it
def probe_world(m, k2_seen):
    """K_INT paused 12-01 11:20 (first seen 11:15). The judge's run of 12-02 01:30 publishes K2 (`k2_seen`). The owner
    writes the clear row for K_INT at 07:00; one late analyst-settle run, at 08:35, applies it and retires."""
    plant(m, [("PAUSED", JV + K_INT, "2026-12-01T11:20:00Z")], "2026-12-01T11:21:00Z")
    return plant(m, [("RESUMED", f"clear:{JV}{K_INT}", "2026-12-02T08:35:00Z"),
                     ("RETIRED", "violation", "2026-12-02T08:35:00Z")], "2026-12-02T08:36:00Z",
                 adj=[pause_row(JV + K_INT, "2026-12-02T07:00:00Z")])


def test_a_late_run_retiring_on_a_key_first_seen_before_the_clear_is_unsupported(m, tmp_path):
    (_res, ret), sha = probe_world(m, "2026-12-02T01:30:00Z")
    out = out_with(tmp_path, [("2026-12-01T11:15:00Z", "VIOLATION", K_INT), ("2026-12-02T01:30:00Z", "VIOLATION", K2)])
    assert state_keys(m.judge(out_dir=out)) == [key_of("retire_unsupported", ret, sha)]


def test_the_same_run_retiring_on_a_key_first_seen_after_the_clear_is_supported(m, tmp_path):
    probe_world(m, "2026-12-02T07:30:00Z")
    out = out_with(tmp_path, [("2026-12-01T11:15:00Z", "VIOLATION", K_INT), ("2026-12-02T07:30:00Z", "VIOLATION", K2)])
    assert state_keys(m.judge(out_dir=out)) == []


# ---------------------------------------------------------------- the arming time and the supporting key
def live_clear(m):
    """A live integrity pause of K_INT at 12-01 10:00, the owner's row at 12:00, the RESUMED event at 13:00: A is 12:00
    (the row's utc, not the event's)."""
    plant(m, [("PAUSED", JV + K_INT, "2026-12-01T10:00:00Z")], "2026-12-01T10:05:00Z")
    plant(m, [("RESUMED", f"clear:{JV}{K_INT}", "2026-12-01T13:00:00Z")], "2026-12-01T13:05:00Z",
          adj=[pause_row(JV + K_INT, "2026-12-01T12:00:00Z")])


def retire(m, when="2026-12-02T10:00:00Z", extra=()):
    paths, sha = plant(m, list(extra) + [("RETIRED", "violation", when)], when)
    return key_of("retire_unsupported", paths[-1], sha)


@pytest.mark.parametrize("seen", ["2026-12-01T12:30:00Z",          # between the row (12:00) and the RESUMED (13:00)
                                  "2026-12-02T09:00:00Z",
                                  "2026-12-02T10:10:00Z"])         # the RETIRED event's utc + 10 min
def test_a_key_first_seen_after_the_arming_time_supports_the_retirement(m, tmp_path, seen):
    live_clear(m)
    retire(m)
    out = out_with(tmp_path, [("2026-12-01T09:50:00Z", "VIOLATION", K_INT), (seen, "VIOLATION", K2)])
    assert state_keys(m.judge(out_dir=out)) == []


@pytest.mark.parametrize("rows,adj", [
    ([("2026-12-01T11:00:00Z", "VIOLATION", K2)], ()),                          # before A
    ([("2026-12-01T12:00:00Z", "VIOLATION", K2)], ()),                          # at A: "after" is strict
    ([("2026-12-02T10:10:01Z", "VIOLATION", K2)], ()),                          # later than the event + 10 min
    ([("2026-12-01T18:00:00Z", "VIOLATION", K_PROBE)], ()),                     # operational (A12 probe_failed)
    ([("2026-12-01T18:00:00Z", "VIOLATION", K_OP)], ()),                        # operational (A0)
    ([("2026-12-01T18:00:00Z", "WARNING", K2)], ()),                            # not a VIOLATION
    ([("2026-12-01T18:00:00Z", "VIOLATION", K2)], [("2026-12-02T09:00:00Z", K2)]),   # cleared with the judge first
    ([("not a time", "VIOLATION", K2)], ()),
    ([], ()),                                                                   # no FINDINGS.csv row at all
])
def test_a_retirement_no_key_supports_by_time_is_unsupported(m, tmp_path, rows, adj):
    live_clear(m)
    k = retire(m)
    out = out_with(tmp_path, [("2026-12-01T09:50:00Z", "VIOLATION", K_INT)] + rows, adj)
    assert state_keys(m.judge(out_dir=out)) == [k]


def test_a_key_with_an_earlier_pause_does_not_support_a_retirement(m, tmp_path):
    """A live integrity key that was paused stays paused until its own clear (R-AN-55 step 2); it never retires."""
    live_clear(m)
    k = retire(m, extra=[("PAUSED", JV + K2, "2026-12-02T10:00:00Z")])
    out = out_with(tmp_path, [("2026-12-01T09:50:00Z", "VIOLATION", K_INT), ("2026-12-02T09:00:00Z", "VIOLATION", K2)])
    assert state_keys(m.judge(out_dir=out)) == [k]


def test_the_arming_time_is_the_earliest_live_clear(m, tmp_path):
    """Two live clears, rows at 12:00 and 18:00: a key first seen at 13:00 is after the earliest one."""
    live_clear(m)
    k3 = "A3|agent_scope|inbox/refs/heads/claude/analyst-z|" + "e" * 40
    plant(m, [("PAUSED", JV + k3, "2026-12-01T14:00:00Z")], "2026-12-01T14:05:00Z")
    plant(m, [("RESUMED", f"clear:{JV}{k3}", "2026-12-01T18:30:00Z")], "2026-12-01T18:35:00Z",
          adj=[pause_row(JV + k3, "2026-12-01T18:00:00Z")])
    retire(m)
    out = out_with(tmp_path, [("2026-12-01T09:50:00Z", "VIOLATION", K_INT), ("2026-12-01T13:50:00Z", "VIOLATION", k3),
                              ("2026-12-01T13:00:00Z", "VIOLATION", K2)])
    assert state_keys(m.judge(out_dir=out)) == []


def test_run_judge_reads_the_findings_from_the_out_folder(m, tmp_path):
    """World.judge with out_dir, like run_judge, gives the judge its own FINDINGS.csv: without it nothing supports."""
    live_clear(m)
    k = retire(m)
    out = out_with(tmp_path, [("2026-12-01T09:50:00Z", "VIOLATION", K_INT), ("2026-12-02T09:00:00Z", "VIOLATION", K2)])
    assert state_keys(m.judge(out_dir=out)) == []
    assert state_keys(m.judge()) == [k]


# ---------------------------------------------------------------- the verdict's first-seen times (R-AN-70)
def test_the_verdict_carries_each_latched_keys_first_seen_time(tmp_path):
    out = str(tmp_path / "out")
    k1 = "A1|call_bytes|analyst/calls/2026-12-01_W1.json|" + "a" * 40
    blind = "A0|inbox_blind|api|2026-11-30T23:40:00Z"
    F = Findings()
    F.v("A1", "call_bytes", "analyst/calls/2026-12-01_W1.json", "a" * 40)
    F.v("A0", "inbox_blind", "api", "2026-11-30T23:40:00Z")
    v1 = report.write_outputs(Result(F, "f" * 40), out, "2026-12-01T10:00:00Z", "x")
    assert v1["violation_keys"] == sorted([k1, blind])
    assert v1["violation_first_seen"] == {k1: "2026-12-01T10:00:00Z"}              # A0: never in FINDINGS.csv
    F2 = Findings()                                                                # k1 not found again: latched
    F2.v("A10", "in_span_without_attempt", "analyst/runs/2026-W49.json", "b" * 40)
    F2.w("A11", "ledger_mismatch", "analyst/ledger.csv", "-")
    warn = "A11|ledger_mismatch|analyst/ledger.csv|-"
    report.write_outputs(Result(F2, "f" * 40), out, "2026-12-01T16:00:00Z", "x")
    report.append_csv(os.path.join(out, "ADJUDICATIONS.csv"), report.ADJ_HEADER,
                      [{"utc": "2026-12-01T17:00:00Z", "ref": "warning", "check": "A11", "subject": warn,
                        "decision": "system_error", "note": "owner"},
                       {"utc": "2026-12-01T17:00:00Z", "ref": "latch", "check": "A1", "subject": k1,
                        "decision": "clear", "note": "owner"}])
    v3 = report.write_outputs(Result(F2, "f" * 40), out, "2026-12-01T22:00:00Z", "x")
    assert v3["violation_keys"] == [K2, f"system_error:{warn}"]
    assert v3["violation_first_seen"] == {K2: "2026-12-01T16:00:00Z"}             # the run that first found it
    with open(os.path.join(out, "analyst_verdict.json"), encoding="utf-8") as f:
        assert json.load(f)["violation_first_seen"] == {K2: "2026-12-01T16:00:00Z"}
    assert v3["schema"] == "analyst-verdict/1"


def test_the_verdict_with_no_violation_has_an_empty_map(tmp_path):
    v = report.write_outputs(Result(Findings(), "f" * 40), str(tmp_path / "out"), "2026-12-01T10:00:00Z", "x")
    assert v["analyst_verdict"] == "SOUND" and v["violation_first_seen"] == {}
