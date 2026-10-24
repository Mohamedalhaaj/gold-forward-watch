"""Planted cases of blocker J-5 of the fifth review of register §16.18 A6 (2026-10-23): A10 judges calls as inbox main
showed them. Register decision 33 and R-AN-67 "A10's pause intervals, as inbox main showed them" (xauusd-quant
166c6b0); judge decisions J-D14 and J-D31 as amended there, and J-D34 (README). Written from the register text, not
from the analyst code.

`start` reads STATE.json at inbox main when it runs (R-AN-24), and a PAUSED, RESUMED or RETIRED event reaches inbox main
only when analyst-inbox-mirror pushes a commit that holds the analyst-settle commit adding it (R-AN-83). So:
- V(e), an event's time on inbox main: the timestamp of the earliest (timestamp, id) known inbox activity entry (live
  list or `inbox_activity` evidence rows) with timestamp >= PINS.inbox_from_utc, on `refs/heads/main`, whose `after` is
  the commit that added e or has it as an ancestor; an `after` not on gold-analyst main gives no time; none while no
  such entry is known;
- an interval runs from V(PAUSED), else the PAUSED event's utc, to V(RESUMED) of the RESUMED event that closes its
  subject, and stays open while V(RESUMED) is none: no fixed grace (considered and not adopted); after RETIRED, from
  V(RETIRED), else its utc, on;
- a run is not judged in_span_without_attempt when an interval meets [its created_utc, its window's deadline_utc -
  T_run]: it starts at or before that range's end and ends after created_utc;
- without PINS.inbox_repo, and for an event dated before PINS.inbox_from_utc, the event utcs are kept.
The verifier's probes are cases below: verify5/probes_judge/test_v5_judge.py::
test_a_fire_two_minutes_after_a_lift_is_an_in_span_run, turned round, and verify5/r6/probes_judge/test_r6_judge.py.

A10's key names the runs export and its commit, so one export with two in-span runs gives one finding: each world
here holds one owner-attested W2 run on 2026-12-01 (EST: span 13:45..14:15 UTC, deadline_utc 14:15, T_run and T_setup
0, so the start interval ends at 14:15), at 13:50 or at 14:00, and no attempt."""
import datetime as dt
import json
import os

import pytest

from jlib.common import record_form
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
    """A10 reports the 2026-12-01 W2 run as in-span without an attempt (and the A10 check ran to its end)."""
    assert not [f for f in res.findings.items if f.code == "check_crashed" and f.path == "judge/runs_exports"]
    return any(CID in d for d in in_span(res))


def mirror(m, sha, at):
    """analyst-inbox-mirror fast-forwards inbox main to `sha` at `at` (an inbox activity entry, R-AN-83)."""
    return m.inbox_activity("refs/heads/main", sha, T(f"{DAY}T{at}:00Z"), OWNER, "push")


def lift(m, at, reason=LIFT, pause_seen="00:10"):
    """A pause dated 00:00 (committed 00:05; inbox main holds it from `pause_seen`, or never with None) and its RESUMED
    event dated `at`, committed at `at` (as R-AN-55's settle run writes both), with no mirror entry for the lift.
    Returns (the pause's commit, the lift's commit)."""
    subject = reason.split(":", 1)[1]
    _, paused = plant(m, [("PAUSED", subject, f"{DAY}T00:00:00Z")], f"{DAY}T00:05:00Z")
    if pause_seen:
        mirror(m, paused, pause_seen)
    if reason.startswith("clear:"):
        _, lifted = plant(m, [("RESUMED", reason, f"{DAY}T{at}:00Z")], f"{DAY}T{at}:00Z",
                          adj=[pause_row(subject, f"{DAY}T09:00:00Z")])
    else:
        _, lifted = plant(m, [("RESUMED", reason, f"{DAY}T{at}:00Z")], f"{DAY}T{at}:00Z", fresh=True)
    return paused, lifted


def pause_at(m, at, committed=None, event="PAUSED", reason=f"judge_violation:{K_OP}"):
    """One PAUSED (or RETIRED) event dated `at`, committed at `committed` (default `at`); returns its commit."""
    _, sha = plant(m, [(event, reason, f"{DAY}T{at}:00Z")], f"{DAY}T{committed or at}:00Z")
    return sha


def set_pins(m, **kw):
    """The owner changes analyst/PINS.json (a key set to None is removed)."""
    p = os.path.join(m.repo.path, "analyst", "PINS.json")
    pins = json.loads(open(p, encoding="utf-8").read())
    for k, v in kw.items():
        if v is None:
            pins.pop(k, None)
        else:
            pins[k] = v
    m.repo.write("analyst/PINS.json", record_form(pins))
    m.repo.commit("owner: pins", T(f"{DAY}T00:01:00Z"))


# ---------------------------------------------------------------- controls
@pytest.mark.parametrize("fire", ["13:50", "14:00"])
def test_a_run_is_found_without_a_pause(world, fire):
    assert found(world(fire).judge())


# ---------------------------------------------------------------- the end of an interval: V(RESUMED)
@pytest.mark.parametrize("seen", [None, "13:55"])
def test_the_reviewers_probe_turned_round(world, seen):
    """Register build list (fifth review, J-5): a lift at 13:48 with no inbox main entry holding its commit gives no
    finding for the 13:50 fire, and none with the mirror's entry at 13:55."""
    m = world("13:50")
    _, lifted = lift(m, "13:48")
    if seen:
        mirror(m, lifted, seen)
    assert not found(m.judge())


def test_an_entry_before_the_run_gives_the_finding(world):
    """Register build list: an entry at 13:49 for the 13:50 run gives the finding (inbox main showed calls enabled from
    13:49, the whole time the run's `start` could have read it)."""
    m = world("13:50")
    _, lifted = lift(m, "13:48")
    mirror(m, lifted, "13:49")
    assert found(m.judge())


def test_an_interval_that_ends_at_created_utc_does_not_meet_the_run(world):
    """'Ends after created_utc' is strict: inbox main held the lift from 13:50, the run's own created_utc."""
    m = world("13:50")
    _, lifted = lift(m, "13:48")
    mirror(m, lifted, "13:50")
    assert found(m.judge())


@pytest.mark.parametrize("fire,expect", [
    ("13:50", False),       # the fire read STATE.json before the mirror carried the lift; refused
    ("14:00", True),        # the fire came after the mirror push
])
def test_the_lift_counts_from_the_mirror_push_that_carried_it(world, fire, expect):
    """A lift dated 13:48 (the settle run's t0) that inbox main got at 13:55."""
    m = world(fire)
    _, lifted = lift(m, "13:48")
    mirror(m, lifted, "13:55")
    assert found(m.judge()) is expect


@pytest.mark.parametrize("fire,at", [("13:50", "13:48"), ("14:00", "13:48"), ("13:50", "13:25"), ("14:00", "13:25"),
                                     ("13:50", "13:00"), ("14:00", "13:00")])
def test_with_no_mirror_entry_known_the_interval_stays_open(world, fire, at):
    """No inbox main entry holds the lift's commit, while `git ls-remote` shows inbox main holding it (the entry aged
    out, or the activity listing lags): V(RESUMED) is none and the interval stays open. Inverted from
    49c655f's test_with_no_mirror_entry_known_the_lift_counts_30_minutes_after_its_event: 'A fixed grace after the
    RESUMED utc, used when no entry is known, was considered and not adopted' (R-AN-67, decision 33)."""
    m = world(fire)
    lift(m, at)
    assert not found(m.judge())


def test_a_run_left_out_is_judged_again_once_the_entry_is_known(world):
    """R-AN-67: 'a run left out then is judged again once the entry is known'. The verifier's round-6 control: a lift
    at 13:25 whose mirror push (13:30) becomes known."""
    m = world("14:00")
    _, lifted = lift(m, "13:25")
    assert not found(m.judge())
    mirror(m, lifted, "13:30")
    assert found(m.judge())


@pytest.mark.parametrize("fire,expect", [("13:50", False), ("14:00", True)])
def test_the_first_mirror_push_whose_after_descends_from_the_lift(world, fire, expect):
    """A mirror push of an older commit (the pause's, 13:05) does not carry the lift; a push of a later commit (13:54)
    does, since its `after` has the lift's commit as an ancestor. The interval ends at 13:54: not at the event (13:00),
    not at the first main push after it (13:05), not at the lift's own entry (13:58)."""
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
    """`git ls-remote` lists inbox main at the pause's commit and no entry carries the lift: the mirror has not pushed
    it yet, so no session could have read calls enabled, though the lift is dated over an hour before the fire."""
    m = world("14:00")
    paused, _ = lift(m, "12:50")
    m.ls_main[INBOX] = paused
    assert not found(m.judge())


@pytest.mark.parametrize("fire", ["13:50", "14:00"])
def test_with_neither_the_activity_nor_ls_remote_read_the_interval_stays_open(world, fire):
    """No activity entry known (this run's read failed, no evidence rows) and no ls-remote read of the inbox: the
    interval runs from the PAUSED event's utc (V(PAUSED) none) and stays open. Inverted from 49c655f, whose fallback
    grace ended it at 13:55."""
    m = world(fire)
    lift(m, "13:25")
    api = FakeGitHub(m.api_data(), repo=GA, fail={"repo_activity", f"ls_remote:{INBOX}"})
    assert not found(m.judge(api=api))


def evidence_row(sha, at, aid):
    row = {k: "" for k in EVIDENCE_HEADER}
    row.update(judge_utc=f"{DAY}T20:00:00Z", source="inbox_activity", ref="refs/heads/main", push_after=sha,
               activity_id=aid, activity_type="push", activity_utc=f"{DAY}T{at}:00Z", actor=OWNER)
    return row


@pytest.mark.parametrize("fire,expect", [("13:50", False), ("14:00", True)])
def test_entries_known_from_the_evidence_rows_date_the_interval(world, fire, expect):
    """This run's activity read failed; the judge's own `inbox_activity` rows (R-AN-69) still date the mirror pushes
    that carried the pause (00:10) and the lift (13:58)."""
    m = world(fire)
    paused, lifted = lift(m, "13:00", pause_seen=None)
    rows = [evidence_row(paused, "00:10", "79998"), evidence_row(lifted, "13:58", "79999")]
    api = FakeGitHub(m.api_data(), repo=GA, fail={"repo_activity"})
    assert found(m.judge(api=api, evidence=rows)) is expect


@pytest.mark.parametrize("fire", ["13:50", "14:00"])
def test_a_mirror_entry_before_inbox_from_does_not_count(world, fire):
    """Inbox activity entries count only at or after PINS.inbox_from_utc (R-AN-67). An entry holding the lift dated
    before it is ignored (counted, it would end the interval at once); no other entry holds the lift, so it stays
    open."""
    m = world(fire)
    _, lifted = lift(m, "13:25")
    m.inbox_activity("refs/heads/main", lifted, T(m.inbox_from) - dt.timedelta(minutes=1), OWNER, "push")
    assert not found(m.judge())


def test_v_is_the_entrys_own_timestamp(world):
    """V(e) is the timestamp of the earliest entry holding e's commit (R-AN-67); the register sets no lower bound at
    the event's utc. An entry at 13:40 holding a lift dated 13:52 (only clocks that disagree could give one) ends the
    interval at 13:40, so the 13:50 fire is judged. Inverted from 49c655f's
    test_a_mirror_entry_dated_before_the_event_never_shortens_the_interval."""
    m = world("13:50")
    _, lifted = lift(m, "13:52")
    mirror(m, lifted, "13:40")
    assert found(m.judge())


@pytest.mark.parametrize("fire,expect", [("13:50", False), ("14:00", True)])
def test_a_clear_reaches_the_sessions_through_the_mirror_too(world, fire, expect):
    """A RESUMED `clear:` (an owner clear, R-AN-55 step 1) lands in a settle commit as a lift does."""
    m = world(fire)
    _, lifted = lift(m, "13:48", reason="clear:model:r-1")
    mirror(m, lifted, "13:55")
    assert found(m.judge()) is expect


@pytest.mark.parametrize("base,fire,expect", [
    ("lift", "13:50", False),      # the merged side commit descends from the lift: the interval ends at 13:54
    ("lift", "14:00", True),
    ("pause", "13:50", False),     # it branched from the pause's commit: no push carried the lift, the interval is open
    ("pause", "14:00", False),
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


def test_an_entry_whose_after_is_not_on_gold_analyst_main_gives_no_time(world):
    """Register build list: 'an entry whose `after` is not on gold-analyst main does not' count (A12
    `inbox_main_foreign`). A commit built on the lift but never on gold-analyst main, pushed to inbox main at 13:49:
    counted, it would end the interval before the 13:50 fire; the mirror's own push of the lift (13:55) ends it."""
    m = world("13:50")
    _, lifted = lift(m, "13:48")
    m.repo("checkout", "-q", "-b", "foreign", lifted)
    foreign = m.repo.commit("a commit off gold-analyst main", T(f"{DAY}T13:48:30Z"))
    m.repo("checkout", "-q", "main")
    mirror(m, foreign, "13:49")
    mirror(m, lifted, "13:55")
    res = m.judge()
    assert any(f.code == "inbox_main_foreign" and f.commit == foreign for f in res.findings.items)
    assert not found(res)


@pytest.mark.parametrize("fresh,expect", [(True, True), (False, False)])
def test_a_mirror_push_newer_than_the_clone_counts_after_the_fresh_fetch(world, fresh, expect):
    """R-AN-67: the `after` is tested 'in the judge's gold-analyst clone after its one fresh fetch of main'. Inbox main
    went to a commit after the lift (13:52) that the clone's main lacks but gold-analyst main has (the fresh fetch
    returns it); its push at 13:55 ends the interval, so the 14:00 run is judged. Without the fresh fetch that `after`
    is not known to be on gold-analyst main, gives no time, and the interval stays open."""
    m = world("14:00")
    _, lifted = lift(m, "13:48")
    m.repo("checkout", "-q", "-b", "newer", lifted)
    newer = m.repo.commit("analyst-merge (after the clone's main)", T(f"{DAY}T13:52:00Z"))
    m.repo("checkout", "-q", "main")
    mirror(m, newer, "13:55")
    assert found(m.judge(fresh_main=(lambda: newer) if fresh else None)) is expect


# ---------------------------------------------------------------- the start of an interval and the range rule
def test_a_run_created_before_a_pause_reached_inbox_main_in_its_start_interval(world):
    """Register build list: 'a run created 20 minutes before a pause reached inbox main, inside the same start
    interval, gives no finding'. The verifier's round-6 case: run 13:50; settle pauses at 14:05; the mirror pushes it
    at 14:10; the run's `start` (any time up to 14:15) could have read calls disabled and been refused."""
    m = world("13:50")
    sha = pause_at(m, "14:05")
    mirror(m, sha, "14:10")
    assert not found(m.judge())


def test_a_pause_that_reached_inbox_main_after_the_start_interval_does_not_excuse(world):
    """Register build list: '... and one whose start interval ended before it does'. The pause is dated 14:05, inside
    the start interval, but inbox main held it only from 14:20: the interval starts at V(PAUSED), after 14:15."""
    m = world("13:50")
    sha = pause_at(m, "14:05")
    mirror(m, sha, "14:20")
    assert found(m.judge())


def test_a_pause_counts_from_its_time_on_inbox_main_not_its_utc(world):
    """A pause dated 13:55 that inbox main held only from 14:20: the 14:00 run's `start` read calls enabled all
    through its start interval (to 14:15), so the run is judged."""
    m = world("14:00")
    sha = pause_at(m, "13:55", committed="13:56")
    mirror(m, sha, "14:20")
    assert found(m.judge())


@pytest.mark.parametrize("fire", ["13:50", "14:00"])
def test_a_pause_dated_inside_the_start_interval_excuses_the_run(world, fire):
    """No entry holds the pause, so its interval starts at its utc, 13:55, and meets [created_utc, 14:15] for both
    runs. Inverted from 49c655f's test_the_pause_start_is_unchanged, which judged the 13:50 run (the verifier's
    round-6 case: the run's `start` could have read inbox main after 13:55)."""
    m = world(fire)
    pause_at(m, "13:55", committed="13:56")
    assert not found(m.judge())


@pytest.mark.parametrize("at,expect", [("14:15", False), ("14:16", True)])
def test_the_range_ends_at_deadline_minus_t_run(world, at, expect):
    """An interval meets the range when it starts at or before deadline_utc - T_run (14:15 here)."""
    m = world("13:50")
    pause_at(m, at)
    assert found(m.judge()) is expect


@pytest.mark.parametrize("fire,at,seen,expect", [
    ("14:00", "13:55", "14:20", True),      # retired at 13:55, on inbox main only from 14:20: after the start interval
    ("14:00", "13:55", "13:58", False),
    ("13:50", "14:10", None, False),        # no entry: from its utc, 14:10, inside the 13:50 run's start interval
])
def test_a_retirement_counts_from_its_time_on_inbox_main(world, fire, at, seen, expect):
    """After RETIRED, calls are disabled from V(RETIRED), else its utc, on."""
    m = world(fire)
    sha = pause_at(m, at, event="RETIRED", reason="violation")
    if seen:
        mirror(m, sha, seen)
    assert found(m.judge()) is expect


# ---------------------------------------------------------------- where the event utcs are kept
@pytest.mark.parametrize("fire,case,expect", [
    ("13:50", "lift", True),     # pause 00:00 to lift 13:25, dated by the events: the run is judged (no grace)
    ("14:00", "lift", True),
    ("13:50", "pause", False),   # a pause dated 14:05 still meets the 13:50 run's range [13:50, 14:15]
])
def test_without_the_inbox_pin_the_event_utcs_are_kept(world, fire, case, expect):
    """Without PINS.inbox_repo (J-D20) sessions read gold-analyst itself, and the event utcs are kept (R-AN-67); the
    range rule still applies. 49c655f added its 30-minute grace here, which excused the 13:50 run."""
    m = world(fire)
    set_pins(m, inbox_repo=None)
    if case == "lift":
        lift(m, "13:25")
    else:
        pause_at(m, "14:05")
    assert found(m.judge()) is expect


@pytest.mark.parametrize("at,expect", [("13:25", True), ("13:35", False)])
def test_an_event_dated_before_inbox_from_keeps_its_utc(world, at, expect):
    """PINS.inbox_from_utc moved to 13:30. A lift dated 13:25 (before it) ends the interval at its utc, though a counting
    mirror entry (13:55) holds it: the 13:50 run is judged. A lift dated 13:35 ends at V, 13:55: the run is not."""
    m = world("13:50")
    set_pins(m, inbox_from_utc=f"{DAY}T13:30:00Z")
    _, lifted = lift(m, at, pause_seen=None)
    mirror(m, lifted, "13:55")
    assert found(m.judge()) is expect


def test_a_pause_inbox_main_never_showed_excuses_nothing(world):
    """The mirror ran late and pushed the pause and its lift in one push (13:55): V(PAUSED) = V(RESUMED), so inbox main
    never showed calls disabled and the 13:50 run's `start` read them enabled (decision 33: 'inbox main showed calls
    disabled at any time'). An empty interval meets no range (judge decision J-D34)."""
    m = world("13:50")
    _, lifted = lift(m, "13:48", pause_seen=None)
    mirror(m, lifted, "13:55")
    assert found(m.judge())
