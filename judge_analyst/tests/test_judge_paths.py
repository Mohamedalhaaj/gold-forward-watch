"""Paths and times are matched in full (register R-AN-33 clarification A3 of 2026-10-23).

Written from the register text, not from the analyst's code: an agent path must match an allowlist pattern as a whole
and hold no control character, and Python's `$` also matches just before a trailing newline. A path holding a newline
must also never reach `git cat-file --batch`, whose protocol is one name per line: git answers twice for it, and every
later read in the run would be shifted by one."""
import subprocess

import pytest

from jlib.common import is_day, is_server, is_utc, is_utc_ms, parse_utc
from jlib.gitrepo import GitRepo
from jlib.judge import classify_path

CALL = "analyst/canary/calls/2026-11-10_W1.json"


@pytest.mark.parametrize("path,expected", [
    (CALL, ("canary", "call")),
    ("analyst/calls/2026-11-10_W2.json", ("live", "call")),
    ("analyst/canary/attempts/lesson-2026-11-10_W1_2.json", ("canary", "attempt")),
    ("analyst/playbooks/v3.md", ("live", "revision")),
    (CALL + "\n", None),
    (CALL + "\r", None),
    (CALL + "\t", None),
    ("analyst/canary/attempts/2026-11-10_W1_1.json\n", None),
    ("analyst/playbooks/v3.md\n", None),
    ("analyst/canary/calls/2026-11-10_W1\n.json", None),
    ("\x00" + CALL, None),
])
def test_an_agent_path_must_match_in_full(path, expected):
    assert classify_path(path) == expected


def test_a_newline_path_reads_as_absent_and_does_not_shift_later_reads(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "a.json").write_bytes(b"AAA")
    (repo / "b.json").write_bytes(b"BBBBB")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"],
                   check=True)
    g = GitRepo(str(repo))
    head = g.rev("HEAD")
    assert g.show(head, "a.json\n") is None
    assert g.show(head, "a.json\nb.json") is None
    assert g.show(head, "b.json") == b"BBBBB"
    assert g.show(head, "a.json") == b"AAA"


@pytest.mark.parametrize("fn,good", [
    (is_utc, "2026-11-10T07:25:00Z"),
    (is_utc_ms, "2026-11-10T07:25:00.123Z"),
    (is_day, "2026-11-10"),
    (is_server, "2026-11-10 09:25"),
])
def test_a_time_with_a_trailing_newline_is_malformed(fn, good):
    assert fn(good) is True
    assert fn(good + "\n") is False


def test_parse_utc_refuses_a_trailing_newline():
    assert parse_utc("2026-11-10T07:25:00Z").hour == 7
    with pytest.raises(ValueError):
        parse_utc("2026-11-10T07:25:00Z\n")
