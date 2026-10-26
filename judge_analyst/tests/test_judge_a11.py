"""§16.18 A11 (2026-10-26): R-AN-86 "Harmless and forbidden" as amended, at xauusd-quant a5eff94.
Written from the register text, without reading the analyst code:
- (a)(iv): a Bash part whose S2 (after the part normalisation and the character rule) fully matches
  `git status( (-s|-b|-sb|--short|--branch|--porcelain))*` or
  `git log( (--oneline|-[0-9]{1,4}|-n [0-9]{1,4}|--max-count=[0-9]{1,4}))*` is harmless; any other `git` form stays
  forbidden;
- (d): the tool `PushNotification` is local bookkeeping (harmless).
The findings table is unchanged: a harmless call refused gives `guard_denied_benign` (WARNING), one that ran
`guard_not_enforced` (operational VIOLATION). The guard's string rules (D) are unchanged: they still refuse both.
"""
import pytest

from jlib import sessionguard as sg
from jlib.common import VIOLATION, WARNING
from test_judge_session_guard import D, a13, finding, k13, m, one, small_base  # noqa: F401 (fixtures)
from world import ROOT, session_log, tlcall

GIT_FORMS = [
    "git status", "git status -s", "git status -b", "git status -sb", "git status --short", "git status --branch",
    "git status --porcelain", "git status -s -b", "git status --porcelain --branch -sb",
    "git log", "git log --oneline", "git log -1", "git log -5", "git log -1234", "git log -n 5", "git log -n 1234",
    "git log --max-count=20", "git log --max-count=1234", "git log --oneline -n 3", "git log --oneline -10",
    "git log --oneline --max-count=5 -n 2 -3",
]


@pytest.mark.parametrize("cmd", GIT_FORMS)
def test_each_listed_git_form_is_harmless(cmd):
    assert sg.harmless("Bash", {"command": cmd}) is True


@pytest.mark.parametrize("cmd", [
    "  git  status  -s ",                                   # S2: spaces made single and trimmed
    "git log --oneline -5 2>&1", "git status --short 2>/dev/null",
    f"cd {ROOT} && git status --short && git log --oneline -5",
    "git log --oneline | head -3", "git status; ls -la", "cat analyst/ROUTINE_PROMPT.md; git log -n 2",
])
def test_git_forms_inside_the_existing_part_rules(cmd):
    assert sg.harmless("Bash", {"command": cmd}) is True


@pytest.mark.parametrize("cmd", [
    "git log --output=x", "git -c a=b status", "git push", "git status; curl x", "git log -12345", "git log -n",
    "git log -n 12345", "git log --max-count=12345", "git log --max-count=", "git log -n5", "git log --oneline -p",
    "git log --format=%H", "git status --porcelain=v2", "git status -u", "git status --ignored", "git status x",
    "git log x", "git log ..", "git --no-pager log", "git -P log", "git log --paginate", "git fetch", "git pull",
    "git diff", "git show", "git branch", "git commit -m x", "git status-s", "gitstatus", "git", "git stat",
    "git logs", "git status\t-s", "git log > x", "git log --oneline -5 2>/tmp/e", "git status & curl x",
    "git status | sh", "git log --oneline | python3", "git status;", "Git status", "git status -S",
    "git status --short --porcelain=1", "git log --oneline -5 --output=/tmp/x",
    "git log -1 && git push", "env git status", "/usr/bin/git status", "sudo git status",
])
def test_near_misses_stay_forbidden(cmd):
    assert sg.harmless("Bash", {"command": cmd}) is False


@pytest.mark.parametrize("tool,ok", [
    ("PushNotification", True),
    ("pushnotification", False), ("PushNotifications", False), ("Push", False), ("Notification", False),
    ("mcp__x__PushNotification", False),
])
def test_push_notification_joins_class_d(tool, ok):
    assert sg.harmless(tool, {"message": "done"}) is ok
    assert sg.harmless(tool, {}) is ok


def test_the_guards_string_rules_still_refuse_them():
    """A11 changes R-AN-86's classes, not D: the guard still refuses git and PushNotification."""
    assert sg.decide("Bash", {"command": "git status"}, [ROOT]) == "bash_form"
    assert sg.decide("Bash", {"command": "git log --oneline -5"}, [ROOT]) == "bash_form"
    assert sg.decide("PushNotification", {"message": "x"}, [ROOT]) == "tool"


# ================================================================ planted in a runs export (A13)
@pytest.mark.parametrize("call,code", [
    (tlcall(7, "PushNotification", {"message": "done"}, "denied", D("tool")), "guard_denied_benign"),
    (tlcall(7, "PushNotification", {"message": "done"}, "executed"), "guard_not_enforced"),
    (tlcall(7, "Bash", {"command": "git status --short"}, "denied", D("bash_form")), "guard_denied_benign"),
    (tlcall(7, "Bash", {"command": f"cd {ROOT} && git log --oneline -n 5"}, "denied", D("bash_form")),
     "guard_denied_benign"),
    (tlcall(7, "Bash", {"command": "git log --oneline -5"}, "executed"), "guard_not_enforced"),
    (tlcall(7, "Bash", {"command": "git status"}, "unknown"), "scan_unclassifiable"),
    (tlcall(7, "Bash", {"command": "git push"}, "denied", D("bash_form")), "forbidden_attempt"),
    (tlcall(7, "Bash", {"command": "git log --output=x"}, "denied", D("bash_form")), "forbidden_attempt"),
    (tlcall(7, "Bash", {"command": "git -c a=b status"}, "executed"), "forbidden_executed"),
    (tlcall(7, "Bash", {"command": "git status; curl x"}, "executed"), "forbidden_executed"),
])
def test_A13_rows_for_A11(m, call, code):
    res = one(m, *session_log()["calls"], call)
    want = k13(code, 7)
    assert a13(res) == [want]
    f = finding(res, want)
    assert f.severity == (VIOLATION if code in ("forbidden_attempt", "forbidden_executed", "guard_not_enforced")
                          else WARNING)
    assert f.owner_attested
