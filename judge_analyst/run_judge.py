"""Analyst judge entry point (prereg §8, IMPLEMENTATION_REGISTER R-AN-1, R-AN-66..R-AN-70, amendment §16.18 A6).

The judge lives in gold-forward-watch (R-AN-1). Usage, from the gold-forward-watch root:
    python -I judge_analyst/run_judge.py --repo <FULL clone of gold-analyst main> [--inbox <clone of the inbox>]
        [--now YYYY-MM-DDTHH:MM:SSZ] [--out reports/judge_analyst] [--site reports/forward_site/judge_analyst|none]
        [--api github|none|fake:<file.json>] [--hours dukascopy|none|fake:<dir>] [--store .|<path>|none]
        [--fetch-pushes]

--repo is the public gold-analyst repository, read as data only: through git objects (cat-file, ls-tree, log, diff),
never from its working tree, never imported or executed. Relative --out, --site and --store paths are taken from
the gold-forward-watch root; --store defaults to this checkout (the system store at HEAD) and --site to the folder
the gold-watch site serves at <PINS.judge_site_url>/judge_analyst/ (R-AN-70).
--fetch-pushes (A6, R-AN-70): pushed agent commits are fetched by sha (else by their ref) from the inbox,
PINS.inbox_repo, into the gold-analyst clone, without credentials: from --inbox (a local clone of the public inbox,
data only) when given, else from https://github.com/<PINS.inbox_repo>.git. It also allows the one fresh fetch of
gold-analyst main that A4 repo_head_foreign and A12 inbox_main_foreign retest against.
The GitHub token is read from the GITHUB_TOKEN environment variable and only placed in request headers. Nothing from
an agent-pushed commit is executed: pushed commits are fetched as data only and read with git.
Only enums, counts and hashes are printed; model text never reaches stdout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE_ROOT = os.path.dirname(HERE)           # the gold-forward-watch checkout (R-AN-1)
sys.path.insert(0, HERE)

from jlib import report  # noqa: E402
from jlib.common import UTC, fmt_utc, load_json_bytes  # noqa: E402
from jlib.gitrepo import GitRepo  # noqa: E402
from jlib.judge import EVIDENCE_HEADER, Judge  # noqa: E402
from jlib.sources import FakeGitHub, FakeHourFetcher, GitHubAPI, HourSource, HttpHourFetcher  # noqa: E402

MANIFEST = "FROZEN_JUDGE_ANALYST.sha256"
NO_CREDENTIALS = ["-c", "credential.helper=", "-c", "core.askPass=", "-c", "http.https://github.com/.extraheader="]


def _git(root, *args, timeout=180):
    """A git command on the gold-analyst clone that never sends a credential (no helper, no prompt, and the
    extraheader actions/checkout may persist reset to empty)."""
    return subprocess.run(["git", *NO_CREDENTIALS, "-C", root, *args], capture_output=True, timeout=timeout,
                          env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))


def make_fetch(root, source, timeout=180, max_failures=3):
    """fetch(sha, ref) for --fetch-pushes (R-AN-70, A6): bring a pushed commit from the inbox (`source`: a local clone
    or https://github.com/<inbox>.git) into the gold-analyst clone as data: `git fetch` by sha, else by the push's
    ref (objects and FETCH_HEAD only; no ref, no checkout, nothing run). Each fetch is bounded by `timeout`; after
    `max_failures` failed pushes the judge stops fetching (their diffs are then unverified: WARNING)."""
    failures = [0]

    def fetch(sha, ref=None):
        if failures[0] >= max_failures:
            return False
        for spec in (sha, ref):
            if not spec:
                continue
            try:
                p = _git(root, "fetch", "--no-tags", "-q", source, spec, timeout=timeout)
            except subprocess.TimeoutExpired:
                break
            if p.returncode == 0:
                return True
        failures[0] += 1
        return False
    return fetch


def make_fresh_main(root, source, timeout=180):
    """fresh_main() (A6): fetch gold-analyst main once more (into FETCH_HEAD only) and return its sha, or None."""
    def fresh_main():
        try:
            p = _git(root, "fetch", "--no-tags", "-q", source, "refs/heads/main", timeout=timeout)
            if p.returncode != 0:
                return None
            q = _git(root, "rev-parse", "--verify", "-q", "FETCH_HEAD^{commit}", timeout=60)
        except subprocess.TimeoutExpired:
            return None
        sha = q.stdout.decode("ascii", "replace").strip()
        return sha if q.returncode == 0 and len(sha) == 40 else None
    return fresh_main


def manifest_status(root: str = JUDGE_ROOT):
    """(ok, code_sha8): every file the judge's manifest lists has its sha256, and every judge source file is listed."""
    mpath = os.path.join(HERE, MANIFEST)
    if not os.path.exists(mpath):
        return False, "00000000"
    with open(mpath, "rb") as f:
        mb = f.read()
    code_sha8 = hashlib.sha256(mb).hexdigest()[:8]
    listed = set()
    ok = True
    for line in mb.decode("utf-8").split("\n"):
        if not line.strip():
            continue
        sha, _, path = line.partition("  ")
        listed.add(path)
        p = os.path.join(root, path)
        if not os.path.exists(p):
            ok = False
            continue
        with open(p, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != sha:
                ok = False
    if set(judge_files(root)) - listed:
        ok = False
    return ok, code_sha8


WORKFLOW = ".github/workflows/analyst-judge.yml"


def judge_files(root: str = JUDGE_ROOT):
    """Repository-relative paths the judge's manifest covers: every file of judge_analyst/ (caches excluded) and the
    judge's workflow."""
    out = []
    for dirpath, dirs, files in os.walk(HERE):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache"))
        for name in sorted(files):
            if name == MANIFEST or name.endswith(".pyc"):
                continue
            out.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    if os.path.exists(os.path.join(root, WORKFLOW)):
        out.append(WORKFLOW)
    return sorted(out)


def write_manifest(root: str = JUDGE_ROOT):
    lines = []
    for rel in judge_files(root):
        with open(os.path.join(root, rel), "rb") as f:
            lines.append(f"{hashlib.sha256(f.read()).hexdigest()}  {rel}\n")
    with open(os.path.join(HERE, MANIFEST), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(lines))
    return len(lines)


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None, help="a FULL clone of gold-analyst main (data only)")
    ap.add_argument("--inbox", default=None, help="a clone of the public inbox, the source of pushed commits (data)")
    ap.add_argument("--out", default="reports/judge_analyst")
    ap.add_argument("--site", default="reports/forward_site/judge_analyst", help="verdict feed folder, or none")
    ap.add_argument("--now", default=None)
    ap.add_argument("--api", default="github")
    ap.add_argument("--hours", default="dukascopy")
    ap.add_argument("--store", default=".", help="gold-forward-watch at HEAD (default: this checkout), or none")
    ap.add_argument("--fetch-pushes", action="store_true")
    ap.add_argument("--write-manifest", action="store_true", help="rewrite FROZEN_JUDGE_ANALYST.sha256 and exit")
    return ap.parse_args(argv)


def _at_root(p):
    if p is None or p == "none":
        return None
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(JUDGE_ROOT, p))


def resolve(a):
    """Absolute paths: --repo and --inbox from the working directory; --out, --site and --store from the judge
    root."""
    a.repo = os.path.abspath(a.repo) if a.repo else None
    a.inbox = os.path.abspath(a.inbox) if a.inbox else None
    a.out = _at_root(a.out)
    a.site = _at_root(a.site)
    a.store = _at_root(a.store)
    return a


def main(argv=None):
    a = parse_args(argv)
    if a.write_manifest:
        print(f"manifest lines={write_manifest(JUDGE_ROOT)}")
        return 0
    if not a.repo:
        print("error: --repo <full clone of gold-analyst> is required", file=sys.stderr)
        raise SystemExit(2)
    a = resolve(a)
    root, out = a.repo, a.out
    now = a.now or fmt_utc(dt.datetime.now(UTC).replace(microsecond=0))
    git = GitRepo(root)
    pins = {}
    pb = git.show(git.head(), "analyst/PINS.json")
    if pb:
        try:
            pins = load_json_bytes(pb)
        except Exception:  # noqa: BLE001
            pins = {}
    if a.api == "github":
        api = GitHubAPI(pins.get("repo") or "Mohamedalhaaj/gold-analyst", os.environ.get("GITHUB_TOKEN"))
    elif a.api.startswith("fake:"):
        with open(a.api[5:], encoding="utf-8") as f:
            api = FakeGitHub(json.load(f), repo=pins.get("repo") or "Mohamedalhaaj/gold-analyst")
    else:
        api = None
    if a.hours == "dukascopy":
        fetcher = HttpHourFetcher()
    elif a.hours.startswith("fake:"):
        files = {}
        idx = os.path.join(a.hours[5:], "index.json")
        with open(idx, encoding="utf-8") as f:
            for url, (http, name) in json.load(f).items():
                body = b""
                if name:
                    with open(os.path.join(a.hours[5:], name), "rb") as g:
                        body = g.read()
                files[url] = (http, body)
        fetcher = FakeHourFetcher(files)
    else:
        fetcher = FakeHourFetcher({}, down=True)
    os.makedirs(out, exist_ok=True)
    hours = HourSource(fetcher, os.path.join(out, "hours.csv"), now)
    store_git = GitRepo(a.store) if a.store else None
    fetch = fresh = None
    if a.fetch_pushes:
        ga_repo = pins.get("repo") or "Mohamedalhaaj/gold-analyst"
        inbox = pins.get("inbox_repo")
        source = a.inbox or f"https://github.com/{inbox or ga_repo}.git"     # before A6: gold-analyst itself
        fetch = make_fetch(root, source)
        fresh = make_fresh_main(root, f"https://github.com/{ga_repo}.git")
    ok, code_sha8 = manifest_status(JUDGE_ROOT)
    evidence = report.read_csv(os.path.join(out, "evidence.csv"), EVIDENCE_HEADER)
    judge = Judge(git, now, api=api, hours=hours, store_git=store_git, fetch_commit=fetch, evidence_rows=evidence,
                  prev_anchor=report.last_anchor(out), judge_manifest_ok=ok, fresh_main=fresh,
                  prev_judge_utc=report.last_judge_utc(out))
    res = judge.run()
    v = report.write_outputs(res, out, now, code_sha8, hours)
    if a.site:                               # R-AN-70: the feed analyst-settle reads, byte-identical to the record
        os.makedirs(a.site, exist_ok=True)
        with open(os.path.join(out, "analyst_verdict.json"), "rb") as f:
            vb = f.read()
        with open(os.path.join(a.site, "analyst_verdict.json"), "wb") as f:
            f.write(vb)
    git.close()
    if store_git is not None:
        store_git.close()
    print(f"analyst_verdict={v['analyst_verdict']} violation_keys={len(v['violation_keys'])} "
          f"findings={len(res.findings.items)} head={res.head[:12]} code_sha8={code_sha8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
