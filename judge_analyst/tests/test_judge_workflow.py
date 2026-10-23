""".github/workflows/analyst-judge.yml in gold-forward-watch (prereg §8, §9; register R-AN-1, R-AN-66, R-AN-69,
R-AN-70, R-AN-75 items 4-5; review blockers B1 and B3; §16.18 A6: the inbox is a third checkout, read as data).

The rules the analyst's own workflows follow in gold-analyst (script only, permissions declared, no pull_request
trigger, no model key) hold here too, plus the judge's own: the gold-analyst clone is data (full history, no stored
credentials), the judge job only reads, and only the short publish job writes, inside the judge's two folders,
then deploys the site that carries the verdict feed. The commit step's script runs for real against a local bare
remote."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WF_PATH = ROOT / ".github/workflows/analyst-judge.yml"
WF = WF_PATH.read_text()
GITENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
          "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
ALLOWED = ("reports/judge_analyst", "reports/forward_site/judge_analyst")


def step(name):
    """The text of one step, from its `- name:` line to the next step or job."""
    i = WF.index(f"- name: {name}\n")
    nxt = [k for k in (WF.find("\n      - ", i + 1), WF.find("\n  publish:", i + 1)) if k != -1]
    return WF[i:min(nxt)] if nxt else WF[i:]


def step_script(name):
    lines = step(name).splitlines()
    j = next(k for k, ln in enumerate(lines) if ln.strip() == "run: |")
    ind = len(lines[j]) - len(lines[j].lstrip())
    return "\n".join(ln[ind + 2:] for ln in lines[j + 1:]) + "\n"


def job(name):
    lines = WF.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln == f"  {name}:")
    j = next((k for k in range(i + 1, len(lines)) if re.match(r"^  [a-z_]+:$", lines[k])), len(lines))
    return "\n".join(lines[i:j]) + "\n"


def top():
    """The workflow's head without its comment block."""
    return WF[WF.index("\nname: analyst-judge"):WF.index("\njobs:")]


def test_triggers_are_script_only_and_never_an_agent_push():
    t = top()
    assert re.search(r"^on:\n  workflow_run:\n    workflows: \[analyst-export\]\n    types: \[completed\]\n"
                     r"  schedule:\n    - cron: \"40 23 \* \* \*\"[^\n]*\n  workflow_dispatch:\n", t, re.M)
    for bad in ("push:", "pull_request", "pull_request_target", "issue_comment", "repository_dispatch"):
        assert bad not in t, bad


def test_no_model_and_no_model_key():
    """Prereg §8: the analyst judge never receives the model key; no model runs here (as gold-analyst's
    test_every_workflow_is_script_only_and_declares_permissions)."""
    low = WF.lower()
    assert "anthropic" not in low and "claude" not in low and "routine" not in low


def test_permissions_are_declared_and_minimal():
    assert re.search(r"^permissions: \{\}$", top(), re.M)
    judge, publish = job("judge"), job("publish")
    assert re.search(r"\n    permissions:\n      contents: read\n      actions: read\n      issues: read\n    outputs:",
                     judge)
    assert re.search(r"\n    permissions:\n      contents: write\n    concurrency:", publish)
    assert "write" not in judge.replace("wrote", "")


def test_secrets_reach_only_the_deploy_step():
    refs = re.findall(r"secrets\.([A-Z_]+)", WF)
    assert refs == ["CLOUDFLARE_API_TOKEN"]
    assert "secrets." in step("Deploy the site from the post-commit checkout")
    judge = job("judge")
    assert "secrets." not in judge and "wrangler" not in judge and "git push" not in judge
    assert "GITHUB_TOKEN: ${{ github.token }}" in step("Judge run")


def test_concurrency_own_group_and_the_shared_group_only_on_publish():
    assert re.search(r"^concurrency:\n  group: analyst-judge\n  cancel-in-progress: false$", top(), re.M)
    assert "group: forward-watch" not in top() and "group: forward-watch" not in job("judge")
    assert WF.count("group: forward-watch") == 1
    assert re.search(r"\n    concurrency:\n      group: forward-watch\n      cancel-in-progress: false\n", job("publish"))


def test_the_three_checkouts():
    """R-AN-66: a full clone of gold-analyst (read as data, no credentials kept) and gold-forward-watch at HEAD with
    its history (the mirror is checked against the source at each source_sha). A6 (R-AN-70): the public inbox, full
    with every branch, also as data: pushed agent commits are fetched from it by sha into the gold-analyst clone."""
    judge = job("judge")
    gfw = judge[judge.index("- uses: actions/checkout@v4"):judge.index("repository: Mohamedalhaaj/gold-analyst\n")]
    assert "path: gfw" in gfw and "fetch-depth: 0" in gfw and "persist-credentials: false" in gfw
    ga = judge[judge.index("repository: Mohamedalhaaj/gold-analyst\n"):
               judge.index("repository: Mohamedalhaaj/gold-analyst-inbox\n")]
    assert "path: ga" in ga and "ref: main" in ga and "fetch-depth: 0" in ga and "fetch-tags: true" in ga
    assert "persist-credentials: false" in ga
    inbox = judge[judge.index("repository: Mohamedalhaaj/gold-analyst-inbox\n"):judge.index("astral-sh/setup-uv")]
    assert "path: inbox" in inbox and "ref: main" in inbox and "fetch-depth: 0" in inbox
    assert "persist-credentials: false" in inbox and "fetch-tags" not in inbox
    run = step("Judge run")
    assert "working-directory: gfw" in run
    assert ("uv run --frozen --no-dev python -I judge_analyst/run_judge.py --repo ../ga --inbox ../inbox "
            "--fetch-pushes") in run
    assert "--store" not in run and "--out" not in run                  # the defaults: this checkout, its folders


def test_the_judge_writes_only_its_folders_and_never_the_analyst_clone():
    chk = step_script("Check that the judge wrote only its folders")
    for p in ALLOWED:
        assert f"':(exclude){p}'" in chk
    clean = step("Check that the judge left the gold-analyst clone untouched")
    assert "working-directory: ga" in clean and "git status --porcelain" in clean
    clean = step("Check that the judge left the inbox clone untouched")
    assert "working-directory: inbox" in clean and "git status --porcelain" in clean
    up = step("Upload the judge records")
    assert re.search(r"path: \|\n\s+gfw/reports/judge_analyst\n\s+gfw/reports/forward_site/judge_analyst\n", up)
    assert "if-no-files-found: error" in up and "name: judge-analyst-records" in up
    down = step("Restore the judge records")
    assert "name: judge-analyst-records" in down and "path: reports\n" in down
    assert "git add -A" not in WF


def test_publish_order_and_deploy():
    """R-AN-70: the verdict is deployed at <PINS.judge_site_url>/judge_analyst/analyst_verdict.json, the site that
    reports/forward_deploy/wrangler.jsonc serves from reports/forward_site/."""
    publish = job("publish")
    assert "needs: judge" in publish and "needs.judge.result == 'success'" in publish
    assert "needs.judge.outputs.finished == '1'" in publish
    i_r, i_c, i_d = (publish.index(f"- name: {n}") for n in (
        "Restore the judge records", "Commit the judge records", "Deploy the site from the post-commit checkout"))
    assert i_r < i_c < i_d
    dep = step("Deploy the site from the post-commit checkout")
    assert "steps.commit.outcome == 'success'" in dep
    assert "npx --yes wrangler@4.151.1 deploy --config reports/forward_deploy/wrangler.jsonc" in dep
    assert '"directory": "../forward_site"' in (ROOT / "reports/forward_deploy/wrangler.jsonc").read_text()


# ---------------------------------------------------------------- the commit step, run for real
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
    return subprocess.run(["bash", "-e", "-c", step_script("Commit the judge records")], cwd=work,
                          env=dict(os.environ, **GITENV), capture_output=True, text=True)


def test_commit_step_commits_only_the_judge_folders(clone, tmp_path):
    origin, work = clone
    judged = tmp_path / "judged"                                         # what download-artifact puts in reports/
    (judged / "judge_analyst").mkdir(parents=True)
    (judged / "forward_site/judge_analyst").mkdir(parents=True)
    (judged / "judge_analyst/VERDICTS.csv").write_text("judge_utc\nx\n")
    (judged / "judge_analyst/analyst_verdict.json").write_text("{}\n")
    (judged / "forward_site/judge_analyst/analyst_verdict.json").write_text("{}\n")
    shutil.copytree(judged, work / "reports", dirs_exist_ok=True)
    (work / "stray.txt").write_text("untracked, never added\n")
    r = run_commit_step(work)
    assert r.returncode == 0, r.stdout + r.stderr
    files = _git(origin, "diff-tree", "--no-commit-id", "--name-only", "-r", "main").split("\n")
    assert sorted(files) == ["reports/forward_site/judge_analyst/analyst_verdict.json",
                             "reports/judge_analyst/VERDICTS.csv", "reports/judge_analyst/analyst_verdict.json"]
    assert _git(origin, "log", "-1", "--format=%s", "main").startswith("analyst-judge run ")


@pytest.mark.parametrize("outside", ["data/x.csv", "reports/judge/VERDICTS.csv"])
def test_commit_step_refuses_a_change_outside_its_folders(clone, outside):
    origin, work = clone
    before = _git(origin, "rev-parse", "main")
    (work / "reports/judge_analyst").mkdir(parents=True)
    (work / "reports/judge_analyst/VERDICTS.csv").write_text("judge_utc\nx\n")
    (work / outside).write_text("changed\n")
    r = run_commit_step(work)
    assert r.returncode != 0 and "outside the judge folders" in r.stdout
    assert _git(origin, "rev-parse", "main") == before
