""".github/workflows/judge.yml (SYSTEM_V2_PREREG.md §3.1): triggers, the shared concurrency group, a full-history
checkout with tags, the key on the judge step only, the commit path guard (never `git add -A`) and the deploy from
the post-commit checkout. The commit step's script is run for real against a local bare remote."""
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WF = (ROOT / ".github/workflows/judge.yml").read_text()
GITENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
          "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def step_script(name):
    lines = WF.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.strip() == f"- name: {name}")
    j = next(k for k in range(i, len(lines)) if lines[k].strip() == "run: |")
    ind = len(lines[j]) - len(lines[j].lstrip())
    body = []
    for ln in lines[j + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) <= ind:
            break
        body.append(ln[ind + 2:])
    return "\n".join(body) + "\n"


def test_triggers_concurrency_checkout_and_secrets():
    assert re.search(r"workflow_run:\n\s+workflows: \[system\]\n\s+types: \[completed\]", WF)
    assert 'cron: "10 13 * * 2-6"' in WF and "workflow_dispatch:" in WF
    assert re.search(r"concurrency:\n\s+group: forward-watch\n\s+cancel-in-progress: false", WF)
    assert "fetch-depth: 0" in WF and "fetch-tags: true" in WF
    assert sum("TWELVEDATA_API_KEY" in ln for ln in WF.splitlines()) == 1      # one env line, one step
    judge_step = WF[WF.index("- name: Judge run"):WF.index("- name: Commit the judge records")]
    assert "TWELVEDATA_API_KEY: ${{ secrets.TWELVEDATA_API_KEY }}" in judge_step
    assert "uv run --frozen python -I judge/run.py" in judge_step
    assert "git add -A" not in WF.replace("never `git add -A`", "")
    deploy = WF[WF.index("- name: Deploy the site"):]
    assert "wrangler" in deploy and "steps.commit.outcome == 'success'" in deploy
    assert WF.index("- name: Commit the judge records") < WF.index("- name: Deploy the site")


def _git(repo, *a):
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, env=dict(os.environ, **GITENV))
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture()
def clone(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    (seed / "data").mkdir()
    (seed / "data/x.csv").write_text("a\n1\n")
    (seed / "reports/judge").mkdir(parents=True)
    (seed / "reports/judge/VERDICTS.csv").write_text("utc\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "main")
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, env=dict(os.environ, **GITENV))
    return origin, work


def run_commit_step(work):
    env = dict(os.environ, **GITENV)
    return subprocess.run(["bash", "-e", "-c", step_script("Commit the judge records")], cwd=work, env=env,
                          capture_output=True, text=True)


def test_commit_step_commits_only_the_judge_folders(clone):
    origin, work = clone
    (work / "reports/judge/VERDICTS.csv").write_text("utc\nx\n")
    (work / "reports/forward_site/judge").mkdir(parents=True)
    (work / "reports/forward_site/judge/VolMapJudge.csv").write_text("key,value\nend,1\n")
    (work / "stray.txt").write_text("untracked, never added\n")
    r = run_commit_step(work)
    assert r.returncode == 0, r.stdout + r.stderr
    files = _git(origin, "diff-tree", "--no-commit-id", "--name-only", "-r", "main").split("\n")
    assert sorted(files) == ["reports/forward_site/judge/VolMapJudge.csv", "reports/judge/VERDICTS.csv"]
    assert _git(origin, "log", "-1", "--format=%s", "main").startswith("judge run ")


def test_commit_step_refuses_a_change_outside_its_folders(clone):
    origin, work = clone
    before = _git(origin, "rev-parse", "main")
    (work / "reports/judge/VERDICTS.csv").write_text("utc\nx\n")
    (work / "data/x.csv").write_text("a\n2\n")
    r = run_commit_step(work)
    assert r.returncode != 0 and "outside its folders" in r.stdout
    assert _git(origin, "rev-parse", "main") == before
