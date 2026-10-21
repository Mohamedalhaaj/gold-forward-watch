"""Read-only git helpers for the history checks (J2, J3, J4, J8). Every call is `git -C <repo> ...`; nothing is
written to the repository."""
import subprocess
from functools import lru_cache

import pandas as pd


class GitError(Exception):
    pass


def _git(repo, *args, check=True, binary=False):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and r.returncode != 0:
        raise GitError(f"git {' '.join(args[:3])}: {r.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return r if binary else (r.returncode, r.stdout.decode("utf-8", "replace"))


def is_repo(repo):
    code, out = _git(repo, "rev-parse", "--is-inside-work-tree", check=False)
    return code == 0 and out.strip() == "true"


def is_shallow(repo):
    code, out = _git(repo, "rev-parse", "--is-shallow-repository", check=False)
    return code == 0 and out.strip() == "true"


def head(repo):
    return _git(repo, "rev-parse", "HEAD")[1].strip()


def has_commit(repo, sha):
    if not sha:
        return False
    code, _ = _git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False)
    return code == 0


def tag_commit(repo, tag):
    code, out = _git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", check=False)
    return out.strip() if code == 0 and out.strip() else None


def is_ancestor(repo, a, b):
    code, _ = _git(repo, "merge-base", "--is-ancestor", a, b, check=False)
    return code == 0


@lru_cache(maxsize=4096)
def show_bytes(repo, commit, path):
    r = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


@lru_cache(maxsize=8192)
def blob(repo, commit, path):
    code, out = _git(repo, "rev-parse", "-q", "--verify", f"{commit}:{path}", check=False)
    return out.strip() if code == 0 and out.strip() else None


def commit_time(repo, sha):
    out = _git(repo, "show", "-s", "--format=%cI", sha)[1].strip()
    return pd.Timestamp(out).tz_convert("UTC")


def commits_touching(repo, path, base=None):
    """[(sha, [parents], committer time)] of commits that change `path`, oldest first, full history (merges
    included with their real parents). base: only commits after it (base..HEAD)."""
    rng = [f"{base}..HEAD"] if base else ["HEAD"]
    code, out = _git(repo, "log", "--full-history", "--reverse", "--format=%H %P|%cI", *rng, "--", path, check=False)
    if code != 0:
        return []
    res = []
    for ln in out.splitlines():
        if not ln.strip():
            continue
        left, ct = ln.split("|", 1)
        parts = left.split()
        res.append((parts[0], parts[1:], pd.Timestamp(ct).tz_convert("UTC")))
    return res


def changed_paths(repo, paths, filters="DMRT"):
    """[(sha, status, path)] of commits in the whole history that modify, delete, rename or retype files under
    `paths` (merges compared with each parent)."""
    code, out = _git(repo, "log", "--full-history", "-m", "--no-renames", f"--diff-filter={filters}",
                     "--format=commit %H", "--name-status", "HEAD", "--", *paths, check=False)
    if code != 0:
        return []
    res, cur = [], None
    for ln in out.splitlines():
        if ln.startswith("commit "):
            cur = ln.split()[1]
        elif ln.strip() and cur:
            st, p = ln.split("\t", 1)
            res.append((cur, st, p))
    return res


def worktree_diff(repo, paths):
    """Tracked files under `paths` whose working-tree content differs from HEAD (name-status lines)."""
    code, out = _git(repo, "diff", "--no-renames", "--name-status", "HEAD", "--", *paths, check=False)
    return [ln.split("\t", 1) for ln in out.splitlines() if ln.strip()] if code == 0 else []


def ls_tree(repo, commit, path):
    code, out = _git(repo, "ls-tree", "-r", "--name-only", commit, "--", path, check=False)
    return out.splitlines() if code == 0 else []


def last_commit_touching(repo, path):
    code, out = _git(repo, "log", "-1", "--format=%H|%cI", "HEAD", "--", path, check=False)
    if code != 0 or not out.strip():
        return None
    sha, ct = out.strip().split("|", 1)
    return sha, pd.Timestamp(ct).tz_convert("UTC")
