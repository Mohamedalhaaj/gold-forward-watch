"""Planted cases of the second review of register §16.18 A6 (2026-10-23, decisions 20-23; blockers SEC-1, SEC-2 and
SEC-3), as R-AN-60, R-AN-61, R-AN-66 and R-AN-67 define them at xauusd-quant 62a0d80 (prereg v0.6 §8).

Written from the register text, not from the analyst code:
- A12 `app_scope` (SEC-1): a runs export whose `inbox_checks.app_repositories` has a `repository_selection` other
  than `selected`, or names gold-analyst, gold-forward-watch or xauusd-quant; owner-attested VIOLATION.
  `inbox_checks_missing` (WARNING) also when `inbox_checks` lacks `app_repositories`, for a week with windows;
- A12 `routine_connectors` (SEC-2): a version of `analyst/ROUTINE_CONFIG.json` committed to gold-analyst main at or
  after PINS.inbox_from_utc in which a routine's `raw` lacks `mcp_connections` or `enabled_plugins`, or holds a
  non-empty one; owner-attested VIOLATION;
- A12 `probe_flood` (SEC-3): a listed `claude/probe-*` ref first seen at or after PINS.inbox_from_utc whose name is
  not `claude/probe-<c3|del|wf|result>-<call_id | pYYYYMMDDTHHMMSSZ>`, or more than 40 `branch_creation` entries on
  probe refs in one UTC day; VIOLATION;
- A0 `inbox_blind` (SEC-3): the judge's last complete read of the inbox's activity is more than 24 h old, a
  VIOLATION that holds the verdict at VIOLATION while it lasts; the time is kept across runs in the evidence file
  (fourth review, J-3: and at least two failed runs after it, key `A0|inbox_blind|api|<L>`; more cases in
  tests/test_judge_fourth_review.py);
- the inbox's activity is read with `time_period=month`; older entries come from the `inbox_activity` evidence rows.
"""
import datetime as dt
import os
import subprocess

import pytest

from jlib import report
from jlib.common import VIOLATION, WARNING, fmt_utc, record_form
from jlib.gitrepo import GitRepo
from jlib.judge import EVIDENCE_HEADER, Judge
from jlib.sources import FakeGitHub
from world import GA, INBOX, OWNER, T, World, routine_config

SMALL = dict(canary_days=(), live_from="2026-11-30", live_to="2026-12-01", now="2026-12-02T23:00:00Z")
P49 = "analyst/runs/2026-W49.json"
RC = "analyst/ROUTINE_CONFIG.json"
FLOOD = "A12|probe_flood|inbox/refs/heads/claude/probe-*|2026-12-02"    # fourth review: the sha slot holds the day


def blind(L):
    """A0 inbox_blind's key names its episode by L, the last complete read (fourth review of A6, J-3, J-4)."""
    return f"A0|inbox_blind|api|{L}"


@pytest.fixture(scope="module")
def small_base(tmp_path_factory):
    return World(str(tmp_path_factory.mktemp("small2") / "w"), **SMALL).build()


@pytest.fixture
def m(small_base, tmp_path):
    return small_base.clone(str(tmp_path / "copy"))


def keys(res, check=None, severity=None, code=None):
    return [f.key for f in res.findings.items if (not check or f.check == check) and
            (not severity or f.severity == severity) and (not code or f.code == code)]


def finding(res, key):
    return {f.key: f for f in res.findings.items}[key]


def first_add(world, path):
    out = subprocess.run(["git", "-C", world.repo.path, "log", "--diff-filter=A", "--format=%H", "--", path],
                         capture_output=True, text=True, check=True).stdout.strip()
    return out.split("\n")[-1]


def evidence_of(world, out, **kw):
    res = world.judge(out_dir=str(out), **kw)
    report.write_outputs(res, str(out), world.now, "x")
    return report.read_csv(os.path.join(str(out), "evidence.csv"), EVIDENCE_HEADER)


# ---------------------------------------------------------------- the clean world
def test_the_clean_world_has_none_of_the_new_codes(small_base, tmp_path):
    """The world holds what the owner exports after the second review: `app_repositories` with the inbox only, a
    ROUTINE_CONFIG.json with connectors from before PINS.inbox_from_utc (not judged) and a clean export after it, and
    the probe session's four branches under R-AN-84's names."""
    res = small_base.judge(out_dir=str(tmp_path))
    assert keys(res) == []
    assert res.summary["routine_config_versions_checked"] == 2           # fourth review: and the version in force
    assert res.summary["inbox_last_complete_read_utc"] == small_base.now


# ---------------------------------------------------------------- A12 app_scope and inbox_checks_missing (SEC-1)
def add_export(world, week, app="omit", when="2026-12-02T20:00:00Z"):
    """An owner runs export for a week without windows (create-only: a new file), with `app_repositories` = app."""
    rec = {"schema": "analyst-runs/1", "iso_week": week, "exported_utc": when, "attested_by": "owner",
           "routines": [], "runs": [],
           "inbox_checks": {"checked_utc": when, "hooks": 0, "deploy_keys": 1, "actions_enabled": False,
                            "security_log_hook_events": 0,
                            # §16.18 A7 (detection 2): the security log's filter and events, consistent
                            "security_log_filter": f"repo:{INBOX} action:hook", "security_log_events": []}}
    if app != "omit":
        rec["inbox_checks"]["app_repositories"] = app
    path = f"analyst/runs/{week}.json"
    world.repo.write(path, record_form(rec))
    return path, world.repo.commit("owner runs export", T(when))


@pytest.mark.parametrize("app,detail", [
    ({"repository_selection": "all", "full_names": [INBOX]}, "repository_selection; all"),
    ({"repository_selection": None, "full_names": [INBOX]}, "repository_selection; None"),
    ({"repository_selection": "selected", "full_names": [GA, INBOX]}, GA),
    ({"repository_selection": "selected", "full_names": [INBOX, f"{OWNER}/gold-forward-watch"]},
     f"{OWNER}/gold-forward-watch"),
    ({"repository_selection": "selected", "full_names": [f"{OWNER}/xauusd-quant"]}, f"{OWNER}/xauusd-quant"),
    ({"repository_selection": "selected", "full_names": ["mohamedalhaaj/Gold-Analyst"]}, "mohamedalhaaj/Gold-Analyst"),
])
def test_A12_app_scope(m, app, detail):
    path, sha = add_export(m, "2026-W50", app)
    res = m.judge()
    key = f"A12|app_scope|{path}|{sha}"
    assert keys(res) == [key]
    f = finding(res, key)
    assert f.severity == VIOLATION and f.owner_attested and detail in f.detail


@pytest.mark.parametrize("app", [
    {"repository_selection": "selected", "full_names": [INBOX]},
    {"repository_selection": "selected", "full_names": [INBOX, f"{OWNER}/gold-analyst-exam", f"{OWNER}/other"]},
    "omit",                                      # a week without windows: no inbox_checks_missing either
])
def test_A12_app_scope_allows_the_inbox_and_other_repositories(m, app):
    add_export(m, "2026-W50", app)
    assert keys(m.judge()) == []


@pytest.mark.parametrize("app,codes", [
    ("omit", ["inbox_checks_missing"]),
    ({"repository_selection": "selected", "full_names": INBOX}, ["inbox_checks_missing"]),
    ({"repository_selection": "selected"}, ["inbox_checks_missing"]),
    ({"repository_selection": "all"}, ["app_scope", "inbox_checks_missing"]),
])
def test_A12_inbox_checks_missing_without_app_repositories(tmp_path, app, codes):
    def rec_hook(world, wk, rec):
        if wk == "2026-W49":
            if app == "omit":
                del rec["inbox_checks"]["app_repositories"]
            else:
                rec["inbox_checks"]["app_repositories"] = app
    world = World(str(tmp_path / "s"), hooks={"runs_record": rec_hook}, **SMALL).build()
    res = world.judge()
    sha = first_add(world, P49)
    assert sorted(keys(res)) == sorted(f"A12|{c}|{P49}|{sha}" for c in codes)
    missing = finding(res, f"A12|inbox_checks_missing|{P49}|{sha}")
    assert missing.severity == WARNING and missing.owner_attested and "app_repositories" in missing.detail


# ---------------------------------------------------------------- A12 routine_connectors (SEC-2)
def commit_config(world, rec, when, raw_bytes=None):
    world.repo.write(RC, raw_bytes if raw_bytes is not None else record_form(rec))
    return world.repo.commit("owner: routine config export", T(when))


def test_A12_routine_connectors_every_version_from_inbox_from(m):
    bad1 = routine_config()
    bad1["routines"][0]["raw"]["mcp_connections"] = [{"name": "Gmail", "uuid": "x"}]
    s1 = commit_config(m, bad1, "2026-12-02T10:00:00Z")
    bad2 = routine_config()
    del bad2["routines"][4]["raw"]["enabled_plugins"]
    s2 = commit_config(m, bad2, "2026-12-02T11:00:00Z")
    s3 = commit_config(m, routine_config(), "2026-12-02T12:00:00Z")       # a clean export hides no earlier one
    res = m.judge()
    assert sorted(keys(res)) == sorted([f"A12|routine_connectors|{RC}|{s1}", f"A12|routine_connectors|{RC}|{s2}"])
    f1, f2 = finding(res, f"A12|routine_connectors|{RC}|{s1}"), finding(res, f"A12|routine_connectors|{RC}|{s2}")
    assert f1.severity == f2.severity == VIOLATION and f1.owner_attested and f2.owner_attested
    assert "analyst-w1" in f1.detail and "mcp_connections" in f1.detail
    assert "analyst-probe" in f2.detail and "enabled_plugins" in f2.detail
    assert res.summary["routine_config_versions_checked"] == 5           # with the version in force (fourth review)
    assert s3 not in " ".join(keys(res))


def _set(path_fn):
    def make():
        rec = routine_config()
        path_fn(rec)
        return rec
    return make


@pytest.mark.parametrize("make", [
    _set(lambda r: r["routines"][1]["raw"].update(enabled_plugins=["github@claude-plugins"])),
    _set(lambda r: r["routines"][2]["raw"].pop("mcp_connections")),
    _set(lambda r: r["routines"][3]["raw"].update(mcp_connections=None)),
    _set(lambda r: r["routines"][0]["raw"].update(mcp_connections={})),
    _set(lambda r: r["routines"][0].update(raw="x")),
    _set(lambda r: r["routines"][0].pop("raw")),
    _set(lambda r: r["routines"].append("analyst-extra")),
    _set(lambda r: r.pop("routines")),
    None,                                                                   # not JSON
])
def test_A12_routine_connectors_breach_forms(m, make):
    if make is None:
        sha = commit_config(m, None, "2026-12-02T10:00:00Z", raw_bytes=b"{not json\n")
    else:
        sha = commit_config(m, make(), "2026-12-02T10:00:00Z")
    res = m.judge()
    assert keys(res) == [f"A12|routine_connectors|{RC}|{sha}"]


def test_A12_routine_connectors_counts_from_inbox_from(m):
    """A version committed before PINS.inbox_from_utc is judged only when it is the version in force then (fourth
    review of A6, N3: the newest committed before it); one committed at that second is judged as a later version."""
    bad = routine_config()
    bad["routines"][0]["raw"]["mcp_connections"] = [{"name": "Drive"}]
    commit_config(m, bad, fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=2)))
    clean = routine_config()
    clean["exported_utc"] = "2026-11-03T00:00:00Z"
    commit_config(m, clean, fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1)))     # supersedes it: not judged
    assert keys(m.judge()) == []
    bad["routines"][0]["raw"]["mcp_connections"] = [{"name": "Calendar"}]      # a new version (an empty commit is none)
    sha = commit_config(m, bad, m.inbox_from)
    assert keys(m.judge()) == [f"A12|routine_connectors|{RC}|{sha}"]


# ---------------------------------------------------------------- A12 probe_flood (SEC-3)
def probe_branch(world, name, when, sha="e" * 40, listed=True, typ="branch_creation"):
    ref = f"refs/heads/{name}"
    world.inbox_activity(ref, sha, T(when), OWNER, typ)
    if listed:
        world.api["ls_remote"][INBOX].append([sha, ref])
    return ref


@pytest.mark.parametrize("name", ["claude/probe-c3-2026-12-01_W1", "claude/probe-del-2026-12-01_W2",
                                  "claude/probe-wf-p20261202T101500Z", "claude/probe-result-p20261202T101500Z"])
def test_A12_probe_flood_names_of_R_AN_84_pass(m, name):
    probe_branch(m, name, "2026-12-02T10:16:00Z")
    assert keys(m.judge()) == []


@pytest.mark.parametrize("name", ["claude/probe-x-1", "claude/probe-ga-p20261202T101500Z",
                                  "claude/probe-c3-2026-12-01_W3", "claude/probe-c3-p20261202T1015Z",
                                  "claude/probe-c3-p20261202T101500Z-2", "claude/probe-wf-owner",
                                  "claude/probe-result-p20261202T101500Z/x", "claude/probe-C3-p20261202T101500Z",
                                  "claude/probe-"])
def test_A12_probe_flood_a_name_outside_R_AN_84(m, name):
    sha = "f" * 40
    ref = probe_branch(m, name, "2026-12-02T10:16:00Z", sha=sha)
    res = m.judge()
    assert keys(res) == [f"A12|probe_flood|inbox/{ref}|{sha}"]
    assert res.findings.items[0].severity == VIOLATION


def test_A12_probe_flood_names_first_seen_before_inbox_from_or_unseen_are_not_judged(m):
    """The owner's set-up probes (`claude/probe-ok-1`, `claude/probe-wf-owner`) predate PINS.inbox_from_utc; a later
    entry on the same ref does not move its first entry. A listed ref with no known entry gives nothing."""
    ref = probe_branch(m, "claude/probe-ok-1", "2026-11-20T09:52:00Z")
    m.inbox_activity(ref, "d" * 40, T("2026-12-02T10:00:00Z"), OWNER, "push")
    m.api["ls_remote"][INBOX].append(["c" * 40, "refs/heads/claude/probe-unseen"])
    assert keys(m.judge()) == []


@pytest.mark.parametrize("n,spread,want", [(41, False, True), (40, False, False), (41, True, False)])
def test_A12_probe_flood_more_than_40_creations_in_one_utc_day(m, n, spread, want):
    for i in range(n):
        day = "2026-12-01" if spread and i % 2 else "2026-12-02"
        probe_branch(m, f"claude/probe-c3-p{day.replace('-', '')}T{i // 60:02d}{i % 60:02d}00Z",
                     f"{day}T{i // 60:02d}:{i % 60:02d}:00Z", sha=f"{i:040x}", listed=False)
    res = m.judge()
    assert keys(res) == ([FLOOD] if want else [])
    if want:
        assert finding(res, FLOOD).severity == VIOLATION and "2026-12-02" in finding(res, FLOOD).detail


def test_A12_probe_flood_counts_only_creations_from_inbox_from(m):
    for i in range(30):                          # before PINS.inbox_from_utc (2026-11-27T10:00:00Z): not counted
        probe_branch(m, f"claude/probe-c3-p20261127T09{i:02d}00Z", f"2026-11-27T09:{i:02d}:00Z", sha=f"{i:040x}",
                     listed=False)
    for i in range(30):
        probe_branch(m, f"claude/probe-del-p20261127T10{i:02d}00Z", f"2026-11-27T10:{i:02d}:00Z",
                     sha=f"{i + 100:040x}", listed=False)
    for i in range(20):                          # pushes are not creations
        m.inbox_activity("refs/heads/claude/probe-del-p20261127T100000Z", f"{i + 200:040x}",
                         T(f"2026-11-27T11:{i:02d}:00Z"), OWNER, "push")
    assert keys(m.judge()) == []


def test_A12_probe_flood_from_the_evidence_rows_after_the_month(m, tmp_path):
    """time_period=month: entries that left the API's list still count from the judge's `inbox_activity` rows."""
    for i in range(41):
        probe_branch(m, f"claude/probe-wf-p20261202T00{i:02d}00Z", f"2026-12-02T00:{i:02d}:00Z", sha=f"{i:040x}",
                     listed=False)
    bad = probe_branch(m, "claude/probe-zz", "2026-12-02T01:00:00Z", sha="a" * 40)
    want = sorted([FLOOD, f"A12|probe_flood|inbox/{bad}|{'a' * 40}"])
    ev = evidence_of(m, tmp_path / "ev")
    m.api["repo_activity"][INBOX] = [a for a in m.api["repo_activity"][INBOX]
                                     if not a["ref"].startswith("refs/heads/claude/probe-")]
    assert sorted(keys(m.judge(evidence=ev))) == want
    assert keys(m.judge()) == []                 # without the evidence rows the judge cannot see them


# ---------------------------------------------------------------- A0 inbox_blind (SEC-3)
def aged(ev, when, sources=("inbox_read", "inbox_activity")):
    out = []
    for r in ev:
        r = dict(r)
        if r["source"] in sources:
            r["judge_utc"] = when
        out.append(r)
    return out


def failing(world):
    return FakeGitHub(world.api_data(), repo=GA, fail={"repo_activity"})


def failed_run(when):
    """An `inbox_read_failed` evidence row (fourth review of A6, J-3; R-AN-69): a judge run whose read failed."""
    return dict({k: "" for k in EVIDENCE_HEADER}, judge_utc=when, source="inbox_read_failed", ref=INBOX)


def test_A0_inbox_blind_after_24_hours_without_a_complete_read(m, tmp_path):
    ev = evidence_of(m, tmp_path / "ev")
    assert [r["judge_utc"] for r in ev if r["source"] == "inbox_read"] == [m.now]
    now = T(m.now)
    before = [failed_run(fmt_utc(now - dt.timedelta(hours=1)))]          # fourth review: a second failed run
    day = aged(ev, fmt_utc(now - dt.timedelta(hours=24)))
    assert keys(m.judge(api=failing(m), evidence=day + before)) == ["A0|inbox_api_unreachable|api|-"]
    L = fmt_utc(now - dt.timedelta(hours=24, seconds=1))
    late = aged(ev, L)
    assert keys(m.judge(api=failing(m), evidence=late)) == ["A0|inbox_api_unreachable|api|-"]   # one run only
    res = m.judge(api=failing(m), evidence=late + before)
    assert sorted(keys(res)) == sorted(["A0|inbox_api_unreachable|api|-", blind(L)])
    assert finding(res, blind(L)).severity == VIOLATION
    assert finding(res, "A0|inbox_api_unreachable|api|-").severity == WARNING
    # a complete read ends it, and records its own time
    res = m.judge(evidence=late + before)
    assert keys(res) == [] and [r["source"] for r in res.evidence_new] == ["inbox_read"]


def test_A0_inbox_blind_keeps_the_time_of_a_read_that_listed_nothing_new(m, tmp_path):
    """The `inbox_read` row carries the last complete read across runs even when it added no `inbox_activity` row;
    `inbox_activity` rows also prove a complete read (the rows of runs from before this change)."""
    now = T(m.now)
    ev = evidence_of(m, tmp_path / "ev")
    old, recent = fmt_utc(now - dt.timedelta(days=3)), fmt_utc(now - dt.timedelta(hours=2))
    only_read = aged(aged(ev, old, ("inbox_activity",)), recent, ("inbox_read",))
    assert keys(m.judge(api=failing(m), evidence=only_read)) == ["A0|inbox_api_unreachable|api|-"]
    no_read_rows = [r for r in aged(ev, recent, ("inbox_activity",)) if r["source"] != "inbox_read"]
    assert keys(m.judge(api=failing(m), evidence=no_read_rows)) == ["A0|inbox_api_unreachable|api|-"]
    both_old = aged(ev, old) + [failed_run(recent)]
    assert blind(old) in keys(m.judge(api=failing(m), evidence=both_old))


def test_A0_inbox_blind_with_no_read_recorded_counts_from_inbox_from(m):
    prior = [failed_run(fmt_utc(T(m.now) - dt.timedelta(hours=12)))]
    assert blind(m.inbox_from) in keys(m.judge(api=failing(m), evidence=prior))   # inbox_from + 5 days, never read
    just = fmt_utc(T(m.inbox_from) + dt.timedelta(hours=23))
    prior = [failed_run(fmt_utc(T(m.inbox_from) + dt.timedelta(hours=22)))]
    assert not [k for k in keys(m.judge(api=failing(m), now=just, evidence=prior)) if "inbox_blind" in k]


def test_A0_inbox_blind_without_an_api_client(m):
    """No API client (an offline run) reads nothing: a failed read (fourth review: blind once a second failed run
    follows a last complete read more than a day old)."""
    def run(evidence):
        git = GitRepo(m.repo.path)
        try:
            return Judge(git, m.now, api=None, evidence_rows=evidence).run()
        finally:
            git.close()
    assert "A0|inbox_api_unreachable|api|-" in keys(run([]), "A0")
    assert not [k for k in keys(run([]), "A0") if "inbox_blind" in k]
    res = run([failed_run(fmt_utc(T(m.now) - dt.timedelta(hours=2)))])
    assert {blind(m.inbox_from), "A0|inbox_api_unreachable|api|-"} <= set(keys(res, "A0"))


def test_A0_inbox_blind_is_in_force_while_it_lasts_and_never_latched(m, tmp_path):
    """The verdict is VIOLATION while the judge is blind (P7 is then false and the pause rule sees the key). It is
    never latched or cleared (judge decision J-D27; fourth review: the key names its episode, L): it is in force
    exactly while the condition holds, and a second run of the same episode reports it again."""
    out = tmp_path / "out"
    ev = evidence_of(m, out)
    L = fmt_utc(T(m.now) - dt.timedelta(days=2))
    late = aged(ev, L) + [failed_run(fmt_utc(T(m.now) - dt.timedelta(days=1)))]
    res = m.judge(api=failing(m), evidence=late)
    report.append_csv(str(out / "ADJUDICATIONS.csv"), report.ADJ_HEADER,
                      [{"utc": m.now, "ref": "latch", "check": "A0", "subject": blind(L), "decision": "clear",
                        "note": "x"}])
    v = report.write_outputs(res, str(out), m.now, "x")
    assert v["analyst_verdict"] == "VIOLATION" and v["violation_keys"] == [blind(L)]
    assert "inbox_blind" not in (out / "FINDINGS.csv").read_text(encoding="utf-8")
    assert blind(L) in (out / "REPORT.md").read_text(encoding="utf-8")
    v = report.write_outputs(m.judge(evidence=late), str(out), m.now, "x")
    assert v["analyst_verdict"] == "SOUND" and v["violation_keys"] == []
    v = report.write_outputs(m.judge(api=failing(m), evidence=late), str(out), m.now, "x")
    assert v["violation_keys"] == [blind(L)]


# ---------------------------------------------------------------- the activity read (SEC-3)
def test_older_entries_come_from_the_evidence_rows(base, tmp_path):
    """The read returns the last month only; entries that left it are the judge's `inbox_activity` rows (lock times,
    closer races, inbox main), so the base world stays clean."""
    ev = evidence_of(base, tmp_path / "ev")
    data = base.api_data()
    data["repo_activity"][INBOX] = [a for a in data["repo_activity"][INBOX] if a["timestamp"] >= "2026-11-25"]
    assert keys(base.judge(api=FakeGitHub(data, repo=GA), evidence=ev)) == []
    assert keys(base.judge(api=FakeGitHub(data, repo=GA)))                  # without them, findings
