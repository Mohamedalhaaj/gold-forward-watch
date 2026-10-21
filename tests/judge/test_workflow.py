""".github/workflows/judge.yml (SYSTEM_V2_PREREG.md §3.1 with Amendment B2 item 7; IMPLEMENTATION_REGISTER R-JC-1,
R-JC-2): triggers, its own concurrency group `judge` with the shared group `forward-watch` held only by the publish
job (commit and deploy), a full-history checkout with tags, the key and JUDGE_SITE_URL on the judge step only, the
records handed over as an artifact, the commit path guard (never `git add -A`) and the deploy from the post-commit
checkout. The commit step's script is run for real against a local bare remote."""
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


def job(name):
    """The text of one job of the workflow."""
    lines = WF.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln == f"  {name}:")
    j = next((k for k in range(i + 1, len(lines)) if re.match(r"^  [a-z_]+:$", lines[k])), len(lines))
    return "\n".join(lines[i:j]) + "\n"


def test_triggers_concurrency_checkout_and_secrets():
    assert re.search(r"workflow_run:\n\s+workflows: \[system\]\n\s+types: \[completed\]", WF)
    assert 'cron: "10 13 * * 2-6"' in WF and "workflow_dispatch:" in WF
    # B2 item 7: the workflow's own group; the shared group only on the publish job (commit + deploy)
    top = WF[WF.index("\nname: judge"):WF.index("\njobs:")]
    assert re.search(r"^concurrency:\n  group: judge\n  cancel-in-progress: false$", top, re.M)
    assert "forward-watch" not in top
    judge, publish = job("judge"), job("publish")
    assert "concurrency" not in judge and "forward-watch" not in judge
    assert re.search(r"\n    concurrency:\n      group: forward-watch\n      cancel-in-progress: false\n", publish)
    assert WF.count("group: forward-watch") == 1
    assert "needs: judge" in publish and "needs.judge.outputs.finished == '1'" in publish
    assert "needs.judge.result == 'success'" in publish
    assert "fetch-depth: 0" in judge and "fetch-tags: true" in judge and "fetch-depth: 0" in publish
    assert sum("TWELVEDATA_API_KEY" in ln for ln in WF.splitlines()) == 1      # one env line, one step
    judge_step = WF[WF.index("- name: Judge run"):WF.index("- name: Check that the judge wrote only its folders")]
    assert "TWELVEDATA_API_KEY: ${{ secrets.TWELVEDATA_API_KEY }}" in judge_step
    assert "uv run --frozen python -I judge/run.py" in judge_step
    assert "git add -A" not in WF.replace("never `git add -A`", "")
    assert "contents: write" not in judge and "contents: write" in publish
    assert "git push" not in judge and "wrangler" not in judge and "CLOUDFLARE_API_TOKEN" not in judge
    deploy = WF[WF.index("- name: Deploy the site"):]
    assert "wrangler" in deploy and "steps.commit.outcome == 'success'" in deploy
    assert WF.index("- name: Commit the judge records") < WF.index("- name: Deploy the site")
    assert WF.index("- name: Restore the judge records") < WF.index("- name: Commit the judge records")


def test_the_site_url_is_set_on_the_judge_step():
    """B2 item 7, R-JC-2 (review MF4): J8 reads the published VolMapJudge.csv of the gold-watch site."""
    judge_step = WF[WF.index("- name: Judge run"):WF.index("- name: Check that the judge wrote only its folders")]
    assert "JUDGE_SITE_URL: https://gold-watch-mq1dqc.xauusd-quant.workers.dev\n" in judge_step
    assert sum("JUDGE_SITE_URL" in ln for ln in WF.splitlines()) == 1


def test_the_artifact_carries_exactly_the_judge_folders():
    judge, publish = job("judge"), job("publish")
    up = judge[judge.index("- name: Upload the judge records"):]
    assert "actions/upload-artifact@v4" in up and "name: judge-records" in up
    assert re.search(r"path: \|\n\s+reports/judge\n\s+reports/forward_site/judge\n", up)
    assert "if-no-files-found: error" in up and "steps.judge.outputs.finished == '1'" in up
    down = publish[publish.index("- name: Restore the judge records"):publish.index("- name: Commit the judge records")]
    assert "actions/download-artifact@v4" in down and "name: judge-records" in down and "path: reports\n" in down


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


def test_the_artifact_round_trip_then_the_commit_step(clone, tmp_path):
    """The publish job's path: the judge folders as the judge job left them are copied over a fresh checkout of main
    (download-artifact into reports/), then the commit step commits only them."""
    import shutil
    origin, work = clone
    judged = tmp_path / "judged"
    (judged / "judge").mkdir(parents=True)
    (judged / "forward_site/judge").mkdir(parents=True)
    (judged / "judge/VERDICTS.csv").write_text("utc\nx\n")
    (judged / "judge/FINDINGS.csv").write_text("utc,key,check,reason,detail\n")
    (judged / "forward_site/judge/VolMapJudge.csv").write_text("key,value\nend,1\n")
    shutil.copytree(judged, work / "reports", dirs_exist_ok=True)      # download-artifact with path: reports
    r = run_commit_step(work)
    assert r.returncode == 0, r.stdout + r.stderr
    files = _git(origin, "diff-tree", "--no-commit-id", "--name-only", "-r", "main").split("\n")
    assert sorted(files) == ["reports/forward_site/judge/VolMapJudge.csv", "reports/judge/FINDINGS.csv",
                             "reports/judge/VERDICTS.csv"]
