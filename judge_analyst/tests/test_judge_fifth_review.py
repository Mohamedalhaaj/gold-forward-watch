"""Planted cases of blocker J-5 of the fifth review of register §16.18 A6 (2026-10-23): when a lift reaches the
sessions. Judge decision J-D34 (README), pending the register's own text for J-5.

A RESUMED event's `utc` is the t0 of the analyst-settle run that wrote it (R-AN-55, R-AN-56). Its commit reaches
gold-analyst main minutes later, and analyst-inbox-mirror carries it to inbox main later still (R-AN-83), which GitHub
can start hours late. Sessions read STATE.json at inbox main (R-AN-24), so `start` refuses `calls_disabled` until the
mirror has pushed the lift. A10's pause interval (J-D14) therefore ends:
1. at the first counting inbox activity entry on `refs/heads/main` whose `after` has the RESUMED event's commit as an
   ancestor (the live list or the `inbox_activity` evidence rows, R-AN-69);
2. else, while the inbox's main as `git ls-remote` lists it lacks that commit, not yet: inbox main only fast-forwards
   (R-AN-83), so no session has seen the lift;
3. else (no inbox pinned, no entry known, no ls-remote read), 30 minutes after the event's `utc`: the lag the judge
   already treats as normal for the mirror (A12 `inbox_stale`).
Never before the event's own `utc`. Written from the register text, not from the analyst code. The verifier's probe
(scratchpad verify5/probes_judge/test_v5_judge.py::test_a_fire_two_minutes_after_a_lift_is_an_in_span_run) is the
first case below.

A10's key names the runs export and its commit, so one export with two in-span runs gives one finding: each world
here holds one owner-attested W2 run on 2026-12-01 (EST: span 13:45..14:15 UTC, T_run and T_setup 0), at 13:50 or at
14:00, and no attempt."""
import datetime as dt

import pytest

from jlib.judge import EVIDENCE_HEADER
from jlib.sources import FakeGitHub
from test_judge_fourth_review import A10_PLANS, K_OP, in_span, pause_row, plant
from world import GA, INBOX, OWNER, T, World

DAY = "2026-12-01"
CID = f"{DAY}_W2"
LIFT = f"lifted:judge_violation:{K_OP}"


def runs_at(fire):
    def hook(world, weeks):
        weeks.setdefault("2026-W49", []).append({"routine": "analyst-w2", "run_id": f"r-{fire}",
                                                 "session_id": f"s-{fire}", "created_utc": f"{DAY}T{fire}:00Z",
                                                 "status": "success", "model": "claude-opus-5-5",
                                                 "model_source": "get_run_log"})
    return hook


@pytest.fixture(scope="module")
def bases(tmp_path_factory):
    built = {}

    def get(fire):
        if fire not in built:
            built[fire] = World(str(tmp_path_factory.mktemp("j5") / "w"), canary_days=("2026-11-25",),
                                live_from="2026-11-30", live_to=DAY, now="2026-12-02T23:00:00Z", plans=A10_PLANS,
                                hooks={"runs": runs_at(fire)}).build()
        return built[fire]
    return get


@pytest.fixture
def world(bases, tmp_path):
    """world(fire): a copy of the world whose only 2026-12-01 W2 run fired at `fire`."""
    return lambda fire: bases(fire).clone(str(tmp_path / ("c" + fire.replace(":", ""))))


def found(res) -> bool:
    """A10 reports the 2026-12-01 W2 run as in-span without an attempt."""
    return any(CID in d for d in in_span(res))


def lift(m, at, reason=LIFT):
    """A pause from 00:00 and its RESUMED event dated `at`, committed at `at` (as R-AN-55's settle run writes both).
    Returns (the pause's commit, the lift's commit)."""
    subject = reason.split(":", 1)[1]
    _, paused = plant(m, [("PAUSED", subject, f"{DAY}T00:00:00Z")], f"{DAY}T00:05:00Z")
    if reason.startswith("clear:"):
        _, lifted = plant(m, [("RESUMED", reason, f"{DAY}T{at}:00Z")], f"{DAY}T{at}:00Z",
                          adj=[pause_row(subject, f"{DAY}T09:00:00Z")])
    else:
        _, lifted = plant(m, [("RESUMED", reason, f"{DAY}T{at}:00Z")], f"{DAY}T{at}:00Z", fresh=True)
    return paused, lifted


def mirror(m, sha, at):
    """analyst-inbox-mirror fast-forwards inbox main to `sha` at `at` (an inbox activity entry, R-AN-83)."""
    return m.inbox_activity("refs/heads/main", sha, T(f"{DAY}T{at}:00Z"), OWNER, "push")


@pytest.mark.parametrize("fire", ["13:50", "14:00"])
def test_a_run_is_found_without_a_pause(world, fire):
    assert found(world(fire).judge())


@pytest.mark.parametrize("fire,expect", [
    ("13:50", False),       # case (1): the fire read STATE.json before the mirror carried the lift; refused
    ("14:00", True),        # case (2): the fire came after the mirror push
])
def test_the_lift_counts_from_the_mirror_push_that_carried_it(world, fire, expect):
    """The orchestrator's cases (1) and (2): a lift dated 13:48 (the settle run's t0) that inbox main got at 13:55."""
    m = world(fire)
    _, lifted = lift(m, "13:48")
    mirror(m, lifted, "13:55")
    assert found(m.judge()) is expect


@pytest.mark.parametrize("fire,at,expect", [
    ("13:50", "13:48", False),     # the orchestrator's case (3): the interval ends at 14:18
    ("14:00", "13:48", False),
    ("13:50", "13:25", False),     # it ends at 13:55
    ("14:00", "13:25", True),
    ("13:50", "13:00", True),      # it ends at 13:30
])
def test_with_no_mirror_entry_known_the_lift_counts_30_minutes_after_its_event(world, fire, at, expect):
    """No inbox main entry holds the lift's commit, while `git ls-remote` shows inbox main holding it (the entry aged
    out, or the activity listing lags): the fallback grace of 30 minutes applies."""
    m = world(fire)
    lift(m, at)
    assert found(m.judge()) is expect


@pytest.mark.parametrize("fire,expect", [("13:50", False), ("14:00", True)])
def test_the_first_mirror_push_whose_after_descends_from_the_lift(world, fire, expect):
    """A mirror push of an older commit (the pause's, 13:05) does not carry the lift; a push of a later commit (13:54)
    does, since its `after` has the lift's commit as an ancestor. The interval ends at 13:54: not at the event (13:00),
    not at the first main push after it (13:05), not at the fallback (13:30), not at the lift's own entry (13:58)."""
    m = world(fire)
    paused, lifted = lift(m, "13:00")
    later = m.repo.commit("analyst-merge (a later commit)", T(f"{DAY}T13:52:00Z"))
    mirror(m, paused, "13:05")
    mirror(m, later, "13:54")
    mirror(m, lifted, "13:58")
    assert found(m.judge()) is expect


def test_a_late_mirror_excuses_a_fire_long_after_the_lift(world):
    """GitHub started the mirror hours late: calls stayed disabled for the sessions until 16:40."""
    m = world("14:00")
    _, lifted = lift(m, "13:00")
    mirror(m, lifted, "16:40")
    assert not found(m.judge())


def test_with_inbox_main_still_lacking_the_lift_the_interval_stays_open(world):
    """`git ls-remote` lists inbox main at the pause's commit and no entry carries the lift: the mirror has not
    pushed it yet (it only fast-forwards), so no session could have read calls enabled, though the lift is dated over
    an hour before the fire. A judge run after the mirror push judges the fire again."""
    m = world("14:00")
    paused, _ = lift(m, "12:50")
    m.ls_main[INBOX] = paused
    assert not found(m.judge())


@pytest.mark.parametrize("fire,expect", [("13:50", False), ("14:00", True)])
def test_with_neither_the_activity_nor_ls_remote_read_the_grace_applies(world, fire, expect):
    """No activity entry and no ls-remote read of the inbox: the fallback grace (lift at 13:25, end at 13:55)."""
    m = world(fire)
    lift(m, "13:25")
    api = FakeGitHub(m.api_data(), repo=GA, fail={"repo_activity", f"ls_remote:{INBOX}"})
    assert found(m.judge(api=api)) is expect


@pytest.mark.parametrize("fire,expect", [("13:50", False), ("14:00", True)])
def test_an_entry_known_from_the_evidence_rows_ends_the_interval(world, fire, expect):
    """This run's activity read failed; the judge's own `inbox_activity` row (R-AN-69) still dates the mirror push
    that carried the lift (13:58, later than the fallback's 13:30)."""
    m = world(fire)
    _, lifted = lift(m, "13:00")
    row = {k: "" for k in EVIDENCE_HEADER}
    row.update(judge_utc=f"{DAY}T20:00:00Z", source="inbox_activity", ref="refs/heads/main", push_after=lifted,
               activity_id="79999", activity_type="push", activity_utc=f"{DAY}T13:58:00Z", actor=OWNER)
    api = FakeGitHub(m.api_data(), repo=GA, fail={"repo_activity"})
    assert found(m.judge(api=api, evidence=[row])) is expect


def test_a_mirror_entry_before_inbox_from_does_not_count(world):
    """Inbox activity entries count only at or after PINS.inbox_from_utc (R-AN-67). An entry dated before it is
    ignored (counted, it would end the interval at the event, 13:25), and the fallback grace applies (13:55)."""
    m = world("13:50")
    _, lifted = lift(m, "13:25")
    m.inbox_activity("refs/heads/main", lifted, T(m.inbox_from) - dt.timedelta(minutes=1), OWNER, "push")
    assert not found(m.judge())


def test_a_mirror_entry_dated_before_the_event_never_shortens_the_interval(world):
    """An entry holding the lift's commit but dated before the event's `utc` (no real mirror push is): the interval
    still runs to the event's `utc` (13:52), so the 13:50 fire stays inside it."""
    m = world("13:50")
    _, lifted = lift(m, "13:52")
    mirror(m, lifted, "13:40")
    assert not found(m.judge())


@pytest.mark.parametrize("fire,expect", [("13:50", False), ("14:00", True)])
def test_a_clear_reaches_the_sessions_through_the_mirror_too(world, fire, expect):
    """A RESUMED `clear:` (an owner clear, R-AN-55 step 1) lands in a settle commit as a lift does."""
    m = world(fire)
    _, lifted = lift(m, "13:48", reason="clear:model:r-1")
    mirror(m, lifted, "13:55")
    assert found(m.judge()) is expect


@pytest.mark.parametrize("fire,expect", [("13:50", True), ("14:00", False)])
def test_the_pause_start_is_unchanged(world, fire, expect):
    """Only the interval's end moves: a pause dated 13:55 still starts at 13:55."""
    m = world(fire)
    plant(m, [("PAUSED", f"judge_violation:{K_OP}", f"{DAY}T13:55:00Z")], f"{DAY}T13:56:00Z")
    assert found(m.judge()) is expect


@pytest.mark.parametrize("base,fire,expect", [
    ("lift", "13:50", False),      # the merged side commit descends from the lift: the interval ends at 13:54
    ("lift", "14:00", True),
    ("pause", "13:50", True),      # it branched from the pause's commit: no push carried the lift, grace to 13:30
])
def test_a_mirror_push_off_mains_first_parent_line_is_asked_of_git(world, base, fire, expect):
    """Inbox main at a commit that is on gold-analyst main only through a merge's second parent: main's first-parent
    order cannot answer, so git does (`merge-base --is-ancestor`)."""
    m = world(fire)
    paused, lifted = lift(m, "13:00")
    m.repo("checkout", "-q", "-b", "side", lifted if base == "lift" else paused)
    side = m.repo.commit("side commit", T(f"{DAY}T13:52:00Z"))
    m.repo("checkout", "-q", "main")
    m.repo("merge", "-q", "--no-ff", "-m", "merge side", "side", when=T(f"{DAY}T13:53:00Z"))
    mirror(m, side, "13:54")
    assert found(m.judge()) is expect
