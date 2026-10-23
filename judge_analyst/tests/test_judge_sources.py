"""The judge's public reads of register §16.18 A6 (R-AN-66, R-AN-70), against local doubles only (no network):

- `git ls-remote` of a repository, with peeled tags, and no credential;
- the GitHub reads are complete or they fail: every page 200 with the expected JSON and no further page; the token
  first, and once without it when GitHub refuses the token (401, 403, 404), since the repositories are public;
  the inbox's activity is read for the last month only (second review of A6, SEC-3);
- `--fetch-pushes` / `--inbox`: a pushed commit is fetched by sha (else by its ref) from the inbox into the
  gold-analyst clone as data, without credentials, and a stuck fetch is bounded;
- the runs day range starts two days before the newest verdict.
"""
import io
import json
import os
import subprocess
import urllib.error

import pytest

import run_judge
from jlib import report, sources
from jlib.sources import ApiError, GitHubAPI, git_ls_remote

GITENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
          "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *a):
    p = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, env=dict(os.environ, **GITENV))
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


@pytest.fixture()
def repos(tmp_path):
    """A gold-analyst stand-in (main) and an inbox stand-in holding one agent commit on a claude/ branch."""
    ga = tmp_path / "ga"
    ga.mkdir()
    git(ga, "init", "-q", "-b", "main")
    (ga / "a.txt").write_text("a\n")
    git(ga, "add", ".")
    git(ga, "commit", "-q", "-m", "main")
    git(ga, "tag", "-a", "-m", "freeze", "analyst-v1-freeze")
    git(ga, "tag", "light")
    inbox = tmp_path / "inbox"
    subprocess.run(["git", "clone", "-q", "--bare", str(ga), str(inbox)], check=True, env=dict(os.environ, **GITENV))
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(inbox), str(work)], check=True, env=dict(os.environ, **GITENV))
    git(work, "switch", "-q", "-c", "claude/analyst-live-call-x")
    (work / "analyst").mkdir()
    (work / "analyst/x.json").write_text("{}\n")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "session push")
    git(work, "push", "-q", "origin", "claude/analyst-live-call-x")
    return ga, inbox, git(work, "rev-parse", "HEAD")


# ---------------------------------------------------------------- git ls-remote
def test_ls_remote_lists_refs_with_peeled_tags(repos):
    ga, _, _ = repos
    got = git_ls_remote(str(ga))
    refs = dict((ref, sha) for sha, ref in got)
    head = git(ga, "rev-parse", "HEAD")
    assert refs["HEAD"] == head and refs["refs/heads/main"] == head
    assert refs["refs/tags/analyst-v1-freeze"] == git(ga, "rev-parse", "refs/tags/analyst-v1-freeze") != head
    assert refs["refs/tags/analyst-v1-freeze^{}"] == head and refs["refs/tags/light"] == head


def test_ls_remote_failure_raises(tmp_path):
    with pytest.raises(ApiError):
        git_ls_remote(str(tmp_path / "missing"))


# ---------------------------------------------------------------- GitHub reads: complete or failed
class _Resp:
    def __init__(self, status, body, link=""):
        self.status, self._body, self.headers = status, body, {"Link": link}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(script, seen):
    """script: url -> list of (status, json_obj, link), consumed per request (the last entry repeats)."""
    def urlopen(req, timeout=None):
        auth = req.get_header("Authorization")
        seen.append((req.full_url, bool(auth)))
        key = (req.full_url, bool(auth)) if (req.full_url, bool(auth)) in script else req.full_url
        q = script[key]
        status, obj, link = q.pop(0) if len(q) > 1 else q[0]
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "x", {}, io.BytesIO(b"{}"))
        return _Resp(status, obj if isinstance(obj, bytes) else json.dumps(obj).encode(), link)
    return urlopen


B = "https://api.github.com"
INBOX = "Mohamedalhaaj/gold-analyst-inbox"


def api(monkeypatch, script, token="t0ken"):
    seen = []
    monkeypatch.setattr(sources.urllib.request, "urlopen", fake_urlopen(script, seen))
    return GitHubAPI("Mohamedalhaaj/gold-analyst", token, pause=0), seen


def test_activity_pages_with_the_token_then_anonymously_when_refused(monkeypatch):
    u1 = f"{B}/repos/{INBOX}/activity?per_page=100&time_period=month"
    u2 = f"{B}/repositories/1/activity?per_page=100&after=x"
    a, seen = api(monkeypatch, {(u1, True): [(403, None, "")],
                                (u1, False): [(200, [{"id": 1}], f'<{u2}>; rel="next", <{u1}>; rel="first"')],
                                u2: [(200, [{"id": 2}], f'<{u1}>; rel="first"')]})
    assert [x["id"] for x in a.repo_activity(INBOX)] == [1, 2]
    assert seen == [(u1, True), (u1, False), (u2, False)]          # the anonymous read restarts once, then holds


def test_the_inbox_activity_is_read_for_the_last_month(monkeypatch):
    """R-AN-66 (second review of A6, SEC-3): the read is bounded to `time_period=month`, as the merge reads it, so a
    flood of branches cannot make it grow without bound; older entries are the judge's evidence rows."""
    u1 = f"{B}/repos/{INBOX}/activity?per_page=100&time_period=month"
    a, seen = api(monkeypatch, {u1: [(200, [{"id": 1}], "")]})
    assert a.repo_activity(INBOX) == [{"id": 1}]
    assert seen == [(u1, True)]


@pytest.mark.parametrize("second", [(500, None, ""), (200, {"not": "a list"}, ""), (404, None, "")])
def test_an_incomplete_activity_read_fails(monkeypatch, second):
    u1 = f"{B}/repos/{INBOX}/activity?per_page=100&time_period=month"
    u2 = f"{B}/repositories/1/activity?page=2"
    a, _ = api(monkeypatch, {u1: [(200, [{"id": 1}], f'<{u2}>; rel="next"')], u2: [second]})
    with pytest.raises(ApiError):
        a.repo_activity(INBOX)


def test_a_transient_error_is_retried(monkeypatch):
    u1 = f"{B}/repos/{INBOX}/actions/runs?per_page=1"
    a, seen = api(monkeypatch, {u1: [(502, None, ""), (200, {"total_count": 0, "workflow_runs": []}, "")]})
    assert a.runs_total(INBOX) == 0 and len(seen) == 2


def test_repo_info_404_and_rules_and_runs_by_day(monkeypatch):
    ur = f"{B}/repos/{INBOX}"
    ub = f"{B}/repos/{INBOX}/rules/branches/claude/x"
    ud = f"{B}/repos/Mohamedalhaaj/gold-analyst/actions/runs?created=2026-10-23&per_page=100"
    ud2 = f"{B}/repositories/9/actions/runs?created=2026-10-23&per_page=100&page=2"
    a, seen = api(monkeypatch, {ur: [(404, None, "")], ub: [(200, [{"type": "deletion"}], "")],
                                ud: [(200, {"total_count": 2, "workflow_runs": [{"id": 1}]}, f'<{ud2}>; rel="next"')],
                                ud2: [(200, {"total_count": 2, "workflow_runs": [{"id": 2}]}, "")]})
    assert a.repo_info(INBOX) is None
    assert seen[:2] == [(ur, True), (ur, False)]                 # a 404 with the token is asked once more without it
    assert a.branch_rules(INBOX, "claude/x") == [{"type": "deletion"}]
    assert [r["id"] for r in a.runs_on_day("Mohamedalhaaj/gold-analyst", "2026-10-23")] == [1, 2]


def test_no_token_reads_anonymously_once(monkeypatch):
    ur = f"{B}/repos/{INBOX}"
    a, seen = api(monkeypatch, {ur: [(200, {"id": 5, "private": False}, "")]}, token=None)
    assert a.repo_info(INBOX) == {"id": 5, "private": False} and seen == [(ur, False)]


# ---------------------------------------------------------------- --fetch-pushes from the inbox (R-AN-70)
def test_fetch_by_sha_from_the_inbox_into_the_clone(repos):
    ga, inbox, sha = repos
    assert subprocess.run(["git", "-C", str(ga), "cat-file", "-e", sha]).returncode != 0
    fetch = run_judge.make_fetch(str(ga), str(inbox))
    assert fetch(sha, "refs/heads/claude/analyst-live-call-x") is True
    assert subprocess.run(["git", "-C", str(ga), "cat-file", "-e", sha + "^{commit}"]).returncode == 0
    assert git(ga, "status", "--porcelain") == "" and git(ga, "for-each-ref", "refs/heads") .count("\n") == 0


def test_fetch_falls_back_to_the_ref_and_bounds_failures(repos, monkeypatch):
    ga, inbox, sha = repos
    calls = []
    real = subprocess.run

    def run(args, **kw):
        if "fetch" in args:
            calls.append(args[-1])
            if args[-1] == sha:                                  # a server that refuses a fetch by sha
                return subprocess.CompletedProcess(args, 1, b"", b"")
        return real(args, **kw)
    monkeypatch.setattr(run_judge.subprocess, "run", run)
    fetch = run_judge.make_fetch(str(ga), str(inbox), max_failures=2)
    assert fetch(sha, "refs/heads/claude/analyst-live-call-x") is True
    assert calls == [sha, "refs/heads/claude/analyst-live-call-x"]
    calls.clear()
    assert fetch("e" * 40, "refs/heads/claude/none") is False
    assert fetch("f" * 40, "refs/heads/claude/none") is False
    assert fetch("a" * 40, "refs/heads/claude/analyst-live-call-x") is False   # bounded: no further fetch
    assert len(calls) == 4


def test_fetch_and_fresh_main_run_without_credentials(repos, monkeypatch):
    ga, inbox, sha = repos
    head = git(ga, "rev-parse", "HEAD")
    seen = []
    real = subprocess.run

    def run(args, **kw):
        seen.append((args, kw.get("env", {}), kw.get("timeout")))
        return real(args, **kw)
    monkeypatch.setattr(run_judge.subprocess, "run", run)
    assert run_judge.make_fetch(str(ga), str(inbox))(sha, None) is True
    assert run_judge.make_fresh_main(str(ga), str(inbox))() == head
    monkeypatch.undo()
    assert len(seen) == 3
    for args, env, timeout in seen:
        assert "credential.helper=" in args and "http.https://github.com/.extraheader=" in args
        assert env.get("GIT_TERMINAL_PROMPT") == "0" and timeout is not None


def test_the_runs_day_range_starts_two_days_before_the_newest_verdict(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    assert report.last_judge_utc(str(out)) is None
    report.append_csv(str(out / "VERDICTS.csv"), report.VERDICTS_HEADER,
                      [{"judge_utc": "2026-10-24T23:40:00Z", "head_sha": "a"}, {"judge_utc": "2026-10-23T08:41:00Z",
                                                                                 "head_sha": "b"}])
    assert report.last_judge_utc(str(out)) == "2026-10-24T23:40:00Z"


def test_inbox_argument():
    a = run_judge.resolve(run_judge.parse_args(["--repo", "../ga", "--inbox", "../inbox", "--fetch-pushes"]))
    assert a.inbox == os.path.abspath("../inbox") and a.fetch_pushes
    assert run_judge.resolve(run_judge.parse_args(["--repo", "x"])).inbox is None
