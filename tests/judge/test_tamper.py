"""The tamper suite (SYSTEM_V2_PREREG.md §4 "Judge"): in temporary git repositories built from the synthetic fixture,
rewrite a ledger row; alter a registry file; register after data; change a FROZEN file; corrupt a raw file;
force-push (rewritten history); shallow checkout. Each gives its specified verdict (§3.1, §3.2), and the latch and
the adjudication rules hold."""
import os
import shutil
import subprocess

import pandas as pd
import pytest

from judge import checks, publish, run as judge_run, verdict
from judge.common import iso_s, parse_utc, sha256_file, write_csv_append

NOW = parse_utc("2026-12-05T13:10:00Z")
GITENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
          "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args, date=None):
    env = dict(os.environ, **GITENV)
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    r = subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def commit(repo, paths, msg, date):
    git(repo, "add", "--", *paths)
    git(repo, "commit", "-q", "-m", msg, date=date)
    return git(repo, "rev-parse", "HEAD")


def manifest(repo, rel, files):
    lines = [f"{sha256_file(repo / f)}  {f}" for f in files]
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text("\n".join(lines) + "\n")


def build_repo(repo, W, v2_start_text=None, v2_start_date=None):
    """A repository whose history mimics the system's: the freeze, v1 registration, v2 registration, the runs.
    v2_start_text replaces reports/system/lab_v2/START.json in its first commit; v2_start_date commits that file on its
    own, at that date, after the v2 registration commit."""
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "gc.auto", "0")              # no background gc while the tests copy the repository
    git(repo, "config", "maintenance.auto", "false")
    shutil.copytree(W / "reports/system/lab/registry", repo / "reports/system/lab/registry")
    shutil.copytree(W / "reports/system/lab_v2/registry", repo / "reports/system/lab_v2/registry")
    ev1 = repo / "reports/system/lab/registry/events.csv"
    ev2 = repo / "reports/system/lab_v2/registry/events.csv"
    ev1.unlink()
    ev2.unlink()
    (repo / "analysis/system/lab_v2").mkdir(parents=True)
    (repo / "analysis/system/x.py").write_text("X = 1\n")
    (repo / "analysis/system/lab_v2/y.py").write_text("Y = 2\n")
    reg1 = [f"reports/system/lab/registry/{i}.json" for i in ("S1", "S1R", "C1")]
    reg2 = [f"reports/system/lab_v2/registry/{i}.json" for i in ("S2", "S3", "S4", "S5")]
    manifest(repo, "analysis/system/FROZEN.sha256", ["analysis/system/x.py"] + reg1)
    manifest(repo, "analysis/system/lab_v2/FROZEN_V2.sha256", ["analysis/system/lab_v2/y.py"] + reg2)
    c0 = commit(repo, ["analysis", "reports"], "freeze", "2026-10-26T12:00:00Z")
    git(repo, "tag", "lab-v1-freeze", c0)
    git(repo, "tag", "lab-v2-freeze", c0)
    shutil.copy(W / "reports/system/START.json", repo / "reports/system/START.json")
    shutil.copy(W / "reports/system/lab/registry/events.csv", ev1)
    c1 = commit(repo, ["reports"], "system run 2026-10-27T03:25Z", "2026-10-27T03:25:00Z")
    v2s = repo / "reports/system/lab_v2/START.json"
    shutil.copy(W / "reports/system/lab_v2/registry/events.csv", ev2)
    if v2_start_date is None:
        shutil.copy(W / "reports/system/lab_v2/START.json", v2s)
        if v2_start_text is not None:
            v2s.write_text(v2_start_text)
    c2 = commit(repo, ["reports"], "lab v2 run 2026-11-03T03:25Z", "2026-11-03T03:25:00Z")
    if v2_start_date is not None:
        shutil.copy(W / "reports/system/lab_v2/START.json", v2s)
        commit(repo, ["reports"], "lab v2 START", v2_start_date)
    shutil.copytree(W / "data", repo / "data")
    shutil.copytree(W / "reports", repo / "reports", dirs_exist_ok=True)
    if v2_start_text is not None:
        v2s.write_text(v2_start_text)
    c3 = commit(repo, ["data", "reports"], "system run 2026-12-05T03:25Z", "2026-12-05T03:25:00Z")
    git(repo, "repack", "-a", "-d", "-q")
    return {"repo": repo, "c0": c0, "c1": c1, "c2": c2, "c3": c3,
            "pins": {"lab-v1-freeze": c0, "lab-v2-freeze": c0, "judge-v1-freeze": None}}


@pytest.fixture(scope="session")
def base_repo(tmp_path_factory, fixture_world):
    return build_repo(tmp_path_factory.mktemp("tamper") / "base", fixture_world)


@pytest.fixture()
def repo(tmp_path, base_repo):
    dst = tmp_path / "r"
    shutil.copytree(base_repo["repo"], dst, symlinks=True)
    return dst


def judge_history(repo, pins, now=NOW, record=True):
    """J2, J3, J4, J7, J8 and the verdict, as run.main computes them (J1, J5, J6, J9 are covered elsewhere)."""
    hist_ok, probs, tagv = checks.history_state(repo, pins)
    cs = [checks.j2(repo, repo, hist_ok), checks.j3(repo, repo, pins, hist_ok, repo),
          checks.j4(repo, repo, pins, hist_ok, tagv, repo), checks.j7(repo, repo, now), checks.j8(repo, repo, hist_ok)]
    v, code, ok, since, lines = verdict.decide(cs, repo, now)
    if record:
        head = git(repo, "rev-parse", "HEAD")
        verdict.record(repo, now, head, v, code, ok, 9, since, "x" * 64, cs)
        publish.write_all(repo, now, head, v, code, ok, 9, cs + [checks.Check(i) for i in ("J1", "J5", "J6", "J9")],
                          lines, "x" * 64)
    return v, code, {c.id: c for c in cs}


def test_untampered_history_is_sound(repo, base_repo):
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "SOUND" and code == "sound", {k: (c.status, c.evidence) for k, c in cs.items()}


def test_ledger_row_rewrite_is_a_violation(repo, base_repo):
    p = repo / "reports/system/lab/trades.csv"
    lines = p.read_text().splitlines()
    lines[2] = lines[2].replace(",time,", ",stop,", 1)
    p.write_text("\n".join(lines) + "\n")
    v, code, cs = judge_history(repo, base_repo["pins"], record=False)      # uncommitted: the working tree
    assert v == "VIOLATION" and code == "j3_ledger" and cs["J3"].status == "violation"
    commit(repo, ["reports"], "system run 2026-12-06T03:25Z", "2026-12-06T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and code == "j3_ledger"
    assert any("trades.csv: row 3 rewritten" in e for e in cs["J3"].evidence)


def test_appending_rows_is_not_a_violation(repo, base_repo):
    p = repo / "reports/system/lab/lab_days.csv"
    p.write_text(p.read_text() + "2026-12-07,2026-12-08T03:20:00Z\n")
    commit(repo, ["reports"], "system run 2026-12-08T03:25Z", "2026-12-08T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"], now=parse_utc("2026-12-08T13:10:00Z"))
    assert cs["J3"].status == "ok"


def test_registry_edit_is_a_violation(repo, base_repo):
    p = repo / "reports/system/lab/registry/S1.json"
    p.write_text(p.read_text().replace('"days": 15', '"days": 31'))
    commit(repo, ["reports"], "edit", "2026-12-06T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION"
    assert cs["J2"].status == "violation" and "j2_registry" in cs["J2"].reasons
    assert cs["J4"].status == "violation" and "j4_frozen" in cs["J4"].reasons


def test_register_after_data_is_a_violation(repo, base_repo):
    p1 = repo / "reports/system/lab/registry/P001.json"
    p1.write_text((repo / "reports/system/lab/registry/S1.json").read_text().replace('"id": "S1"', '"id": "P001"'))
    ev = repo / "reports/system/lab/registry/events.csv"
    ev.write_text(ev.read_text() + "2026-11-01T03:20:00Z,P001,REGISTERED,found at HEAD,0,1.0,1.0,0,77,abc\n")
    commit(repo, ["reports"], "late registration", "2026-12-06T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and code == "j2_register", cs["J2"].evidence


def test_ledger_rows_before_first_day_are_a_violation(repo, base_repo):
    p = repo / "reports/system/lab/decisions.csv"
    p.write_text(p.read_text() + "S1,2026-10-30,no_trigger,0,4.0,0.1,,10.0,10.0,2026-12-06T03:20:00Z\n")
    commit(repo, ["reports"], "system run", "2026-12-06T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and "j2_firstday" in cs["J2"].reasons


def test_start_change_is_a_violation(repo, base_repo):
    p = repo / "reports/system/lab_v2/START.json"
    p.write_text(p.read_text().replace("2026-11-09", "2026-11-16"))
    commit(repo, ["reports"], "start", "2026-12-06T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and "j2_start" in cs["J2"].reasons


@pytest.mark.parametrize("how", ["edit", "drop_entry", "tag_moved"])
def test_frozen_change_is_a_violation(repo, base_repo, how):
    if how == "edit":
        (repo / "analysis/system/x.py").write_text("X = 2\n")
        commit(repo, ["analysis"], "edit frozen", "2026-12-06T03:25:00Z")
        want = "j4_frozen"
    elif how == "drop_entry":
        m = repo / "analysis/system/FROZEN.sha256"
        m.write_text("\n".join(m.read_text().splitlines()[1:]) + "\n")
        commit(repo, ["analysis"], "drop", "2026-12-06T03:25:00Z")
        want = "j4_frozen"
    else:
        git(repo, "tag", "-f", "lab-v1-freeze", base_repo["c1"])
        want = "j4_tag"
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and want in cs["J4"].reasons, cs["J4"].evidence


@pytest.mark.parametrize("how", ["corrupt", "delete"])
def test_raw_corruption_is_a_violation(repo, base_repo, how):
    p = repo / "data/system/raw/2026/11/03/BID.bi5"
    if how == "corrupt":
        b = bytearray(p.read_bytes())
        b[-5] ^= 0xFF
        p.write_bytes(bytes(b))
    else:
        p.unlink()
    git(repo, "add", "-A", "data")
    git(repo, "commit", "-q", "-m", "raw", date="2026-12-06T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and code == "j3_raw"
    assert any("2026/11/03/BID.bi5" in e for e in cs["J3"].evidence)


def _rewrite_c3(repo, base_repo):
    """Replace c3 by another commit with the same tree position (a force-push of rewritten history)."""
    git(repo, "reset", "-q", "--hard", base_repo["c2"])
    shutil.copytree(base_repo["repo"] / "data", repo / "data")
    shutil.copytree(base_repo["repo"] / "reports", repo / "reports", dirs_exist_ok=True)
    p = repo / "reports/system/lab/trades.csv"
    lines = p.read_text().splitlines()
    lines[2] = lines[2].replace(",time,", ",stop,", 1)            # the edit the rewrite was made for
    p.write_text("\n".join(lines) + "\n")
    git(repo, "add", "-A", "data", "reports")
    git(repo, "commit", "-q", "-m", "system run 2026-12-05T03:25Z", date="2026-12-05T03:26:00Z")


def test_force_push_rewritten_history_is_a_violation(repo, base_repo):
    v, code, _ = judge_history(repo, base_repo["pins"])           # the judge checked c3 and recorded it
    assert v == "SOUND"
    git(repo, "add", "-A", "reports/judge", "reports/forward_site/judge")
    git(repo, "commit", "-q", "-m", "judge run", date="2026-12-05T13:12:00Z")
    jc = git(repo, "rev-parse", "HEAD")
    _rewrite_c3(repo, base_repo)
    git(repo, "cherry-pick", jc, date="2026-12-05T13:30:00Z")     # the judge's records carried over
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and code == "j8_rewritten", cs["J8"].evidence
    assert sum("not an ancestor" in e for e in cs["J8"].evidence) == 2   # VERDICTS.csv and VolMapJudge.csv
    c3 = base_repo["c3"][:12]
    assert sorted(k for k, _, _ in cs["J8"].findings) == [
        f"J8|j8_rewritten|reports/forward_site/judge/VolMapJudge.csv|{c3}",
        f"J8|j8_rewritten|reports/judge/VERDICTS.csv|{c3}"]


def test_force_push_that_drops_the_judge_records_is_caught_by_the_deployed_file(repo, base_repo, tmp_path,
                                                                               monkeypatch):
    judge_history(repo, base_repo["pins"])
    site = tmp_path / "site"
    (site / "judge").mkdir(parents=True)
    shutil.copy(repo / "reports/forward_site/judge/VolMapJudge.csv", site / "judge/VolMapJudge.csv")
    shutil.rmtree(repo / "reports/judge")
    shutil.rmtree(repo / "reports/forward_site/judge")
    _rewrite_c3(repo, base_repo)
    monkeypatch.setenv("JUDGE_SITE_URL", f"file://{site}")
    v, code, cs = judge_history(repo, base_repo["pins"], record=False)
    assert v == "VIOLATION" and code == "j8_rewritten", cs["J8"].evidence
    assert [k for k, _, _ in cs["J8"].findings] == [f"J8|j8_rewritten|/judge/VolMapJudge.csv|{base_repo['c3'][:12]}"]


def test_the_deployed_file_unreachable_or_without_head_is_unverified(repo, base_repo, tmp_path, monkeypatch):
    judge_history(repo, base_repo["pins"])
    monkeypatch.setenv("JUDGE_SITE_URL", f"file://{tmp_path / 'nothing-here'}")
    _, _, cs = judge_history(repo, base_repo["pins"], record=False)
    assert cs["J8"].status == "ok" and any("could not be fetched" in u for u in cs["J8"].unverified)
    site = tmp_path / "site"
    (site / "judge").mkdir(parents=True)
    (site / "judge/VolMapJudge.csv").write_text("<html>not the file</html>\n")
    monkeypatch.setenv("JUDGE_SITE_URL", f"file://{site}")
    _, _, cs = judge_history(repo, base_repo["pins"], record=False)
    assert cs["J8"].status == "ok" and any("no valid head_sha" in u for u in cs["J8"].unverified)


def test_shallow_checkout_is_a_warning_never_sound(tmp_path, base_repo):
    sh = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{base_repo['repo']}", str(sh)], check=True,
                   env=dict(os.environ, **GITENV), capture_output=True)
    v, code, cs = judge_history(sh, base_repo["pins"])
    assert v == "WARNING" and code == "unverified"
    assert all(cs[i].status == "warning" for i in ("J2", "J3", "J4"))
    raw = (sh / "reports/forward_site/judge/VolMapJudge.csv").read_text()
    assert "reason_ar,تعذر التحقق\n" in raw and "verdict,WARNING" in raw


def test_missing_pinned_commit_is_a_warning(repo, base_repo):
    pins = dict(base_repo["pins"], **{"lab-v2-freeze": "1" * 40})
    v, code, cs = judge_history(repo, pins, record=False)
    assert v == "VIOLATION" and "j4_tag" in cs["J4"].reasons        # the tag resolves to another commit
    git(repo, "tag", "-d", "lab-v2-freeze")                          # no tag, and the pinned commit is missing
    v, code, cs = judge_history(repo, pins)
    assert v == "WARNING" and code == "unverified"


def test_shallow_checkout_end_to_end_publishes_the_unverified_reason(tmp_path, base_repo, monkeypatch):
    sh = tmp_path / "shallow2"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{base_repo['repo']}", str(sh)], check=True,
                   env=dict(os.environ, **GITENV), capture_output=True)
    monkeypatch.setattr(checks, "load_pins", lambda: dict(base_repo["pins"]))
    assert judge_run.main(["--repo", str(sh), "--now", iso_s(NOW), "--no-network", "--j1-sample", "0",
                           "--j1-max-days", "1"]) == 0
    raw = (sh / "reports/forward_site/judge/VolMapJudge.csv").read_bytes().decode("utf-8")
    assert "verdict,WARNING" in raw and "reason_ar,تعذر التحقق" in raw
    assert (sh / "reports/judge/REPORT.md").read_text().startswith('<div dir="rtl" lang="ar">')


def test_judge_records_rewrite_is_a_violation(repo, base_repo):
    judge_history(repo, base_repo["pins"])
    git(repo, "add", "-A", "reports/judge", "reports/forward_site/judge")
    git(repo, "commit", "-q", "-m", "judge run", date="2026-12-05T13:12:00Z")
    p = repo / "reports/judge/VERDICTS.csv"
    lines = p.read_text().splitlines()
    lines[1] = lines[1].replace("SOUND", "WARNING")
    p.write_text("\n".join(lines) + "\n")
    git(repo, "add", "-A", "reports/judge")
    git(repo, "commit", "-q", "-m", "edit verdicts", date="2026-12-05T13:20:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and "j3_judge" in cs["J3"].reasons


# ---------------------------------------------------------------- latch, finding keys and clearing (B2 item 6)
def clear_row(repo, t, key, ref="latch", check=None):
    write_csv_append(repo / verdict.ADJ, verdict.ADJ_HEAD,
                     [[iso_s(t), ref, check or key.split("|")[0], key, "clear", "adjudicated"]])


def _rewrite_trade_row(repo, i, date):
    p = repo / "reports/system/lab/trades.csv"
    lines = p.read_text().splitlines()
    lines[i] = lines[i].replace(",time,", ",stop,", 1) if ",time," in lines[i] else lines[i].replace(",stop,", ",time,",
                                                                                                     1)
    p.write_text("\n".join(lines) + "\n")
    return commit(repo, ["reports"], f"system run {date}", date)


def test_a_committed_violation_is_cleared_only_by_rows_naming_its_keys(repo, base_repo):
    """B2 item 6, R-JV-1 .. R-JV-4 (review MF3): a committed ledger rewrite is found again by every run; only dated
    ADJUDICATIONS.csv rows naming its keys clear it; the clearing is listed in REPORT.md; a new rewrite on a new commit
    is a new finding."""
    sha = _rewrite_trade_row(repo, 2, "2026-12-06T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    keys = [k for k, _, _ in cs["J3"].findings]
    assert v == "VIOLATION" and code == "j3_ledger"
    assert keys == [f"J3|j3_ledger|reports/system/lab/trades.csv|{sha[:12]}"], keys
    assert any(f"[finding {keys[0]}]" in e for e in cs["J3"].evidence)
    assert keys[0] in (repo / "reports/judge/REPORT.md").read_text()
    assert [r["key"] for r in verdict.finding_log(repo).values()] == keys
    # a generic `clear,latch` row (no key) clears nothing
    t2 = NOW + pd.Timedelta(hours=1)
    clear_row(repo, t2, "trades.csv", check="J3")
    v, code, cs = judge_history(repo, base_repo["pins"], now=t2 + pd.Timedelta(hours=1))
    assert v == "VIOLATION" and code == "j3_ledger"
    # a row naming the key but dated before the key was first found clears nothing either
    clear_row(repo, NOW - pd.Timedelta(minutes=1), keys[0])
    v, code, cs = judge_history(repo, base_repo["pins"], now=t2 + pd.Timedelta(hours=2))
    assert v == "VIOLATION"
    # the row naming the key clears it: SOUND although the rewrite is still found
    clear_row(repo, t2 + pd.Timedelta(hours=3), keys[0])
    v, code, cs = judge_history(repo, base_repo["pins"], now=t2 + pd.Timedelta(hours=4))
    assert (v, code) == ("SOUND", "sound") and cs["J3"].status == "ok"
    assert [k for k, _, _ in cs["J3"].findings] == keys
    rep = (repo / "reports/judge/REPORT.md").read_text()
    assert f"cleared finding key {keys[0]}" in rep and "still found by this run" in rep
    v, code, _ = judge_history(repo, base_repo["pins"], now=t2 + pd.Timedelta(days=30))
    assert v != "VIOLATION" and code == "j7_stale"            # a month later only the status file's age warns
    assert f"cleared finding key {keys[0]}" in (repo / "reports/judge/REPORT.md").read_text()   # R-JV-3
    # the same kind of rewrite on a NEW commit: a new key, VIOLATION again until it is cleared in turn
    sha2 = _rewrite_trade_row(repo, 3, "2027-01-06T03:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"], now=t2 + pd.Timedelta(days=32))
    new = f"J3|j3_ledger|reports/system/lab/trades.csv|{sha2[:12]}"
    assert v == "VIOLATION" and sorted(k for k, _, _ in cs["J3"].findings) == sorted(keys + [new])
    clear_row(repo, t2 + pd.Timedelta(days=33), new)
    v, code, _ = judge_history(repo, base_repo["pins"], now=t2 + pd.Timedelta(days=34))
    assert v != "VIOLATION" and code == "j7_stale"


def test_a_finding_that_disappears_stays_latched_until_its_key_is_cleared(repo, base_repo):
    p = repo / "reports/system/lab/eproc.csv"
    orig = p.read_text()
    lines = orig.splitlines()
    lines[1] = lines[1].replace(",REF", ",PAPER")
    p.write_text("\n".join(lines) + "\n")                        # tampered (working tree)
    v, code, cs = judge_history(repo, base_repo["pins"])
    key = "J3|j3_ledger|reports/system/lab/eproc.csv|worktree"
    assert v == "VIOLATION" and code == "j3_ledger" and [k for k, _, _ in cs["J3"].findings] == [key]
    p.write_text(orig)                                           # the tamper is undone
    t2 = NOW + pd.Timedelta(hours=1)
    v, code, cs = judge_history(repo, base_repo["pins"], now=t2)
    assert v == "VIOLATION" and code == "j3_ledger" and cs["J3"].status == "ok"      # latched by its key
    assert f"open finding key {key}" in (repo / "reports/judge/REPORT.md").read_text()
    prev = verdict.read_dicts(repo / verdict.VERDICTS)
    assert prev[-1]["latched_since"] == prev[-2]["latched_since"] == iso_s(NOW)
    clear_row(repo, t2 + pd.Timedelta(minutes=5), key)
    v, code, _ = judge_history(repo, base_repo["pins"], now=t2 + pd.Timedelta(hours=1))
    assert v == "SOUND"


def test_a_cleared_finding_of_one_check_does_not_clear_another(repo, base_repo):
    sha = _rewrite_trade_row(repo, 2, "2026-12-06T03:25:00Z")
    (repo / "analysis/system/x.py").write_text("X = 3\n")
    c4 = commit(repo, ["analysis"], "edit frozen", "2026-12-06T04:25:00Z")
    v, code, cs = judge_history(repo, base_repo["pins"])
    assert v == "VIOLATION" and code == "j4_frozen"
    assert [k for k, _, _ in cs["J4"].findings] == [f"J4|j4_frozen|analysis/system/x.py|{c4[:12]}"]
    clear_row(repo, NOW + pd.Timedelta(hours=1), f"J3|j3_ledger|reports/system/lab/trades.csv|{sha[:12]}")
    v, code, cs = judge_history(repo, base_repo["pins"], now=NOW + pd.Timedelta(hours=2))
    assert (v, code) == ("VIOLATION", "j4_frozen") and cs["J3"].status == "ok"
    # a row with the right key but another check clears nothing
    clear_row(repo, NOW + pd.Timedelta(hours=3), f"J4|j4_frozen|analysis/system/x.py|{c4[:12]}", check="J3")
    v, code, _ = judge_history(repo, base_repo["pins"], now=NOW + pd.Timedelta(hours=4))
    assert v == "VIOLATION"


def test_finding_key_of_a_moved_tag(repo, base_repo):
    git(repo, "tag", "-f", "lab-v1-freeze", base_repo["c1"])
    _, _, cs = judge_history(repo, base_repo["pins"], record=False)
    assert f"J4|j4_tag|refs/tags/lab-v1-freeze|{base_repo['c1'][:12]}" in [k for k, _, _ in cs["J4"].findings]


# ---------------------------------------------------------------- START.json follows its rule (review MF5)
def _start_text(fixture_world, **kw):
    import json
    j = json.loads((fixture_world / "reports/system/lab_v2/START.json").read_text())
    j.update(kw)
    return json.dumps(j, indent=1, ensure_ascii=False) + "\n"


def test_a_start_first_committed_one_week_later_is_a_violation(tmp_path, fixture_world):
    b = build_repo(tmp_path / "late_start", fixture_world, v2_start_text=_start_text(fixture_world, start="2026-11-16"))
    v, code, cs = judge_history(b["repo"], b["pins"], record=False)
    assert v == "VIOLATION" and "j2_start" in cs["J2"].reasons, cs["J2"].evidence
    assert any("start 2026-11-16 != 2026-11-09, the rule's value" in e for e in cs["J2"].evidence)
    assert f"J2|j2_start|reports/system/lab_v2/START.json|{b['c2'][:12]}" in [k for k, _, _ in cs["J2"].findings]


def test_a_start_first_committed_two_days_after_its_first_run_is_a_violation(tmp_path, fixture_world):
    b = build_repo(tmp_path / "late_commit", fixture_world, v2_start_date="2026-11-05T03:25:00Z")
    v, code, cs = judge_history(b["repo"], b["pins"], record=False)
    assert v == "VIOLATION" and code == "j2_start", cs["J2"].evidence
    assert set(cs["J2"].reasons) == {"j2_start"}
    assert any("more than 60 min after its first_cloud_run_utc 2026-11-03T03:20:00Z" in e for e in cs["J2"].evidence)


def test_the_real_start_files_follow_the_rule(root):
    """The real v1 START (run 2026-10-17T18:55:29Z, committed in c629430 at 18:55:48) gives 2026-11-02."""
    import json
    sj = json.loads((root / "reports/system/START.json").read_text())
    assert checks.start_problems(sj, 1, None) == [] and sj["start"] == "2026-11-02"


def test_j5_mismatch_is_a_warning_and_only_a_system_error_row_makes_a_violation(tmp_path):
    from judge.recompute import Finding
    f = Finding("v1", "v1 trades S1 2026-11-03", "P_x '1' != 2.0")
    open_f, rows = verdict.j5_adjudicate([f], tmp_path, NOW)
    assert len(rows) == 1 and rows[0][4] == "pending" and verdict.undecided(tmp_path)
    c5 = checks.Check("J5", status="warning", reasons=["j5_mismatch"])
    v, code, *_ = verdict.decide([c5], tmp_path, NOW)
    assert (v, code) == ("WARNING", "j5_mismatch")
    # the same mismatch again adds no row
    assert verdict.j5_adjudicate([f], tmp_path, NOW + pd.Timedelta(days=1))[1] == []
    ref = rows[0][1]
    write_csv_append(tmp_path / verdict.ADJ, verdict.ADJ_HEAD,
                     [[iso_s(NOW + pd.Timedelta(days=2)), ref, "J5", f.key(), "system_error", "confirmed"]])
    v, code, *_ = verdict.decide([checks.Check("J5")], tmp_path, NOW + pd.Timedelta(days=2))
    assert (v, code) == ("VIOLATION", "adj_system_error")
    write_csv_append(tmp_path / verdict.ADJ, verdict.ADJ_HEAD,
                     [[iso_s(NOW + pd.Timedelta(days=3)), ref, "J5", f.key(), "clear", "fixed"]])
    v, code, *_ = verdict.decide([checks.Check("J5")], tmp_path, NOW + pd.Timedelta(days=3))
    assert (v, code) == ("SOUND", "sound")
    g = Finding("v2", "v2 trades S2 2026-11-09", "R differs")
    _, rows = verdict.j5_adjudicate([g], tmp_path, NOW)
    write_csv_append(tmp_path / verdict.ADJ, verdict.ADJ_HEAD,
                     [[iso_s(NOW + pd.Timedelta(days=1)), rows[0][1], "J5", g.key(), "spec_gap", "R-V2-17 gap"]])
    assert not verdict.undecided(tmp_path) and verdict.j5_adjudicate([g], tmp_path, NOW)[0] == []
