"""External inputs of the analyst judge, each behind a small interface with a test double:

- GitHub REST API (activity, the witness issue's comments, workflow runs): `GitHubAPI` / `FakeGitHub`.
  Since register §16.18 A6 also the public reads of R-AN-66: the inbox's repository, activity, runs and rules,
  gold-analyst's runs by day and its rules, and `git ls-remote` of both repositories. These reads are complete or
  they fail (`ApiError`): every page must answer 200 with the expected JSON, so a failed read can never look like an
  empty list. GETs only; `git ls-remote` runs without any credential. The inbox's activity is read for the last
  month (`time_period=month`, second review of A6).
- Dukascopy hour files (re-downloads, R-AN-66): `HttpHourFetcher` / `FakeHourFetcher`, behind `HourSource`, which keeps
  the judge's own append-only cache `hours.csv` so a file is downloaded once and later runs reuse its summary.

The token (GITHUB_TOKEN of the judge job) is read from the environment by the caller and only ever placed in a request
header; it is never logged or written.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

from . import ticks
from .common import fmt_utc, norm_api_time, sha256_bytes


class ApiError(RuntimeError):
    pass


class _Refused(Exception):
    """GitHub refused the token (401, 403 or 404): read once more without it."""


# ---------------------------------------------------------------- git ls-remote (R-AN-66, A6)

_LS_LINE = re.compile(r"[0-9a-f]{40}\t\S+")


def git_ls_remote(url: str, timeout: int = 60):
    """[(sha, ref)] as `git ls-remote <url>` lists them (HEAD, branches, pull refs, tags and their `^{}` peel lines).
    Public data: no credential helper, no prompt. A failure or an unreadable line raises ApiError."""
    try:
        p = subprocess.run(["git", "-c", "credential.helper=", "-c", "core.askPass=", "ls-remote", url],
                           capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    except (subprocess.TimeoutExpired, OSError) as e:
        raise ApiError(f"ls-remote {type(e).__name__}") from None
    if p.returncode != 0:
        raise ApiError(f"ls-remote exit {p.returncode}")
    out = []
    for line in p.stdout.split("\n"):
        if not line:
            continue
        if not _LS_LINE.fullmatch(line):
            raise ApiError("ls-remote line")
        sha, _, ref = line.partition("\t")
        out.append((sha, ref))
    return out


# ---------------------------------------------------------------- GitHub


class GitHubAPI:
    def __init__(self, repo: str, token: str | None, base: str = "https://api.github.com", timeout: int = 20,
                 pause: float = 5.0):
        self.repo = repo
        self.token = token
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.pause = pause

    def _get(self, url: str):
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "X-GitHub-Api-Version": "2022-11-28",
                                                   "User-Agent": "gold-analyst-judge"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        last = None
        for i in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8")), r.headers.get("Link", "")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None, ""
                last = f"http {e.code}"
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = type(e).__name__
            time.sleep(5 * (i + 1))
        raise ApiError(last or "unreachable")

    def _paged(self, url: str):
        out = []
        while url:
            data, link = self._get(url)
            if data is None:
                break
            out.extend(data)
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part[part.find("<") + 1:part.find(">")]
        return out

    def activity(self):
        return self._paged(f"{self.base}/repos/{self.repo}/activity?per_page=100")

    def issue_comments(self, issue: int):
        return self._paged(f"{self.base}/repos/{self.repo}/issues/{int(issue)}/comments?per_page=100")

    def run(self, run_id):
        data, _ = self._get(f"{self.base}/repos/{self.repo}/actions/runs/{int(run_id)}")
        return data

    # ------------------------------------------------------------ public reads of R-AN-66 (A6): complete or failed
    def _once(self, url: str, token: str | None):
        """(status, data, link) of one GET; status 0 = no response or the timeout; data None when not JSON."""
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "X-GitHub-Api-Version": "2022-11-28",
                                                   "User-Agent": "gold-analyst-judge"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read()
                status, link = r.status, r.headers.get("Link", "") or ""
        except urllib.error.HTTPError as e:
            return e.code, None, ""
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, None, ""
        try:
            return status, json.loads(body.decode("utf-8")), link
        except (UnicodeDecodeError, ValueError):
            return status, None, link

    def _public(self, url: str, kind, token):
        """One GET of public data. A try that gets no response, a 429, a 5xx or a body that is not `kind` is
        repeated, up to 3 tries. Returns (200, data, link), or (404, None, "") for a 404 without a token. A 401, 403
        or 404 with the token raises _Refused (the caller reads once more without it); anything else ApiError."""
        status = 0
        for i in range(3):
            status, data, link = self._once(url, token)
            if status == 200 and isinstance(data, kind):
                return status, data, link
            if status in (401, 403, 404):
                if token:
                    raise _Refused()
                if status == 404:
                    return 404, None, ""
                raise ApiError(f"http {status}")
            if i < 2:
                time.sleep(self.pause)
        raise ApiError(f"http {status}")

    def _with_fallback(self, read):
        """read(token) with the token first; if GitHub refuses the token (401, 403, 404) anywhere in the read, the
        whole read starts again without it, once (the repositories read here are public; as R-AN-32's merge)."""
        for token in ([self.token, None] if self.token else [None]):
            try:
                return read(token)
            except _Refused:
                continue
        raise ApiError("refused")

    def _pages(self, url: str, kind=list, key: str | None = None):
        """Every page of a list (Link rel="next"): complete, or ApiError (a 404 on any page is a failure here)."""
        def read(token):
            out, u = [], url
            while u:
                status, data, link = self._public(u, kind, token)
                if status != 200:
                    raise ApiError(f"http {status}")
                items = data.get(key) if key else data
                if not isinstance(items, list):
                    raise ApiError("not a list")
                out.extend(items)
                u = None
                for part in link.split(","):
                    if 'rel="next"' in part:
                        u = part[part.find("<") + 1:part.find(">")]
            return out
        return self._with_fallback(read)

    def repo_info(self, repo: str):
        """GET /repos/{repo}: the repository object, or None when GitHub answers 404."""
        status, data, _ = self._with_fallback(lambda t: self._public(f"{self.base}/repos/{repo}", dict, t))
        return data if status == 200 else None

    def repo_activity(self, repo: str):
        """The inbox's activity for the last month only (R-AN-66, second review of A6, SEC-3: as analyst-merge reads
        it, so a flood of branches cannot make the read grow without bound); older entries are the judge's
        `inbox_activity` evidence rows."""
        return self._pages(f"{self.base}/repos/{repo}/activity?per_page=100&time_period=month")

    def runs_total(self, repo: str) -> int:
        url = f"{self.base}/repos/{repo}/actions/runs?per_page=1"
        status, data, _ = self._with_fallback(lambda t: self._public(url, dict, t))
        total = data.get("total_count") if status == 200 else None
        if not isinstance(total, int) or isinstance(total, bool):
            raise ApiError("total_count")
        return total

    def branch_rules(self, repo: str, branch: str):
        return self._pages(f"{self.base}/repos/{repo}/rules/branches/{branch}")

    def runs_on_day(self, repo: str, day: str):
        """The runs created on one UTC day (one query a day keeps it under GitHub's 1000-result cap)."""
        return self._pages(f"{self.base}/repos/{repo}/actions/runs?created={day}&per_page=100", dict,
                           "workflow_runs")

    def ls_remote(self, repo: str):
        return git_ls_remote(f"https://github.com/{repo}.git")


class FakeGitHub:
    """Test double in the API's shapes:
    {"activity": [...], "comments": {"<issue>": [...]}, "runs": {"<id>": {...}},          gold-analyst (`repo`)
     "repos": {"<repo>": {...} | None (404)}, "repo_activity": {"<repo>": [...]}, "runs_total": {"<repo>": int},
     "rules": {"<repo>": {"<branch>": [...]}}, "ls_remote": {"<repo>": [[sha, ref], ...]},
     "day_runs": {"<repo>": [...]}}   (gold-analyst's runs by day default to the "runs" values)
    `fail` names reads that raise ApiError: a method name, or "<method>:<repo>". `calls` records every read."""

    def __init__(self, data: dict | None = None, unreachable: bool = False, repo: str = "Mohamedalhaaj/gold-analyst",
                 fail=()):
        self.data = data if data is not None else {"activity": [], "comments": {}, "runs": {}}
        self.unreachable = unreachable
        self.repo = repo
        self.fail = set(fail)
        self.calls = []

    def _guard(self, name="", *args):
        self.calls.append((name, args))
        if self.unreachable or name in self.fail or (args and f"{name}:{args[0]}" in self.fail):
            raise ApiError("unreachable (test double)")

    def activity(self):
        self._guard("activity")
        return list(self.data.get("activity", []))

    def issue_comments(self, issue: int):
        self._guard("issue_comments")
        return list(self.data.get("comments", {}).get(str(issue), []))

    def run(self, run_id):
        self._guard("run")
        return self.data.get("runs", {}).get(str(run_id))

    def repo_info(self, repo):
        self._guard("repo_info", repo)
        return self.data.get("repos", {}).get(repo)

    def repo_activity(self, repo):
        self._guard("repo_activity", repo)
        return list(self.data.get("repo_activity", {}).get(repo, []))

    def runs_total(self, repo):
        self._guard("runs_total", repo)
        return self.data.get("runs_total", {}).get(repo, 0)

    def branch_rules(self, repo, branch):
        self._guard("branch_rules", repo, branch)
        return list(self.data.get("rules", {}).get(repo, {}).get(branch, []))

    def runs_on_day(self, repo, day):
        self._guard("runs_on_day", repo, day)
        runs = self.data.get("day_runs", {}).get(repo)
        if runs is None:
            runs = list(self.data.get("runs", {}).values()) if repo == self.repo else []
        return [r for r in runs if (norm_api_time(r.get("created_at")) or "")[:10] == day]

    def ls_remote(self, repo):
        self._guard("ls_remote", repo)
        return [tuple(x) for x in self.data.get("ls_remote", {}).get(repo, [])]


# ---------------------------------------------------------------- hour files


class HttpHourFetcher:
    UA = "Mozilla/5.0 (gold-analyst judge)"

    def __init__(self, pacing_s: float = 1.5, timeout: int = 20):
        self.pacing_s = pacing_s
        self.timeout = timeout
        self._last = 0.0

    def get(self, url: str):
        """(http, body); http 0 = connection error after the tries."""
        for i in range(3):
            wait = self._last + self.pacing_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self.UA})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read()
                    self._last = time.monotonic()
                    return r.status, body
            except urllib.error.HTTPError as e:
                self._last = time.monotonic()
                if e.code in (429, 500, 502, 503, 504) and i < 2:
                    continue
                return e.code, b""
            except (urllib.error.URLError, TimeoutError, OSError):
                self._last = time.monotonic()
                if i < 2:
                    continue
                return 0, b""
        return 0, b""


class FakeHourFetcher:
    """Test double: {url: (http, body)}; an unknown url is a 404. `calls` counts requests."""

    def __init__(self, files: dict | None = None, down: bool = False):
        self.files = files if files is not None else {}
        self.down = down
        self.calls = 0

    def get(self, url: str):
        self.calls += 1
        if self.down:
            return 0, b""
        return self.files.get(url, (404, b""))


HOURS_HEADER = ["judge_utc", "sym", "hour_utc", "url", "http", "bytes", "sha256", "ticks", "status", "first_ms",
                "first_ask", "first_bid", "last_ms", "last_ask", "last_bid", "max_sum", "min_sum"]
_INTS = ("http", "bytes", "ticks", "first_ms", "first_ask", "first_bid", "last_ms", "last_ask", "last_bid", "max_sum",
         "min_sum")


class HourSource:
    """The judge's view of one hour file: its own download, cached in `hours.csv` (append-only).
    A file whose download fails (status `error`) is not cached and is retried by a later run."""

    def __init__(self, fetcher, cache_path: str | None, now_utc: str, max_fetch: int = 3000):
        self.fetcher = fetcher
        self.cache_path = cache_path
        self.now_utc = now_utc
        self.max_fetch = max_fetch
        self.fetched = 0
        self.cache = {}
        self.new_rows = []
        self.unavailable = 0
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    row = {k: r[k] for k in HOURS_HEADER}
                    for k in _INTS:
                        row[k] = int(row[k]) if row[k] != "" else None
                    self.cache[(row["sym"], row["hour_utc"])] = row

    def get(self, sym: str, hour):
        """The judge's record for (sym, hour): dict with status/sha256/... or None when it could not be fetched."""
        key = (sym, fmt_utc(hour))
        if key in self.cache:
            return self.cache[key]
        if self.fetched >= self.max_fetch:
            self.unavailable += 1
            return None
        url = ticks.hour_url(sym, hour)
        self.fetched += 1
        http, body = self.fetcher.get(url)
        status, summ = ticks.classify(http, body)
        if status == "error":
            self.unavailable += 1
            return None
        row = {"judge_utc": self.now_utc, "sym": sym, "hour_utc": key[1], "url": url, "http": http,
               "bytes": len(body or b""), "sha256": sha256_bytes(body) if body else "", "ticks": None,
               "status": status}
        for k in ("first_ms", "first_ask", "first_bid", "last_ms", "last_ask", "last_bid", "max_sum", "min_sum"):
            row[k] = None
        if summ:
            row.update(summ)
        self.cache[key] = row
        self.new_rows.append(row)
        return row

    def flush(self):
        if not self.cache_path or not self.new_rows:
            return
        new = not os.path.exists(self.cache_path)
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        if new:
            w.writerow(HOURS_HEADER)
        for r in self.new_rows:
            w.writerow(["" if r[k] is None else r[k] for k in HOURS_HEADER])
        with open(self.cache_path, "a", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
        self.new_rows = []
