"""Planted cases of the fourth review of register §16.18 A6 (2026-10-23, decisions 24-32; blockers J-3 and J-4, notes
N2 and N3), as R-AN-55, R-AN-56, R-AN-60, R-AN-62, R-AN-66, R-AN-67, R-AN-69 and R-AN-70 define them at xauusd-quant
5d7fcdc (prereg v0.6 §8, fourth review).

Written from the register text, not from the analyst code:
- A0 `inbox_blind` (J-3, decision 24): this run's read of the inbox's activity failed, the last complete read L (the
  newest `inbox_read`/`inbox_activity` evidence row, else PINS.inbox_from_utc) is more than 24 h old, and at least two
  judge runs after L failed that read, this one included, counted from the new `inbox_read_failed` evidence rows
  (R-AN-69). Key `A0|inbox_blind|api|<L>`: each episode its own key; never latched, written to FINDINGS.csv or
  cleared (J-D27 as amended). One failed run after a long gap, as every Sunday can bring, stays the WARNING
  `inbox_api_unreachable`. The verifier's probe (scratchpad verify4/probes_judge/test_v4_judge.py) is the first test;
- every VIOLATION key names its incident (J-4 part 2, decision 26): `inbox_identity` what was seen (`404`, `id-<id>`,
  `private`), `inbox_runs` the run count, the `probe_flood` day count its day; `inbox_config` (deploy keys, Actions)
  split from `inbox_hook` (webhooks);
- `routine_connectors` also judges the version in force at PINS.inbox_from_utc (N3, J-D26 as extended);
- each runs export is judged by its own path, whatever `iso_week` it claims (N3);
- A11 state events (J-4, R-AN-55, R-AN-56, R-AN-67): `resume_unsupported` for `clear:` and `lifted:`,
  `retire_unsupported`, `pause_early`; A10's pause intervals end at a `lifted:` resume too.
"""
import datetime as dt
import json
import os

import pytest

from jlib import report
from jlib.common import VIOLATION, WARNING, fmt_utc, record_form
from jlib.gitrepo import GitRepo
from jlib.judge import EVIDENCE_HEADER, Judge
from jlib.sources import FakeGitHub
from world import GA, INBOX, INBOX_ID, OWNER, T, World, routine_config

SMALL = dict(canary_days=(), live_from="2026-11-30", live_to="2026-12-01", now="2026-12-02T23:00:00Z")
UNREACHABLE = "A0|inbox_api_unreachable|api|-"
RC = "analyst/ROUTINE_CONFIG.json"


@pytest.fixture(scope="module")
def small_base(tmp_path_factory):
    return World(str(tmp_path_factory.mktemp("small4") / "w"), **SMALL).build()


@pytest.fixture
def m(small_base, tmp_path):
    return small_base.clone(str(tmp_path / "copy"))


def keys(res, check=None, severity=None, code=None):
    return [f.key for f in res.findings.items if (not check or f.check == check) and
            (not severity or f.severity == severity) and (not code or f.code == code)]


def finding(res, key):
    return {f.key: f for f in res.findings.items}[key]


def failing(world):
    return FakeGitHub(world.api_data(), repo=GA, fail={"repo_activity"})


def evidence_of(world, out, **kw):
    res = world.judge(out_dir=str(out), **kw)
    report.write_outputs(res, str(out), kw.get("now") or world.now, "x")
    return report.read_csv(os.path.join(str(out), "evidence.csv"), EVIDENCE_HEADER)


def aged(ev, when, sources=("inbox_read", "inbox_activity")):
    return [dict(r, judge_utc=when) if r["source"] in sources else dict(r) for r in ev]


def ago(world, **kw):
    return fmt_utc(T(world.now) - dt.timedelta(**kw))


def blind(L):
    return f"A0|inbox_blind|api|{L}"


# ---------------------------------------------------------------- A0 inbox_blind (J-3)
def test_one_failed_run_after_a_24h_gap_is_not_a_violation(tmp_path):
    """The verifier's probe (round 4), kept as it was written: the last complete read a little more than 24 h earlier,
    as between the Saturday and Sunday 23:40 backstops, and ONE failed read. Before the fourth review it was A0
    `inbox_blind`, a VIOLATION that paused the canary's calls."""
    m = World(str(tmp_path / "w"), **SMALL).build()
    out = tmp_path / "ev"
    res = m.judge(out_dir=str(out))
    report.write_outputs(res, str(out), m.now, "x")
    ev = report.read_csv(os.path.join(str(out), "evidence.csv"), EVIDENCE_HEADER)
    prev = fmt_utc(T(m.now) - dt.timedelta(hours=24, minutes=7))      # the previous run started 7 min earlier
    ev = [dict(r, judge_utc=prev) if r["source"] in ("inbox_read", "inbox_activity") else r for r in ev]
    one_fail = FakeGitHub(m.api_data(), repo=GA, fail={"repo_activity"})
    res = m.judge(api=one_fail, evidence=ev)
    v = report.write_outputs(res, str(tmp_path / "out"), m.now, "x")
    assert v["analyst_verdict"] != "VIOLATION", "a single failed read after a 24 h gap is a VIOLATION"
    assert v["analyst_verdict"] == "WARNING" and v["violation_keys"] == []
    assert keys(res) == [UNREACHABLE] and finding(res, UNREACHABLE).severity == WARNING


def test_a_failed_read_writes_one_inbox_read_failed_row(m, tmp_path):
    """R-AN-69: one row per judge run whose read of the inbox's activity failed: `judge_utc` = the run's time, `ref` =
    PINS.inbox_repo, the other columns empty; none for a complete read, and none twice for one run time."""
    ev = evidence_of(m, tmp_path / "ev")
    assert [r["source"] for r in ev].count("inbox_read_failed") == 0
    res = m.judge(api=failing(m), evidence=ev)
    rows = [r for r in res.evidence_new if r["source"] == "inbox_read_failed"]
    assert rows == [dict({k: "" for k in EVIDENCE_HEADER}, judge_utc=m.now, source="inbox_read_failed", ref=INBOX)]
    again = m.judge(api=failing(m), evidence=ev + rows)
    assert not [r for r in again.evidence_new if r["source"] == "inbox_read_failed"]
    ok = m.judge(evidence=ev + rows)
    assert not [r for r in ok.evidence_new if r["source"] == "inbox_read_failed"]


def test_inbox_blind_needs_two_failed_runs_after_a_read_more_than_a_day_old(m, tmp_path):
    """Decision 24: L more than 24 h before this run AND at least two runs after L that failed the read (this one
    included). The key carries L in R-C4, so the episode is named."""
    ev = evidence_of(m, tmp_path / "ev")
    L = ago(m, hours=30)
    old = aged(ev, L)
    first = m.judge(api=failing(m), evidence=old, now=ago(m, hours=6))           # 24 h after L: one failed run
    assert blind(L) not in keys(first) and UNREACHABLE in keys(first)
    failed = [r for r in first.evidence_new if r["source"] == "inbox_read_failed"]
    assert [r["judge_utc"] for r in failed] == [ago(m, hours=6)]
    res = m.judge(api=failing(m), evidence=old + failed)
    assert sorted(keys(res, "A0")) == sorted([UNREACHABLE, blind(L)])
    f = finding(res, blind(L))
    assert f.severity == VIOLATION and f.check == "A0" and f.code == "inbox_blind"
    assert res.summary["inbox_failed_runs_since_last_read"] == 2


@pytest.mark.parametrize("L_age,failed_ages,want", [
    (dict(hours=24, seconds=1), [dict(hours=1)], True),                     # just over a day, two runs
    (dict(hours=24), [dict(hours=1)], False),                               # exactly a day: not more than 24 h
    (dict(hours=23), [dict(hours=20), dict(hours=10), dict(hours=1)], False),  # many failures inside a day
    (dict(hours=30), [dict(hours=40)], False),                              # a failure before L does not count
    (dict(hours=30), [], False),                                            # this run alone
    (dict(days=3), [dict(days=2), dict(days=1)], True),
])
def test_inbox_blind_counting_rule(m, tmp_path, L_age, failed_ages, want):
    ev = evidence_of(m, tmp_path / "ev")
    L = ago(m, **L_age)
    rows = aged(ev, L) + [dict({k: "" for k in EVIDENCE_HEADER}, judge_utc=ago(m, **a), source="inbox_read_failed",
                               ref=INBOX) for a in failed_ages]
    res = m.judge(api=failing(m), evidence=rows)
    assert (blind(L) in keys(res)) is want
    assert UNREACHABLE in keys(res)
    assert [k for k in keys(res, "A0") if k.startswith("A0|inbox_blind|")] == ([blind(L)] if want else [])


def test_a_complete_read_ends_the_episode_and_a_later_episode_has_another_key(m, tmp_path):
    """Each episode is keyed by its own L, so neither the judge's clear (never applied to A0) nor the analyst's lift
    of one episode covers a later one (J-D27 as amended; R-AN-55)."""
    out = tmp_path / "out"
    ev = evidence_of(m, tmp_path / "ev")
    L1 = ago(m, days=4)
    rows = aged(ev, L1)
    r1 = m.judge(api=failing(m), evidence=rows, now=ago(m, days=3, hours=-2))       # L1 + 26 h: one failed run
    assert not [k for k in keys(r1, "A0") if "inbox_blind" in k]
    rows += r1.evidence_new
    r2 = m.judge(api=failing(m), evidence=rows, now=ago(m, days=3, hours=-3))       # L1 + 27 h: blind, episode 1
    assert [k for k in keys(r2, "A0") if "inbox_blind" in k] == [blind(L1)]
    rows += r2.evidence_new
    L2 = ago(m, days=2)
    r3 = m.judge(evidence=rows, now=L2)                                              # a complete read ends it
    assert not [k for k in keys(r3, "A0") if "inbox_blind" in k]
    assert [r["source"] for r in r3.evidence_new if r["source"].startswith("inbox_read")] == ["inbox_read"]
    os.makedirs(out)
    report.append_csv(str(out / "ADJUDICATIONS.csv"), report.ADJ_HEADER,       # a clear of episode 1: no effect
                      [{"utc": L2, "ref": "latch", "check": "A0", "subject": blind(L1), "decision": "clear",
                        "note": "x"}])
    rows += r3.evidence_new
    r4 = m.judge(api=failing(m), evidence=rows, now=ago(m, days=1, hours=-1))       # L2 + 25 h: one failed run
    assert not [k for k in keys(r4, "A0") if "inbox_blind" in k]
    rows += r4.evidence_new
    r5 = m.judge(api=failing(m), evidence=rows)                                      # L2 + 47 h: episode 2
    assert [k for k in keys(r5, "A0") if "inbox_blind" in k] == [blind(L2)]
    v = report.write_outputs(r5, str(out), m.now, "x")
    assert v["analyst_verdict"] == "VIOLATION" and v["violation_keys"] == [blind(L2)]
    assert "inbox_blind" not in (out / "FINDINGS.csv").read_text(encoding="utf-8")


def test_inbox_blind_with_no_read_recorded_counts_from_inbox_from(m):
    """With no `inbox_read`/`inbox_activity` row, L is PINS.inbox_from_utc (J-D25)."""
    res = m.judge(api=failing(m))
    assert blind(m.inbox_from) not in keys(res)                              # one failed run only
    row = dict({k: "" for k in EVIDENCE_HEADER}, judge_utc=ago(m, hours=2), source="inbox_read_failed", ref=INBOX)
    assert blind(m.inbox_from) in keys(m.judge(api=failing(m), evidence=[row]))


def test_a_run_without_an_api_client_is_a_failed_read(m):
    """J-D25: a run without an API client reads nothing; it is a failed read (an `inbox_read_failed` row) and counts
    like one: blind only with a second failed run after L."""
    def run(evidence):
        git = GitRepo(m.repo.path)
        try:
            return Judge(git, m.now, api=None, evidence_rows=evidence).run()
        finally:
            git.close()
    res = run([])
    assert UNREACHABLE in keys(res, "A0") and not [k for k in keys(res) if "inbox_blind" in k]
    assert [r["source"] for r in res.evidence_new if r["source"].startswith("inbox_read")] == ["inbox_read_failed"]
    row = dict({k: "" for k in EVIDENCE_HEADER}, judge_utc=ago(m, hours=3), source="inbox_read_failed", ref=INBOX)
    assert blind(m.inbox_from) in keys(run([row]))


def test_no_inbox_read_failed_row_without_inbox_from(m):
    """R-AN-69: the row is written only while PINS.inbox_repo and PINS.inbox_from_utc are set."""
    pins = json.loads(open(os.path.join(m.repo.path, "analyst/PINS.json"), encoding="utf-8").read())
    del pins["inbox_from_utc"]
    m.repo.write("analyst/PINS.json", record_form(pins))
    m.repo.commit("owner: pins", T("2026-12-02T20:00:00Z"))
    res = m.judge(api=failing(m))
    assert not [r for r in res.evidence_new if r["source"] == "inbox_read_failed"]
    assert not [k for k in keys(res) if "inbox_blind" in k]


# ---------------------------------------------------------------- keys that name their incident (J-4 part 2)
@pytest.mark.parametrize("info,seen", [
    (None, "404"),
    ({"id": 1, "private": False}, "id-1"),
    ({"id": 1, "private": True}, "id-1"),                                  # the first that applies
    ({"id": INBOX_ID, "private": True}, "private"),
])
def test_A12_inbox_identity_key_names_what_was_seen(m, info, seen):
    m.api["repos"][INBOX] = info
    res = m.judge()
    assert keys(res) == [f"A12|inbox_identity|inbox|{seen}"]
    assert finding(res, f"A12|inbox_identity|inbox|{seen}").severity == VIOLATION


def test_A12_inbox_runs_key_carries_the_count(m):
    m.api["runs_total"][INBOX] = 2
    assert keys(m.judge()) == ["A12|inbox_runs|inbox/actions/runs|2"]
    m.api["runs_total"][INBOX] = 3                                          # a further run: a new key
    assert keys(m.judge()) == ["A12|inbox_runs|inbox/actions/runs|3"]


def flood(world, day, n, start=0):
    for i in range(start, start + n):
        name = f"claude/probe-c3-p{day.replace('-', '')}T{i // 60:02d}{i % 60:02d}00Z"
        world.inbox_activity(f"refs/heads/{name}", f"{i + 1000 * int(day[-2:]):040x}",
                             T(f"{day}T{i // 60:02d}:{i % 60:02d}:00Z"), OWNER, "branch_creation")


def test_A12_probe_flood_day_count_key_carries_its_day(m):
    flood(m, "2026-12-02", 41)
    res = m.judge()
    key = "A12|probe_flood|inbox/refs/heads/claude/probe-*|2026-12-02"
    assert keys(res) == [key]
    assert finding(res, key).severity == VIOLATION and "41" in finding(res, key).detail
    flood(m, "2026-12-01", 45)
    assert sorted(keys(m.judge())) == sorted([key, "A12|probe_flood|inbox/refs/heads/claude/probe-*|2026-12-01"])


# ---------------------------------------------------------------- inbox_config split from inbox_hook (J-4 part 2)
def add_export(world, path, week, checks=None, app="inbox", when="2026-12-02T20:00:00Z"):
    """An owner runs export at `path` claiming `week` (create-only: a new file)."""
    ic = {"checked_utc": when, "hooks": 0, "deploy_keys": 1, "actions_enabled": False, "security_log_hook_events": 0,
          "security_log_filter": f"repo:{INBOX} action:hook", "security_log_events": [],     # §16.18 A7
          "app_repositories": {"repository_selection": "selected", "full_names": [INBOX]}}
    if app != "inbox":
        ic["app_repositories"] = app
    rec = {"schema": "analyst-runs/1", "iso_week": week, "exported_utc": when, "attested_by": "owner",
           "routines": [], "runs": [], "inbox_checks": ic}
    if checks == "omit":
        del rec["inbox_checks"]
    else:
        ic.update(checks or {})
    world.repo.write(path, record_form(rec))
    return world.repo.commit("owner runs export", T(when))


@pytest.mark.parametrize("checks,codes", [
    ({"deploy_keys": 2}, ["inbox_config"]),
    ({"deploy_keys": 0}, ["inbox_config"]),
    ({"actions_enabled": True}, ["inbox_config"]),
    ({"hooks": 1}, ["inbox_hook"]),
    ({"security_log_hook_events": 2,                    # §16.18 A7: the count with its events, event by event
      "security_log_events": [{"action": a, "created_utc": "2026-12-02T10:00:00Z", "actor": OWNER}
                              for a in ("hook.create", "hook.destroy")]}, ["inbox_hook"]),
    ({"hooks": 1, "actions_enabled": True}, ["inbox_config", "inbox_hook"]),
])
def test_A12_inbox_config_is_its_own_code(m, checks, codes):
    """R-AN-60, R-AN-67 (fourth review): `deploy_keys` != 1 and `actions_enabled` true are `inbox_config`, an
    operational owner-attested VIOLATION; `inbox_hook` keeps the webhooks."""
    path = "analyst/runs/2026-W50.json"
    sha = add_export(m, path, "2026-W50", checks)
    res = m.judge()
    assert sorted(keys(res)) == sorted(f"A12|{c}|{path}|{sha}" for c in codes)
    for c in codes:
        f = finding(res, f"A12|{c}|{path}|{sha}")
        assert f.severity == VIOLATION and f.owner_attested
    if "inbox_config" in codes:
        detail = finding(res, f"A12|inbox_config|{path}|{sha}").detail
        assert "hooks" not in detail and ("deploy_keys" in detail or "actions_enabled" in detail)


# ---------------------------------------------------------------- each runs export by its path (N3)
def test_each_runs_export_is_judged_by_its_path(m):
    """Two export files claiming the same iso_week are both judged (before, the second hid the first). (Since
    §16.18 A7 the small world exports its probe run in 2026-W48, so the planted file is a week without an export.)"""
    bad = "analyst/runs/2026-W46.json"
    sha = add_export(m, bad, "2026-W49", {"hooks": 1},
                     app={"repository_selection": "selected", "full_names": [GA]})
    assert sorted(keys(m.judge())) == sorted([f"A12|inbox_hook|{bad}|{sha}", f"A12|app_scope|{bad}|{sha}"])


def test_a_runs_export_claiming_a_judged_week_is_checked_for_inbox_checks(m):
    """J-D33: a file is judged for `inbox_checks_missing` when its path's week or the week it claims has windows."""
    other = "analyst/runs/2026-W47.json"
    sha = add_export(m, other, "2026-W49", "omit")
    res = m.judge()
    assert keys(res) == [f"A12|inbox_checks_missing|{other}|{sha}"]
    assert finding(res, f"A12|inbox_checks_missing|{other}|{sha}").severity == WARNING


# ---------------------------------------------------------------- routine_connectors: the version in force (N3)
def commit_config(world, rec, when):
    world.repo.write(RC, record_form(rec))
    return world.repo.commit("owner: routine config export", T(when))


def test_the_clean_world_judges_the_version_in_force_and_the_later_one(small_base):
    """The world's exports: one with connectors, superseded before PINS.inbox_from_utc (not judged); the cleared one
    in force at PINS.inbox_from_utc (judged); the fresh export after it (judged)."""
    res = small_base.judge()
    assert keys(res) == []
    assert res.summary["routine_config_versions_checked"] == 2


def test_A12_routine_connectors_judges_the_version_in_force_at_inbox_from(m):
    """J-D26 as extended (R-AN-67, fourth review): the newest version committed before PINS.inbox_from_utc is judged,
    whatever came after it; an older one it superseded is not."""
    bad = routine_config()
    bad["routines"][2]["raw"]["enabled_plugins"] = ["x@plugins"]
    sha = commit_config(m, bad, fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1)))
    res = m.judge()
    assert keys(res) == [f"A12|routine_connectors|{RC}|{sha}"]
    assert finding(res, f"A12|routine_connectors|{RC}|{sha}").owner_attested
    assert res.summary["routine_config_versions_checked"] == 2


def test_A12_routine_connectors_a_version_superseded_before_inbox_from_is_not_judged(m):
    bad = routine_config()
    bad["routines"][0]["raw"]["mcp_connections"] = [{"name": "Drive"}]
    commit_config(m, bad, fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=2)))
    clean = routine_config()
    clean["exported_utc"] = "2026-11-03T00:00:00Z"
    commit_config(m, clean, fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1)))
    assert keys(m.judge()) == []


# ---------------------------------------------------------------- A11 state events (J-4; R-AN-55, R-AN-56, R-AN-67)
K_INT = "A3|agent_scope|analyst/witness/000123.json|" + "a" * 40              # an integrity key
K_OP = "A0|inbox_blind|api|2026-11-30T23:40:00Z"                             # an operational key (A0)
K_PROBE = "A12|probe_failed|analyst/canary/calls/2026-11-27_W1.json|" + "b" * 40   # operational (A12)
STATE_CODES = ("resume_unsupported", "retire_unsupported", "pause_early")
CANARY_MODE = {"mode": "canary", "canary_from": "2026-11-25", "canary_to": "2026-11-27", "live_from": "2026-11-30",
               "set_utc": "2026-11-01T00:00:00Z", "note": "world"}


def state_keys(res):
    return sorted(f.key for f in res.findings.items if f.check == "A11" and f.code in STATE_CODES)


def plant(world, events, when, mode=None, adj=(), fresh=None):
    """Planted state events (`analyst-state-event/1`, R-AN-56) in one commit at `when`, as an analyst-settle run
    would add them; `mode` is MODE.json in that commit (the owner's file is restored after it); `adj` rows are
    appended to analyst/ADJUDICATIONS.csv (`utc,ref,subject,decision,note`); `fresh` sets STATE.json's
    `judge_verdict.fresh` in that commit. Returns ([event paths], commit)."""
    folder = os.path.join(world.repo.path, "analyst", "state")
    seq = len(os.listdir(folder)) + 1 if os.path.isdir(folder) else 1
    paths = []
    for i, (event, reason, utc) in enumerate(events):
        rec = {"schema": "analyst-state-event/1", "seq": seq + i, "event": event, "reason": reason,
               "model_day": None, "n": 0, "E": 1.0, "K": 1.0, "utc": utc, "run_id": 9000 + seq + i,
               "head_sha": "0" * 40}
        p = f"analyst/state/{seq + i:06d}.json"
        world.repo.write(p, record_form(rec))
        paths.append(p)
    mode_path = os.path.join(world.repo.path, "analyst", "MODE.json")
    old_mode = open(mode_path, "rb").read()
    if mode is not None:
        world.repo.write("analyst/MODE.json", record_form(mode))
    for row in adj:
        world.repo.append("analyst/ADJUDICATIONS.csv", (",".join(row) + "\n").encode())
    if fresh is not None:
        sp = os.path.join(world.repo.path, "analyst", "STATE.json")
        S = json.loads(open(sp, encoding="utf-8").read())
        S["judge_verdict"] = {"value": "VIOLATION", "asof_utc": when, "fetched": True, "fresh": fresh,
                              "last_fresh_asof_utc": when}
        if fresh == "absent":
            S["judge_verdict"] = {"value": "VIOLATION", "asof_utc": when, "fetched": True}
        world.repo.write("analyst/STATE.json", record_form(S))
    sha = world.repo.commit("analyst-settle (planted state events)", T(when))
    if mode is not None:
        world.repo.write("analyst/MODE.json", old_mode)
        world.repo.commit("owner: mode", T(when) + dt.timedelta(seconds=1))
    return paths, sha


def pause_row(subject, utc, ref="pause"):
    return (utc, ref, subject, "clear", "owner")


def key_of(code, path, sha):
    return f"A11|{code}|{path}|{sha}"


def test_pause_early(m):
    """A PAUSED `judge_violation:<K>` or `judge_silent` dated before P0 (00:00Z of the earliest of canary_from and
    live_from in the event's commit; here live_from 2026-11-30) is `pause_early`; at P0 it is not; a model pause is
    not the verdict's."""
    paths, sha = plant(m, [("PAUSED", f"judge_violation:{K_INT}", "2026-11-29T23:59:59Z"),
                           ("PAUSED", "judge_silent", "2026-11-29T12:00:00Z"),
                           ("PAUSED", f"judge_violation:{K_OP}", "2026-11-30T00:00:00Z")], "2026-12-01T00:00:00Z")
    res = m.judge()
    assert state_keys(res) == sorted([key_of("pause_early", paths[0], sha), key_of("pause_early", paths[1], sha)])
    assert all(finding(res, k).severity == WARNING for k in state_keys(res))


def test_pause_early_with_no_period_set(m):
    """No P0 (canary_from and live_from both null in the event's commit): no PAUSED may come from the verdict."""
    mode = dict(CANARY_MODE, canary_from=None, canary_to=None, live_from=None, mode="off")
    paths, sha = plant(m, [("PAUSED", f"judge_violation:{K_OP}", "2026-12-01T10:00:00Z")], "2026-12-01T10:05:00Z",
                       mode=mode)
    assert state_keys(m.judge()) == [key_of("pause_early", paths[0], sha)]


@pytest.mark.parametrize("adj,ok", [
    ([pause_row(f"judge_violation:{K_INT}", "2026-12-01T12:00:00Z")], True),
    ([pause_row(f"judge_violation:{K_INT}", "2026-12-01T10:00:00Z")], True),      # at the PAUSED event
    ([pause_row(f"judge_violation:{K_INT}", "2026-12-01T13:00:00Z")], True),      # at the RESUMED event
    ([pause_row(f"judge_violation:{K_INT}", "2026-12-01T09:59:59Z")], False),     # before the pause existed
    ([pause_row(f"judge_violation:{K_INT}", "2026-12-01T13:00:01Z")], False),     # after the resume
    ([pause_row(f"judge_violation:{K_INT}", "2026-12-01T12:00:00Z", ref="latch")], False),
    ([pause_row(f"judge_violation:{K_OP}", "2026-12-01T12:00:00Z")], False),      # another subject
    ([], False),
])
def test_clear_of_a_live_integrity_pause_needs_a_dated_owner_row(m, adj, ok):
    """R-AN-55 step 1, R-AN-62, R-AN-67: a RESUMED `clear:<S>` needs an analyst/ADJUDICATIONS.csv row for S, ref
    `pause`, decision `clear`, dated at or after S's PAUSED event and at or before the RESUMED event."""
    plant(m, [("PAUSED", f"judge_violation:{K_INT}", "2026-12-01T10:00:00Z")], "2026-12-01T10:05:00Z")
    paths, sha = plant(m, [("RESUMED", f"clear:judge_violation:{K_INT}", "2026-12-01T13:00:00Z")],
                       "2026-12-01T13:05:00Z", adj=adj)
    assert state_keys(m.judge()) == ([] if ok else [key_of("resume_unsupported", paths[0], sha)])


@pytest.mark.parametrize("subject,mode,paused", [
    (f"judge_violation:{K_OP}", None, "2026-12-01T10:00:00Z"),                  # operational (A0)
    (f"judge_violation:{K_PROBE}", None, "2026-12-01T10:00:00Z"),               # operational (A12 probe_failed)
    (f"judge_violation:system_error:{K_INT}", None, "2026-12-01T10:00:00Z"),    # operational (system_error:)
    (f"judge_violation:{K_INT}", CANARY_MODE, "2026-11-27T10:00:00Z"),          # a canary pause (before LS)
    ("judge_silent", None, "2026-12-01T10:00:00Z"),
])
def test_clear_of_a_mirrored_pause_is_unsupported(m, subject, mode, paused):
    """A clear row does nothing for a mirrored pause (R-AN-55 step 1, R-AN-62): the verdict lifts it."""
    plant(m, [("PAUSED", subject, paused)], paused, mode=mode)
    resumed = fmt_utc(T(paused) + dt.timedelta(hours=3))
    paths, sha = plant(m, [("RESUMED", f"clear:{subject}", resumed)], resumed, mode=mode,
                       adj=[pause_row(subject, fmt_utc(T(paused) + dt.timedelta(hours=1)))])
    assert state_keys(m.judge()) == [key_of("resume_unsupported", paths[0], sha)]


def test_clear_of_a_model_pause_with_a_dated_row(m):
    plant(m, [("PAUSED", "model:r-1", "2026-12-01T10:00:00Z")], "2026-12-01T10:05:00Z")
    paths, sha = plant(m, [("RESUMED", "clear:model:r-1", "2026-12-01T13:00:00Z")], "2026-12-01T13:05:00Z",
                       adj=[pause_row("model:r-1", "2026-12-01T09:00:00Z")])
    assert state_keys(m.judge()) == [key_of("resume_unsupported", paths[0], sha)]


def test_a_resume_without_an_open_pause_is_unsupported(m):
    paths, sha = plant(m, [("RESUMED", f"lifted:judge_violation:{K_OP}", "2026-12-01T13:00:00Z")],
                       "2026-12-01T13:05:00Z", fresh=True)
    assert state_keys(m.judge()) == [key_of("resume_unsupported", paths[0], sha)]


@pytest.mark.parametrize("subject,mode,paused,fresh,judge_clear,ok", [
    (f"judge_violation:{K_OP}", None, "2026-12-01T10:00:00Z", True, None, True),
    (f"judge_violation:{K_OP}", None, "2026-12-01T10:00:00Z", False, None, False),       # not a fresh verdict
    (f"judge_violation:{K_OP}", None, "2026-12-01T10:00:00Z", "absent", None, False),    # no `fresh` in STATE
    (f"judge_violation:system_error:{K_INT}", None, "2026-12-01T10:00:00Z", True, None, True),
    ("judge_silent", None, "2026-12-01T10:00:00Z", True, None, True),
    ("judge_silent", None, "2026-12-01T10:00:00Z", False, None, False),
    (f"judge_violation:{K_INT}", None, "2026-12-01T10:00:00Z", True, "2026-12-01T12:00:00Z", False),  # live
    (f"judge_violation:{K_INT}", CANARY_MODE, "2026-11-27T10:00:00Z", True, None, False),  # latched, no clear
    (f"judge_violation:{K_INT}", CANARY_MODE, "2026-11-27T10:00:00Z", True, "2026-11-27T12:00:00Z", True),
    (f"judge_violation:{K_INT}", CANARY_MODE, "2026-11-27T10:00:00Z", True, "2026-11-27T13:00:01Z", False),
    (f"judge_violation:{K_PROBE}", CANARY_MODE, "2026-11-27T10:00:00Z", True, None, False),  # latched A12 key
    (f"judge_violation:{K_PROBE}", None, "2026-12-01T10:00:00Z", True, "2026-12-01T12:00:00Z", True),
    ("model:r-1", None, "2026-12-01T10:00:00Z", True, None, False),                       # never lifted
])
def test_lifted_resumes(m, subject, mode, paused, fresh, judge_clear, ok):
    """R-AN-55 steps 3 and 4, R-AN-67: a RESUMED `lifted:<S>` needs `judge_verdict.fresh` true in its commit's
    STATE.json; S must not be a live integrity pause; for a latched key K (not A0, not system_error:) the judge's
    ADJUDICATIONS.csv must hold a clear row for K dated at or before the RESUMED event."""
    plant(m, [("PAUSED", subject, paused)], paused, mode=mode)
    resumed = fmt_utc(T(paused) + dt.timedelta(hours=3))
    paths, sha = plant(m, [("RESUMED", f"lifted:{subject}", resumed)], resumed, mode=mode, fresh=fresh)
    adj = []
    if judge_clear:
        k = subject[len("judge_violation:"):]
        adj = [{"utc": judge_clear, "ref": "latch", "check": k.split("|")[0], "subject": k, "decision": "clear",
                "note": "owner"}]
    assert state_keys(m.judge(adjudications=adj)) == ([] if ok else [key_of("resume_unsupported", paths[0], sha)])


@pytest.mark.parametrize("key,mirrored", [
    ("A12|probe_failed|analyst/canary/checks/PROBE_p20261201T101500Z.json|" + "c" * 40, True),
    ("A12|app_scope|analyst/runs/2026-W49.json|" + "c" * 40, True),
    ("A12|routine_connectors|analyst/ROUTINE_CONFIG.json|" + "c" * 40, True),
    ("A12|inbox_identity|inbox|404", True),
    ("A12|inbox_config|analyst/runs/2026-W49.json|" + "c" * 40, True),
    ("A12|inbox_hook|analyst/runs/2026-W49.json|" + "c" * 40, False),          # webhooks: an integrity key
    ("A12|inbox_runs|inbox/actions/runs|2", False),
])
def test_the_operational_a12_codes_are_lifted_in_the_live_period(m, key, mirrored):
    """R-AN-55 (fourth review, J-4): A12 `probe_failed`, `app_scope`, `routine_connectors`, `inbox_identity` and
    `inbox_config` are operational: in the live period too their pause is lifted by a fresh verdict (after the judge's
    clear, as latched keys), never cleared on the analyst's side; every other A12 code is an integrity key."""
    subject = f"judge_violation:{key}"
    plant(m, [("PAUSED", subject, "2026-12-01T10:00:00Z")], "2026-12-01T10:05:00Z")
    paths, sha = plant(m, [("RESUMED", f"lifted:{subject}", "2026-12-01T13:00:00Z")], "2026-12-01T13:05:00Z",
                       fresh=True)
    adj = [{"utc": "2026-12-01T12:00:00Z", "ref": "latch", "check": "A12", "subject": key, "decision": "clear",
            "note": "owner"}]
    assert state_keys(m.judge(adjudications=adj)) == ([] if mirrored else
                                                      [key_of("resume_unsupported", paths[0], sha)])


def test_a_pause_at_live_from_is_a_live_pause(m):
    """LS is 00:00:00Z of live_from; a PAUSED event at LS is a live integrity pause (mirrored only before LS)."""
    plant(m, [("PAUSED", f"judge_violation:{K_INT}", "2026-11-30T00:00:00Z")], "2026-11-30T00:05:00Z")
    plant(m, [("RESUMED", f"clear:judge_violation:{K_INT}", "2026-11-30T13:00:00Z")], "2026-11-30T13:05:00Z",
          adj=[pause_row(f"judge_violation:{K_INT}", "2026-11-30T12:00:00Z")])
    assert state_keys(m.judge()) == []


def test_the_judge_adjudications_come_from_the_out_folder(m, tmp_path):
    """run_judge reads the judge's own ADJUDICATIONS.csv (R-AN-70) for the `lifted:` check; so does World.judge with
    out_dir."""
    plant(m, [("PAUSED", f"judge_violation:{K_INT}", "2026-11-27T10:00:00Z")], "2026-11-27T10:00:00Z",
          mode=CANARY_MODE)
    plant(m, [("RESUMED", f"lifted:judge_violation:{K_INT}", "2026-11-27T13:00:00Z")], "2026-11-27T13:00:00Z",
          mode=CANARY_MODE, fresh=True)
    out = tmp_path / "out"
    os.makedirs(out)
    report.append_csv(str(out / "ADJUDICATIONS.csv"), report.ADJ_HEADER,
                      [{"utc": "2026-11-27T12:00:00Z", "ref": "latch", "check": "A3", "subject": K_INT,
                        "decision": "clear", "note": "owner"}])
    assert state_keys(m.judge(out_dir=str(out))) == []
    assert len(state_keys(m.judge())) == 1


def test_retire_unsupported(m):
    """R-AN-55, R-AN-67: a RETIRED `violation` dated before LS (live_from 00:00Z), or with no earlier RESUMED
    `clear:judge_violation:K'` for a live integrity pause, is `retire_unsupported`."""
    early, s1 = plant(m, [("RETIRED", "violation", "2026-11-29T10:00:00Z")], "2026-11-29T10:05:00Z")
    unarmed, s2 = plant(m, [("RETIRED", "violation", "2026-12-01T09:00:00Z")], "2026-12-01T09:05:00Z")
    assert state_keys(m.judge()) == sorted([key_of("retire_unsupported", early[0], s1),
                                            key_of("retire_unsupported", unarmed[0], s2)])


def test_retirement_after_a_live_clear_is_supported(m, tmp_path):
    """Armed: a live integrity pause the owner cleared; a new integrity key after it retires the analyst. (Sixth
    review, R6-2: "after" by time, the key's first_seen_utc in the judge's FINDINGS.csv after the clear row's utc.)"""
    plant(m, [("PAUSED", f"judge_violation:{K_INT}", "2026-12-01T10:00:00Z")], "2026-12-01T10:05:00Z")
    plant(m, [("RESUMED", f"clear:judge_violation:{K_INT}", "2026-12-01T13:00:00Z")], "2026-12-01T13:05:00Z",
          adj=[pause_row(f"judge_violation:{K_INT}", "2026-12-01T12:00:00Z")])
    plant(m, [("RETIRED", "violation", "2026-12-02T10:00:00Z")], "2026-12-02T10:05:00Z")
    out = tmp_path / "out"
    os.makedirs(out)
    k2 = "A3|agent_scope|inbox/refs/heads/claude/analyst-y|" + "c" * 40
    report.append_csv(str(out / "FINDINGS.csv"), report.FINDINGS_HEADER,
                      [{"first_seen_utc": "2026-12-01T09:50:00Z", "severity": VIOLATION, "check": "A3", "key": K_INT},
                       {"first_seen_utc": "2026-12-02T09:50:00Z", "severity": VIOLATION, "check": "A3", "key": k2}])
    assert state_keys(m.judge(out_dir=str(out))) == []


def test_an_armed_retirement_dated_before_live_from_is_unsupported(m):
    """Retirement for a VIOLATION exists only in the live period (R-AN-55): even after a live clear, a RETIRED
    `violation` dated before LS is `retire_unsupported`."""
    plant(m, [("PAUSED", f"judge_violation:{K_INT}", "2026-12-01T10:00:00Z")], "2026-12-01T10:05:00Z")
    plant(m, [("RESUMED", f"clear:judge_violation:{K_INT}", "2026-12-01T13:00:00Z")], "2026-12-01T13:05:00Z",
          adj=[pause_row(f"judge_violation:{K_INT}", "2026-12-01T12:00:00Z")])
    ret, sha = plant(m, [("RETIRED", "violation", "2026-11-29T23:59:59Z")], "2026-12-02T10:05:00Z")
    assert state_keys(m.judge()) == [key_of("retire_unsupported", ret[0], sha)]


@pytest.mark.parametrize("subject,mode,paused", [
    (f"judge_violation:{K_OP}", None, "2026-12-01T10:00:00Z"),                 # an operational pause
    (f"judge_violation:{K_INT}", CANARY_MODE, "2026-11-27T10:00:00Z"),         # a canary pause
])
def test_a_clear_of_a_mirrored_pause_never_arms_retirement(m, subject, mode, paused):
    plant(m, [("PAUSED", subject, paused)], paused, mode=mode)
    resumed = fmt_utc(T(paused) + dt.timedelta(hours=3))
    r, s = plant(m, [("RESUMED", f"clear:{subject}", resumed)], resumed, mode=mode,
                 adj=[pause_row(subject, fmt_utc(T(paused) + dt.timedelta(hours=1)))])
    ret, s2 = plant(m, [("RETIRED", "violation", "2026-12-02T10:00:00Z")], "2026-12-02T10:05:00Z")
    assert state_keys(m.judge()) == sorted([key_of("resume_unsupported", r[0], s),
                                            key_of("retire_unsupported", ret[0], s2)])


# ---------------------------------------------------------------- A10's pause intervals (J-D14; R-AN-67)
A10_PLANS = {"2026-11-25_W2": ("missed",), "2026-12-01_W2": ("missed",)}


def a10_runs(world, weeks):
    """Owner-attested in-span runs without an attempt: the canary's 2026-11-25 W2 and the live 2026-12-01 W2."""
    for wk, day in (("2026-W48", "2026-11-25"), ("2026-W49", "2026-12-01")):
        weeks.setdefault(wk, []).append({"routine": "analyst-w2", "run_id": f"r-extra-{day}",
                                         "session_id": f"s-extra-{day}",
                                         "created_utc": f"{day}T13:50:00Z", "status": "success",
                                         "model": "claude-opus-5-5", "model_source": "get_run_log"})


@pytest.fixture(scope="module")
def a10_base(tmp_path_factory):
    return World(str(tmp_path_factory.mktemp("a10") / "w"), canary_days=("2026-11-25",), live_from="2026-11-30",
                 live_to="2026-12-01", now="2026-12-02T23:00:00Z", plans=A10_PLANS,
                 hooks={"runs": a10_runs}).build()


@pytest.fixture
def a10(a10_base, tmp_path):
    return a10_base.clone(str(tmp_path / "copy"))


def in_span(res):
    return sorted(f.detail for f in res.findings.items if f.code == "in_span_without_attempt")


def test_A10_both_runs_are_found_without_a_pause(a10):
    assert len(in_span(a10.judge())) == 2


@pytest.mark.parametrize("lift,found", [("2026-12-01T20:00:00Z", False), ("2026-12-01T10:00:00Z", True)])
def test_A10_a_lifted_resume_ends_the_pause_interval(a10, lift, found):
    """J-D14 (R-AN-67, fourth review): calls are disabled from a PAUSED event to its RESUMED, `lifted:` included.
    Since the fifth review (J-5, decision 33) both ends are the times inbox main first held the events, so
    analyst-inbox-mirror pushes each settle commit 5 minutes after it (an interval stays open while no push of the
    lift is known; tests/test_judge_fifth_review.py)."""
    _, paused = plant(a10, [("PAUSED", f"judge_violation:{K_OP}", "2026-12-01T00:00:00Z")], "2026-12-01T00:05:00Z")
    a10.inbox_activity("refs/heads/main", paused, T("2026-12-01T00:10:00Z"), OWNER, "push")
    _, lifted = plant(a10, [("RESUMED", f"lifted:judge_violation:{K_OP}", lift)], lift, fresh=True)
    a10.inbox_activity("refs/heads/main", lifted, T(lift) + dt.timedelta(minutes=5), OWNER, "push")
    live = [d for d in in_span(a10.judge()) if "2026-12-01_W2" in d]
    assert bool(live) is found


def test_A10_a_canary_window_inside_a_pause_is_not_an_in_span_run(a10):
    """J-D31: the pause rule now pauses the canary's calls (R-AN-55), and `start` refuses `calls_disabled` in any
    mode, so A10's pause intervals cover canary windows too."""
    plant(a10, [("PAUSED", f"judge_violation:{K_INT}", "2026-11-25T00:00:00Z")], "2026-11-25T00:05:00Z")
    found = in_span(a10.judge())
    assert not [d for d in found if "2026-11-25_W2" in d]


# ---------------------------------------------------------------- run_judge: the judge's own clears; the verdict's time
def test_run_judge_hands_the_judge_its_adjudications_and_dates_the_verdict(tmp_path, monkeypatch, capsys):
    """run_judge reads the judge's ADJUDICATIONS.csv from --out for the A11 `lifted:` check (R-AN-67, R-AN-70), and
    the verdict's `asof_utc` is the run's time (R-AN-70, fourth review of A6, N2: analyst-settle judges its age)."""
    import subprocess
    import run_judge
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    ga = tmp_path / "ga"
    ga.mkdir()
    for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "seed"]):
        subprocess.run(["git", "-C", str(ga), *args], check=True, capture_output=True, env=env)
    out = tmp_path / "out"
    os.makedirs(out)
    row = {"utc": "2026-11-01T00:00:00Z", "ref": "latch", "check": "A3", "subject": K_INT, "decision": "clear",
           "note": "owner"}
    report.append_csv(str(out / "ADJUDICATIONS.csv"), report.ADJ_HEADER, [row])
    seen = {}

    class Spy(Judge):
        def __init__(self, *a, **kw):
            seen.update(kw)
            super().__init__(*a, **kw)
    monkeypatch.setattr(run_judge, "Judge", Spy)
    assert run_judge.main(["--repo", str(ga), "--out", str(out), "--site", "none", "--store", "none", "--api", "none",
                           "--hours", "none", "--now", "2026-11-02T00:00:00Z"]) == 0
    assert seen["judge_adjudications"] == [row]
    v = json.loads((out / "analyst_verdict.json").read_text(encoding="utf-8"))
    assert v["asof_utc"] == "2026-11-02T00:00:00Z" and v["schema"] == "analyst-verdict/1"
    assert isinstance(v["violation_keys"], list) and all(isinstance(k, str) for k in v["violation_keys"])
