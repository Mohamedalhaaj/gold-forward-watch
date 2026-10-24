"""§16.18 A8: public-repository git reads are measured, never a probe failure (client approval 2026-10-24)."""
from jlib.judge import PROBE_FAILS


def test_public_git_reads_are_not_probe_failures():
    assert "git.ls_remote_public" not in PROBE_FAILS and "git.ls_remote_public_proxy" not in PROBE_FAILS


def test_the_private_and_inbox_git_rules_stay():
    assert PROBE_FAILS["git.ls_remote_gfw"]("accepted") and PROBE_FAILS["git.ls_remote_gfw_proxy"]("accepted")
