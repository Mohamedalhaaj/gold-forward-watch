"""Planted cases of the third review of register §16.18 A7 (2026-10-24, decisions 21 and 22; notes N1 and N2), as
R-AN-25, R-AN-55, R-AN-60, R-AN-61, R-AN-66, R-AN-67, R-AN-74, R-AN-84 and R-AN-85 define them at xauusd-quant 12ffdda
(prereg v0.6 R1 Isolation (e) and (f), R5 C20, §8).

Written from the register text, not from the analyst code:
- A13 `routine_project` (decision 21; owner-attested, operational): in a version of `analyst/ROUTINE_CONFIG.json`
  that `routine_connectors` judges, a routine whose `project` is present and not null, or whose `raw` holds, at any
  depth, a key whose name contains `project` (case ignored) with a value other than null, "", [] or {}; in a version
  committed at or after PINS.inbox_from_utc, also a routine without `project`. In a runs export, file by file, an
  entry of `routines` without `project` or with a `project` other than null (judge decisions J-D41, J-D42);
- A13 `cc_version_below` and `cc_version_unknown` (decision 22; self-reported, operational): the attempt records and
  call files at main's head of a guarded session (its `repo_head_sha` names a gold-analyst commit whose tree holds
  `.claude/hooks/guard.py`), judged by R-AN-85's version rule against 2.1.295; a call file gives `cc_version_below`
  only (J-D43);
- a probe record with `cc_version` stays readable, and A12 `probe_failed` and `probe_incomplete` are unchanged.
The clean world gives none of these: its routine export in force at PINS.inbox_from_utc has no `project` key, its
later export and its runs exports carry `project` null, and its sessions report Claude Code 2.9.0 from guarded commits.
"""
import datetime as dt
import json
import os

import pytest

from jlib import gitrepo, report, sessionguard as sg
from jlib.common import VIOLATION, WARNING, fmt_utc, record_form
from jlib.judge import operational
from test_judge_second_review import commit_config, first_add
from test_judge_session_guard import checks
from world import GUARD_PY_BYTES, OMIT, T, World, routine_config

SMALL = dict(canary_days=(), live_from="2026-11-30", live_to="2026-12-01", now="2026-12-02T23:00:00Z")
RC = "analyst/ROUTINE_CONFIG.json"
NEW = ("routine_project", "cc_version_below", "cc_version_unknown")
FOLDERS = ("analyst/attempts/", "analyst/calls/", "analyst/canary/attempts/", "analyst/canary/calls/")
PLANTED = "2026-12-02T20:00:00Z"


@pytest.fixture(scope="module")
def small_base(tmp_path_factory):
    return World(str(tmp_path_factory.mktemp("guard3") / "w"), **SMALL).build()


@pytest.fixture
def m(small_base, tmp_path):
    return small_base.clone(str(tmp_path / "copy"))


def keys(res, check=None, code=None):
    return sorted(f.key for f in res.findings.items if (not check or f.check == check) and
                  (not code or f.code == code))


def new_keys(res):
    """The keys of the three new codes; and no check may have crashed on a planted record."""
    assert keys(res, check="A0", code="check_crashed") == []
    return sorted(k for c in NEW for k in keys(res, check="A13", code=c))


def finding(res, key):
    return {f.key: f for f in res.findings.items}[key]


# ================================================================ R-AN-85 "Claude Code version", unit level
@pytest.mark.parametrize("v,cls", [
    # the register's examples
    ("2.1.295", "meets"), ("2.1.309 (Claude Code)", "meets"), ("2.2.0", "meets"), ("3.0.0", "meets"),
    ("2.1.294", "below"), ("2.0.999", "below"),
    ("v2.1.309", "unknown"), ("2.1.309-beta", "unknown"), ("2.1", "unknown"), ("", "unknown"),
    (None, "unknown"),
    # the rule's edges: the part before the first space (U+0020), 1 to 9 ASCII digits, integers compared in order
    ("2.1.309 ", "meets"), ("10.0.0", "meets"), ("002.001.0295", "meets"), ("2.1.296 anything at all", "meets"),
    ("2.1.294 (Claude Code)", "below"), ("1.99.999", "below"), ("0.0.0", "below"), ("2.0.1000", "below"),
    ("123456789.0.0", "meets"), ("2.1.1234567890", "unknown"), (" 2.1.309", "unknown"), ("2.1.309\n", "unknown"),
    ("2.1.309\t(Claude Code)", "unknown"), ("2.1.309.1", "unknown"), ("2..309", "unknown"), ("2.1.3a9", "unknown"),
    ("٢.١.٣٠٩", "unknown"), ("２.１.３０９", "unknown"),
    (2.1, "unknown"), (21295, "unknown"), (True, "unknown"), (["2.1.309"], "unknown"), ({"v": "2.1.309"}, "unknown"),
])
def test_the_version_rule(v, cls):
    assert sg.cc_version_class(v) == cls


def test_the_three_keys_are_operational():
    """R-AN-55, R-AN-67 (third review of A7): `routine_project`, `cc_version_below` and `cc_version_unknown` pause the
    analyst while the verdict carries them and never retire it."""
    for k in (f"A13|routine_project|{RC}|{'a' * 40}", "A13|routine_project|analyst/runs/2026-W50.json|" + "b" * 40,
              "A13|cc_version_below|analyst/attempts/2026-12-02_W1_1.json|" + "c" * 40,
              "A13|cc_version_below|analyst/canary/calls/2026-12-02_W1.json|" + "d" * 40,
              "A13|cc_version_unknown|analyst/attempts/2026-12-02_W1_1.json|" + "e" * 40):
        assert operational(k)
    assert not operational("A13|forbidden_attempt|analyst/runs/2026-W50.json|r#1")


def test_the_clean_world_has_none_of_the_new_codes(small_base):
    """Its routine export in force at PINS.inbox_from_utc has no `project` key (no finding), the later one and the runs
    exports carry `project` null, and every attempt record and call file is a guarded session's, at 2.9.0."""
    res = small_base.judge()
    assert keys(res) == []
    assert res.summary["routine_config_versions_checked"] == 2
    n = sum(len([x for x in os.listdir(os.path.join(small_base.repo.path, f)) if x.endswith(".json")])
            for f in FOLDERS if os.path.isdir(os.path.join(small_base.repo.path, f)))
    assert n == 8 and res.summary["cc_version_records_checked"] == n           # 4 windows: an attempt and a call each


# ================================================================ A13 routine_project: ROUTINE_CONFIG.json (R-AN-61)
def rk(sha, path=RC):
    return f"A13|routine_project|{path}|{sha}"


def with_project(i, value, **kw):
    rec = routine_config(**kw)
    rec["routines"][i]["project"] = value
    return rec


def test_routine_project_a_routine_in_a_project(m):
    sha = commit_config(m, with_project(0, "Gold analyst"), "2026-12-02T10:00:00Z")
    res = m.judge()
    assert new_keys(res) == [rk(sha)]
    f = finding(res, rk(sha))
    assert f.severity == VIOLATION and f.owner_attested
    assert "analyst-w1" in f.detail and "project" in f.detail and "Gold" not in f.detail     # no value is printed
    assert keys(res, check="A12") == []                                                       # the connectors are []


@pytest.mark.parametrize("value", ["x", "", False, 0, {}, [], {"name": "p"}, ["p"]])
def test_routine_project_only_null_is_accepted(m, value):
    sha = commit_config(m, with_project(4, value), "2026-12-02T10:00:00Z")      # analyst-probe, the fifth routine
    res = m.judge()
    assert new_keys(res) == [rk(sha)]
    assert "analyst-probe" in finding(res, rk(sha)).detail


def test_routine_project_null_gives_nothing(m):
    commit_config(m, with_project(0, None), "2026-12-02T10:00:00Z")
    assert new_keys(m.judge()) == []


def test_routine_project_a_later_version_without_the_key(m):
    sha = commit_config(m, routine_config(project=OMIT), "2026-12-02T10:00:00Z")
    res = m.judge()
    assert new_keys(res) == [rk(sha)]
    assert "lacks project" in finding(res, rk(sha)).detail


def test_routine_project_one_routine_without_the_key(m):
    rec = routine_config()
    del rec["routines"][2]["project"]
    sha = commit_config(m, rec, "2026-12-02T10:00:00Z")
    res = m.judge()
    assert new_keys(res) == [rk(sha)]
    assert finding(res, rk(sha)).detail == "analyst-lesson lacks project"


def test_routine_project_the_version_in_force_without_the_key_gives_nothing(m):
    """The export in force (gold-analyst d1725d7) has no `project` key, and that alone raises no finding."""
    sha = commit_config(m, routine_config(project=OMIT), fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1)))
    res = m.judge()
    assert new_keys(res) == []
    assert res.summary["routine_config_versions_checked"] == 2 and sha


def test_routine_project_a_version_committed_at_inbox_from_without_the_key(m):
    sha = commit_config(m, routine_config(project=OMIT), m.inbox_from)
    assert new_keys(m.judge()) == [rk(sha)]


def test_routine_project_the_version_in_force_with_a_project(m):
    sha = commit_config(m, with_project(1, "p", project=OMIT), fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1)))
    assert new_keys(m.judge()) == [rk(sha)]


def test_routine_project_the_version_in_force_with_a_raw_project_field(m):
    rec = routine_config(project=OMIT)
    rec["routines"][3]["raw"]["project_id"] = "proj_1"
    sha = commit_config(m, rec, fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1)))
    res = m.judge()
    assert new_keys(res) == [rk(sha)]
    assert "analyst-revision" in finding(res, rk(sha)).detail and "proj_1" not in finding(res, rk(sha)).detail


def test_routine_project_a_version_superseded_before_inbox_from_is_not_judged(m):
    commit_config(m, with_project(0, "p"), fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=2)))
    commit_config(m, routine_config(project=OMIT), fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1)))
    assert new_keys(m.judge()) == []


@pytest.mark.parametrize("raw,found", [
    ({"project_id": "p1"}, True),
    ({"Project": {"name": "x"}}, True),
    ({"PROJECT_NAME": "x"}, True),
    ({"session_context": {"projectUuid": "u"}}, True),                              # at any depth
    ({"x": [{"y": [{"subProject": 0}]}]}, True),                                    # inside lists; 0 is a value
    ({"project": False}, True),
    ({"projects": ["a"]}, True),
    ({"project": {"id": None}}, True),                                              # a non-empty object
    ({"project": None, "project_id": "", "projects": [], "projectConfig": {}}, False),
    ({"x": [{"project": None}]}, False),
    ({"name": "project", "note": "a project"}, False),                              # values are not key names
])
def test_routine_project_raw_fields(m, raw, found):
    rec = routine_config()
    rec["routines"][0]["raw"].update(raw)
    sha = commit_config(m, rec, "2026-12-02T10:00:00Z")
    assert new_keys(m.judge()) == ([rk(sha)] if found else [])


@pytest.mark.parametrize("form", ["routine not an object", "no routines", "not json"])
def test_routine_project_a_version_that_cannot_show_null(m, form):
    """J-D42: where a missing key counts, a version that is not a JSON record with a `routines` list, or an entry that
    is not an object, cannot show `project` null and is reported, as `routine_connectors` reports it."""
    rec = routine_config()
    if form == "routine not an object":
        rec["routines"].append("analyst-extra")
    elif form == "no routines":
        rec.pop("routines")
    sha = commit_config(m, rec, "2026-12-02T10:00:00Z", raw_bytes=b"{not json\n" if form == "not json" else None)
    res = m.judge()
    assert new_keys(res) == [rk(sha)]
    assert keys(res, check="A12") == [f"A12|routine_connectors|{RC}|{sha}"]


@pytest.mark.parametrize("form", ["routine not an object", "no routines", "not json"])
def test_routine_project_the_version_in_force_that_cannot_show_null_is_routine_connectors_only(m, form):
    rec = routine_config(project=OMIT)
    if form == "routine not an object":
        rec["routines"].append("analyst-extra")
    elif form == "no routines":
        rec.pop("routines")
    sha = commit_config(m, rec, fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1)),
                        raw_bytes=b"{not json\n" if form == "not json" else None)
    res = m.judge()
    assert new_keys(res) == []
    assert keys(res, check="A12") == [f"A12|routine_connectors|{RC}|{sha}"]


def test_routine_project_each_version_has_its_key(m):
    s1 = commit_config(m, with_project(0, "a"), "2026-12-02T10:00:00Z")
    s2 = commit_config(m, routine_config(project=OMIT), "2026-12-02T11:00:00Z")
    s3 = commit_config(m, routine_config(), "2026-12-02T12:00:00Z")           # a clean export hides no earlier one
    res = m.judge()
    assert new_keys(res) == sorted([rk(s1), rk(s2)]) and s3 not in " ".join(keys(res))


# ================================================================ A13 routine_project: the runs exports (R-AN-60)
def runs_export(world, routines, week, when=PLANTED, **extra):
    """An owner runs export for a week without windows (create-only: a new file). Returns (path, commit)."""
    rec = {"schema": "analyst-runs/1", "iso_week": week, "exported_utc": when, "attested_by": "owner",
           "routines": routines, "runs": [], "inbox_checks": checks()}
    rec.update(extra)
    if routines is OMIT:
        del rec["routines"]
    path = f"analyst/runs/{week}.json"
    world.repo.write(path, record_form(rec))
    return path, world.repo.commit("owner runs export", T(when))


def entry(name="analyst-w1", project=None):
    e = {"name": name, "trigger_id": "t1", "model": "claude-opus-5-5", "effort": "high", "crons": [], "enabled": True}
    if project is not OMIT:
        e["project"] = project
    return e


@pytest.mark.parametrize("routines,found", [
    ([entry(project="Gold analyst")], True),
    ([entry(project=OMIT)], True),
    ([entry(), entry("analyst-probe", "")], True),
    ([entry(project=False)], True),
    ([entry(project={})], True),
    (["analyst-w1"], True),                                                  # an entry that is not an object
    ([entry(), entry("analyst-w2"), entry("analyst-probe")], False),
    ([], False),
])
def test_routine_project_in_a_runs_export(m, routines, found):
    path, sha = runs_export(m, routines, "2026-W46")
    res = m.judge()
    assert new_keys(res) == ([rk(sha, path)] if found else [])
    if found:
        f = finding(res, rk(sha, path))
        assert f.severity == VIOLATION and f.owner_attested and "Gold" not in f.detail


@pytest.mark.parametrize("routines", [OMIT, "analyst-w1", {"name": "analyst-w1", "project": None}])
def test_routine_project_a_runs_export_without_a_routines_list(m, routines):
    """J-D42: an export added at or after PINS.inbox_from_utc whose `routines` is missing or not a list cannot show
    `project` null."""
    path, sha = runs_export(m, routines, "2026-W46")
    assert new_keys(m.judge()) == [rk(sha, path)]


def test_routine_project_each_runs_export_is_judged_by_its_path(m):
    p1, s1 = runs_export(m, [entry(project="x")], "2026-W45", "2026-12-02T19:00:00Z")
    p2, s2 = runs_export(m, [entry(project="x")], "2026-W46", iso_week="2026-W45")       # claims another week
    p3, _ = runs_export(m, [entry()], "2026-W47", "2026-12-02T21:00:00Z")
    assert new_keys(m.judge()) == sorted([rk(s1, p1), rk(s2, p2)])


def test_routine_project_a_runs_export_added_before_inbox_from(m):
    """J-D41: in an export added before PINS.inbox_from_utc a missing key gives nothing (the row's rule for the
    version in force); a `project` other than null is reported in every export."""
    before = fmt_utc(T(m.inbox_from) - dt.timedelta(seconds=1))
    runs_export(m, [entry(project=OMIT)], "2026-W45", before)
    p2, s2 = runs_export(m, [entry(project="x")], "2026-W46", before)
    p3, s3 = runs_export(m, [entry(project=OMIT)], "2026-W47", m.inbox_from)                # at inbox_from: judged
    assert new_keys(m.judge()) == sorted([rk(s2, p2), rk(s3, p3)])


def test_routine_project_without_inbox_from_nothing_is_judged(tmp_path):
    def build(world):
        pins = json.loads(open(os.path.join(world.repo.path, "analyst/PINS.json"), encoding="utf-8").read())
        del pins["inbox_from_utc"]
        world.repo.write("analyst/PINS.json", record_form(pins))

    def config(world, rec):
        rec["routines"][0]["project"] = "p"

    def runs_record(world, wk, rec):
        rec["routines"][0]["project"] = "p"
        del rec["routines"][1]["project"]
    res = World(str(tmp_path / "w"), hooks={"build": build, "routine_config": config, "runs_record": runs_record},
                **SMALL).build().judge()
    assert keys(res, code="routine_project") == []


# ================================================================ A13 cc_version_below / cc_version_unknown (R-AN-85)
def source(world, folder):
    """A world record of the same kind (an attempt record or a call file), as JSON."""
    kind = "attempts" if folder.endswith("attempts/") else "calls"
    d = os.path.join(world.repo.path, "analyst", kind)
    name = sorted(n for n in os.listdir(d) if n.endswith(".json"))[0]
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return json.load(f)


def plant(world, folder, cc="2.9.0", head="default", sr="keep", name=None, when=PLANTED):
    """A record in `folder` (a copy of the world's own record of that kind) with self_reported.cc_version = cc (OMIT
    leaves the key out) and repo_head_sha = head (default: main's head, a guarded commit). Returns (path, commit)."""
    rec = source(world, folder)
    rec["repo_head_sha"] = world.repo.head() if head == "default" else head
    if head is OMIT:
        del rec["repo_head_sha"]
    if sr != "keep":
        if sr is OMIT:
            del rec["self_reported"]
        else:
            rec["self_reported"] = sr
    elif cc is OMIT:
        del rec["self_reported"]["cc_version"]
    else:
        rec["self_reported"]["cc_version"] = cc
    if name is None:
        name = "2026-12-02_W1_1.json" if folder.endswith("attempts/") else "2026-12-02_W1.json"
    path = folder + name
    world.repo.write(path, record_form(rec))
    return path, world.repo.commit("a planted session record", T(when))


def ck(code, path, sha):
    return f"A13|{code}|{path}|{sha}"


@pytest.mark.parametrize("folder", FOLDERS)
@pytest.mark.parametrize("cc", ["2.1.294", "2.0.999", "2.1.294 (Claude Code)", "1.0.0"])
def test_cc_version_below(m, folder, cc):
    path, sha = plant(m, folder, cc)
    res = m.judge()
    assert new_keys(res) == [ck("cc_version_below", path, sha)]
    f = finding(res, ck("cc_version_below", path, sha))
    assert f.severity == VIOLATION and not f.owner_attested and "self-reported" in f.detail
    assert "2.1.295" in f.detail


@pytest.mark.parametrize("folder", ["analyst/attempts/", "analyst/canary/attempts/"])
@pytest.mark.parametrize("cc,sr", [
    (None, "keep"), (OMIT, "keep"), ("v2.1.309", "keep"), ("2.1.309-beta", "keep"), ("2.1", "keep"), ("", "keep"),
    (2.1, "keep"), ("x", OMIT), ("x", "self-reported"), ("x", None), ("x", ["2.1.309"]),
])
def test_cc_version_unknown_in_an_attempt_record(m, folder, cc, sr):
    path, sha = plant(m, folder, cc, sr=sr)
    res = m.judge()
    assert new_keys(res) == [ck("cc_version_unknown", path, sha)]
    f = finding(res, ck("cc_version_unknown", path, sha))
    assert f.severity == VIOLATION and not f.owner_attested and "self-reported" in f.detail


@pytest.mark.parametrize("folder", ["analyst/calls/", "analyst/canary/calls/"])
@pytest.mark.parametrize("cc,sr", [(None, "keep"), (OMIT, "keep"), ("v2.1.309", "keep"), ("", "keep"),
                                   ("x", OMIT), ("x", "self-reported")])
def test_a_call_file_gives_no_cc_version_unknown(m, folder, cc, sr):
    plant(m, folder, cc, sr=sr)
    assert new_keys(m.judge()) == []


@pytest.mark.parametrize("folder", FOLDERS)
@pytest.mark.parametrize("cc", ["2.1.295", "2.1.309 (Claude Code)", "2.2.0", "3.0.0"])
def test_cc_version_that_meets_the_minimum_gives_nothing(m, folder, cc):
    plant(m, folder, cc)
    assert new_keys(m.judge()) == []


def test_has_blob_reads_the_tree_entry_only(small_base):
    git = gitrepo.GitRepo(small_base.repo.path)
    head = small_base.repo.head()
    assert git.has_blob(head, sg.GUARD_PATH) and git.has_blob(head, sg.SETTINGS_PATH)
    assert not git.has_blob(head, ".claude/hooks")                                  # a tree, not a file
    assert not git.has_blob(head, ".claude/hooks/guard")
    assert not git.has_blob(head, ".claude/hooks/guard.py.bak")
    assert not git.has_blob("f" * 40, sg.GUARD_PATH)
    assert not git.has_blob(head, sg.GUARD_PATH + "\n")


def unguarded_commit(world):
    """A gold-analyst main commit whose tree lacks `.claude/hooks/guard.py` (a session before the guard), followed by
    one that puts the guard back, so main's head keeps it (no `guard_config`)."""
    os.remove(os.path.join(world.repo.path, sg.GUARD_PATH))
    u = world.repo.commit("guard removed (planted)", T("2026-12-02T18:00:00Z"))
    world.repo.write(sg.GUARD_PATH, GUARD_PY_BYTES)
    g = world.repo.commit("guard restored (planted)", T("2026-12-02T18:30:00Z"))
    return u, g


@pytest.mark.parametrize("folder", FOLDERS)
def test_a_record_of_an_unguarded_session_gives_nothing(m, folder):
    u, g = unguarded_commit(m)
    plant(m, folder, "2.0.0", head=u)
    plant(m, folder, None, head=u, name="2026-12-02_W2_1.json" if "attempts" in folder else "2026-12-02_W2.json",
          when="2026-12-02T20:10:00Z")
    assert new_keys(m.judge()) == []


def test_the_same_records_of_a_guarded_session_are_findings(m):
    u, g = unguarded_commit(m)
    p1, s1 = plant(m, "analyst/attempts/", "2.0.0", head=g)
    p2, s2 = plant(m, "analyst/attempts/", None, head=g.upper(), name="2026-12-02_W2_1.json",
                   when="2026-12-02T20:10:00Z")                                   # 40 hex digits in either case
    assert new_keys(m.judge()) == sorted([ck("cc_version_below", p1, s1), ck("cc_version_unknown", p2, s2)])


@pytest.mark.parametrize("head", ["f" * 40, "HEAD", "main", "", None, 7, OMIT, "-" * 40, "abbrev"])
def test_a_repo_head_sha_that_names_no_commit_gives_nothing(m, head):
    """A `repo_head_sha` that names no gold-analyst commit is A4's finding, not this one (J-D43: 40 hex digits)."""
    if head == "abbrev":
        head = m.repo.head()[:12]
    plant(m, "analyst/attempts/", "2.0.0", head=head)
    plant(m, "analyst/attempts/", None, head=head, name="2026-12-02_W2_1.json", when="2026-12-02T20:10:00Z")
    assert new_keys(m.judge()) == []


def test_only_the_four_folders_direct_json_records_are_judged(m):
    """J-D43: the records are `*.json` directly in the four folders; lesson records and probe records are not."""
    plant(m, "analyst/attempts/", "2.0.0", name="sub/2026-12-02_W1_1.json")
    plant(m, "analyst/attempts/", "2.0.0", name="2026-12-02_W1_1.txt", when="2026-12-02T20:01:00Z")
    plant(m, "analyst/lessons/", "2.0.0", name="2026-12-02_W1.json", when="2026-12-02T20:02:00Z")
    plant(m, "analyst/canary/lessons/", None, name="2026-12-02_W1.json", when="2026-12-02T20:03:00Z")
    assert new_keys(m.judge()) == []


def test_the_key_names_the_commit_that_added_the_record(m):
    path, sha = plant(m, "analyst/calls/", "2.1.0")
    m.repo.write("README.txt", b"later\n")
    m.repo.commit("unrelated", T("2026-12-02T21:00:00Z"))
    res = m.judge()
    assert new_keys(res) == [ck("cc_version_below", path, first_add(m, path))] and first_add(m, path) == sha


def test_the_report_labels_the_version_self_reported(m, tmp_path):
    path, sha = plant(m, "analyst/attempts/", "2.0.0")
    res = m.judge()
    out = str(tmp_path / "out")
    v = report.write_outputs(res, out, m.now, "x")
    assert ck("cc_version_below", path, sha) in v["violation_keys"]
    text = open(os.path.join(out, "REPORT.md"), encoding="utf-8").read()
    line = [ln for ln in text.split("\n") if ck("cc_version_below", path, sha) in ln][0]
    assert "self-reported" in line and "(owner-attested)" not in line
    assert "cc_version_below" in text.split("## VIOLATION keys")[0]                 # the intro names the source


# ================================================================ the probe record's cc_version (R-AN-84, R-AN-74 C20)
def probe_copy(world, change, tag="p20261202T100000Z", when="2026-12-02T20:30:00Z"):
    d = os.path.join(world.repo.path, "analyst/canary/checks")
    name = [p for p in os.listdir(d) if p.startswith("PROBE_")][0]
    rec = json.load(open(os.path.join(d, name), encoding="utf-8"))
    rec["tag"] = tag
    change(rec)
    path = f"analyst/canary/checks/PROBE_{tag}.json"
    world.repo.write(path, record_form(rec))
    return path, world.repo.commit("owner probe copy", T(when))


@pytest.mark.parametrize("cc", ["2.1.309 (Claude Code)", None, "2.0.0", "v2"])
def test_a_probe_record_with_cc_version_stays_readable(m, cc):
    """The judge does not judge the probe record's version (C20 does, R-AN-74); the record stays readable."""
    probe_copy(m, lambda r: r.update(cc_version=cc))
    res = m.judge()
    assert keys(res) == []
    assert res.summary["probe_records"] == 2


def test_probe_failed_is_unchanged_with_cc_version(m):
    def change(r):
        r["cc_version"] = "2.1.309 (Claude Code)"
        r["outcomes"]["rest.hooks"] = 2
    path, sha = probe_copy(m, change)
    assert keys(m.judge()) == [f"A12|probe_failed|{path}|{sha}"]


def test_canary_probes_with_cc_version_keep_probe_failed_and_probe_incomplete(tmp_path):
    def probe(world, win, rec):
        rec["cc_version"] = None if win.call_id.endswith("W2") else "2.1.309 (Claude Code)"
        if win.call_id == "2026-11-30_W1":
            rec["pass"]["rest.ga"] = False
            rec["outcomes"]["rest.ga"] = "ok"
            rec["verdict"] = "fail"
        if win.call_id == "2026-11-30_W2":
            rec["pass"]["rest.inbox"] = None
            rec["outcomes"]["rest.inbox"] = "none"
            rec["verdict"] = "incomplete"
    world = World(str(tmp_path / "s"), hooks={"probe": probe}, canary_days=("2026-11-30", "2026-12-01"),
                  live_from="2026-12-02", live_to="2026-12-02", now="2026-12-03T23:00:00Z").build()
    res = world.judge()
    pre = "analyst/canary/calls/"
    assert keys(res, check="A12") == sorted([
        f"A12|probe_failed|{pre}2026-11-30_W1.json|{first_add(world, pre + '2026-11-30_W1.json')}",
        f"A12|probe_incomplete|{pre}2026-11-30_W2.json|{first_add(world, pre + '2026-11-30_W2.json')}"])
    assert new_keys(res) == []
    sev = {f.key: f.severity for f in res.findings.items if f.check == "A12"}
    assert sorted(sev.values()) == [VIOLATION, WARNING]
