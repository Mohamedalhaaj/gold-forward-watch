"""The analyst judge's checks A0-A13 (prereg §8 as amended by v0.5 M7 and v0.6; IMPLEMENTATION_REGISTER R-AN-66..R-AN-70
with amendments §16.18 A6, the agent inbox, and A7, the session guard).

A0 is the judge's own input check (a shallow clone, an unreachable API, an unreadable source store or hour file, a
PINS.json without the inbox pins): WARNING, never SOUND, never latched. The one A0 VIOLATION, `inbox_blind` (second
review of A6, SEC-3; rewritten in the fourth review, J-3: no complete read of the inbox's activity for more than 24 h
and at least two failed runs after it, keyed by its episode), holds the verdict at VIOLATION while it lasts, and is
never latched either. A1-A12 follow R-AN-67's table; A12 is the repository boundary of A6 (gold-analyst's refs, tags
and runs; the inbox's identity, main, refs, rewrites, runs and rules; the session probes; the owner's inbox checks;
the mirror's lag; after the second review the App's repository list, the routines' connectors and a flood of probe
branches; after the fourth review the inbox's deploy keys and Actions switch, `inbox_config`). Since the fourth review
every VIOLATION key names its incident, and A11 checks the analyst's pause, lift and retirement events against the
pause rule of R-AN-55.

A13 (§16.18 A7, R-AN-85, R-AN-86) is the session guard: each run's tool calls in the owner's run-log export, classified
by the guard's string rules as `jlib/sessionguard.py` re-implements them from the register (the analyst's `guard.py`
is never read, parsed or run; A11 hashes it against FROZEN_ANALYST.sha256), and the guard's files at gold-analyst
main's head (`guard_config`). Since A7, A11 also holds that a verdict older than one the analyst already used is not
fresh (decision 15), and A12 reads the owner's security-log events (`inbox_hook`, detection 2).

Since A6 the agent's pushes are entries of the inbox's activity log (PINS.inbox_repo), counted only at or after
PINS.inbox_from_utc. Without the inbox pins (a gold-analyst main from before A6) the judge reads pushes from
gold-analyst's own log as before, and A0 `inbox_unpinned` keeps the verdict from SOUND.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import re
from dataclasses import dataclass, field

from . import derive, sessionguard, settle, stats, td, ticks, watch
from .clock import (HALF, MACRO_PATH, OPS_PATH, Events, Holidays, Window, add_months_12, check_grid, iso_week,
                    macro_problems, model_to_utc, parse_call_id, scheduled_checks, tday, to_server, windows_between)
from .common import (UTC, VIOLATION, ZERO64, Findings, compact_form, fmt_utc, is_day, is_utc, load_json_bytes,
                     norm_api_time, num_exact, parse_utc, price_eq, record_form, rel_eq, safe_detail, sha256_bytes,
                     sha256_compact)
from . import config
from .context import (SCHEMA_V2, SCHEMA_V3, SCHEMA_V4, SCHEMAS as CONTEXT_SCHEMAS, compare_context, cross_detail,
                      is_trading_hour, rebuild_context, td_cross_check)
from .m1 import DaysTable, Store

EPROC_SHA256 = "ee8d456ae3b5ddd1112bad92d12fffa95d2b12e0559335233c6a9b3a68067973"
BOT_LOGIN = "github-actions[bot]"
PREFIX = {"live": "analyst/", "canary": "analyst/canary/"}
# §16.18 A14 (R-AN-33): W1b, W2b and the trigger windows T<hhmm> too
CALL_ID_RE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}_(?:W[12]b?|T(?:[01][0-9]|2[0-3])(?:00|30))"
TERMINAL_STATUSES = {"called", "stay_out", "no_call:refusal", "no_call:invalid", "no_call:data", "no_call:d_ref",
                     "no_call:late", "no_call:run", "missed:trigger", "missed:push", "skipped:holiday",
                     "skipped:trade_open", "skipped:day_cap"}          # §16.18 A14 (R-AN-36): the closer's two
GATED = ("skipped:trade_open", "skipped:day_cap")
CALL_STATUSES = {"called", "stay_out", "no_call:data", "no_call:d_ref", "no_call:invalid", "no_call:refusal"}
WITNESS_VIOLATION = {"agent_scope", "rewrite", "invalid_content", "attempt_cap"}
WITNESS_WARNING = {"mode", "attempt_n", "window_closed", "no_settled", "lesson_cap", "not_saturday", "incomplete_week",
                   "version", "week_done", "window_order"}     # §16.18 A14 (R-AN-33): window_order
H = dt.timedelta(hours=1)
COMPLETENESS_GRACE = dt.timedelta(hours=36)   # judge decision J-D3: after deadline + 20 min
COMMENT_GRACE = dt.timedelta(hours=24)
PUSH_GRACE = dt.timedelta(hours=24)
SETTLE_GRACE = dt.timedelta(hours=36)

# Path classes (R-AN-2, R-AN-59).
_CREATE_ONLY = re.compile(
    r"^analyst/(canary/)?(attempts|calls|lessons|witness|terminal|settled|twins|revisions|state)/[^/]+$"
    r"|^analyst/(canary/)?playbooks/v[1-9][0-9]*\.md$"
    r"|^analyst/(runs|usage)/[^/]+\.json$"
    r"|^analyst/canary/checks/[^/]+$")
_WRITE_ONCE = re.compile(r"^analyst/START(_[^/]+)?\.json$|^mirror/system/raw/.+\.bi5$")
APPEND_ONLY = {"mirror/system/days.csv", "mirror/system/forecasts_slots.csv", "mirror/exports.csv",
               "analyst/ADJUDICATIONS.csv", "analyst/ops_changes.csv", "reports/judge_analyst/evidence.csv",
               "reports/judge_analyst/FINDINGS.csv", "reports/judge_analyst/VERDICTS.csv",
               "reports/judge_analyst/ADJUDICATIONS.csv", "reports/judge_analyst/hours.csv"}

EVIDENCE_HEADER = ["judge_utc", "source", "ref", "push_after", "activity_id", "activity_type", "activity_utc", "actor",
                   "run_id", "run_attempt", "run_event", "run_created_utc", "comment_id", "comment_created_utc",
                   "comment_body_sha256"]

# ---------------------------------------------------------------- the agent inbox (register §16.18 A6)
ANALYST_REF = "refs/heads/claude/analyst-"     # R-AN-31/32: the pushes analyst-merge processes
PROBE_REF = "refs/heads/claude/probe-"         # R-AN-84: probe pushes, never read by analyst-merge
WF = ".github/workflows/"
# R-AN-75 item 4: the only (workflow path, event) pairs a gold-analyst run may have from PINS.inbox_from_utc on.
TRIGGERS = {WF + "analyst-merge.yml": {"schedule", "workflow_dispatch"},
            WF + "analyst-settle.yml": {"push", "schedule", "workflow_dispatch"},
            WF + "analyst-deploy.yml": {"workflow_dispatch", "schedule"},
            WF + "analyst-track.yml": {"workflow_dispatch"},
            WF + "analyst-canary-poll.yml": {"schedule", "workflow_dispatch"},
            WF + "analyst-inbox-mirror.yml": {"push", "workflow_run", "schedule", "workflow_dispatch"}}
# R-AN-67 A6 witness_run_trigger: the runs that may witness (main's merge and settle runs).
WITNESS_TRIGGERS = {WF + "analyst-merge.yml": {"schedule", "workflow_dispatch"},
                    WF + "analyst-settle.yml": {"push", "schedule", "workflow_dispatch"}}
WITNESS_EVENTS = set().union(*WITNESS_TRIGGERS.values())
# R-AN-67 A12 inbox_rules: the rule types GitHub must report for each branch name queried (R-AN-75 items 2, 3).
INBOX_RULES = {"main": {"update", "deletion", "non_fast_forward"}, "claude/x": {"deletion", "non_fast_forward"},
               "x": {"creation"}}
GA_RULES = {"claude/x": {"creation"}}
STALE = dt.timedelta(minutes=30)               # A12 inbox_stale (R-AN-83)
NEVER = dt.datetime.max.replace(tzinfo=UTC)    # the open end of A10's pause intervals (R-AN-67, decision 33)
INBOX_CHECK_TYPES = {"checked_utc": (str,), "hooks": (int,), "deploy_keys": (int,), "actions_enabled": (bool,),
                     "security_log_hook_events": (int, type(None))}
# The second review of A6 (2026-10-23, register §16.18 A6 decisions 20-23; R-AN-60, R-AN-61, R-AN-66, R-AN-67).
APP_FORBIDDEN = {"gold-analyst", "gold-forward-watch", "xauusd-quant"}   # A12 app_scope (SEC-1): repository names
ROUTINE_CONFIG = "analyst/ROUTINE_CONFIG.json"                          # A12 routine_connectors (SEC-2)
CONNECTOR_LISTS = ("mcp_connections", "enabled_plugins")                # each must be [] in every routine's raw
PROBE_NAME = re.compile(rf"refs/heads/claude/probe-(c3|del|wf|result)-({CALL_ID_RE}|p[0-9]{{8}}T[0-9]{{6}}Z)")
PROBE_DAY_CAP = 40                             # A12 probe_flood (SEC-3): probe branch creations in one UTC day
BLIND = dt.timedelta(hours=24)                 # A0 inbox_blind (SEC-3): age of the last complete activity read
BLIND_RUNS = 2                                 # A0 inbox_blind (fourth review, J-3): failed judge runs after it
# The fourth review of A6 (2026-10-23, register §16.18 A6 decisions 24-32; R-AN-55, R-AN-67): the operational A12
# codes. With every A0 key and every `system_error:` entry they pause the analyst while the verdict carries them and
# never retire it; every other VIOLATION key is an integrity key.
OPERATIONAL_A12 = {"probe_failed", "app_scope", "routine_connectors", "inbox_identity", "inbox_config"}
# §16.18 A7 (R-AN-55, R-AN-67, R-AN-86): the guard not acting, or its files wrong, is the system's fault; (third review
# of A7, decisions 21 and 22) so are a routine in a claude.ai project and a harness that may not keep the guard closed.
OPERATIONAL_A13 = {"guard_not_enforced", "guard_config", "routine_project", "cc_version_below", "cc_version_unknown"}
# §16.18 A14 (R-AN-67): check A14's operational keys; `not_triggered`, `trade_open`, `day_cap` and `wake_record` are
# integrity keys (the first three stop the canary at once, R-AN-75 item 1)
OPERATIONAL_A14 = {"skipped_wrong", "a14_from"}
OPERATIONAL = {"A12": OPERATIONAL_A12, "A13": OPERATIONAL_A13, "A14": OPERATIONAL_A14}
WAKE_ROUTINES = ("analyst-wake", "analyst-w1", "analyst-w2")   # A14-D12: any of them can reach a new window
C20_PATH = "analyst/canary/checks/C20.json"     # R-AN-74 C20: the probe session's root, when a run log has none
SECURITY_LOG_FILTER = "repo:{} action:hook"     # R-AN-60 (A7, detection 2), with PINS.inbox_repo
# The third review of A7 (2026-10-24, register §16.18 A7 decisions 21 and 22; R-AN-25, R-AN-60, R-AN-61, R-AN-67,
# R-AN-85). A13 `cc_version_below` and `cc_version_unknown`: the session records of these folders at main's head.
CC_RECORD_FOLDERS = ("analyst/attempts/", "analyst/calls/", "analyst/canary/attempts/", "analyst/canary/calls/")
_SHA40 = re.compile(r"[0-9a-fA-F]{40}")


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _zero(sha) -> bool:
    return not sha or set(sha) == {"0"}


def _id_key(aid: str):
    return (0, int(aid), "") if aid.isdigit() else (1, 0, aid)


FIRST_SEEN_SLACK = dt.timedelta(minutes=10)   # R-AN-70: a verdict dated up to 10 min after a settle run counts


def operational(key: str) -> bool:
    """R-AN-55, R-AN-67 (fourth review of A6, J-4): a `violation_keys` entry that starts with `A0|` or
    `system_error:`, or whose check and code are A12 `probe_failed`, `app_scope`, `routine_connectors`,
    `inbox_identity` or `inbox_config`; (§16.18 A7) or A13 `guard_not_enforced` or `guard_config`; (third review of
    A7) or A13 `routine_project`, `cc_version_below` or `cc_version_unknown`."""
    if key.startswith(("A0|", "system_error:")):
        return True
    parts = key.split("|")
    return len(parts) >= 2 and parts[1] in OPERATIONAL.get(parts[0], ())


def resumed_subject(reason):
    """(`clear` | `lifted`, subject) of a RESUMED event's reason, or (None, None) (R-AN-56: the subject of a RESUMED
    event is its reason after the first `clear:` or `lifted:`)."""
    r = str(reason or "")
    for kind in ("clear", "lifted"):
        if r.startswith(kind + ":"):
            return kind, r[len(kind) + 1:]
    return None, None


def _utc_or_none(s):
    try:
        return parse_utc(s)
    except (TypeError, ValueError):
        return None


# R-AN-84: an outcome its probe's "Pass iff" column fails, whatever the record's own pass flag says (the session
# writes both). The immediate-stop outcomes are among them. Outcomes of `error`/`none`, the measured probes and
# `workflow_push` (judged by A12 inbox_runs) are never a failure here.
_ACC = ("accepted",)
PROBE_FAILS = {
    "net.google": lambda o: _int(o) and 200 <= o <= 399,
    "net.raw_public": lambda o: _int(o) and o == 200,
    "rest.ga": lambda o: o == "ok", "rest.gfw": lambda o: o == "ok",
    "rest.hooks": lambda o: _int(o) and o > 0,
    "git.ls_remote_gfw": lambda o: o in _ACC, "git.ls_remote_gfw_proxy": lambda o: o in _ACC,
    # git.ls_remote_public and _proxy are measured since §16.18 A8 (public-repository reads; the guard is the control)
    "push_main": lambda o: o in _ACC, "force_main": lambda o: o in _ACC, "tag_push": lambda o: o in _ACC,
    "other_branch_push": lambda o: o in _ACC, "branch_delete": lambda o: o in _ACC,
    "rest.force_main": lambda o: o == "ok", "rest.tag_create": lambda o: o == "ok",
    "rest.delete_branch": lambda o: o == "ok",
    "ga_push": lambda o: o in ("accepted", "refused_rule"), "ga_push_proxy": lambda o: o in ("accepted", "refused_rule"),
    "admin_probe": lambda o: o == "ok",
}
# §16.18 A9 (R-AN-84 as amended): `net.twelvedata`, the data control, passes only on 200; in a canary `context`
# its outcomes 0, −2, 429 and 500-599 (an outage, no request, the minute's credits) are null. `net.dukascopy` is
# expected refused in both kinds: 200 fails. Judge decision J-D44: a record without a `net.twelvedata` outcome was
# written by the pre-A9 code, whose `net.dukascopy` passed on 200, so the A9 rule of `net.dukascopy` applies only
# to a record that has a `net.twelvedata` outcome.
DUKASCOPY_TAG = ("refs/tags/analyst-dukascopy-v0.6", "79b9247901f15ee40d14d0f33cc8001f89bf31ce")   # A12 ga_tag (A9)


def _td_canary_null(o) -> bool:
    return _int(o) and (o in (0, -2, 429) or 500 <= o <= 599)


def probe_fails(outcomes: dict, canary: bool) -> list:
    """The probes whose outcome its "Pass iff" column fails (R-AN-84; PROBE_FAILS and the A9 rules)."""
    failed = [k for k, f in PROBE_FAILS.items() if k in outcomes and f(outcomes[k])]
    if "net.twelvedata" in outcomes:
        o = outcomes["net.twelvedata"]
        if o != 200 and not (canary and (_td_canary_null(o) or not _int(o))):
            failed.append("net.twelvedata")
        if outcomes.get("net.dukascopy") == 200:
            failed.append("net.dukascopy")
    return sorted(failed)


def allow_patterns(prefix: str):
    p = re.escape(prefix)
    return {
        "attempt": re.compile(rf"{p}attempts/(({CALL_ID_RE})|lesson-({CALL_ID_RE})|revision-v[1-9][0-9]*)_[12]\.json"),
        "call": re.compile(rf"{p}calls/{CALL_ID_RE}\.json"),
        "lesson": re.compile(rf"{p}lessons/{CALL_ID_RE}\.json"),
        "revision": re.compile(rf"{p}playbooks/v[1-9][0-9]*\.md"),
    }


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def classify_path(path: str):
    """(mode, kind) of an allowlisted agent path, or None (R-AN-33; clarification A3 of 2026-10-23: the whole path
    must match one pattern and hold no control character)."""
    if path.startswith(".github/") or _CONTROL.search(path):
        return None
    for mode in ("canary", "live"):
        for kind, rx in allow_patterns(PREFIX[mode]).items():
            if rx.fullmatch(path):
                return mode, kind
    return None


def diff_conforms(changes) -> bool:
    return len(changes) == 1 and changes[0][0] == "A" and classify_path(changes[0][1]) is not None


@dataclass
class Rec:
    path: str
    raw: bytes
    rec: object
    commit: str = "-"


@dataclass
class Result:
    findings: Findings
    head: str
    evidence_new: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


class Judge:
    def __init__(self, git, now_utc: str, api=None, hours=None, store_git=None, fetch_commit=None,
                 evidence_rows=None, prev_anchor=None, judge_manifest_ok=True, events=None, fresh_main=None,
                 prev_judge_utc=None, judge_adjudications=None, judge_findings=None, a12_commit="config",
                 a14_commit="config", m30=None, halves=None):
        """fetch_commit(sha, ref) brings a pushed commit from the inbox into the clone (data only; --fetch-pushes);
        fresh_main() fetches gold-analyst main once more and returns its sha (or None); prev_judge_utc is the newest
        judge_utc of VERDICTS.csv (the runs day range, R-AN-66); judge_adjudications are the rows of the judge's own
        ADJUDICATIONS.csv (R-AN-70; the A11 check of a `lifted:` resume of a latched key, fourth review of A6);
        judge_findings are the rows of its FINDINGS.csv before this run (the A11 check of a retirement by time,
        sixth review of A6, R6-2). a12_commit (§16.18 A12, R-AN-23): the pinned A12 build commit; by default
        config.A12_BUILD_COMMIT. (§16.18 A14) a14_commit: the pinned A14 build commit (config.A14_BUILD_COMMIT);
        m30: the judge's own Twelve Data 30-minute fetch (watch.M30Source, R-AN-66), or None; halves: the Dukascopy
        half-hour view (sources.HalfSource) for the cross-check of a trigger's bars (R-AN-68), or None."""
        self.git = git
        self.a12_commit = config.A12_BUILD_COMMIT if a12_commit == "config" else a12_commit
        self.a14_commit = config.A14_BUILD_COMMIT if a14_commit == "config" else a14_commit
        self.m30 = m30
        self.halves = halves
        self._wd = {}
        self.term_by = {"canary": {}, "live": {}}
        self.now_s = now_utc
        self.now = parse_utc(now_utc)
        self.api = api
        self.hours = hours
        self.store_git = store_git
        self.fetch_commit = fetch_commit
        self.evidence_rows = evidence_rows or []
        self.prev_anchor = prev_anchor
        self.judge_manifest_ok = judge_manifest_ok
        self.events = events or Events.judge_copies()
        self.fresh_main = fresh_main
        self.prev_judge_utc = prev_judge_utc
        self.judge_adjudications = judge_adjudications or []
        self.judge_findings = judge_findings or []
        self._mode_at = {}
        self._floor = None
        self._fresh = False
        self._diffs = {}
        self._guarded = {}
        self._macro_seen = set()
        self.F = Findings()
        self.summary = {}
        self.evidence_new = []

    # ================================================================ helpers
    def bytes_at_head(self, path):
        return self.git.show(self.head, path)

    def json_at_head(self, path):
        b = self.bytes_at_head(path)
        if b is None:
            return None
        try:
            return load_json_bytes(b)
        except Exception:  # noqa: BLE001
            return None

    def records(self, folder: str):
        out = {}
        for p in self.git.ls_tree(self.head, folder):
            if p[len(folder):].count("/"):
                continue
            b = self.bytes_at_head(p)
            try:
                r = load_json_bytes(b) if p.endswith(".json") else None
            except Exception:  # noqa: BLE001
                r = None
            out[p] = Rec(p, b, r, self.first_add.get(p, "-"))
        return out

    def commit_of(self, path):
        return self.first_add.get(path, "-")

    # ================================================================ run
    def run(self) -> Result:
        self.head = self.git.head()
        self.log = self.git.first_parent_log(self.head)
        self.first_add = {}
        for sha, _parent, changes in self.log:
            for st, p in changes:
                if st.startswith("A") and p not in self.first_add:
                    self.first_add[p] = sha
        if self.git.is_shallow():
            self.F.w("A0", "shallow_clone", "refs/heads/main", "-", "a full clone is required (R-AN-66)")
        if not self.judge_manifest_ok:
            self.F.w("A0", "judge_manifest", "judge_analyst/FROZEN_JUDGE_ANALYST.sha256", "-",
                     "the judge's files differ from its own manifest")
        self.mode_cfg = self.json_at_head("analyst/MODE.json")
        self.params = self.json_at_head("analyst/PARAMS.json") or {}
        self.pins = self.json_at_head("analyst/PINS.json") or {}
        if not isinstance(self.mode_cfg, dict):
            self.F.v("A8", "mode_file", "analyst/MODE.json", "-", "MODE.json unreadable: expected windows unknown")
            self.mode_cfg = {}
        self.holidays = Holidays(self.bytes_at_head("analyst/tables/holidays.csv"))
        self.a14_day = self.a14_from_value()
        self.load_api()
        self.safe("inbox_reads", self.load_inbox)
        self.wit = []
        self.wit_by_seq = {}
        self.windows = {"canary": [], "live": []}
        self.terminal_info = {}
        self.first_day = None
        self.overlay = {}
        self.safe("witnesses", self.load_witnesses)
        self.safe("witness_runs", self.check_witness_runs)
        self.safe("comments", self.check_comments)
        self.safe("pushes", self.check_pushes)
        for mode in ("canary", "live"):
            self.safe(f"mode_{mode}", self.check_mode, mode)
        self.safe("watching", self.check_watching)
        self.safe("a14_from", self.check_a14_from)
        self.safe("start", self.check_start)
        self.safe("runs_exports", self.check_runs_exports)
        self.safe("routine_config", self.check_routine_config)
        self.safe("routine_project", self.check_routine_project_config)
        self.safe("probes", self.check_probes)
        self.safe("boundary", self.check_boundary)
        self.safe("settlement_state", self.check_settlement_and_state)
        self.safe("mirror_source", self.check_mirror_source)
        self.safe("frozen", self.check_frozen)
        self.safe("guard_config", self.check_guard_config)
        self.safe("cc_versions", self.check_cc_versions)
        self.safe("history", self.check_history)
        self.summary["head"] = self.head
        return Result(self.F, self.head, self.evidence_new, self.summary)

    def safe(self, name, fn, *args):
        """Run one check; an unexpected exception (a malformed record the code did not foresee) becomes an A0 WARNING
        naming the check, so the run still ends with a verdict that is never SOUND."""
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001
            self.F.w("A0", "check_crashed", f"judge/{name}", "-", safe_detail(type(e).__name__))
            return None

    # ================================================================ API and evidence (R-AN-66, R-AN-69)
    def load_api(self):
        self.activity = []
        self.comments = []
        self.runs = {}
        self.api_ok = False
        if self.api is not None:
            try:
                self.activity = self.api.activity()
                issue = self.pins.get("witness_issue")
                self.comments = self.api.issue_comments(issue) if isinstance(issue, int) else []
                self.api_ok = True
            except Exception as e:  # noqa: BLE001
                self.F.w("A0", "api_unreachable", "api", "-", safe_detail(type(e).__name__))
        else:
            self.F.w("A0", "api_unreachable", "api", "-", "no API client")
        ev_act = {r["activity_id"]: r for r in self.evidence_rows if r["source"] == "activity"}
        ev_cmt = {r["comment_id"]: r for r in self.evidence_rows if r["source"] == "comment"}
        self.ev_runs = {(r["run_id"], r["run_attempt"]): r for r in self.evidence_rows if r["source"] == "run"}
        self.act_by_after = {}
        seen_ids = set()
        for r in ev_act.values():
            if r["push_after"]:
                seen_ids.add(r["activity_id"])
                self.act_by_after.setdefault(r["push_after"], []).append(
                    {"timestamp_utc": r["activity_utc"], "id": r["activity_id"], "ref": r["ref"],
                     "type": r["activity_type"], "actor": r["actor"], "source": "evidence"})
        for a in self.activity:
            aid = str(a.get("id"))
            ts = norm_api_time(a.get("timestamp"))
            actor = (a.get("actor") or {}).get("login", "")
            row = {"timestamp_utc": ts, "id": aid, "ref": a.get("ref", ""), "type": a.get("activity_type", ""),
                   "actor": actor, "source": "api"}
            if aid in ev_act and ev_act[aid]["activity_utc"] != ts:
                self.F.w("A11", "evidence_changed", f"activity/{aid}", "-", "activity timestamp differs from evidence")
            if a.get("after") and aid not in seen_ids:
                self.act_by_after.setdefault(a["after"], []).append(row)
            if aid not in ev_act:
                self.evidence_new.append(self._ev("activity", ref=a.get("ref", ""), push_after=a.get("after", ""),
                                                  activity_id=aid, activity_type=a.get("activity_type", ""),
                                                  activity_utc=ts, actor=actor))
                ev_act[aid] = self.evidence_new[-1]
        self.comment_by_id = {}
        for c in self.comments:
            cid = str(c.get("id"))
            body = c.get("body") or ""
            created = norm_api_time(c.get("created_at"))
            updated = norm_api_time(c.get("updated_at")) if c.get("updated_at") else None
            self.comment_by_id[cid] = {"body": body, "created_utc": created, "login": (c.get("user") or {}).get("login"),
                                       "sha": sha256_bytes(body.encode("utf-8")), "updated_utc": updated}
            if cid not in ev_cmt and (c.get("user") or {}).get("login") == BOT_LOGIN:
                self.evidence_new.append(self._ev("comment", comment_id=cid, comment_created_utc=created,
                                                  comment_body_sha256=sha256_bytes(body.encode("utf-8"))))
                ev_cmt[cid] = self.evidence_new[-1]
        self.ev_cmt = ev_cmt

    # ================================================================ the inbox and the boundary reads (A6)
    def load_inbox(self):
        """R-AN-66 (A6): the public reads of the inbox (repository, activity, runs, rules, refs) and of gold-analyst
        (refs, runs by day, rules). A failed read is A0 `inbox_api_unreachable` (the inbox) or `api_unreachable`
        (gold-analyst), never SOUND; the checks that need it are skipped, except the push times, which fall back to
        the judge's own `inbox_activity` evidence rows."""
        p = self.pins
        self.inbox = p.get("inbox_repo") if isinstance(p.get("inbox_repo"), str) and p.get("inbox_repo") else None
        self.inbox_id = p.get("inbox_repo_id") if _int(p.get("inbox_repo_id")) else None
        self.inbox_from = p.get("inbox_from_utc") if is_utc(p.get("inbox_from_utc")) else None
        self.ga_repo = p.get("repo") if isinstance(p.get("repo"), str) and p.get("repo") else "Mohamedalhaaj/gold-analyst"
        self.inbox_entries = []
        self.inbox_lock = {}
        self.inbox_info = self.inbox_runs = self.inbox_ls = self.ga_ls = self.ga_runs = None
        self.inbox_info_ok = self.inbox_read_ok = False
        self.inbox_rules = {}
        self.ga_rules = {}
        self.ga_ref_rows = {}
        for r in self.evidence_rows:
            if r["source"] == "ga_ref" and r["push_after"] not in self.ga_ref_rows.setdefault(r["ref"], []):
                self.ga_ref_rows[r["ref"]].append(r["push_after"])
        missing = [k for k, v in (("inbox_repo", self.inbox), ("inbox_repo_id", self.inbox_id),
                                  ("inbox_from_utc", self.inbox_from)) if v is None]
        if missing:
            self.F.w("A0", "inbox_unpinned", "analyst/PINS.json", "-",
                     safe_detail("PINS lacks", *missing, "the A6 boundary is not fully judged"))
        api_list = None
        if self.api is None:
            if self.inbox:
                self.F.w("A0", "inbox_api_unreachable", "api", "-", "no API client")
        else:
            if self.inbox:
                self.inbox_info_ok, self.inbox_info = self._read("inbox_api_unreachable", "repo_info", self.inbox)
                self.inbox_read_ok, api_list = self._read("inbox_api_unreachable", "repo_activity", self.inbox)
                ok, self.inbox_runs = self._read("inbox_api_unreachable", "runs_total", self.inbox)
                for br in INBOX_RULES:
                    ok, lst = self._read("inbox_api_unreachable", "branch_rules", self.inbox, br)
                    if ok:
                        self.inbox_rules[br] = lst
                ok, self.inbox_ls = self._read("inbox_api_unreachable", "ls_remote", self.inbox)
            ok, self.ga_ls = self._read("api_unreachable", "ls_remote", self.ga_repo)
            for br in GA_RULES:
                ok, lst = self._read("api_unreachable", "branch_rules", self.ga_repo, br)
                if ok:
                    self.ga_rules[br] = lst
            runs = []
            for d in self.run_days():
                ok, lst = self._read("api_unreachable", "runs_on_day", self.ga_repo, d.isoformat())
                if not ok:
                    runs = None
                    break
                runs.extend(lst or [])
            self.ga_runs = runs
        if self.inbox:
            self.merge_inbox_activity(api_list)
            self.check_inbox_blind()

    def check_inbox_blind(self):
        """A0 `inbox_blind` (VIOLATION; second review of A6, SEC-3; rewritten in the fourth review, J-3, decision 24):
        this run's read of the inbox's activity failed, the last complete read L is more than 24 h before this run,
        and at least two judge runs after L failed that read, this one included. Then `closer_raced` and the other
        inbox checks are blind. Any other failed read stays `inbox_api_unreachable` (WARNING): one failed run after a
        long gap, such as Sunday's, is not blindness.
        L is the newest judge_utc of an `inbox_read` row (one per complete read) or of an `inbox_activity` row (only a
        complete read writes them), else PINS.inbox_from_utc (judge decision J-D25). The failed runs are the
        `inbox_read_failed` rows (R-AN-69: one per run whose read failed, written only while PINS.inbox_repo and
        PINS.inbox_from_utc are set; a run without an API client reads nothing, so its read failed too). They are
        written with the run's other outputs, so a run that publishes nothing counts for nothing.
        Key `A0|inbox_blind|api|<L>`: each episode has its own key (J-D27 as amended)."""
        seen = [r["judge_utc"] for r in self.evidence_rows
                if r["source"] in ("inbox_read", "inbox_activity") and is_utc(r["judge_utc"])]
        if self.inbox_read_ok:
            if not any(r["source"] == "inbox_read" and r["judge_utc"] == self.now_s for r in self.evidence_rows):
                self.evidence_new.append(self._ev("inbox_read", ref=self.inbox))
            self.summary["inbox_last_complete_read_utc"] = self.now_s
            return
        last = max(seen) if seen else None
        self.summary["inbox_last_complete_read_utc"] = last or "-"
        if self.inbox_from is None:
            return
        if not any(r["source"] == "inbox_read_failed" and r["judge_utc"] == self.now_s for r in self.evidence_rows):
            self.evidence_new.append(self._ev("inbox_read_failed", ref=self.inbox))
        L = last or self.inbox_from
        failed = {r["judge_utc"] for r in self.evidence_rows if r["source"] == "inbox_read_failed" and
                  is_utc(r["judge_utc"]) and L < r["judge_utc"] <= self.now_s}
        failed.add(self.now_s)
        self.summary["inbox_failed_runs_since_last_read"] = len(failed)
        if self.now - parse_utc(L) > BLIND and len(failed) >= BLIND_RUNS:
            self.F.v("A0", "inbox_blind", "api", L,
                     safe_detail("last complete read" if last else "no complete read since inbox_from", L,
                                 f"{len(failed)} failed runs since"))

    def _read(self, code, name, *args):
        try:
            return True, getattr(self.api, name)(*args)
        except Exception as e:  # noqa: BLE001
            self.F.w("A0", code, "api", "-", safe_detail(name, type(e).__name__))
            return False, None

    def run_days(self):
        """R-AN-66 (A6): the UTC days whose gold-analyst runs are read, D0 to today. D0 is two days before the newest
        judge_utc of VERDICTS.csv, or the day of PINS.inbox_from_utc on a first run (judge decision J-D16: today's
        date when neither exists)."""
        today = self.now.date()
        if self.prev_judge_utc:
            try:
                d0 = parse_utc(self.prev_judge_utc).date() - dt.timedelta(days=2)
            except ValueError:
                d0 = today
        elif self.inbox_from:
            d0 = parse_utc(self.inbox_from).date()
        else:
            d0 = today
        d0 = min(d0, today)
        return [d0 + dt.timedelta(days=i) for i in range((today - d0).days + 1)]

    def counts(self, e) -> bool:
        """An inbox activity entry counts only with timestamp >= PINS.inbox_from_utc (R-AN-7, R-AN-67)."""
        return self.inbox_from is not None and e["ts"] is not None and e["ts"] >= self.inbox_from

    def merge_inbox_activity(self, api_list):
        """The inbox's activity: the live API list and the judge's own `inbox_activity` evidence rows (R-AN-69; an
        entry first seen keeps its first-seen timestamp), sorted by (timestamp, id). Builds the lock-time index of
        R-AN-34 (A6, one rule for the merge and the judge): for each pushed sha, the earliest counting entry on a
        `claude/analyst-*` ref; entries on other refs (probe refs, main) never give a push its time."""
        ev = {r["activity_id"]: r for r in self.evidence_rows if r["source"] == "inbox_activity"}
        entries = {}
        for aid, r in ev.items():
            entries[aid] = {"id": aid, "ref": r["ref"], "after": r["push_after"], "before": None,
                            "type": r["activity_type"], "ts": r["activity_utc"] or None, "actor": r["actor"],
                            "listed": False}
        listed = []
        for a in api_list or []:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id"))
            try:
                ts = norm_api_time(a.get("timestamp"))
            except (TypeError, ValueError):
                ts = None
            actor = (a.get("actor") or {}).get("login", "") if isinstance(a.get("actor"), dict) else ""
            e = {"id": aid, "ref": a.get("ref") or "", "after": a.get("after") or "", "before": a.get("before") or "",
                 "type": a.get("activity_type") or "", "ts": ts, "actor": actor, "listed": True}
            if ts:
                listed.append(ts)
            if aid in ev:
                if ev[aid]["activity_utc"] != ts:
                    self.F.w("A11", "evidence_changed", f"inbox/activity/{aid}", "-",
                             "inbox activity timestamp differs from evidence")
                e["ts"] = ev[aid]["activity_utc"] or ts
            else:
                self.evidence_new.append(self._ev("inbox_activity", ref=e["ref"], push_after=e["after"],
                                                  activity_id=aid, activity_type=e["type"], activity_utc=ts,
                                                  actor=actor))
                ev[aid] = self.evidence_new[-1]
            entries[aid] = e
        self.inbox_entries = sorted(entries.values(), key=lambda x: (x["ts"] or "", _id_key(x["id"])))
        self.inbox_lock = {}
        for e in self.inbox_entries:
            if self.counts(e) and e["ref"].startswith(ANALYST_REF) and not _zero(e["after"]) and \
                    e["type"] != "branch_deletion":
                self.inbox_lock.setdefault(e["after"], e)
        if listed:
            self.summary["inbox_activity_oldest_listed_utc"] = min(listed)    # C6: retention
        self.summary["inbox_activity_entries"] = len(self.inbox_entries)

    def note_ref(self, ref, sha):
        """A `ga_ref` evidence row for a ref first seen at a sha (R-AN-69, A6); returns the ref's first-seen sha."""
        rows = self.ga_ref_rows.setdefault(ref, [])
        if sha not in rows:
            rows.append(sha)
            self.evidence_new.append(self._ev("ga_ref", ref=ref, push_after=sha))
        return rows[0]

    def fresh_head(self):
        """gold-analyst main after one fresh fetch (once per run), or None."""
        if self._fresh is False:
            self._fresh = None
            if self.fresh_main is not None:
                try:
                    self._fresh = self.fresh_main()
                except Exception:  # noqa: BLE001
                    self._fresh = None
        return self._fresh

    def expected_context_schema(self, sha) -> str:
        """R-AN-23 (§16.18 A12): `analyst-context/3` for a repo_head_sha that is the pinned A12 build commit or has it
        as an ancestor, `analyst-context/2` for an earlier one (and for every one while nothing is pinned).
        (§16.18 A14) `analyst-context/4` for one that is the pinned A14 build commit or descends from it."""
        b = self.a14_commit
        if b and self.git.commit_exists(b) and (sha == b or self.git.is_ancestor(b, sha)):
            return SCHEMA_V4
        a = self.a12_commit
        if a and self.git.commit_exists(a) and (sha == a or self.git.is_ancestor(a, sha)):
            return SCHEMA_V3
        return SCHEMA_V2

    def on_main(self, sha) -> bool:
        """sha is gold-analyst main's head or an ancestor of it: the clone's main, else main after one fresh fetch
        (R-AN-67 A4 repo_head_foreign, A12 inbox_main_foreign)."""
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            return False
        if self.git.commit_exists(sha) and self.git.is_ancestor(sha, self.head):
            return True
        fresh = self.fresh_head()
        return bool(fresh) and self.git.commit_exists(sha) and self.git.is_ancestor(sha, fresh)

    def _ev(self, source, **kw):
        row = {k: "" for k in EVIDENCE_HEADER}
        row["judge_utc"] = self.now_s
        row["source"] = source
        for k, v in kw.items():
            row[k] = "" if v is None else str(v)
        return row

    def run_meta(self, run_id, run_attempt=None):
        """Run metadata: from the evidence file when the judge has seen the run before, else from the API (and then
        copied to the evidence file)."""
        if run_id is None:
            return None
        key = str(run_id)
        if key in self.runs:
            return self.runs[key]
        meta = None
        for (rid, att), r in self.ev_runs.items():
            if rid == key:
                ref = r.get("ref") or ""
                meta = {"id": rid, "attempt": att, "event": r["run_event"], "created_utc": r["run_created_utc"],
                        "path": None, "name": None,
                        "head_branch": ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None,
                        "head_sha": r.get("push_after") or None}
        if meta is None and self.api_ok:
            try:
                r = self.api.run(run_id)
            except Exception:  # noqa: BLE001
                r = None
            if r:
                meta = {"id": str(r.get("id")), "attempt": str(r.get("run_attempt", "")),
                        "event": r.get("event", ""), "created_utc": norm_api_time(r.get("created_at")),
                        "path": r.get("path", ""), "name": r.get("name", ""),
                        "head_branch": r.get("head_branch"), "head_sha": r.get("head_sha")}
                if (meta["id"], meta["attempt"]) not in self.ev_runs:
                    # R-AN-69 (A6): `ref` holds refs/heads/<head_branch>, `push_after` the run's head_sha
                    self.evidence_new.append(self._ev("run", run_id=meta["id"], run_attempt=meta["attempt"],
                                                      run_event=meta["event"], run_created_utc=meta["created_utc"],
                                                      ref=f"refs/heads/{meta['head_branch']}"
                                                      if meta["head_branch"] else "",
                                                      push_after=meta["head_sha"] or ""))
                    self.ev_runs[(meta["id"], meta["attempt"])] = self.evidence_new[-1]
        self.runs[key] = meta
        return meta

    def check_witness_runs(self):
        """Copy every witness run's metadata to the evidence file (C14) and check the witness's run block: the run is
        one of main's analyst-merge runs (schedule, workflow_dispatch) or analyst-settle runs (push, schedule,
        workflow_dispatch) (A6 `witness_run_trigger`; from the run's evidence row, which has no path, the event must be
        one of these and the branch main), and its recorded created_utc/event/attempt match (A11)."""
        missing = 0
        for r in self.wit:
            run = r.rec.get("run")
            if not isinstance(run, dict) or run.get("id") is None:
                self.F.v("A6", "witness_run", r.path, r.commit, "witness without its run")
                continue
            m = self.run_meta(run.get("id"))
            if m is None:
                missing += 1
                continue
            bad = []
            if m.get("head_branch") not in (None, "", "main"):
                bad.append("head_branch")
            if m.get("path") is not None:
                if m.get("event") not in WITNESS_TRIGGERS.get(m["path"], ()):
                    bad.append("workflow_event")
            elif m.get("event") not in WITNESS_EVENTS:
                bad.append("event")
            if bad:
                self.F.v("A6", "witness_run_trigger", r.path, r.commit,
                         safe_detail("not a main merge/settle run", *bad))
            if run.get("created_utc") != m.get("created_utc") or str(run.get("attempt")) != str(m.get("attempt")) \
                    or run.get("event") != m.get("event"):
                self.F.w("A11", "run_meta", r.path, r.commit, "witness run block differs from the run record")
        if missing:
            self.F.w("A0", "runs_unreachable", "api", "-", f"{missing} witness runs not readable")

    def server_time(self, after, run_id, ref=None):
        """(time_utc, source) recomputed (R-AN-34; R-AN-67 A2). With the inbox pinned (A6): the earliest (timestamp,
        id) inbox entry at or after PINS.inbox_from_utc on a `claude/analyst-*` ref whose `after` is the pushed sha
        (live API, else the `inbox_activity` evidence rows). Before A6: the push's activity timestamp in gold-analyst's
        log (the entry on the push's ref, else the earliest with that `after`). Only when no entry is found, the
        witness run's created_at, which can only make a push later."""
        if self.inbox is not None:
            e = self.inbox_lock.get(after) if after else None
            if e is not None:
                return e["ts"], "activity"
            lst = None
        else:
            lst = self.act_by_after.get(after) if after else None
        if lst:
            same = [a for a in lst if ref and a["ref"] == ref]
            a = min(same or lst, key=lambda x: x["timestamp_utc"])
            return a["timestamp_utc"], "activity"
        m = self.run_meta(run_id)
        if m and m.get("created_utc"):
            return m["created_utc"], "run_created"
        return None, None

    # ================================================================ witnesses (R-AN-35)
    def load_witnesses(self):
        self.wit = []
        for mode in ("live", "canary"):
            folder = PREFIX[mode] + "witness/"
            for p, r in sorted(self.records(folder).items()):
                if not isinstance(r.rec, dict):
                    self.F.v("A6", "unreadable_witness", p, r.commit, "witness file is not a JSON record")
                    continue
                w = r.rec
                name = p.rsplit("/", 1)[-1]
                if w.get("schema") != "analyst-witness/1" or not isinstance(w.get("seq"), int) or \
                        name != f"{w['seq']:06d}.json" or w.get("mode") != mode:
                    self.F.v("A6", "witness_fields", p, r.commit, "schema, seq, file name or mode")
                if r.raw != record_form(w):
                    self.F.w("A11", "record_form", p, r.commit, "bytes differ from the R-AN-3 record form")
                r.mode = mode
                self.wit.append(r)
        seqs = {}
        for r in self.wit:
            s = r.rec.get("seq")
            if s in seqs:
                self.F.v("A6", "duplicate_seq", r.path, r.commit, f"seq {s}")
            seqs[s] = r
        self.wit_by_seq = seqs

    def wits(self, mode=None, kind=None, wid=None, status=None):
        out = []
        for r in self.wit:
            w = r.rec
            if mode is not None and r.mode != mode:
                continue
            if kind is not None and w.get("kind") != kind:
                continue
            if wid is not None and w.get("id") != wid:
                continue
            if status is not None and w.get("status") != status:
                continue
            out.append(r)
        return out

    @staticmethod
    def comment_body(w: dict) -> str:
        rec = {k: v for k, v in w.items() if k != "comment"}
        return f"analyst-witness/1 {w.get('kind')} {w.get('id') if w.get('id') is not None else '-'} seq " \
               f"{w.get('seq')}\n{compact_form(rec)}"

    def check_comments(self):
        """A6: a witness file whose payload differs from its comment; a file without its comment or the reverse."""
        file_comment_ids = set()
        for r in self.wit:
            w = r.rec
            c = w.get("comment")
            body = self.comment_body(w)
            body_sha = sha256_bytes(body.encode("utf-8"))
            if not isinstance(c, dict) or c.get("issue") != self.pins.get("witness_issue"):
                self.F.v("A6", "file_without_comment", r.path, r.commit, "comment block missing or wrong issue")
                continue
            cid = str(c.get("id"))
            file_comment_ids.add(cid)
            if c.get("body_sha256") != body_sha:
                self.F.v("A6", "payload_differs", r.path, r.commit, "body_sha256 is not the sha of the file payload")
            api_c = self.comment_by_id.get(cid)
            if api_c is not None:
                if api_c["login"] != BOT_LOGIN:
                    self.F.v("A6", "comment_author", r.path, r.commit, "witness comment not by the workflow token")
                if api_c["body"] != body:
                    self.F.v("A6", "payload_differs", r.path, r.commit, "comment body differs from the file payload")
                if c.get("created_utc") != api_c["created_utc"]:
                    self.F.w("A11", "comment_time", r.path, r.commit, "comment created_utc differs from the API")
            elif self.api_ok:
                ev = self.ev_cmt.get(cid)
                if ev is None:
                    self.F.v("A6", "file_without_comment", r.path, r.commit, f"comment {cid} not on the issue")
                elif ev["comment_body_sha256"] != body_sha:
                    self.F.v("A6", "payload_differs", r.path, r.commit, "evidence body sha differs")
                else:
                    # A6: a VIOLATION since §16.18 A6 (it was a WARNING)
                    self.F.v("A6", "comment_deleted", r.path, r.commit, f"comment {cid} only in the evidence file")
        # A6 comment_edited: a bot comment whose updated_at differs from its created_at (R-AN-3 normalised)
        for cid, c in self.comment_by_id.items():
            if c["login"] == BOT_LOGIN and c["updated_utc"] is not None and c["updated_utc"] != c["created_utc"]:
                self.F.v("A6", "comment_edited", f"comment/{cid}", "-", "the bot comment was edited after it was posted")
        # A6 comment_deleted: a bot comment of the evidence file the API no longer returns, without a witness file
        if self.api_ok:
            for cid in sorted(self.ev_cmt, key=_id_key):
                if cid not in self.comment_by_id and cid not in file_comment_ids:
                    self.F.v("A6", "comment_deleted", f"comment/{cid}", "-", "comment only in the evidence file")
        # comments without a file
        seen_seq = {}
        for cid, c in self.comment_by_id.items():
            if c["login"] != BOT_LOGIN or not c["body"].startswith("analyst-witness/1 "):
                continue
            first = c["body"].split("\n", 1)[0].split(" ")
            try:
                seq = int(first[-1])
            except ValueError:
                self.F.v("A6", "comment_unparsable", f"comment/{cid}", "-", "first line")
                continue
            if seq in seen_seq:
                self.F.v("A6", "duplicate_seq", f"comment/{cid}", "-", f"seq {seq}")
            seen_seq[seq] = cid
            if cid not in file_comment_ids:
                age = self.now - parse_utc(c["created_utc"])
                if age > COMMENT_GRACE:
                    self.F.v("A6", "comment_without_file", f"comment/{cid}", "-", f"seq {seq}")
        self.summary["witness_files"] = len(self.wit)
        self.summary["witness_comments"] = len(seen_seq)

    # ================================================================ pushes and the allowlist (A3)
    def commit_available(self, sha, ref=None):
        """The pushed commit is in the clone, or is fetched from the inbox by sha (else by its ref) as data
        (--fetch-pushes, R-AN-70)."""
        if self.git.commit_exists(sha):
            return True
        if self.fetch_commit is not None:
            try:
                if self.fetch_commit(sha, ref):
                    return self.git.commit_exists(sha)
            except Exception:  # noqa: BLE001
                return False
        return False

    def push_diff(self, after, ref=None):
        """R-AN-33's diff of a pushed commit against its merge base with main, or None (cached per sha)."""
        if after in self._diffs:
            return self._diffs[after]
        out = None
        if isinstance(after, str) and re.fullmatch(r"[0-9a-f]{40}", after) and self.commit_available(after, ref):
            base = self.git.merge_base(self.head, after)
            if base is not None:
                out = self.git.diff_name_status(base, after)
        self._diffs[after] = out
        return out

    def check_pushes(self):
        unverified = 0
        # A2 time_source (A6): a witness of an agent push timed from anything but its inbox activity entry
        if self.inbox is not None:
            for r in self.wit:
                push, win = r.rec.get("push"), r.rec.get("window")
                if not isinstance(push, dict):
                    continue
                bad = []
                if push.get("repo") != self.inbox:
                    bad.append("push.repo")
                if isinstance(win, dict) and win.get("time_source") != "activity":
                    bad.append("window.time_source")
                if bad:
                    self.F.v("A2", "time_source", r.path, r.commit, safe_detail(*bad))
        for r in self.wit:
            w = r.rec
            reason = w.get("reason")
            if reason in WITNESS_VIOLATION:
                self.F.v("A3", reason, r.path, r.commit, f"witness kind {w.get('kind')}")
            elif reason in WITNESS_WARNING:
                self.F.w("A3", reason, r.path, r.commit, f"witness kind {w.get('kind')}")
            if w.get("status") == "accepted" and w.get("kind") in ("attempt", "call", "lesson", "revision"):
                path = w.get("path") or ""
                cls = classify_path(path)
                if cls is None or cls[0] != r.mode or cls[1] != w.get("kind"):
                    self.F.v("A3", "accepted_out_of_scope", r.path, r.commit, "path is outside the allowlist")
                b = self.bytes_at_head(path)
                if b is None or sha256_bytes(b) != w.get("file_sha256"):
                    self.F.v("A3", "accepted_copy", r.path, r.commit, "main's file differs from the witnessed sha")
                after = (w.get("push") or {}).get("after")
                ch = self.push_diff(after, (w.get("push") or {}).get("ref")) if after else None
                if ch is None:
                    unverified += 1
                elif not (diff_conforms(ch) and ch[0][1] == path):
                    self.F.v("A3", "accepted_out_of_scope", r.path, r.commit, "pushed diff breaks R-AN-33")
        self.summary["accepted_push_diffs_unverified"] = unverified
        # every session-written record on main came through an accepted witness
        accepted_paths = {(r.rec.get("path"), r.rec.get("file_sha256")) for r in self.wit
                          if r.rec.get("status") == "accepted"}
        for mode in ("live", "canary"):
            pre = PREFIX[mode]
            for sub in ("attempts/", "calls/", "lessons/"):
                for p in self.git.ls_tree(self.head, pre + sub):
                    if p[len(pre + sub):].count("/"):
                        continue
                    if (p, sha256_bytes(self.bytes_at_head(p))) not in accepted_paths:
                        self.F.v("A3", "unwitnessed_record", p, self.commit_of(p), "no accepted witness for it")
            for p in self.git.ls_tree(self.head, pre + "playbooks/"):
                if re.fullmatch(rf"{re.escape(pre)}playbooks/v[1-9][0-9]*\.md", p) and \
                        (p, sha256_bytes(self.bytes_at_head(p))) not in accepted_paths:
                    self.F.v("A3", "unwitnessed_record", p, self.commit_of(p), "no accepted witness for it")
        # pushes seen by GitHub: gold-analyst's own log for its main pushes (A3 main_push_actor, A7)
        witnessed_after = {(r.rec.get("push") or {}).get("after") for r in self.wit}
        owner = (self.pins.get("repo") or "/").split("/")[0]
        for a in self.activity:
            ref = a.get("ref") or ""
            after = a.get("after") or ""
            typ = a.get("activity_type") or ""
            ts = norm_api_time(a.get("timestamp"))
            actor = (a.get("actor") or {}).get("login", "")
            if ref == "refs/heads/main":
                if typ in ("force_push", "branch_deletion"):
                    self.F.v("A7", "main_rewrite", "refs/heads/main", after or "-", f"activity {typ}")
                elif actor not in (BOT_LOGIN, owner):
                    self.F.v("A3", "main_push_actor", "refs/heads/main", after or "-", safe_detail("actor", actor))
                continue
            if self.inbox is None:                   # before A6: the agent's pushes were gold-analyst's own
                self.push_finding(ref, after, typ, ts, witnessed_after, probe_refs=False)
        # A6: the agent's pushes are the inbox's entries at or after PINS.inbox_from_utc
        if self.inbox is not None:
            for e in self.inbox_entries:
                if self.counts(e):
                    self.push_finding(e["ref"], e["after"], e["type"], e["ts"], witnessed_after, probe_refs=True)

    def push_finding(self, ref, after, typ, ts, witnessed_after, probe_refs):
        """A3 on one push seen by GitHub: a `claude/analyst-*` push without a witness after 24 h (its diff breaks
        R-AN-33: VIOLATION; it conforms or cannot be read: WARNING); a probe push (A6, R-AN-84): no finding; any other
        `claude/` ref: WARNING `other_claude_ref`. Deletions are A12's (`inbox_rewrite`)."""
        if not ref.startswith("refs/heads/claude/"):
            return
        if typ == "branch_deletion" or _zero(after):
            return
        if probe_refs and ref.startswith(PROBE_REF):
            return
        if not ref.startswith(ANALYST_REF):
            self.F.w("A3", "other_claude_ref", ref, after, "a claude/ push analyst-merge never sees")
            return
        if after in witnessed_after:
            return
        try:
            if self.now - parse_utc(ts) <= PUSH_GRACE:
                return
        except (TypeError, ValueError):
            return
        ch = self.push_diff(after, ref)
        if ch is None:
            self.F.w("A3", "unwitnessed_push", ref, after, "no witness after 24 h; diff unavailable")
        elif diff_conforms(ch):
            self.F.w("A3", "unwitnessed_push", ref, after, "no witness after 24 h; diff conforms")
        else:
            self.F.v("A3", "unwitnessed_out_of_scope", ref, after, "no witness after 24 h; diff breaks R-AN-33")

    # ================================================================ per mode: A1, A2, A4, A5, A6, A8
    def expected_windows(self, mode):
        m = self.mode_cfg
        if mode == "canary":
            f, t = m.get("canary_from"), m.get("canary_to")
        else:
            f, t = m.get("live_from"), None
        if not f:
            return []
        d0 = dt.date.fromisoformat(f)
        d1 = dt.date.fromisoformat(t) if t else (self.now.date() + dt.timedelta(days=1))
        wins = windows_between(d0, d1, self.a14_day)
        if self.a14_day is not None:
            # R-AN-11 (§16.18 A14): a trigger window is expected once it has an accepted attempt witness
            seen = set()
            for r in self.wits(mode, "attempt", None, "accepted"):
                p = parse_call_id(str(r.rec.get("id") or ""))
                if p is None or not p[1].startswith("T") or p in seen:
                    continue
                seen.add(p)
                if d0 <= p[0] <= d1 and p[0] >= self.a14_day:
                    wins.append(Window(*p))
            wins.sort(key=lambda w: w.order)
        return wins

    def check_mode(self, mode):
        pre = PREFIX[mode]
        wins = self.expected_windows(mode)
        expected = {w.call_id: w for w in wins}
        self.windows[mode] = wins
        terms = self.records(pre + "terminal/")
        calls = self.records(pre + "calls/")
        attempts = self.records(pre + "attempts/")
        term_by_id = self.term_by[mode] = {}
        for p, r in terms.items():
            cid = p.rsplit("/", 1)[-1][:-5]
            term_by_id[cid] = r
            if not isinstance(r.rec, dict):
                self.F.v("A6", "unreadable_terminal", p, r.commit, "")
                continue
            if r.raw != record_form(r.rec):
                self.F.w("A11", "record_form", p, r.commit, "bytes differ from the R-AN-3 record form")
            if cid not in expected:
                self.F.v("A8", "unexpected_terminal", p, r.commit, "terminal for a window outside the mode's period")
        call_by_id = {p.rsplit("/", 1)[-1][:-5]: r for p, r in calls.items()}
        self.summary[f"{mode}_expected_windows"] = 0
        prev_sha = ZERO64
        prev_known = True
        n_closed = 0
        for win in wins:
            cid = win.call_id
            due = self.now >= win.deadline + dt.timedelta(minutes=20) + COMPLETENESS_GRACE
            tr = term_by_id.get(cid)
            twits = self.wits(mode, "terminal", cid)
            tw_acc = [r for r in twits if r.rec.get("status") == "accepted"]
            if due:
                self.summary[f"{mode}_expected_windows"] += 1
                if tr is None:
                    self.F.v("A8", "missing_terminal", f"{pre}terminal/{cid}.json", "-", "no terminal record")
                if len(tw_acc) != 1 and (tr is not None or tw_acc):
                    self.F.v("A8", "terminal_witness_count", f"{pre}terminal/{cid}.json",
                             tr.commit if tr else "-", f"{len(tw_acc)} terminal witnesses")
            elif tr is None and len(tw_acc) > 1:
                self.F.v("A8", "terminal_witness_count", f"{pre}terminal/{cid}.json", "-",
                         f"{len(tw_acc)} terminal witnesses")
            if tr is None:
                prev_known = False
                continue
            n_closed += 1
            t = tr.rec if isinstance(tr.rec, dict) else {}
            tsha = sha256_bytes(tr.raw)
            # chain (R-AN-37)
            if prev_known and t.get("prev_chain_sha256") != prev_sha:
                self.F.v("A6", "broken_chain", tr.path, tr.commit, "prev_chain_sha256 is not the previous terminal")
            prev_sha, prev_known = tsha, True
            if len(tw_acc) == 1:
                tw = tw_acc[0].rec.get("terminal") or {}
                if tw.get("terminal_sha256") != tsha or tw.get("prev_chain_sha256") != t.get("prev_chain_sha256"):
                    self.F.v("A6", "terminal_witness_differs", tr.path, tr.commit, "witness terminal block")
            self.safe(f"window_{mode}_{cid}", self.check_window, mode, win, tr, t, call_by_id.get(cid), attempts)
        self.summary[f"{mode}_terminals"] = n_closed

    def check_window(self, mode, win, tr, t, call_r, attempts):
        pre = PREFIX[mode]
        cid = win.call_id
        # fixed fields
        want = {"schema": "analyst-terminal/1", "call_id": cid, "mode": mode, "window": win.w,
                "model_day": win.day.isoformat(), "entry_utc": fmt_utc(win.entry),
                "deadline_utc": fmt_utc(win.deadline)}
        for k, v in want.items():
            if t.get(k) != v:
                self.F.w("A11", "terminal_fields", tr.path, tr.commit, f"field {k}")
        status = t.get("status")
        if status not in TERMINAL_STATUSES or status == "missed:push":
            self.F.v("A6", "terminal_status_enum", tr.path, tr.commit, safe_detail(status))
        # attempts of this draw (accepted witnesses)
        acc = self.wits(mode, "attempt", cid, "accepted")
        att = []
        for r in acc:
            w = r.rec
            push = w.get("push") or {}
            ts, src = self.server_time(push.get("after"), (w.get("run") or {}).get("id"), push.get("ref"))
            if ts is None:
                self.summary["times_unverified"] = self.summary.get("times_unverified", 0) + 1
                ts = (w.get("window") or {}).get("time_utc")
            elif ts != (w.get("window") or {}).get("time_utc"):
                self.F.w("A11", "server_time", r.path, r.commit, "attempt time differs from the recomputed one")
            arec = self.json_at_head(w.get("path") or "") or {}
            n = arec.get("n")
            void = ts is None or ts < fmt_utc(win.span_lo) or ts > fmt_utc(win.deadline)
            if not (w.get("window") or {}).get("void") and void:
                self.F.v("A2", "attempt_window", r.path, r.commit, "non-void attempt pushed outside [entry-45, deadline]")
            elif bool((w.get("window") or {}).get("void")) != void:
                self.F.w("A11", "void_flag", r.path, r.commit, "void flag differs from the recomputed one")
            att.append({"n": n, "time": ts, "void": void, "path": w.get("path"), "seq": w.get("seq"),
                        "sha": w.get("file_sha256")})
        if len(att) > 2:
            self.F.v("A2", "attempt_count", tr.path, tr.commit, f"{len(att)} accepted attempts")
        ns = [a["n"] for a in att]
        if len(set(ns)) != len(ns) or any(n not in (1, 2) for n in ns):
            self.F.v("A2", "attempt_numbers", tr.path, tr.commit, "attempt numbers repeat or are not 1/2")
        # the call
        cw = self.wits(mode, "call", cid, "accepted")
        lock = lock_src = None
        call = call_r.rec if call_r is not None and isinstance(call_r.rec, dict) else None
        if cw:
            w = cw[0].rec
            push = w.get("push") or {}
            lock, lock_src = self.server_time(push.get("after"), (w.get("run") or {}).get("id"), push.get("ref"))
            if lock is None:
                self.summary["times_unverified"] = self.summary.get("times_unverified", 0) + 1
                lock = (w.get("window") or {}).get("time_utc")
            elif lock != (w.get("window") or {}).get("time_utc"):
                self.F.w("A11", "server_time", cw[0].path, cw[0].commit, "lock time differs from the recomputed one")
        # expected terminal status (R-AN-36, R-AN-39)
        derivable = True
        if call is not None:
            derivable = self.check_call(mode, win, call_r, call, lock)
        if cw and t.get("writer") == "merge":
            if lock is None or lock > fmt_utc(win.deadline):
                exp = ("no_call:late", None)
            else:
                k = (call or {}).get("attempt_n")
                a = [x for x in att if x["n"] == k]
                if not a or a[0]["time"] is None or not (a[0]["time"] < lock):
                    exp = ("no_call:invalid", "no_attempt")
                elif a[0]["void"]:
                    exp = ("no_call:invalid", "void_attempt")
                elif not derivable:
                    exp = ("no_call:invalid", "underivable")
                else:
                    exp = ((call or {}).get("status"), (call or {}).get("detail"))
        elif self.holidays.window_holiday(win):
            exp = ("skipped:holiday", None)
        elif att:
            exp = ("no_call:run", None)
        else:
            exp = ("missed:trigger", t.get("detail") if status == "missed:trigger" else None)
            if not self.holidays.covers(win.day):
                exp = ("missed:trigger", "no_table")
        # §16.18 A14 (R-AN-39 step 2): the gates the closer applies after `no_call:run`, for model days >= a14_from
        sw = None
        gates = self.closer_gates(mode, win) if exp[0] == "missed:trigger" else {}
        if gates.get("skipped:trade_open"):
            opn = gates["skipped:trade_open"]
            exp = ("skipped:trade_open", t.get("detail") if t.get("detail") in opn else opn[0])
        elif gates.get("skipped:day_cap") is not None:
            n_e = gates["skipped:day_cap"]
            exp = ("skipped:day_cap", t.get("detail") if t.get("detail") in (n_e, str(n_e)) else n_e)
        if status in GATED and not (status in gates and exp[0] in GATED):
            sw = safe_detail(status, "condition does not hold", "expected", exp[0])
        elif status == "missed:trigger" and exp[0] in GATED:
            sw = safe_detail("missed:trigger while", exp[0], "holds")
        got = (status, t.get("detail"))
        if status in ("called", "stay_out"):
            if not cw:
                self.F.v("A2", "call_without_witness", tr.path, tr.commit, "no accepted call push")
            elif lock is not None and lock > fmt_utc(win.deadline):
                self.F.v("A1", "late_lock", tr.path, tr.commit, safe_detail("lock", lock, "deadline",
                                                                             fmt_utc(win.deadline)))
            elif exp[0] == "no_call:invalid" and exp[1] in ("no_attempt", "void_attempt"):
                self.F.v("A2", exp[1], tr.path, tr.commit, "counted call without a valid earlier attempt")
            elif exp[0] == "no_call:invalid" and exp[1] == "underivable":
                pass  # reported by A5 on the call file
            elif got != exp:
                self.F.v("A2", "terminal_status", tr.path, tr.commit, safe_detail("expected", exp[0], exp[1]))
        elif sw is not None:
            self.F.v("A14", "skipped_wrong", tr.path, tr.commit, sw)
        elif got != exp and not (exp[0] == "missed:trigger" and status == "missed:trigger"):
            self.F.w("A11", "terminal_status", tr.path, tr.commit, safe_detail("expected", exp[0], exp[1], "got",
                                                                              status, t.get("detail")))
        # terminal's call and attempts blocks
        tc = t.get("call")
        if cw and t.get("writer") == "merge":
            w = cw[0].rec
            csha = sha256_bytes(call_r.raw) if call_r is not None else None
            if not isinstance(tc, dict) or tc.get("sha256") != csha:
                self.F.v("A6", "terminal_call_sha", tr.path, tr.commit, "terminal.call.sha256 is not the call file's")
            else:
                for k, v in (("path", f"{pre}calls/{win.call_id}.json"), ("plan_status", (call or {}).get("status")),
                             ("lock_utc", (w.get("window") or {}).get("time_utc")),
                             ("push_sha", (w.get("push") or {}).get("after")), ("witness_seq", w.get("seq"))):
                    if tc.get(k) != v:
                        self.F.w("A11", "terminal_fields", tr.path, tr.commit, f"call.{k}")
        ta = t.get("attempts")
        want_att = sorted([{"n": a["n"], "path": a["path"], "sha256": a["sha"], "void": a["void"],
                            "witness_seq": a["seq"]} for a in att], key=lambda x: (x["n"] is None, x["n"]))
        got_att = sorted([{k: x.get(k) for k in ("n", "path", "sha256", "void", "witness_seq")}
                          for x in (ta or []) if isinstance(x, dict)], key=lambda x: (x["n"] is None, x["n"]))
        if not isinstance(ta, list) or got_att != want_att:
            self.F.w("A11", "terminal_fields", tr.path, tr.commit, "attempts")
        self.terminal_info[(mode, win.call_id)] = {"status": status, "lock": lock, "lock_src": lock_src,
                                                   "attempts": len(att), "call": call, "call_raw": call_r,
                                                   "term": tr, "win": win, "detail": t.get("detail")}
        if self.inbox is not None and t.get("writer") == "closer":
            self.check_closer_race(mode, win, tr)

    def check_closer_race(self, mode, win, tr):
        """A8 `closer_raced` (A6, review blocker B1): a terminal written by the closer for window w while a counting
        inbox entry with timestamp <= w's deadline_utc, on a `claude/analyst-*` ref, pushed a commit whose diff
        (R-AN-33) adds exactly w's call path in the terminal's mode. Judge decision J-D17: a push the merge had
        already witnessed as rejected for another reason than `window_closed` before the terminal's witness (a lower
        seq) was processed by the closer's step 1, not raced (its rejection is A3's)."""
        call_path = f"{PREFIX[mode]}calls/{win.call_id}.json"
        deadline = fmt_utc(win.deadline)
        tseqs = [r.rec.get("seq") for r in self.wits(mode, "terminal", win.call_id, "accepted")
                 if _int(r.rec.get("seq"))]
        tseq = min(tseqs) if tseqs else None
        for e in self.inbox_entries:
            if not self.counts(e) or e["ts"] > deadline or not e["ref"].startswith(ANALYST_REF) or \
                    _zero(e["after"]) or e["type"] == "branch_deletion":
                continue
            ch = self.push_diff(e["after"], e["ref"])
            if ch is None:
                self.summary["closer_race_unverified"] = self.summary.get("closer_race_unverified", 0) + 1
                continue
            if ch != [("A", call_path)]:
                continue
            if tseq is not None and any(r.rec.get("status") == "rejected" and r.rec.get("reason") != "window_closed"
                                        and _int(r.rec.get("seq")) and r.rec["seq"] < tseq
                                        for r in self.wit if (r.rec.get("push") or {}).get("after") == e["after"]):
                continue
            self.F.v("A8", "closer_raced", tr.path, e["after"],
                     safe_detail("call pushed", e["ts"], "deadline", deadline))

    # ---------------------------------------------------------------- A11: the Twelve Data cross-check (A9)
    def cross_check(self, p, c, win, ctx):
        """A11 `td_mismatch` / `td_unchecked` (§16.18 A9; R-AN-66, R-AN-68): the recorded Twelve Data values against
        the judge's own Dukascopy downloads (td_cross_check). Both list every value concerned (J-D45)."""
        r = td_cross_check(win.call_id, ctx.get("files"), self.hours,
                           lambda h: self.holidays.is_nyse_full(to_server(h).date()), self.now.date())
        for k, n in (("td_compared", len(r.compared)), ("td_outside", len(r.outside)), ("td_pending", r.pending),
                     ("td_unchecked", len(r.unchecked))):
            self.summary[k] = self.summary.get(k, 0) + n
        if r.outside:
            inside = [x for x in r.compared if x not in r.outside]
            self.F.w("A11", "td_mismatch", p, c,
                     f"outside 1e-3: {cross_detail(r.outside)}; within: {cross_detail(inside) or 'none'}")
        if r.unchecked:
            self.F.w("A11", "td_unchecked", p, c, f"no present Dukascopy file: {cross_detail(r.unchecked)}")

    # ---------------------------------------------------------------- A4 / A5 on one call file
    def check_call(self, mode, win, call_r, call, lock) -> bool:
        """A4 (context reproduction) and A5 (derivability). Returns whether S/T/D_ref follow (R-AN-36 step 4)."""
        p, c = call_r.path, call_r.commit
        ctx = call.get("context")
        derivable = True
        if call.get("schema") != "analyst-call/1" or call.get("call_id") != win.call_id or call.get("mode") != mode \
                or call.get("window") != win.w or call.get("model_day") != win.day.isoformat():
            self.F.v("A5", "call_ids", p, c, "schema, ids or mode")
        for k, v in win.times().items():
            if call.get(k) != v:
                self.F.v("A5", "call_times", p, c, f"field {k}")
        status = call.get("status")
        if status not in CALL_STATUSES:
            self.F.v("A5", "call_status", p, c, safe_detail(status))
        if not isinstance(ctx, dict):
            self.F.v("A4", "context_missing", p, c, "")
            return False
        if call.get("context_sha256") != sha256_compact(ctx):
            self.F.v("A4", "context_sha", p, c, "context_sha256 is not the sha of the compact context")
        if call.get("decision_utc") != ctx.get("asof_utc"):
            self.F.v("A4", "decision_utc", p, c, "decision_utc differs from context.asof_utc")
        if lock is not None and isinstance(ctx.get("asof_utc"), str):
            try:
                if parse_utc(ctx["asof_utc"]) > parse_utc(lock) + dt.timedelta(seconds=60):
                    self.F.v("A4", "asof_after_lock", p, c, "asof_utc > lock_utc + 60 s")
            except ValueError:
                pass
        R = ctx.get("repo_head_sha")
        schema = ctx.get("schema")
        if schema not in CONTEXT_SCHEMAS:
            # §16.18 A9 (R-AN-23): the judge accepts only analyst-context/2 from the first canary day on;
            # (§16.18 A12) and analyst-context/3
            self.F.v("A4", "context_schema", p, c, safe_detail("schema", schema))
        elif not self.on_main(R):
            self.F.v("A4", "repo_head_foreign", p, c, "repo_head_sha is not gold-analyst main's head or an ancestor")
        elif schema != self.expected_context_schema(R):
            # §16.18 A12 (R-AN-23): /3 iff repo_head_sha has the pinned A12 build commit as an ancestor (or is it)
            self.F.v("A4", "context_schema", p, c, safe_detail("schema", schema, "expected",
                                                                self.expected_context_schema(R)))
        else:
            if schema in (SCHEMA_V3, SCHEMA_V4):
                self.check_macro_calendar(R)
            wake = None
            if schema == SCHEMA_V4:                  # A14 (R-AN-23): the wake of the call's attempt record
                arec = self.json_at_head(f"{PREFIX[mode]}attempts/{win.call_id}_{call.get('attempt_n')}.json")
                wake = arec.get("wake") if isinstance(arec, dict) else None
            rb = rebuild_context(ctx, win.call_id, mode, self.git, self.hours, self.holidays, self.events,
                                 schema=schema, wake=wake)
            if rb.error:
                self.F.v("A4", "context_unreproducible", p, c, safe_detail("rebuild", rb.error))
            else:
                mm = compare_context(rb, ctx)
                if mm:
                    self.F.v("A4", "context_differs", p, c, safe_detail(*mm[:12]))
                self.summary["contexts_rebuilt"] = self.summary.get("contexts_rebuilt", 0) + 1
        if schema in CONTEXT_SCHEMAS:
            self.cross_check(p, c, win, ctx)
        # ---- A5: derivable from the plan and the context
        ctx_status = ctx.get("status")
        plan = call.get("plan")
        if ctx_status in ("no_call:data", "no_call:d_ref"):
            if status != ctx_status or plan is not None:
                self.F.v("A5", "status_vs_context", p, c, "a no_call context must give that status and no plan")
        elif status in ("called", "stay_out"):
            errs = derive.plan_errors(plan, v3=(schema in (SCHEMA_V3, SCHEMA_V4)))   # A12: analyst-plan/2 from /3
            if errs:
                self.F.v("A5", "plan_invalid", p, c, safe_detail(*errs))
                derivable = False
            else:
                act = plan["action"]
                if (status == "called") != (act in ("buy", "sell")):
                    self.F.v("A5", "status_vs_plan", p, c, "status does not follow from plan.action")
        dref = ctx.get("d_ref")
        if call.get("d_ref") != dref:
            self.F.v("A5", "d_ref_copy", p, c, "call.d_ref is not context.d_ref")
            derivable = False
        if ctx_status == "ok":
            ok = isinstance(dref, dict) and isinstance(dref.get("rows"), list) and len(dref["rows"]) >= 1
            if ok:
                try:
                    pref = (ctx.get("p_ref") or {}).get("p_ref")
                    v = derive.dref_values([{"F_S": float(r["F_S"])} for r in dref["rows"]], float(pref))
                    ok = (rel_eq(dref.get("F_ref"), v["F_ref"]) and rel_eq(dref.get("D_raw"), v["D_raw"]) and
                          num_exact(dref.get("D_ref"), v["D_ref"]) and dref.get("D_ref_cents") == v["D_ref_cents"] and
                          isinstance(dref.get("D_ref_cents"), int) and price_eq(dref.get("P_ref"), float(pref)) and
                          dref.get("slot") == win.slot and dref.get("k") == derive.K_DREF and len(dref["rows"]) >= 10)
                except (TypeError, ValueError, KeyError):
                    ok = False
            if not ok:
                self.F.v("A5", "d_ref_underivable", p, c, "D_ref does not follow from the context")
                derivable = False
        if status == "called" and derivable and isinstance(plan, dict) and \
                not derive.plan_errors(plan, v3=(schema in (SCHEMA_V3, SCHEMA_V4))):
            side = derive.side_of(plan["action"])
            sd, td = derive.st_dimes(dref["D_ref_cents"], plan["stop_mult"], plan["target_mult"])
            checks = [call.get("side") == side, num_exact(call.get("stop_mult"), float(plan["stop_mult"])),
                      num_exact(call.get("target_mult"), float(plan["target_mult"])),
                      call.get("S_dimes") == sd, call.get("T_dimes") == td,
                      num_exact(call.get("S"), sd / 10), num_exact(call.get("T"), td / 10)]
            if not all(checks):
                self.F.v("A5", "st_underivable", p, c, "side, multiples, S or T do not follow from plan and D_ref")
                derivable = False
        elif status in ("stay_out",) and isinstance(plan, dict):
            if call.get("side") not in (0, None) or any(call.get(k) is not None for k in
                                                         ("stop_mult", "target_mult", "S", "T", "S_dimes", "T_dimes")):
                self.F.v("A5", "st_underivable", p, c, "stay_out carries trade fields")
                derivable = False
        elif status not in ("called", "stay_out"):
            if any(call.get(k) is not None for k in ("S", "T", "S_dimes", "T_dimes")):
                self.F.v("A5", "st_underivable", p, c, "a no_call carries S or T")
        req = call.get("request") or {}
        if req.get("model_set") != self.pins.get("model") or req.get("effort_set") != self.pins.get("effort"):
            self.F.w("A11", "request_pins", p, c, "request.model_set/effort_set differ from PINS")
        self.check_frozen_selfreport(p, c, call, R)
        return derivable

    def check_frozen_selfreport(self, path, commit, call, R):
        fr = call.get("frozen") or {}
        tag = self.pins.get("freeze_tag") or "analyst-v1-freeze"
        ref = self.git.tag_commit(tag) or (R if isinstance(R, str) and self.git.commit_exists(R) else None)
        if ref is None:
            return
        man = self.git.show(ref, "analyst/FROZEN_ANALYST.sha256")
        if man is None:
            return
        msha = sha256_bytes(man)
        rp = self.git.show(ref, "analyst/ROUTINE_PROMPT.md")
        if fr.get("manifest_sha256") != msha or fr.get("code_sha8") != msha[:8] or \
                (rp is not None and fr.get("routine_prompt_sha256") != sha256_bytes(rp)):
            self.F.w("A11", "frozen_selfreport", path, commit, "self-reported manifest or prompt sha differs")

    # ================================================================ A14, watching (§16.18 A14)
    def a14_from_value(self):
        """MODE.json `a14_from` at main as a date (R-AN-5), or None (null, or not a weekday date: A14 `a14_from`)."""
        v = (self.mode_cfg or {}).get("a14_from")
        if not is_day(v):
            return None
        try:
            d = dt.date.fromisoformat(v)
        except ValueError:
            return None
        return d if d.weekday() < 5 else None

    def watch_day(self, mode, d):
        """[(win, accepted attempt witnesses in seq order, terminal status at main or None)] of the mode's expected
        windows of model day d, in window order (R-AN-89's E(T) and O(T) for the judge and the closer)."""
        key = (mode, d)
        if key not in self._wd:
            out = []
            for win in self.windows.get(mode, []):
                if win.day != d:
                    continue
                acc = sorted(self.wits(mode, "attempt", win.call_id, "accepted"),
                             key=lambda r: r.rec.get("seq") if _int(r.rec.get("seq")) else 0)
                tr = self.term_by[mode].get(win.call_id)
                st = tr.rec.get("status") if tr is not None and isinstance(tr.rec, dict) else None
                out.append((win, acc, st))
            self._wd[key] = out
        return self._wd[key]

    def attempt_record(self, wit):
        r = self.json_at_head(wit.rec.get("path") or "")
        return r if isinstance(r, dict) else None

    def e_o(self, mode, d, t_check):
        """(E(T), O(T)) from main (R-AN-89): E = [(check, kind, reason)] of d's windows with check < T and an accepted
        attempt witness (a trigger's reason from its first attempt record's `wake`); O = the call_ids of d's windows
        with check < T, terminal `called` and exit_utc > T + 30 min."""
        E, O = [], []
        for win, acc, st in self.watch_day(mode, d):
            if win.check >= t_check:
                continue
            if acc:
                reason = None
                if win.kind == "trigger":
                    rec = self.attempt_record(acc[0]) or {}
                    reason = (rec.get("wake") or {}).get("reason") if isinstance(rec.get("wake"), dict) else None
                E.append((win.check, win.kind, reason))
            if st == "called" and win.exit > t_check + HALF:
                O.append(win.call_id)
        return E, O

    def closer_gates(self, mode, win):
        """R-AN-39 step 2 (§16.18 A14) for a W1, W2, W1b or W2b window of a model day >= a14_from without an accepted
        attempt: {"skipped:trade_open": [open call_ids]} when an earlier window of d has terminal `called` and an
        exit_utc later than this entry; {"skipped:day_cap": n} when n >= 6 earlier windows of d have an accepted
        attempt. {} otherwise."""
        if self.a14_day is None or win.day < self.a14_day or win.kind == "trigger":
            return {}
        E, O = self.e_o(mode, win.day, win.check)
        out = {}
        if O:
            out["skipped:trade_open"] = O
        if len(E) >= watch.DAY_CAP:
            out["skipped:day_cap"] = len(E)
        return out

    def check_watching(self):
        """Check A14 (R-AN-67, R-AN-68, R-AN-89, R-AN-90): every accepted call attempt of a model day >= a14_from
        (its `wake`, the gates at its check, a trigger's rule rebuilt from its own bars, their Dukascopy cross-check
        and the comparison with the judge's own fetch); the judge's fetch per model day (R-AN-66), `wake_missed` and
        `m30_unchecked`."""
        a14 = self.a14_day
        if a14 is not None:
            self.fetch_m30_days()
        for mode in ("canary", "live"):
            for win in self.windows.get(mode, []):
                self.safe(f"watch_{mode}_{win.call_id}", self.check_wake_window, mode, win)
        if a14 is None:
            return
        for mode in ("canary", "live"):
            for d in sorted({w.day for w in self.windows.get(mode, []) if w.day >= a14}):
                self.safe(f"wake_missed_{mode}_{d}", self.check_wake_missed, mode, d)

    def check_wake_window(self, mode, win):
        """A14 `wake_record` for every `analyst-attempt/2` call attempt (and, from a14_from on, an attempt that is
        not one); for model days >= a14_from the gates at the first accepted attempt's check and a trigger's rule."""
        _w, acc, _st = next(x for x in self.watch_day(mode, win.day) if x[0].call_id == win.call_id)
        a14 = self.a14_day is not None and win.day >= self.a14_day
        if not acc:
            return
        recs = [(w, self.attempt_record(w)) for w in acc]
        first = {}
        for w, rec in recs:
            if rec is not None and rec.get("n") == 1:
                first = rec
        for w, rec in recs:
            if rec is None:
                continue
            p = w.rec.get("path") or "-"
            c = self.commit_of(p)
            if rec.get("schema") != "analyst-attempt/2":
                if a14:
                    self.F.v("A14", "wake_record", p, c, safe_detail("schema", rec.get("schema")))
                continue
            probs = watch.wake_problems(rec, win)
            if rec.get("n") == 2 and first and rec.get("wake") != first.get("wake"):
                probs.append("wake.second_draw")
            if probs:
                self.F.v("A14", "wake_record", p, c, safe_detail(*probs[:8]))
        if not a14:
            return
        w0, rec0 = recs[0]
        p0 = w0.rec.get("path") or "-"
        c0 = self.commit_of(p0)
        E, O = self.e_o(mode, win.day, win.check)
        if win.kind != "trigger":
            if O:
                self.F.v("A14", "trade_open", p0, c0, safe_detail("open", *O))
            if len(E) >= watch.DAY_CAP:
                self.F.v("A14", "day_cap", p0, c0, safe_detail("earlier wakes", len(E)))
            return
        wk = (rec0 or {}).get("wake")
        wk = wk if isinstance(wk, dict) else {}
        bars = watch.recorded_bars(wk)
        cond = None
        if bars is not None:
            cond = watch.conditions(watch.values_at(bars, win.day, win.check), win.day, win.check)
        got = watch.rule(win.day, win.check, E, len(O), self.holidays.any_exchange(win.day), cond)
        if bars is None or got != ("window", win.wid, "trigger", wk.get("reason")):
            self.F.v("A14", "not_triggered", p0, c0,
                     safe_detail("rule gives", got[0], got[1], got[3], "recorded", wk.get("reason"),
                                 "no ok bars" if bars is None else None))
        if bars is not None:
            self.cross_check_m30(p0, c0, win, bars)
            own = self.m30.get(win.day) if self.m30 is not None else None
            if own is not None:
                diffs = watch.m30_compare(bars, own.get("bars"), watch.m30_start(win.day), win.check - HALF)
                self.summary["m30_compared"] = self.summary.get("m30_compared", 0) + 1
                if diffs:
                    self.F.w("A14", "m30_mismatch", p0, c0, safe_detail(len(diffs), "differences", *diffs[:6]))

    def cross_check_m30(self, p, c, win, bars):
        """R-AN-68 (A14): the o and the c of every bar of model day d in a trigger attempt's `wake.td.bars` against the
        first and the last tick mid of the same Dukascopy half hour, with the 1e-3 rule (A11 `td_mismatch`,
        `td_unchecked`). Judge decision: a half outside d's trading hours whose file is empty or has no tick is
        skipped, as an optional hour is (R-AN-15); inside them it is pending, then unchecked."""
        if self.halves is None:
            self.summary["m30_cross_unavailable"] = self.summary.get("m30_cross_unavailable", 0) + 1
            return
        final = td.weekdays_since(win.day, self.now.date()) > td.UNCHECKED_AFTER
        compared, outside, unchecked = [], [], []
        for b in bars:
            t = parse_utc(b["t_utc"])
            if tday(t) != win.day:
                continue
            hour = t.replace(minute=0)
            half = "lo" if t.minute == 0 else "hi"
            row = self.halves.get("XAUUSD", hour, refresh=not final)
            have = row is not None and row.get("status") == "present" and row.get(half + "_first_ask") is not None
            if have:
                for fld, end in (("o", "first"), ("c", "last")):
                    dk = ticks.tick_mid(row[f"{half}_{end}_ask"], row[f"{half}_{end}_bid"], "XAUUSD")
                    item = ("XAUUSD", b["t_utc"], fld, b[fld], dk, td.rel_diff(b[fld], dk))
                    compared.append(item)
                    if not item[5] <= td.CROSS_TOL:
                        outside.append(item)
            elif row is not None and row.get("status") in ("present", "empty") and not is_trading_hour(hour):
                continue
            elif not final:
                self.summary["td_pending"] = self.summary.get("td_pending", 0) + 2
            else:
                unchecked += [("XAUUSD", b["t_utc"], "o", b["o"]), ("XAUUSD", b["t_utc"], "c", b["c"])]
        self.summary["td_compared"] = self.summary.get("td_compared", 0) + len(compared)
        if outside:
            inside = [x for x in compared if x not in outside]
            self.F.w("A11", "td_mismatch", p, c,
                     f"outside 1e-3: {cross_detail(outside)}; within: {cross_detail(inside) or 'none'}")
        if unchecked:
            self.F.w("A11", "td_unchecked", p, c, f"no present Dukascopy half hour: {cross_detail(unchecked)}")

    def fetch_m30_days(self):
        """R-AN-66 (A14): one fetch per model day d >= a14_from of a mode's period, at the first run with now >=
        model_to_utc((d+1) 00:00) + 60 min, never repeated once `ok`; A14 `m30_unchecked` while it is not `ok` once
        d is more than 3 weekdays old. Days with a holiday-table row (no trigger window can open) are not fetched."""
        days = sorted({w.day for m in ("canary", "live") for w in self.windows.get(m, []) if w.day >= self.a14_day})
        for d in days:
            if self.holidays.any_exchange(d):
                continue
            end = model_to_utc(dt.datetime(d.year, d.month, d.day) + dt.timedelta(days=1))
            if self.now < end + dt.timedelta(minutes=60):
                continue
            rec = self.m30.get(d) if self.m30 is not None else None
            if rec is None and self.m30 is not None:
                rec, ev = self.m30.fetch(d, end)
                if ev:
                    self.evidence_new.append(self._ev("td_m30", **ev))
            if rec is None and td.weekdays_since(d, self.now.date()) > td.UNCHECKED_AFTER:
                self.F.w("A14", "m30_unchecked", d.isoformat(), "-", "no ok judge fetch of the 30-minute bars")

    def mode_off_at(self, t):
        """MODE.json's `mode` in force at t is `off`: the first-parent MODE.json version committed last at or before
        t (the earliest version when none is)."""
        if getattr(self, "_mode_versions", None) is None:
            vs = []
            for sha, _parent, changes in self.log:
                if any(p == "analyst/MODE.json" for _st, p in changes):
                    m = None
                    try:
                        b = self.git.show(sha, "analyst/MODE.json")
                        m = load_json_bytes(b) if b is not None else None
                    except Exception:  # noqa: BLE001
                        m = None
                    vs.append((self.git.commit_time(sha) or 0, (m or {}).get("mode") if isinstance(m, dict) else None))
            self._mode_versions = vs
        cur = self._mode_versions[0][1] if self._mode_versions else None
        for ct, mode in self._mode_versions:
            if ct <= t.timestamp():
                cur = mode
        return cur == "off"

    def check_wake_missed(self, mode, d):
        """A14 `wake_missed` (WARNING): the judge's R(T) on its own fetch, with E(T) and O(T) from main, gives a
        trigger window at a check T of d where d has no window with that check; checks inside A10's pause intervals or
        while the mode is `off` are left out."""
        own = self.m30.get(d) if self.m30 is not None else None
        if own is None or self.holidays.any_exchange(d):
            return
        bars = own.get("bars") or []
        have = {w.check for w, _a, _s in self.watch_day(mode, d)}
        sched = scheduled_checks(d)
        if getattr(self, "_pauses", None) is None:
            self._pauses = self.pause_intervals()
        for t in check_grid(d):
            if t in sched or t in have:
                continue
            if any(a <= t < b for a, b in self._pauses) or self.mode_off_at(t):
                continue
            E, O = self.e_o(mode, d, t)
            cond = watch.conditions(watch.values_at(bars, d, t), d, t)
            got = watch.rule(d, t, E, len(O), False, cond)
            if got[0] == "window" and got[2] == "trigger":
                self.F.w("A14", "wake_missed", d.isoformat(), got[1], safe_detail(mode, "reason", got[3]))

    def main_at(self, x):
        """Inbox main at instant x: the `after` of the latest counting inbox main entry with timestamp <= x; without
        the inbox pins, gold-analyst main's latest first-parent commit committed at or before x. None when unknown."""
        if not getattr(self, "inbox", None):
            best = None
            for sha, _parent, _changes in self.log:
                ct = self.git.commit_time(sha)
                if ct is not None and ct <= x.timestamp():
                    best = sha
            return best
        best = None
        xs = fmt_utc(x)
        for e in getattr(self, "inbox_entries", None) or []:
            if self.counts(e) and e["ref"] == "refs/heads/main" and not _zero(e["after"]) and \
                    e["type"] != "branch_deletion" and e["ts"] and e["ts"] <= xs:
                best = e["after"]
        return best

    def check_a14_from(self):
        """A14 `a14_from` (R-AN-5): the value is null or a weekday, set once and never changed; valid iff inbox main at
        22:00:00Z of the calendar day before it holds the pinned A14 build commit, this MODE.json and a
        WATCHER_CONFIG.json whose source_commit is the build commit (or a later main commit with the same `watcher/`
        tree) and whose deployed_utc is at or before that instant; and no W1b, W2b or trigger push accepted for a
        model day before it."""
        path = "analyst/MODE.json"
        v = self.mode_cfg.get("a14_from")
        set_sha, set_val = None, None
        for sha, _parent, changes in self.log:
            if not any(p == path for _st, p in changes):
                continue
            m = self.git.show(sha, path)
            try:
                val = (load_json_bytes(m) or {}).get("a14_from") if m is not None else None
            except Exception:  # noqa: BLE001
                val = None
            if set_sha is None and val is not None:
                set_sha, set_val = sha, val
            elif set_sha is not None and val != set_val:
                self.F.v("A14", "a14_from", path, sha, safe_detail("changed after it was set", set_val, val))
        if v is not None and self.a14_day is None:
            self.F.v("A14", "a14_from", path, set_sha or "-", "not a weekday date")
        if self.a14_day is not None:
            d = self.a14_day
            x = dt.datetime(d.year, d.month, d.day, tzinfo=UTC) - dt.timedelta(hours=2)
            b = self.a14_commit
            if not b:
                self.F.w("A0", "a14_unpinned", "judge_analyst/jlib/config.py", "-",
                         "MODE.json sets a14_from but A14_BUILD_COMMIT is not pinned")
            else:
                M = self.main_at(x)
                if M is None:
                    self.F.w("A0", "a14_from_unverified", path, "-", safe_detail("inbox main unknown at", fmt_utc(x)))
                else:
                    bad = []
                    if not self.git.commit_exists(b) or not self.shows(M, b):
                        bad.append("build commit not on inbox main")
                    mm = self.git.show(M, path)
                    try:
                        mv = (load_json_bytes(mm) or {}).get("a14_from") if mm is not None else None
                    except Exception:  # noqa: BLE001
                        mv = None
                    if mv != v:
                        bad.append("MODE.json")
                    wb = self.git.show(M, "analyst/WATCHER_CONFIG.json")
                    try:
                        wc = load_json_bytes(wb) if wb is not None else None
                    except Exception:  # noqa: BLE001
                        wc = None
                    if not isinstance(wc, dict):
                        bad.append("WATCHER_CONFIG.json")
                    else:
                        sc = wc.get("source_commit")
                        same = sc == b or (isinstance(sc, str) and re.fullmatch(r"[0-9a-f]{40}", sc or "") and
                                           self.git.commit_exists(sc) and self.git.commit_exists(b) and
                                           self.git.is_ancestor(b, sc) and self.on_main(sc) and
                                           self.git.object_id(sc, "watcher") == self.git.object_id(b, "watcher"))
                        if not same:
                            bad.append("source_commit")
                        if not is_utc(wc.get("deployed_utc")) or parse_utc(wc["deployed_utc"]) > x:
                            bad.append("deployed_utc")
                    if bad:
                        self.F.v("A14", "a14_from", path, set_sha or "-", safe_detail(*bad))
        for r in self.wit:
            w = r.rec
            if w.get("status") != "accepted" or w.get("kind") not in ("attempt", "call"):
                continue
            pc = parse_call_id(str(w.get("id") or ""))
            if pc is None or pc[1] in ("W1", "W2"):
                continue
            if self.a14_day is None or pc[0] < self.a14_day:
                self.F.v("A14", "a14_from", path, r.commit, safe_detail("accepted push before a14_from", w.get("id")))

    # ================================================================ START (A9)
    def check_start(self):
        st_path = "analyst/START.json"
        st = self.json_at_head(st_path)
        first = None
        for win in self.windows.get("live", []):
            info = self.terminal_info.get(("live", win.call_id))
            if info and info["status"] in ("called", "stay_out"):
                first = (win, info)
                break
        self.first_day = None
        if first is None:
            if st is not None:
                self.F.v("A9", "start_without_call", st_path, self.commit_of(st_path), "no live called/stay_out")
            return
        win, info = first
        d0 = win.day
        m = d0 + dt.timedelta(days=(7 - d0.weekday()) % 7 or 7)
        if d0.weekday() >= 3:
            m += dt.timedelta(days=7)
        self.first_day = m
        if st is None:
            self.F.v("A9", "start_missing", st_path, "-", "first successful live call has no START.json")
            return
        tr = info["term"]
        want = {"schema": "analyst-start/1", "freeze_tag": self.pins.get("freeze_tag"), "first_call_id": win.call_id,
                "d0": d0.isoformat(), "first_day": m.isoformat(), "terminal_sha256": sha256_bytes(tr.raw),
                "first_call_lock_utc": info["lock"],
                "rule": "first Monday m > d0 with numpy.busday_count(d0, m) >= 3"}
        bad = [k for k, v in want.items() if st.get(k) != v]
        if self.commit_of(st_path) != self.commit_of(tr.path):
            bad.append("commit")
        if bad:
            self.F.v("A9", "start_differs", st_path, self.commit_of(st_path), safe_detail(*bad))
        self.first_day = m

    # ================================================================ owner-attested runs (A10, R-AN-57, R-AN-60)
    def check_runs_exports(self):
        self.overlay = {}
        runs = []
        exports = {}                     # by path: each export file is judged on its own (fourth review of A6, N3)
        export_weeks = set()
        for p, r in self.records("analyst/runs/").items():
            if not isinstance(r.rec, dict) or r.rec.get("schema") != "analyst-runs/1":
                self.F.w("A10", "runs_export_form", p, r.commit, "unreadable export", owner_attested=True)
                continue
            exports[p] = r
            export_weeks |= self.export_weeks(r)
            for x in r.rec.get("runs") or []:
                if isinstance(x, dict):
                    runs.append((r, x))
        self.check_inbox_checks(exports)
        self.safe("run_logs", self.check_run_logs, exports)
        self.safe("runs_routines", self.check_runs_routines, exports)
        model = self.pins.get("model")
        t_run = int(self.params.get("T_run_min") or 0)
        t_setup = int(self.params.get("T_setup_min") or 0)
        acc_by_mode = {}
        for mode in ("live", "canary"):
            acc_by_mode[mode] = {r.rec.get("id") for r in self.wits(mode, "attempt", None, "accepted")}
        win_index = {}
        for mode in ("live", "canary"):
            for w in self.windows.get(mode, []):
                win_index.setdefault(w.call_id, []).append((mode, w))
        pauses = self.pause_intervals()
        for r, x in runs:
            if x.get("model") is None:
                self.F.w("A10", "model_unknown", r.path, r.commit, safe_detail("run", x.get("run_id")),
                         owner_attested=True)
            elif x.get("model") != model:
                self.F.v("A10", "run_model", r.path, r.commit, safe_detail("run", x.get("run_id")),
                         owner_attested=True)
            routine = x.get("routine")
            if routine not in ("analyst-w1", "analyst-w2"):
                continue
            st = str(x.get("status") or "").lower()
            if not (st.startswith("succe") or st == "completed"):
                continue
            try:
                cu = parse_utc(x.get("created_utc"))
            except ValueError:
                continue
            wname = "W1" if routine == "analyst-w1" else "W2"
            cid = f"{cu.date().isoformat()}_{wname}"
            for mode, w in win_index.get(cid, []):
                hi = w.deadline - dt.timedelta(minutes=t_run + t_setup)
                if not (w.span_lo <= cu <= hi) or self.holidays.window_holiday(w):
                    continue
                if (self.terminal_info.get((mode, cid)) or {}).get("status") in GATED:
                    continue                     # A14-D16 (R-AN-60): a window the gates closed
                # J-5 (decision 33, R-AN-67): not judged when a pause interval meets [created_utc, deadline_utc -
                # T_run], the range in which the run's `start` read inbox main; canary windows too (J-D31). An empty
                # interval (inbox main never showed the pause) meets nothing (J-D34).
                end = w.start_hi(t_run)
                if any(a < b and a <= end and b > cu for a, b in pauses):
                    continue
                if cid not in acc_by_mode[mode]:
                    self.F.v("A10", "in_span_without_attempt", r.path, r.commit, safe_detail("run", x.get("run_id"),
                                                                                             cid),
                             owner_attested=True)
        # model overlay for live called/stay_out (R-AN-57)
        for win in self.windows.get("live", []):
            info = self.terminal_info.get(("live", win.call_id))
            if not info or info["status"] not in ("called", "stay_out"):
                continue
            sid = ((info["call"] or {}).get("self_reported") or {}).get("session_id")
            if win.w in ("W1", "W2"):
                routine = "analyst-w1" if win.w == "W1" else "analyst-w2"
                cands = [(r, x) for r, x in runs if x.get("routine") == routine]
                lo, hi, late = win.entry - dt.timedelta(minutes=60), win.deadline, cands
            else:                                # A14 (R-AN-60): any of the three call routines, by session id;
                cands = [(r, x) for r, x in runs if x.get("routine") in WAKE_ROUTINES]   # else analyst-wake
                lo, hi = win.entry - dt.timedelta(minutes=30), win.deadline
                late = [(r, x) for r, x in cands if x.get("routine") == "analyst-wake"]
            match = [(r, x) for r, x in cands if sid and x.get("session_id") == sid]
            if not match:
                match = [(r, x) for r, x in late if not x.get("session_id") and
                         _in(x.get("created_utc"), lo, hi)]
            if not match:
                wk = iso_week(win.day)
                week_end = win.day + dt.timedelta(days=7 - win.day.weekday())
                if wk in export_weeks or self.now.date() > week_end + dt.timedelta(days=3):
                    self.F.w("A11", "unverified_model", info["term"].path, info["term"].commit,
                             "no owner-exported run matches this call", owner_attested=True)
                continue
            r, x = match[0]
            if x.get("model") is not None and x.get("model") != model:
                self.overlay[win.call_id] = str(x.get("run_id"))

    @staticmethod
    def export_weeks(r):
        """The weeks a runs export stands for: the `<iso_week>` of its path `analyst/runs/<iso_week>.json` (R-AN-60)
        and the `iso_week` it claims (judge decision J-D33)."""
        out = {r.path.rsplit("/", 1)[-1][:-len(".json")]}
        if isinstance(r.rec.get("iso_week"), str):
            out.add(r.rec["iso_week"])
        return out

    def check_inbox_checks(self, exports):
        """A12 (A6, review blocker B3; R-AN-60), owner-attested: `inbox_hook` for a runs export whose `inbox_checks`
        has hooks > 0 or security_log_hook_events > 0; (fourth review, J-4) `inbox_config` for deploy_keys != 1 or
        actions_enabled true; `inbox_checks_missing` (WARNING) for an export without complete `inbox_checks` for a
        week with expected canary or live windows, and (second review) one whose `inbox_checks` lacks a readable
        `app_repositories`; `app_scope` (second review, SEC-1) for an export whose `app_repositories` has a
        `repository_selection` other than `selected`, or names gold-analyst, gold-forward-watch or xauusd-quant (judge
        decision J-D24: by repository name, any owner, case ignored as GitHub ignores it). `exports` is keyed by path:
        each file is judged on its own, whatever `iso_week` it claims (fourth review, N3)."""
        weeks = {iso_week(w.day) for mode in ("canary", "live") for w in self.windows.get(mode, [])}
        for _path, r in sorted(exports.items()):
            wk_judged = bool(self.export_weeks(r) & weeks)
            ic = r.rec.get("inbox_checks")
            complete = isinstance(ic, dict) and all(k in ic and isinstance(ic[k], t) and
                                                    (t != (int,) or _int(ic[k]))
                                                    for k, t in INBOX_CHECK_TYPES.items())
            app = ic.get("app_repositories") if isinstance(ic, dict) else None
            app_ok = isinstance(app, dict) and isinstance(app.get("repository_selection"), str) and \
                isinstance(app.get("full_names"), list) and all(isinstance(n, str) for n in app["full_names"])
            if not (complete and app_ok) and wk_judged:
                self.F.w("A12", "inbox_checks_missing", r.path, r.commit,
                         "no complete inbox_checks for a judged week" if not complete else
                         "inbox_checks lacks a readable app_repositories for a judged week", owner_attested=True)
            if isinstance(app, dict):
                bad = []
                if "repository_selection" in app and app["repository_selection"] != "selected":
                    bad.append(safe_detail("repository_selection", str(app["repository_selection"])))
                names = app.get("full_names") if isinstance(app.get("full_names"), list) else []
                bad += sorted({n for n in names if isinstance(n, str) and
                               n.rsplit("/", 1)[-1].lower() in APP_FORBIDDEN})
                if bad:
                    self.F.v("A12", "app_scope", r.path, r.commit, safe_detail(*bad), owner_attested=True)
            if not isinstance(ic, dict):
                continue
            hook, config = [], []
            if _int(ic.get("hooks")) and ic["hooks"] > 0:
                hook.append("hooks")
            if _int(ic.get("security_log_hook_events")) and ic["security_log_hook_events"] > 0:
                hook.append("security_log_hook_events")
            if _int(ic.get("deploy_keys")) and ic["deploy_keys"] != 1:
                config.append("deploy_keys")
            if ic.get("actions_enabled") is True:
                config.append("actions_enabled")
            # §16.18 A7, detection 2 (R-AN-60): the security log's webhook events on the inbox, event by event
            events = ic.get("security_log_events")
            if isinstance(events, list) and events:
                hook.append(safe_detail("security_log_events", len(events)))
            if ic.get("security_log_hook_events") is not None:
                bad = self.security_log_gaps(ic)
                if bad:
                    self.F.w("A12", "inbox_checks_missing", r.path, r.commit, safe_detail(*bad), owner_attested=True)
            if hook:
                self.F.v("A12", "inbox_hook", r.path, r.commit, safe_detail(*hook), owner_attested=True)
            if config:
                self.F.v("A12", "inbox_config", r.path, r.commit, safe_detail(*config), owner_attested=True)

    def security_log_gaps(self, ic):
        """What keeps `inbox_checks`' security-log fields (R-AN-60, §16.18 A7 detection 2) from being consistent, while
        `security_log_hook_events` is not null (C7 found that the log records the inbox's webhook events):
        `security_log_events` missing, not a list, or of another length than the count (the register's rule); and
        (judge decision J-D38) an entry that is not `{action, created_utc, actor}` with an R-C4 `created_utc`, or a
        `security_log_filter` other than `repo:<PINS.inbox_repo> action:hook`, the filter the owner must apply."""
        bad = []
        events, n = ic.get("security_log_events"), ic.get("security_log_hook_events")
        if not isinstance(events, list):
            bad.append("security_log_events missing or not a list")
        else:
            if not (_int(n) and len(events) == n):
                bad.append(safe_detail("security_log_events length", len(events), "count", n if _int(n) else "?"))
            if not all(isinstance(e, dict) and isinstance(e.get("action"), str) and is_utc(e.get("created_utc"))
                       and isinstance(e.get("actor"), str) for e in events):
                bad.append("a security_log_events entry is not {action, created_utc, actor}")
        want = SECURITY_LOG_FILTER.format(self.inbox or "Mohamedalhaaj/gold-analyst-inbox")
        if ic.get("security_log_filter") != want:
            bad.append("security_log_filter is not the register's")
        return bad

    # ================================================================ the session guard's run logs (A13, R-AN-86)
    def check_run_logs(self, exports):
        """A13 (§16.18 A7; R-AN-67, R-AN-86), owner-attested: each runs export, file by file by its path (J-D33), each
        run with `created_utc` at or after PINS.inbox_from_utc (none without it, J-D20): its `tool_log`, missing or
        `absent` (`tool_log_missing`), and each logged call classified by the guard's string rules (R-AN-85, as
        `jlib/sessionguard.py` re-implements them) and R-AN-86's classes, with the session root P from the log, else
        from `analyst/canary/checks/C20.json` at HEAD. A run of `analyst-probe` follows the probe routine's rules; any
        other routine the four session routines' (judge decision J-D36)."""
        if self.inbox_from is None:
            return
        since = parse_utc(self.inbox_from)
        c20 = self.json_at_head(C20_PATH)
        c20_root = sessionguard.norm_root(c20.get("project_dir")) if isinstance(c20, dict) else None
        n_runs = n_calls = 0
        for _path, r in sorted(exports.items()):
            for x in r.rec.get("runs") or []:
                if not isinstance(x, dict):
                    continue
                ct = _utc_or_none(x.get("created_utc"))
                if ct is not None and ct < since:
                    continue
                run_id = safe_detail(x.get("run_id")) or "-"
                tl = x.get("tool_log")
                if not isinstance(tl, dict) or tl.get("form") not in ("full", "condensed", "absent") or \
                        not isinstance(tl.get("calls"), list) or tl.get("form") == "absent":
                    why = "no tool_log" if tl is None else ("form absent" if isinstance(tl, dict) and
                                                             tl.get("form") == "absent" else "tool_log unreadable")
                    self.F.w("A13", "tool_log_missing", r.path, run_id, why, owner_attested=True)
                    continue
                n_runs += 1
                pd = tl.get("project_dir")
                root = c20_root if pd is None else sessionguard.norm_root(pd)
                probe = x.get("routine") == "analyst-probe"
                for i, call in enumerate(tl["calls"], start=1):
                    n_calls += 1
                    seq = call.get("seq") if isinstance(call, dict) else None
                    label = f"{run_id}#{seq if _int(seq) else f'i{i}'}"
                    for code, detail in sessionguard.call_findings(call, root, probe):
                        add = self.F.v if code in sessionguard.VIOLATIONS else self.F.w
                        add("A13", code, r.path, label, safe_detail(detail), owner_attested=True)
        self.summary["run_logs_scanned"] = n_runs
        self.summary["run_log_calls_scanned"] = n_calls

    # ================================================================ the routines' connectors (A12, R-AN-61)
    def check_routine_config(self):
        """A12 `routine_connectors` (second review of A6, SEC-2), owner-attested: every version of
        `analyst/ROUTINE_CONFIG.json` committed to gold-analyst main (first-parent history; committer time, judge
        decision J-D26) at or after PINS.inbox_from_utc, and (fourth review, N3) the version in force at
        PINS.inbox_from_utc, in which a routine's `raw` lacks `mcp_connections` or `enabled_plugins`, or holds anything
        but the empty list in one. The version in force is the last commit of the first-parent history that adds or
        changes the file with a committer time before PINS.inbox_from_utc (none when a later such commit deletes it;
        judge decision J-D32); it is judged whether or not a later version replaced it. A version that is not a JSON
        record with a `routines` list, or a routine that is not an object with an object `raw`, cannot show the empty
        lists and is reported too. Key: the version's commit."""
        if self.inbox_from is None:
            return
        judged = self.routine_config_versions()
        for sha, _later in judged:
            bad = self.connector_breaches(self.git.show(sha, ROUTINE_CONFIG))
            if bad:
                self.F.v("A12", "routine_connectors", ROUTINE_CONFIG, sha, safe_detail(*bad), owner_attested=True)
        self.summary["routine_config_versions_checked"] = len(judged)

    def routine_config_versions(self):
        """The versions of `analyst/ROUTINE_CONFIG.json` that `routine_connectors` judges, oldest first, each with
        whether it was committed at or after PINS.inbox_from_utc: the version in force then (False) and every later one
        (True). Committer time (J-D26); the version in force is J-D32's."""
        since = parse_utc(self.inbox_from)
        judged = []
        in_force = None
        for sha, _parent, changes in self.log:
            sts = {st[:1] for st, p in changes if p == ROUTINE_CONFIG}
            if not sts:
                continue
            ct = self.git.commit_time(sha)
            if ct is None:
                continue
            if dt.datetime.fromtimestamp(ct, UTC) < since:
                in_force = sha if sts & {"A", "M", "T"} else None
            elif sts & {"A", "M", "T"}:
                judged.append((sha, True))
        if in_force is not None:
            judged.insert(0, (in_force, False))
        return judged

    # ================================================================ the routines' project (A13, R-AN-60, R-AN-61)
    def check_routine_project_config(self):
        """A13 `routine_project` (third review of §16.18 A7, decision 21; R-AN-61, R-AN-67), VIOLATION, owner-attested,
        operational, in each version of `analyst/ROUTINE_CONFIG.json` that `routine_connectors` judges: a routine whose
        `project` is present with a value other than null, or whose `raw` holds, at any depth, a key whose name
        contains `project` (case ignored) with a value other than null, "", [] or {}; in a version committed at or
        after PINS.inbox_from_utc, also a routine without the key `project` (judge decision J-D42: and a version or
        an entry that cannot show it, as `routine_connectors` reports them). The version in force at
        PINS.inbox_from_utc without the key gives nothing: the export in force before the decision has none. Key: the
        version's commit."""
        if self.inbox_from is None:
            return
        for sha, later in self.routine_config_versions():
            bad = project_breaches(_json_or_none(self.git.show(sha, ROUTINE_CONFIG)), later, raw=True)
            if bad:
                self.F.v("A13", "routine_project", ROUTINE_CONFIG, sha, safe_detail(*bad), owner_attested=True)

    def check_runs_routines(self, exports):
        """A13 `routine_project` (third review of §16.18 A7, decision 21; R-AN-60, R-AN-67), VIOLATION, owner-attested,
        operational, in each runs export, file by file by its path (J-D33): an entry of `routines` without the key
        `project`, or with a `project` other than null. Judge decision J-D41: without PINS.inbox_from_utc nothing is
        judged (as A13's run logs, J-D20), and a missing key counts only in an export added on main at or after
        PINS.inbox_from_utc (committer time of the commit that added the file), as the row's rule for the routine
        export in force; a `project` other than null counts in every export. J-D42: in such an export a `routines`
        that is missing or not a list cannot show `project` null and is reported too. Key: the commit that added the
        file."""
        if self.inbox_from is None:
            return
        since = parse_utc(self.inbox_from)
        for path, r in sorted(exports.items()):
            ct = self.git.commit_time(r.commit) if r.commit not in (None, "-") else None
            later = ct is None or dt.datetime.fromtimestamp(ct, UTC) >= since
            bad = project_breaches(r.rec, later, raw=False)
            if bad:
                self.F.v("A13", "routine_project", path, r.commit, safe_detail(*bad), owner_attested=True)

    @staticmethod
    def connector_breaches(b):
        """What keeps a ROUTINE_CONFIG.json version from showing `raw.mcp_connections` = [] and `raw.enabled_plugins`
        = [] for every routine (R-AN-61): routine names and field names only (enums for the report)."""
        try:
            rec = load_json_bytes(b) if b is not None else None
        except Exception:  # noqa: BLE001
            rec = None
        if not isinstance(rec, dict) or not isinstance(rec.get("routines"), list):
            return ["export unreadable or without routines"]
        bad = []
        for i, rt in enumerate(rec["routines"]):
            name = rt.get("name") if isinstance(rt, dict) and isinstance(rt.get("name"), str) else f"routine #{i}"
            raw = rt.get("raw") if isinstance(rt, dict) else None
            if not isinstance(raw, dict):
                bad.append(f"{name} raw unreadable")
                continue
            for k in CONNECTOR_LISTS:
                if k not in raw:
                    bad.append(f"{name} lacks {k}")
                elif raw[k] != []:
                    bad.append(f"{name} {k} not empty")
        return bad

    # ================================================================ session probes (A12, R-AN-84)
    def check_probes(self):
        """A12 `probe_failed` (VIOLATION): a canary call's `canary_probe`, or an `analyst/canary/checks/PROBE_<tag>.json`,
        with pass false for any probe, verdict `fail`, or an outcome its probe's "Pass iff" column fails (PROBE_FAILS).
        `probe_incomplete` (WARNING): a canary call whose probe verdict is not `pass` (judge decision J-D18: also a
        canary call without a readable `canary_probe`). The outcomes are self-reported by the session (R-AN-84)."""
        n = 0
        for p, r in sorted(self.records(PREFIX["canary"] + "calls/").items()):
            if not isinstance(r.rec, dict):
                continue
            cp = r.rec.get("canary_probe")
            if not isinstance(cp, dict):
                self.F.w("A12", "probe_incomplete", p, r.commit, "no canary_probe record")
                continue
            self.judge_probe(p, r.commit, cp, canary=True, context=r.rec.get("context"))
            n += 1
        for p, r in sorted(self.records(PREFIX["canary"] + "checks/").items()):
            if not re.fullmatch(r"PROBE_[^/]+\.json", p.rsplit("/", 1)[-1]):
                continue
            if not isinstance(r.rec, dict):
                self.F.w("A12", "probe_incomplete", p, r.commit, "probe record unreadable")
                continue
            self.judge_probe(p, r.commit, r.rec, canary=False)
            n += 1
        self.summary["probe_records"] = n

    def judge_probe(self, path, commit, rec, canary, context=None):
        passes = rec.get("pass") if isinstance(rec.get("pass"), dict) else {}
        outcomes = rec.get("outcomes") if isinstance(rec.get("outcomes"), dict) else {}
        failed = sorted(str(k) for k, v in passes.items() if v is False)
        failed += [k for k in probe_fails(outcomes, canary) if k not in failed]
        if canary and isinstance(context, dict) and context.get("schema") in CONTEXT_SCHEMAS:
            # R-AN-84 (A9): a canary's net.twelvedata is read from its context's first R-AN-87 request
            if outcomes.get("net.twelvedata") != td.probe_outcome(context.get("files")):
                failed.append("net.twelvedata differs from the context's first request")
        if failed or rec.get("verdict") == "fail":
            self.F.v("A12", "probe_failed", path, commit, safe_detail(*(failed or ["verdict fail"])))
        elif canary and rec.get("verdict") != "pass":
            self.F.w("A12", "probe_incomplete", path, commit, safe_detail("verdict", rec.get("verdict")))

    # ================================================================ the repository boundary (A12)
    def check_boundary(self):
        """A12 (A6): gold-analyst's branches, tags and runs; gold-analyst's rules for `claude/x`; and, with the inbox
        pinned, the inbox's identity, runs, rules, refs, main, rewrites and lag, and (second review) a flood of probe
        branches. Each part needs its read (A0 else)."""
        self.check_ga_refs()
        self.check_ga_runs()
        for br, need in GA_RULES.items():
            if br in self.ga_rules:
                got = {x.get("type") for x in self.ga_rules[br] if isinstance(x, dict)}
                if not need <= got:
                    self.F.w("A12", "inbox_rules", f"rules/{br}", "-", safe_detail("lacks", *sorted(need - got)))
        if self.inbox is not None:
            self.check_inbox()
            self.safe("probe_flood", self.check_probe_flood)

    def freeze_tags(self):
        """The `freeze_tag` values of analyst/PINS.json at every commit of main's first-parent history."""
        tags = set()
        for sha, _parent, changes in self.log:
            if any(p == "analyst/PINS.json" and st[:1] in ("A", "M", "T") for st, p in changes):
                b = self.git.show(sha, "analyst/PINS.json")
                try:
                    t = load_json_bytes(b).get("freeze_tag") if b is not None else None
                except Exception:  # noqa: BLE001
                    t = None
                if isinstance(t, str) and t:
                    tags.add(t)
        return tags

    def check_ga_refs(self):
        """`ga_branch`: a branch other than main (pull refs ignored); `ga_tag`: a tag whose name is no freeze tag of
        main's history, or whose (peeled) commit is not on main; `ga_tag_moved`: an allowed tag at another sha than its
        first `ga_ref` evidence row."""
        if self.ga_ls is None:
            return
        allowed = self.freeze_tags()
        peeled = {ref[:-3]: sha for sha, ref in self.ga_ls if ref.endswith("^{}")}
        for sha, ref in self.ga_ls:
            if ref == "HEAD" or ref.endswith("^{}") or ref.startswith("refs/pull/"):
                continue
            first = self.note_ref(ref, sha)
            if ref.startswith("refs/tags/"):
                name = ref[len("refs/tags/"):]
                if ref == DUKASCOPY_TAG[0]:
                    ok = peeled.get(ref, sha) == DUKASCOPY_TAG[1]   # §16.18 A9: that name at that commit only
                else:
                    ok = name in allowed and self.on_main(peeled.get(ref, sha))
                if not ok:
                    self.F.v("A12", "ga_tag", ref, sha, "a tag that is no freeze tag on main")
                elif first != sha:
                    self.F.v("A12", "ga_tag_moved", ref, sha, safe_detail("first seen at", first))
            elif ref != "refs/heads/main":
                self.F.v("A12", "ga_branch", ref, sha, "gold-analyst holds only main")

    def check_ga_runs(self):
        """`ga_run_branch`: a run of the day range whose head_branch is not main; from PINS.inbox_from_utc on,
        `ga_run_trigger` for a (path, event) outside R-AN-75's trigger table, `ga_dynamic_run` (WARNING) for a path
        under dynamic/. Each such run gets a `ga_run` evidence row."""
        if self.ga_runs is None:
            return
        seen = set()
        ev_runs = {(r["run_id"], r["run_attempt"]) for r in self.evidence_rows if r["source"] == "ga_run"}
        for run in self.ga_runs:
            if not isinstance(run, dict) or str(run.get("id")) in seen:
                continue
            rid = str(run.get("id"))
            seen.add(rid)
            hb, hs = run.get("head_branch") or "", run.get("head_sha") or "-"
            path, event = run.get("path") or "", run.get("event") or ""
            try:
                created = norm_api_time(run.get("created_at"))
            except (TypeError, ValueError):
                created = None
            key, hit = f"actions/runs/{rid}", False
            if hb != "main":
                self.F.v("A12", "ga_run_branch", key, hs, safe_detail("head_branch", hb))
                hit = True
            if self.inbox_from and created and created >= self.inbox_from:
                if path.startswith("dynamic/"):
                    self.F.w("A12", "ga_dynamic_run", key, hs, safe_detail(path, event))
                    hit = True
                elif event not in TRIGGERS.get(path, ()):
                    self.F.v("A12", "ga_run_trigger", key, hs, safe_detail(path, event))
                    hit = True
            att = str(run.get("run_attempt", ""))
            if hit and (rid, att) not in ev_runs:
                ev_runs.add((rid, att))
                self.evidence_new.append(self._ev("ga_run", run_id=rid, run_attempt=att, run_event=event,
                                                  run_created_utc=created, ref=f"refs/heads/{hb}" if hb else "",
                                                  push_after=run.get("head_sha") or ""))
        self.summary["ga_runs_read"] = len(seen)

    def check_inbox(self):
        """The inbox (PINS.inbox_repo): `inbox_identity`, `inbox_runs`, `inbox_rules` (WARNING), `inbox_ref`,
        `inbox_main_foreign`, `inbox_rewrite` and `inbox_stale` (WARNING), as R-AN-67's A6 table defines them. Since
        the fourth review (J-4) `inbox_identity` names what was seen (`404`, `id-<id read>` or `private`, the first
        that applies) and `inbox_runs` the `total_count` read, so a later incident is a new key."""
        if self.inbox_info_ok:
            info = self.inbox_info
            if not isinstance(info, dict):
                self.F.v("A12", "inbox_identity", "inbox", "404", "GET /repos answers 404")
            elif self.inbox_id is not None and info.get("id") != self.inbox_id:
                seen = "id-" + safe_detail(info.get("id")).replace("|", "?").replace(" ", "?")
                self.F.v("A12", "inbox_identity", "inbox", seen, safe_detail("id", info.get("id")))
            elif info.get("private") is True:
                self.F.v("A12", "inbox_identity", "inbox", "private", "the inbox is private")
        if _int(self.inbox_runs) and self.inbox_runs > 0:
            self.F.v("A12", "inbox_runs", "inbox/actions/runs", str(self.inbox_runs),
                     safe_detail("total_count", self.inbox_runs))
        for br, need in INBOX_RULES.items():
            if br in self.inbox_rules:
                got = {x.get("type") for x in self.inbox_rules[br] if isinstance(x, dict)}
                if not need <= got:
                    self.F.w("A12", "inbox_rules", f"inbox/rules/{br}", "-", safe_detail("lacks", *sorted(need - got)))
        inbox_main = None
        for sha, ref in self.inbox_ls or []:
            if ref == "HEAD" or ref.endswith("^{}") or ref.startswith("refs/pull/"):
                continue
            self.note_ref("inbox/" + ref, sha)
            if ref == "refs/heads/main":
                inbox_main = sha
            elif not ref.startswith("refs/heads/claude/"):
                self.F.v("A12", "inbox_ref", f"inbox/{ref}", sha, "the inbox holds only main and claude/**")
        mains = [e["after"] for e in self.inbox_entries if self.counts(e) and e["ref"] == "refs/heads/main" and
                 not _zero(e["after"]) and e["type"] != "branch_deletion"]
        for sha in dict.fromkeys(mains + ([inbox_main] if inbox_main else [])):
            if not self.on_main(sha):
                self.F.v("A12", "inbox_main_foreign", "inbox/refs/heads/main", sha, "not on gold-analyst main")
        for e in self.inbox_entries:
            if e["listed"] and self.counts(e) and e["type"] in ("force_push", "branch_deletion"):
                sha = e["before"] if e["type"] == "branch_deletion" else e["after"]
                self.F.v("A12", "inbox_rewrite", f"inbox/{e['ref']}", sha or "-", safe_detail("activity", e["type"]))
        if inbox_main and inbox_main != self.head and self.git.commit_exists(inbox_main) and \
                self.git.is_ancestor(inbox_main, self.head):
            old = self.git.oldest_missing(inbox_main, self.head)
            if old is not None:
                lag = self.now - dt.datetime.fromtimestamp(old[1], UTC)
                if lag > STALE:
                    self.F.w("A12", "inbox_stale", "inbox/refs/heads/main", inbox_main,
                             safe_detail("lacks", old[0][:12], "minutes", int(lag.total_seconds() // 60)))

    def check_probe_flood(self):
        """A12 `probe_flood` (VIOLATION; second review of A6, SEC-3): a `refs/heads/claude/probe-*` ref the inbox lists
        whose earliest inbox activity entry counts (timestamp >= PINS.inbox_from_utc) and whose name is not
        `claude/probe-<c3|del|wf|result>-<call_id | pYYYYMMDDTHHMMSSZ>` (R-AN-84); and more than 40 counting
        `branch_creation` entries on probe refs in one UTC day (key path `inbox/refs/heads/claude/probe-*`; fourth
        review, J-4: the sha slot holds that day, `YYYY-MM-DD`, so a later day's flood is a new key).
        The entries are the live list and the `inbox_activity` evidence rows, so a month-old flood still counts. A
        listed ref without a known entry is not judged (judge decision J-D28: its first entry predates the judge's
        reads, or this run's read failed)."""
        first = {}
        for e in self.inbox_entries:                       # sorted by (timestamp, id)
            if e["ts"] and e["ref"] not in first:
                first[e["ref"]] = e
        for sha, ref in self.inbox_ls or []:
            if not ref.startswith(PROBE_REF) or ref.endswith("^{}"):
                continue
            e = first.get(ref)
            if e is not None and self.counts(e) and not PROBE_NAME.fullmatch(ref):
                self.F.v("A12", "probe_flood", f"inbox/{ref}", sha, "a probe branch outside R-AN-84's names")
        per_day = {}
        for e in self.inbox_entries:
            if self.counts(e) and e["type"] == "branch_creation" and e["ref"].startswith(PROBE_REF):
                per_day[e["ts"][:10]] = per_day.get(e["ts"][:10], 0) + 1
        for d in sorted(d for d, n in per_day.items() if n > PROBE_DAY_CAP):   # fourth review: one key per day
            self.F.v("A12", "probe_flood", "inbox/refs/heads/claude/probe-*", d,
                     safe_detail(f"{d} {per_day[d]} creations"))
        self.summary["probe_creations_max_day"] = max(per_day.values(), default=0)

    def pause_intervals(self):
        """[(start, end)] UTC datetimes when calls were disabled as inbox main showed them (R-AN-67 "A10's pause
        intervals, as inbox main showed them"; register decision 33; judge decisions J-D14 and J-D31 as amended there,
        J-D34): from V(PAUSED), else the PAUSED event's utc, to V(RESUMED) of the RESUMED event that closes its subject
        (after its first `clear:` or `lifted:`, fourth review of A6), open while V(RESUMED) is none (no fixed grace);
        from V(RETIRED), else its utc, on. V is `main_time`. A PAUSED for a subject already open keeps the first; the
        intervals cover canary and live windows alike (J-D31)."""
        out = []
        evs = []
        for p, r in sorted(self.records("analyst/state/").items()):
            if isinstance(r.rec, dict) and r.rec.get("schema") == "analyst-state-event/1":
                evs.append((r.rec, r.commit))
        evs.sort(key=lambda x: x[0].get("seq") or 0)
        open_ = {}
        for e, commit in evs:
            try:
                t = parse_utc(e.get("utc"))
            except (ValueError, TypeError):
                continue
            if e.get("event") == "PAUSED":
                open_.setdefault(e.get("reason"), self.main_time(t, commit) or t)
            elif e.get("event") == "RESUMED":
                _kind, subj = resumed_subject(e.get("reason"))
                if subj is not None and subj in open_:
                    out.append((open_.pop(subj), self.main_time(t, commit) or NEVER))
            elif e.get("event") == "RETIRED":
                out.append((self.main_time(t, commit) or t, NEVER))
        for s in open_.values():
            out.append((s, NEVER))
        return out

    def main_time(self, t, commit):
        """V(e) of a PAUSED, RESUMED or RETIRED event e dated `t` and added in `commit` (the commit J-D30 finds; R-AN-67,
        decision 33): the timestamp of the earliest (timestamp, id) known inbox activity entry (live list or
        `inbox_activity` evidence rows) with timestamp >= PINS.inbox_from_utc, on `refs/heads/main`, whose `after` is
        `commit` or has it as an ancestor (`shows`); None while no such entry is known. Without PINS.inbox_repo
        (J-D20: sessions read gold-analyst itself) and for an event dated before PINS.inbox_from_utc, the event's own
        utc `t` is kept."""
        if not getattr(self, "inbox", None) or (self.inbox_from is not None and t < parse_utc(self.inbox_from)):
            return t
        for e in getattr(self, "inbox_entries", None) or []:          # sorted by (timestamp, id)
            if self.counts(e) and e["ref"] == "refs/heads/main" and not _zero(e["after"]) and \
                    e["type"] != "branch_deletion" and self.shows(e["after"], commit):
                try:
                    return parse_utc(e["ts"])
                except ValueError:
                    continue
        return None

    def shows(self, after, commit) -> bool:
        """Inbox main at `after` holds gold-analyst commit `commit`: `after` is on gold-analyst main (the clone's main,
        else main after its one fresh fetch; an `after` that is not, A12 `inbox_main_foreign`, gives no time) and is
        `commit` or has it as an ancestor. Main's first-parent history answers without git; any other commit is asked
        of git."""
        if not isinstance(after, str) or not re.fullmatch(r"[0-9a-f]{40}", after) or \
                not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            return False
        if getattr(self, "_fp_pos", None) is None:
            self._fp_pos = {c: i for i, (c, _parent, _changes) in enumerate(self.log)}
            self._shows = {}
        if after in self._fp_pos and commit in self._fp_pos:
            return self._fp_pos[after] >= self._fp_pos[commit]
        if (after, commit) not in self._shows:
            self._shows[(after, commit)] = self.on_main(after) and (after == commit or (
                self.git.commit_exists(commit) and self.git.is_ancestor(commit, after)))
        return self._shows[(after, commit)]

    # ================================================================ settlement, twins, E, K, states, ledger (A11)
    def check_settlement_and_state(self):
        days_b = self.bytes_at_head("mirror/system/days.csv")
        if days_b is None:
            self.summary["settled_checked"] = 0
            return
        try:
            days = DaysTable(days_b)
        except ValueError:
            self.F.w("A11", "mirror_days", "mirror/system/days.csv", "-", "unreadable")
            return
        settled = self.records("analyst/settled/")
        twins_r = self.records("analyst/twins/")
        trades = []
        twins = []
        processed = set()
        n_checked = 0
        rows_expected = []
        live_wins = self.windows.get("live", [])
        by_day = {}
        for win in live_wins:
            info = self.terminal_info.get(("live", win.call_id))
            if info is None:
                continue
            by_day.setdefault(win.day, []).append((win, info))
        store = Store(days, lambda p: self.bytes_at_head(p))
        for win in live_wins:
            info = self.terminal_info.get(("live", win.call_id))
            if info is None:
                continue
            two = (win.day - dt.timedelta(days=1), win.day)
            for x in two:
                store.load_day(x)
            final_inputs = all(days.row(x, s) is not None and days.row(x, s)["status"] in ("ok", "missing")
                               for x in two for s in ("BID", "ASK"))
            bad_store = any(m[0] in (two[0].isoformat(), two[1].isoformat()) for m in store.mismatch)
            processable = final_inputs and not bad_store and self.now >= win.exit
            mins = settle.Minutes(store, win)
            void = settle.is_void(days, win.day)
            sp = f"analyst/settled/{win.call_id}.json"
            tp = f"analyst/twins/{win.call_id}.json"
            cls = "counted" if (self.first_day is not None and win.day >= self.first_day) else "shakedown"
            row = {"call_id": win.call_id, "model_day": win.day.isoformat(), "window": win.w,
                   "terminal_status": info["status"], "status": info["status"], "class": cls,
                   "terminal_sha256": sha256_bytes(info["term"].raw)}
            if win.call_id in self.overlay:
                row["status"] = "no_call:model"
            call = info["call"] or {}
            out = None
            if info["status"] == "called" and isinstance(call.get("S_dimes"), int):
                s = call.get("side")
                out = settle.settle_side(mins, s, call["S_dimes"], call["T_dimes"], void) if processable else None
                sr = settled.get(sp)
                if sr is None:
                    if processable and self.now >= win.exit + SETTLE_GRACE:
                        self.F.w("A11", "unsettled", sp, "-", "processable trade without a settled record")
                elif out is None:
                    self.F.w("A11", "settled_unverifiable", sp, sr.commit, "inputs at HEAD not final")
                else:
                    n_checked += 1
                    mm = self.compare_settled(sr, out, mins, s, call, info, cls, days)
                    if mm:
                        self.F.w("A11", "settled_mismatch", sp, sr.commit, safe_detail(*mm[:12]))
                if out is not None and sr is not None and cls == "counted" and win.call_id not in self.overlay:
                    o = out
                    trades.append({"call_id": win.call_id, "model_day": win.day, "w": win.w, "side": s,
                                   "y": o["y"], "R": o["R"], "net": o["net_usd"], "stress": o["stress_net_usd"],
                                   "cost": o["cost_usd"]})
                row.update({"out": out})
            # twin (§16.18 A14: every status but skipped:*)
            if not str(info["status"]).startswith("skipped:"):
                tw = settle.twin(mins, void) if processable else None
                trc = twins_r.get(tp)
                if trc is None:
                    if processable and self.now >= win.exit + SETTLE_GRACE:
                        self.F.w("A11", "untwinned", tp, "-", "processed window without a twin")
                elif tw is not None:
                    mm = self.compare_twin(trc, tw, win, info)
                    if mm:
                        self.F.w("A11", "twin_mismatch", tp, trc.commit, safe_detail(*mm))
                if tw is not None and tw[5] == "final":
                    twins.append((win.day, win.w, tw[4]))
                row["d_W"] = tw[4] if tw else None
            rows_expected.append(row)
        for d, lst in by_day.items():
            ok = True
            for win, info in lst:
                if str(info["status"]).startswith("skipped:"):
                    continue
                if f"analyst/twins/{win.call_id}.json" not in twins_r:
                    ok = False
                if info["status"] == "called" and f"analyst/settled/{win.call_id}.json" not in settled:
                    ok = False
            # every expected window of d processed; (§16.18 A14-D14) for d >= a14_from also once d's trading ended
            n_exp = sum(1 for w in live_wins if w.day == d)
            if ok and len(lst) == n_exp and (self.a14_day is None or d < self.a14_day or
                                              self.now >= model_to_utc(dt.datetime(d.year, d.month, d.day) +
                                                                       dt.timedelta(days=1))):
                processed.add(d)
        self.summary["settled_checked"] = n_checked
        # E path over counted trades (window order), ledger and state
        ys = [t["y"] for t in trades]
        epath = stats.e_path(ys)
        for t, e in zip(trades, epath):
            t["E"] = e
        self.check_ledger(rows_expected, trades)
        self.check_states(trades, twins, processed, rows_expected)

    def compare_settled(self, sr, out, mins, s, call, info, cls, days):
        r = sr.rec if isinstance(sr.rec, dict) else {}
        mm = []
        if sr.raw != record_form(r):
            mm.append("record_form")
        exp_fixed = {"schema": "analyst-settled/1", "call_id": info["win"].call_id, "mode": "live",
                     "window": info["win"].w, "model_day": info["win"].day.isoformat(), "class": cls,
                     "action": (call.get("plan") or {}).get("action"), "side": s,
                     "S_dimes": call.get("S_dimes"), "T_dimes": call.get("T_dimes"),
                     "entry_utc": fmt_utc(info["win"].entry), "exit_utc": fmt_utc(info["win"].exit),
                     "call_sha256": sha256_bytes(info["call_raw"].raw),
                     "terminal_sha256": sha256_bytes(info["term"].raw),
                     "context_sha256": call.get("context_sha256")}
        for k, v in exp_fixed.items():
            if r.get(k) != v:
                mm.append(k)
        for k in ("stop_mult", "target_mult", "D_ref", "S", "T"):
            src = call.get(k) if k != "D_ref" else (call.get("d_ref") or {}).get("D_ref")
            if not num_exact(r.get(k), src):
                mm.append(k)
        if r.get("context") != call.get("context"):
            mm.append("context")
        plan = call.get("plan") or {}
        want_call = {k: plan.get(k) for k in ("action", "stop_mult", "target_mult", "confidence", "reason_ar",
                                              "key_risks_ar")}
        rc = r.get("call") or {}
        if any(not (rc.get(k) == v or num_exact(rc.get(k), v)) for k, v in want_call.items()):
            mm.append("call")
        mm += [f"outcome.{x}" for x in _cmp_outcome(r.get("outcome"), out)]
        opp = settle.settle_side(mins, -s, call["S_dimes"], call["T_dimes"], out["status"] == "void")
        mm += [f"opposite.{x}" for x in _cmp_outcome(r.get("opposite"), opp)]
        ps = settle.path_summary(mins, s, out)
        if ps is not None:
            mm += [f"path_summary.{x}" for x in _cmp_path(r.get("path_summary"), ps)]
        inp = r.get("inputs") or {}
        head_sha = r.get("head_sha")
        if isinstance(head_sha, str) and self.git.commit_exists(head_sha):
            db = self.git.show(head_sha, "mirror/system/days.csv")
            if db is None or inp.get("days_csv_sha256") != sha256_bytes(db):
                mm.append("inputs.days_csv_sha256")
            else:
                dtab = DaysTable(db)
                want = []
                for x in (info["win"].day - dt.timedelta(days=1), info["win"].day):
                    for sd in ("BID", "ASK"):
                        rw = dtab.row(x, sd) or {}
                        want.append({"day": x.isoformat(), "side": sd, "status": rw.get("status"),
                                     "sha256": rw.get("sha256") or None})
                got = [{k: (d.get(k) or None) if k == "sha256" else d.get(k) for k in ("day", "side", "status",
                                                                                         "sha256")}
                       for d in (inp.get("days") or []) if isinstance(d, dict)]
                if got != want:
                    mm.append("inputs.days")
        else:
            mm.append("head_sha")
        return mm

    def compare_twin(self, trc, tw, win, info):
        r = trc.rec if isinstance(trc.rec, dict) else {}
        mm = []
        me, mes, mx, mxs, dW, status = tw
        want = {"schema": "analyst-twin/1", "call_id": win.call_id, "mode": "live", "window": win.w,
                "model_day": win.day.isoformat(), "terminal_status": info["status"], "entry_utc": fmt_utc(win.entry),
                "exit_utc": fmt_utc(win.exit), "status": status}
        for k, v in want.items():
            if r.get(k) != v:
                mm.append(k)
        if status == "final":
            if not (price_eq(r.get("mid_entry"), me) and price_eq(r.get("mid_exit"), mx)):
                mm.append("mids")
            if r.get("mid_entry_src") != mes or r.get("mid_exit_src") != mxs:
                mm.append("mid_src")
            if not rel_eq(r.get("d_W"), dW):
                mm.append("d_W")
        elif r.get("d_W") is not None:
            mm.append("d_W")
        return mm

    def terminals_at_last_change(self, path):
        """call_ids of the live terminal records present at the last main commit that changed `path` (a snapshot is
        compared with the state of the records when it was written)."""
        last = None
        for sha, _parent, changes in self.log:
            if any(p == path for _st, p in changes):
                last = sha
        if last is None:
            return None
        return {p.rsplit("/", 1)[-1][:-5] for p in self.git.ls_tree(last, "analyst/terminal/")}

    def check_ledger(self, rows_expected, trades):
        b = self.bytes_at_head("analyst/ledger.csv")
        if b is None:
            if rows_expected:
                self.F.w("A11", "ledger_missing", "analyst/ledger.csv", "-", "")
            return
        try:
            led = list(csv.DictReader(io.StringIO(b.decode("utf-8"))))
        except Exception:  # noqa: BLE001
            self.F.w("A11", "ledger_unreadable", "analyst/ledger.csv", "-", "")
            return
        by = {r.get("call_id"): r for r in led}
        tno = {t["call_id"]: (i + 1, t) for i, t in enumerate(trades)}
        bad = []
        # the ledger is a snapshot: compare the windows whose terminal existed at its last commit
        known = self.terminals_at_last_change("analyst/ledger.csv")
        for row in rows_expected:
            if known is not None and row["call_id"] not in known:
                continue
            lr = by.get(row["call_id"])
            if lr is None:
                bad.append(f"{row['call_id']}:missing")
                continue
            for k in ("model_day", "window", "terminal_status", "status", "terminal_sha256"):
                if lr.get(k, "") != str(row[k]):
                    bad.append(f"{row['call_id']}:{k}")
            if row["call_id"] in tno:
                i, t = tno[row["call_id"]]
                if lr.get("trade_no") != str(i) or not rel_eq(_f(lr.get("E")), t["E"]) or \
                        not rel_eq(_f(lr.get("y")), t["y"]):
                    bad.append(f"{row['call_id']}:trade")
            elif lr.get("trade_no", "") != "":
                bad.append(f"{row['call_id']}:trade_no")
            o = row.get("out")
            if o is not None and not rel_eq(_f(lr.get("net_usd")), o["net_usd"]):
                bad.append(f"{row['call_id']}:net_usd")
            if row.get("d_W") is not None and not rel_eq(_f(lr.get("d_W")), row["d_W"]):
                bad.append(f"{row['call_id']}:d_W")
        if bad:
            self.F.w("A11", "ledger_mismatch", "analyst/ledger.csv", "-", safe_detail(*bad[:12]))

    def check_states(self, trades, twins, processed, rows_expected):
        evs = []
        for p, r in sorted(self.records("analyst/state/").items()):
            if not isinstance(r.rec, dict) or r.rec.get("schema") != "analyst-state-event/1":
                self.F.w("A11", "state_event_form", p, r.commit, "")
                continue
            evs.append(r)
        evs.sort(key=lambda r: r.rec.get("seq") or 0)
        replay = stats.replay_states(trades, twins, self.first_day, processed)
        got = [(r.rec.get("event"), r.rec.get("reason"), r.rec.get("model_day"), r.rec.get("n"), r.rec.get("E"))
               for r in evs if r.rec.get("event") in ("TESTING", "PROMOTED", "DEMOTED", "RETIRED") and
               r.rec.get("reason") != "violation"]
        want = [(e, rs, d.isoformat(), n, E) for (e, rs, d, n, E, _K) in replay]
        if len(got) > len(want) or any(g[:3] != w[:3] or g[3] != w[3] or not rel_eq(g[4], w[4])
                                       for g, w in zip(got, want)):
            self.F.w("A11", "state_events", "analyst/state/", "-", safe_detail("recorded", len(got), "replayed",
                                                                               len(want)))
        elif len(want) > len(got):
            last = want[len(got)]
            self.F.w("A11", "state_event_missing", "analyst/state/", "-", safe_detail(last[0], last[1], last[2]))
        # PAUSED model:<run_id> needs an overlay; pauses, resumes and retirements follow R-AN-55 (check_state_events)
        for r in evs:
            e = r.rec
            if e.get("event") == "PAUSED" and str(e.get("reason", "")).startswith("model:"):
                if str(e["reason"])[6:] not in set(self.overlay.values()):
                    self.F.w("A11", "pause_unsupported", r.path, r.commit, "no exported run on another model")
        self.check_state_events(evs)
        for run_id in set(self.overlay.values()):
            if not any(r.rec.get("event") == "PAUSED" and r.rec.get("reason") == f"model:{run_id}" for r in evs):
                self.F.w("A11", "overlay_missing", "analyst/state/", "-", safe_detail("run", run_id))
        # STATE.json snapshot
        S = self.json_at_head("analyst/STATE.json")
        if S is None:
            return
        bad = []
        lpd = S.get("last_processed_day")
        upto = [t for t in trades if lpd and t["model_day"].isoformat() <= lpd]
        if S.get("n") != len(upto):
            bad.append("n")
        if not rel_eq(S.get("E"), stats.e_value([t["y"] for t in upto])):
            bad.append("E")
        if S.get("E_star") not in (400, 400.0):
            bad.append("E_star")
        promo = [r.rec.get("model_day") for r in evs if r.rec.get("event") == "PROMOTED"]
        post = [t["y"] for t in upto if promo and t["model_day"].isoformat() > promo[0]]
        if not rel_eq(S.get("K"), stats.k_value(post) if promo else 1.0):
            bad.append("K")
        if (S.get("first_day") or None) != (self.first_day.isoformat() if self.first_day else None):
            bad.append("first_day")
        latched = [r.rec.get("event") for r in evs if r.rec.get("event") in ("TESTING", "PROMOTED", "DEMOTED",
                                                                                 "RETIRED")]
        want_state = latched[-1] if latched else "SHAKEDOWN"
        if S.get("state") != want_state:
            bad.append("state")
        if upto:
            share = max(sum(1 for t in upto if t["side"] == 1), sum(1 for t in upto if t["side"] == -1)) / len(upto)
            if not rel_eq(S.get("side_share"), share) or S.get("side_label") != (share > 0.85):
                bad.append("side_share")
        known = self.terminals_at_last_change("analyst/STATE.json")
        last40 = [r for r in rows_expected if not str(r["terminal_status"]).startswith("skipped:") and
                  (known is None or r["call_id"] in known)][-40:]
        if last40:
            ms = sum(1 for r in last40 if r["status"].startswith(("missed:", "no_call:"))) / len(last40)
            if not rel_eq(S.get("missed_share_40"), ms) and not (ms == 0 and S.get("missed_share_40") in (0, 0.0)):
                bad.append("missed_share_40")
            if S.get("paused_display") != (ms > 0.15):
                bad.append("paused_display")
        if bad:
            self.F.w("A11", "state_snapshot", "analyst/STATE.json", "-", safe_detail(*bad))

    def mode_at(self, commit):
        """(P0, LS) from analyst/MODE.json in `commit` (HEAD when unknown), R-AN-55: P0 is 00:00:00Z of the earliest
        of `canary_from` and `live_from` that is set, LS 00:00:00Z of `live_from`; None when unset."""
        cache = self._mode_at
        c = commit if commit and commit != "-" else self.head
        if c not in cache:
            b = self.git.show(c, "analyst/MODE.json")
            try:
                m = load_json_bytes(b) if b is not None else None
            except Exception:  # noqa: BLE001
                m = None
            m = m if isinstance(m, dict) else {}

            def day0(k):
                v = m.get(k)
                if not is_day(v):
                    return None
                try:
                    return dt.datetime.combine(dt.date.fromisoformat(v), dt.time(), UTC)
                except ValueError:
                    return None
            starts = [x for x in (day0("canary_from"), day0("live_from")) if x is not None]
            cache[c] = (min(starts) if starts else None, day0("live_from"))
        return cache[c]

    def verdict_at(self, commit):
        """`judge_verdict` of analyst/STATE.json in `commit` (an object), or None."""
        if not commit or commit == "-":
            return None
        b = self.git.show(commit, "analyst/STATE.json")
        try:
            S = load_json_bytes(b) if b is not None else None
        except Exception:  # noqa: BLE001
            return None
        jv = S.get("judge_verdict") if isinstance(S, dict) else None
        return jv if isinstance(jv, dict) else None

    def fresh_at(self, commit) -> bool:
        """analyst/STATE.json in `commit` shows `judge_verdict.fresh` true (R-AN-56, fourth review of A6, N2)."""
        jv = self.verdict_at(commit)
        return jv is not None and jv.get("fresh") is True

    def verdict_floor(self, commit):
        """L_prev of `commit` (§16.18 A7 decision 15; R-AN-56, R-AN-67 A11, R-AN-70): the largest
        `judge_verdict.last_fresh_asof_utc` among the versions of analyst/STATE.json in main's first-parent history
        before that commit (the commit's own version not included); None when there is none."""
        if self._floor is None:
            self._floor, m = {}, None
            for sha, _parent, changes in self.log:
                self._floor[sha] = m
                if any(p == "analyst/STATE.json" and st[:1] in ("A", "M", "T") for st, p in changes):
                    jv = self.verdict_at(sha)
                    t = _utc_or_none(jv.get("last_fresh_asof_utc")) if jv is not None else None
                    if t is not None and (m is None or t > m):
                        m = t
        return self._floor.get(commit)

    def older_verdict(self, commit) -> bool:
        """Decision 15: the commit's analyst/STATE.json shows a `judge_verdict.asof_utc` earlier than L_prev, so the
        analyst acted on a verdict older than one it had already used, which is not fresh. No condition while L_prev
        is none; an `asof_utc` that is not an R-C4 time cannot be shown not to be earlier (judge decision J-D37)."""
        floor = self.verdict_floor(commit)
        if floor is None:
            return False
        jv = self.verdict_at(commit)
        asof = _utc_or_none(jv.get("asof_utc")) if jv is not None else None
        return asof is None or asof < floor

    def p7_gaps(self, commit):
        """The judge's recompute of P7 (R-AN-53) for a PROMOTED event, from analyst/STATE.json in the commit that added
        it (judge decision J-D37): a fresh verdict (`judge_verdict.fresh` true) that is not VIOLATION and, since A7
        (decision 15), not older than one the analyst had already used."""
        jv = self.verdict_at(commit)
        bad = []
        if jv is None or jv.get("fresh") is not True:
            bad.append("no fresh verdict")
        elif jv.get("value") == "VIOLATION":
            bad.append("verdict VIOLATION")
        if self.older_verdict(commit):
            bad.append("a verdict older than one already used")
        return bad

    @staticmethod
    def mirrored(subject, paused, LS) -> bool:
        """R-AN-55: a pause of subject `judge_violation:K` is mirrored when K is operational, or LS is none, or its
        PAUSED event's utc < LS. Every other judge pause is a live integrity pause."""
        K = subject[len("judge_violation:"):]
        return operational(K) or LS is None or paused < LS

    def check_state_events(self, evs):
        """A11 (WARNING; fourth review of §16.18 A6, J-4; R-AN-55, R-AN-56, R-AN-67): the pause rule's events.
        The open pauses are replayed by seq (PAUSED opens its reason; RESUMED closes the subject after its first
        `clear:` or `lifted:`); P0 and LS come from analyst/MODE.json in the commit that added each event.
        - `resume_unsupported`: a RESUMED `clear:<S>` without an analyst/ADJUDICATIONS.csv row for S, ref `pause`,
          decision `clear`, dated at or after S's PAUSED event and at or before the RESUMED event, or whose S is a
          mirrored pause (or `judge_silent`: only `model:` and live integrity pauses are cleared, R-AN-55 step 1);
          a RESUMED `lifted:<S>` whose commit's analyst/STATE.json does not show `judge_verdict.fresh` true, or whose S
          is a live integrity pause (or a `model:` pause: only mirrored pauses and `judge_silent` are lifted, steps 3
          and 4), or, for S = `judge_violation:K` with K latched (not A0, not `system_error:`), without a clear row
          for K in the judge's ADJUDICATIONS.csv dated at or before the RESUMED event; and (judge decision J-D30) a
          RESUMED whose reason is neither, or whose subject has no open pause;
        - `retire_unsupported`: a RETIRED `violation` dated before LS, or with no earlier RESUMED
          `clear:judge_violation:K'` event for a live integrity pause (the analyst was not armed); *(sixth review,
          R6-2)* or that no integrity key supports by time: a VIOLATION key of the judge's FINDINGS.csv, not
          operational, first seen strictly after the arming time A and no later than 10 min after the RETIRED
          event (R-AN-70's tolerance), with no earlier PAUSED event for its subject and no clear row for it in the
          judge's ADJUDICATIONS.csv dated at or before the RETIRED event. A is the earliest clear time of the live
          integrity pauses that earlier RESUMED `clear:` events closed: the utc of the pause's earliest
          analyst/ADJUDICATIONS.csv clear row dated at or after its PAUSED event, else the RESUMED event's utc;
        - `pause_early`: a PAUSED `judge_violation:<K>` or `judge_silent` dated before P0, or with no P0.
        - *(§16.18 A7, decision 15)* `resume_unsupported` for a `lifted:` resume, and `retire_unsupported` for a
          RETIRED `violation`, whose commit's STATE.json shows a `judge_verdict.asof_utc` earlier than the largest
          `last_fresh_asof_utc` of the versions before it (an older verdict is not fresh, R-AN-70); and
          `promote_unsupported` for a PROMOTED event whose commit's STATE.json fails the judge's recompute of P7
          (judge decision J-D37: a fresh verdict, not VIOLATION, not older)."""
        pause_rows = {}
        adj = self.bytes_at_head("analyst/ADJUDICATIONS.csv") or b""
        try:
            for a in csv.DictReader(io.StringIO(adj.decode("utf-8"))):
                t = _utc_or_none(a.get("utc"))
                if a.get("ref") == "pause" and a.get("decision") == "clear" and t is not None:
                    pause_rows.setdefault(a.get("subject"), []).append(t)
        except Exception:  # noqa: BLE001
            pass
        judge_rows = {}
        for a in self.judge_adjudications:
            t = _utc_or_none(a.get("utc"))
            if a.get("ref") == "latch" and a.get("decision") == "clear" and t is not None:
                judge_rows.setdefault(a.get("subject"), []).append(t)
        first_seen = {}                       # the judge's FINDINGS.csv: VIOLATION key -> first_seen_utc
        for row in self.judge_findings:
            ft = _utc_or_none(row.get("first_seen_utc"))
            if ft is not None and row.get("severity") == VIOLATION and row.get("key"):
                first_seen[row["key"]] = ft
        open_ = {}
        ever_paused = set()
        arm_times = []                        # the clear times of the live integrity pauses cleared so far
        for r in evs:
            e = r.rec
            ev, reason = e.get("event"), str(e.get("reason") or "")
            t = _utc_or_none(e.get("utc"))
            P0, LS = self.mode_at(r.commit)
            if ev == "PAUSED":
                if (reason.startswith("judge_violation:") or reason == "judge_silent") and t is not None and \
                        (P0 is None or t < P0):
                    self.F.w("A11", "pause_early", r.path, r.commit,
                             safe_detail("paused before P0", fmt_utc(P0) if P0 else "no period set"))
                ever_paused.add(reason)
                if t is not None:
                    open_.setdefault(reason, t)
            elif ev == "RESUMED":
                kind, subj = resumed_subject(reason)
                paused = open_.get(subj) if kind else None
                why, live_int = None, False
                if kind is None:
                    why = "neither clear: nor lifted:"
                elif paused is None:
                    why = "no open pause for its subject"
                elif t is None:
                    why = "event time unreadable"
                else:
                    judge_pause = subj.startswith("judge_violation:")
                    mir = judge_pause and self.mirrored(subj, paused, LS)
                    live_int = judge_pause and not mir
                    if kind == "clear":
                        if not (subj.startswith("model:") or live_int):
                            why = "a clear of a pause the verdict lifts"
                        elif not any(paused <= c <= t for c in pause_rows.get(subj, [])):
                            why = "no owner clear row dated from the pause to the resume"
                    else:
                        K = subj[len("judge_violation:"):] if judge_pause else None
                        if not (subj == "judge_silent" or mir):
                            why = "a lift of a pause only a clear ends"
                        elif not self.fresh_at(r.commit):
                            why = "its commit's STATE.json shows no fresh verdict"
                        elif self.older_verdict(r.commit):
                            why = "its commit's STATE.json shows a verdict older than one already used"
                        elif K is not None and not K.startswith(("A0|", "system_error:")) and \
                                not any(c <= t for c in judge_rows.get(K, [])):
                            why = "a latched key without the judge's clear row"
                if why:
                    self.F.w("A11", "resume_unsupported", r.path, r.commit, why)
                if kind == "clear" and live_int:
                    # a live integrity pause the owner cleared (R-AN-55 step 2): its clear time is its row's utc
                    rows = [c for c in pause_rows.get(subj, []) if c >= paused]
                    arm_times.append(min(rows) if rows else t)
                if subj is not None and subj in open_:
                    open_.pop(subj)
            elif ev == "PROMOTED":
                bad = self.p7_gaps(r.commit)
                if bad:
                    self.F.w("A11", "promote_unsupported", r.path, r.commit, safe_detail("P7 false", *bad))
            elif ev == "RETIRED" and reason == "violation":
                if t is None or LS is None or t < LS:
                    self.F.w("A11", "retire_unsupported", r.path, r.commit, "a retirement before live_from")
                elif self.older_verdict(r.commit):
                    self.F.w("A11", "retire_unsupported", r.path, r.commit,
                             "its commit's STATE.json shows a verdict older than one already used")
                elif not arm_times:
                    self.F.w("A11", "retire_unsupported", r.path, r.commit,
                             "no earlier clear of a live integrity pause")
                else:
                    A = min(arm_times)
                    if not any(A < ft <= t + FIRST_SEEN_SLACK and not operational(K)
                               and f"judge_violation:{K}" not in ever_paused
                               and not any(c <= t for c in judge_rows.get(K, []))
                               for K, ft in first_seen.items()):
                        self.F.w("A11", "retire_unsupported", r.path, r.commit,
                                 safe_detail("no integrity key first seen after the live clear", fmt_utc(A)))

    # ================================================================ mirror vs source (A11)
    def check_mirror_source(self):
        if self.store_git is None:
            self.F.w("A0", "source_store_unavailable", "mirror/system/", "-",
                     "gold-forward-watch not readable: the mirror is not compared with its source")
            return
        sg = self.store_git
        shead = sg.head()
        bad = []
        md = self.bytes_at_head("mirror/system/days.csv")
        sd = sg.show(shead, "data/system/days.csv")
        if md is not None and (sd is None or not sd.startswith(md)):
            self.F.w("A11", "mirror_days", "mirror/system/days.csv", "-", "not a byte prefix of the source days.csv")
        ms = self.bytes_at_head("mirror/system/forecasts_slots.csv")
        sf = sg.show(shead, "data/system/forecasts.csv")
        if ms is not None:
            if sf is None:
                bad.append("forecasts")
            else:
                lines = sf.decode("utf-8").split("\n")
                keep = [lines[0]] + [ln for ln in lines[1:] if ln and ln.split(",")[1:2] and
                                     ln.split(",")[1] in ("9", "10", "15")]
                want = ("\n".join(keep) + "\n").encode("utf-8")
                if not want.startswith(ms):
                    self.F.w("A11", "mirror_slots", "mirror/system/forecasts_slots.csv", "-",
                             "not a prefix of the source's slot 9/10/15 lines")
        # §16.18 A14-D10 (R-AN-12 step 3b): the whole forecast store, a byte prefix of the source, and its sha256 the
        # latest exports.csv row's forecasts_sha256
        mf = self.bytes_at_head("mirror/system/forecasts.csv")
        if mf is not None:
            if sf is None or not sf.startswith(mf):
                self.F.w("A11", "mirror_forecasts", "mirror/system/forecasts.csv", "-",
                         "not a byte prefix of the source forecasts.csv")
            try:
                rows = list(csv.DictReader(io.StringIO((self.bytes_at_head("mirror/exports.csv") or b"")
                                                       .decode("utf-8"))))
            except Exception:  # noqa: BLE001
                rows = []
            if not rows or rows[-1].get("forecasts_sha256") != sha256_bytes(mf):
                self.F.w("A11", "mirror_forecasts", "mirror/system/forecasts.csv", "-",
                         "the latest exports.csv row's forecasts_sha256 is not the copy's sha256")
        for p in self.git.ls_tree(self.head, "mirror/system/raw/"):
            src = "data/system/raw/" + p[len("mirror/system/raw/"):]
            a = self.bytes_at_head(p)
            b = sg.show(shead, src)
            if b is None or a != b:
                self.F.w("A11", "mirror_raw", p, self.commit_of(p), "differs from the source raw file")
        eb = self.bytes_at_head("mirror/exports.csv")
        if eb:
            try:
                for r in csv.DictReader(io.StringIO(eb.decode("utf-8"))):
                    if not sg.commit_exists(r.get("source_sha", "")):
                        self.F.w("A11", "mirror_export_sha", "mirror/exports.csv", "-",
                                 safe_detail("source_sha unknown", r.get("source_sha", "")[:12]))
            except Exception:  # noqa: BLE001
                self.F.w("A11", "mirror_export_sha", "mirror/exports.csv", "-", "unreadable")

    # ================================================================ the live macro calendar (A4, §16.18 A12-D19)
    def check_macro_calendar(self, R):
        """A4 `macro_calendar` (§16.18 A12-D17..D19; R-AN-10, R-AN-67 A4), VIOLATION, once per repo_head_sha of an
        `analyst-context/3` call: the file `analyst/calendars/macro_2026_2027.csv` at R against the build's rows (the
        judge's own copy, sha256-pinned, J-D52) and the `sha256` values logged for it in `analyst/ops_changes.csv` at
        R. Key `A4|macro_calendar|<path>|<R>`; detail: clock.macro_problems' codes."""
        if R in self._macro_seen:
            return
        self._macro_seen.add(R)
        probs = macro_problems(self.git.show(R, MACRO_PATH), self.git.show(R, OPS_PATH))
        if probs:
            self.F.v("A4", "macro_calendar", MACRO_PATH, R, safe_detail(*probs[:8]))

    # ================================================================ frozen inputs (A11)
    def check_frozen(self):
        b = self.bytes_at_head("analyst/vendor/eproc.py")
        if b is None or sha256_bytes(b) != EPROC_SHA256:
            self.F.w("A11", "eproc_sha", "analyst/vendor/eproc.py", "-", "not the lab's frozen eproc.py (R-AN-7)")
        from .clock import BLS_SHA256, FOMC_SHA256
        for name, sha in (("bls_2026_2027.csv", BLS_SHA256), ("fomc_2026_2027.csv", FOMC_SHA256)):
            p = f"analyst/calendars/{name}"
            x = self.bytes_at_head(p)
            if x is None or sha256_bytes(x) != sha:
                self.F.w("A11", "calendar_sha", p, "-", "not R-V1-15's file")
        if self.holidays.table_error:
            self.F.w("A11", "holiday_table", "analyst/tables/holidays.csv", "-", self.holidays.table_error)
        else:
            miss, extra = self.holidays.mismatch_up_to_horizon()
            if miss or extra:
                self.F.w("A11", "holiday_table", "analyst/tables/holidays.csv", "-",
                         safe_detail(f"{len(miss)} register rows missing", f"{len(extra)} rows not in the register"))
        man = self.bytes_at_head("analyst/FROZEN_ANALYST.sha256")
        if man is not None:
            listed = set()
            for line in man.decode("utf-8", "replace").split("\n"):
                if not line.strip():
                    continue
                sha, _, path = line.partition("  ")
                listed.add(path)
                x = self.bytes_at_head(path)
                if x is None or sha256_bytes(x) != sha:
                    self.F.w("A11", "frozen_drift", path, "-", "file differs from FROZEN_ANALYST.sha256 at HEAD")
            # §16.18 A7 (R-AN-7): the manifest lists the guard's files and the probe session's prompt, so that a
            # change of the guard is frozen drift; unlisted, `guard.py` could not be checked at all (judge decision
            # J-D39), since the judge never reads it otherwise (R-AN-66)
            for path in sessionguard.FROZEN_A7:
                if path not in listed:
                    self.F.w("A11", "frozen_unlisted", path, "-", "not listed in FROZEN_ANALYST.sha256 (R-AN-7)")
        else:
            self.F.w("A11", "frozen_drift", "analyst/FROZEN_ANALYST.sha256", "-", "manifest missing")

    # ================================================================ the sessions' Claude Code version (A13)
    def check_cc_versions(self):
        """A13 `cc_version_below` and `cc_version_unknown` (third review of §16.18 A7, decision 22; R-AN-25, R-AN-29,
        R-AN-67, R-AN-85 "Claude Code version"), VIOLATION, operational, self-reported. The records are the `*.json`
        files directly in `analyst/attempts/`, `analyst/calls/`, `analyst/canary/attempts/` and
        `analyst/canary/calls/` at gold-analyst main's head; one is a guarded session's when its `repo_head_sha` names
        a gold-analyst commit whose tree holds `.claude/hooks/guard.py` (a sha that names no commit is A4's finding,
        not this one; judge decision J-D43). `cc_version_below`: its `self_reported.cc_version` is of R-AN-85's form
        and below 2.1.295. `cc_version_unknown`: an attempt record's is unknown by that rule, a missing or non-object
        `self_reported` included; a call file comes from the same session as its attempt record, so it is checked for
        `cc_version_below` only. Key: the record's path and the commit that added it. The version is the session's own
        report: it can show an old or unknown harness, and cannot prove a new one."""
        n = 0
        for folder in CC_RECORD_FOLDERS:
            attempts = folder.endswith("attempts/")
            for p, r in sorted(self.records(folder).items()):
                if not (p.endswith(".json") and isinstance(r.rec, dict) and
                        self.guarded(r.rec.get("repo_head_sha"))):
                    continue
                n += 1
                sr = r.rec.get("self_reported")
                v = sr.get("cc_version") if isinstance(sr, dict) else None
                cls = sessionguard.cc_version_class(v)
                if cls == "below":
                    seen = ".".join(str(int(x)) for x in v.split(" ", 1)[0].split("."))
                    self.F.v("A13", "cc_version_below", p, r.commit,
                             safe_detail(f"self-reported cc_version {seen}", "below 2.1.295 (R-AN-85)"))
                elif cls == "unknown" and attempts:
                    why = ("self_reported missing or not an object" if not isinstance(sr, dict) else
                           "cc_version missing" if "cc_version" not in sr else
                           "cc_version null" if v is None else
                           "cc_version not a string" if not isinstance(v, str) else
                           "cc_version not of R-AN-85's form")
                    self.F.v("A13", "cc_version_unknown", p, r.commit,
                             safe_detail(f"self-reported cc_version unknown: {why}", "minimum 2.1.295 (R-AN-85)"))
        self.summary["cc_version_records_checked"] = n

    def guarded(self, sha) -> bool:
        """Whether `sha` (a record's `repo_head_sha`) names a gold-analyst commit whose tree holds
        `.claude/hooks/guard.py` (J-D43: 40 hex digits in either case, a commit object in the clone). Only the tree
        entry is read: `guard.py` itself never is (R-AN-66)."""
        if not isinstance(sha, str) or not _SHA40.fullmatch(sha):
            return False
        sha = sha.lower()
        if sha not in self._guarded:
            self._guarded[sha] = self.git.commit_exists(sha) and self.git.has_blob(sha, sessionguard.GUARD_PATH)
        return self._guarded[sha]

    # ================================================================ the guard's files (A13 guard_config)
    def check_guard_config(self):
        """A13 `guard_config` (§16.18 A7; R-AN-2 as replaced, R-AN-67, R-AN-85; prereg R1 Isolation (a), (f)),
        VIOLATION, operational, at gold-analyst main's head: `.claude/settings.json` missing, not JSON, or parsed to
        an object other than R-AN-85's; `.claude/hooks/guard.py` missing (never read here: A11 hashes it against
        the manifest, R-AN-66); any other path under a `.claude/` folder (judge decision J-D40: at any depth); a file
        named `.mcp.json`, `CLAUDE.md`, `CLAUDE.local.md` or `AGENTS.md` anywhere. Key `<path>|<blob sha>`, or
        `absent`, so the same content keeps its key. (Before A7 a `CLAUDE.md`, `AGENTS.md` or `.claude/` was A3
        `forbidden_file`; R-AN-2 as replaced makes it this operational code.)"""
        tree = set(self.git.ls_tree(self.head))
        for path in sessionguard.GUARD_FILES:
            if path not in tree:
                self.F.v("A13", "guard_config", path, "absent", "missing at main's head")
        if sessionguard.SETTINGS_PATH in tree:
            b = self.bytes_at_head(sessionguard.SETTINGS_PATH)
            try:
                obj = load_json_bytes(b) if b is not None else None
                same = b is not None and compact_form(obj) == compact_form(sessionguard.GUARD_SETTINGS)
            except Exception:  # noqa: BLE001
                same = False
            if not same:
                self.F.v("A13", "guard_config", sessionguard.SETTINGS_PATH,
                         self.git.object_id(self.head, sessionguard.SETTINGS_PATH) or "-",
                         "not the object of R-AN-85")
        for p in sorted(tree):
            parts = p.split("/")
            if p in sessionguard.GUARD_FILES:
                continue
            if ".claude" in parts[:-1] or parts[-1] in sessionguard.FORBIDDEN_NAMES:
                self.F.v("A13", "guard_config", p, self.git.object_id(self.head, p) or "-",
                         "a file a one-repository session would load (R-AN-2)")

    # ================================================================ history (A7)
    def check_history(self):
        for sha, parent, changes in self.log:
            for st, p in changes:
                kind = st[:1]
                if _CREATE_ONLY.match(p) or _WRITE_ONCE.match(p):
                    if kind in ("M", "D", "T"):
                        self.F.v("A7", "modified" if kind != "D" else "deleted", p, sha,
                                 "create-only/write-once file changed on main")
                elif p in APPEND_ONLY:
                    if kind == "D":
                        self.F.v("A7", "append_break", p, sha, "append-only file deleted")
                    elif kind in ("M", "T") and parent:
                        old = self.git.show(parent, p) or b""
                        new = self.git.show(sha, p) or b""
                        if not new.startswith(old) or (old and not old.endswith(b"\n")):
                            self.F.v("A7", "append_break", p, sha, "not a whole-line append")
        if self.prev_anchor:
            if not self.git.commit_exists(self.prev_anchor) or not self.git.is_ancestor(self.prev_anchor, self.head):
                self.F.v("A7", "anchor", "reports/judge_analyst/VERDICTS.csv", self.prev_anchor,
                         "main does not descend from the judge's previous anchor")


def _json_or_none(b):
    try:
        return load_json_bytes(b) if b is not None else None
    except Exception:  # noqa: BLE001
        return None


def _empty(v) -> bool:
    """null, "", [] or {}: the values a `raw` field named like `project` may hold (R-AN-61; by type, so false and 0
    are values)."""
    return v is None or (type(v) is str and v == "") or (type(v) is list and not v) or (type(v) is dict and not v)


def _project_fields(x):
    """The values of every key whose name contains `project` (case ignored), at any depth of x (objects and lists)."""
    out, stack = [], [x]
    while stack:
        y = stack.pop()
        if isinstance(y, dict):
            for k, v in y.items():
                if isinstance(k, str) and "project" in k.lower():
                    out.append(v)
                stack.append(v)
        elif isinstance(y, list):
            stack.extend(y)
    return out


def project_breaches(rec, later: bool, raw: bool):
    """What keeps an export (a ROUTINE_CONFIG.json version, raw=True, or a runs export, raw=False) from showing that
    no routine is in a claude.ai project (A13 `routine_project`, R-AN-60, R-AN-61, R-AN-67): a `project` present and
    not null; with raw, a field of `raw` named like `project` holding a value; and, when the export is `later` (a
    missing key counts: J-D41), a routine without `project`, an entry that is not an object, or no `routines` list
    (J-D42). Routine names and enums only: no value is printed."""
    routines = rec.get("routines") if isinstance(rec, dict) else None
    if not isinstance(routines, list):
        return ["export unreadable or without a routines list"] if later else []
    bad = []
    for i, rt in enumerate(routines):
        if not isinstance(rt, dict):
            if later:
                bad.append(f"routine #{i} not an object, lacks project")
            continue
        name = rt["name"] if isinstance(rt.get("name"), str) else f"routine #{i}"
        if "project" in rt:
            if rt["project"] is not None:
                bad.append(f"{name} project not null")
        elif later:
            bad.append(f"{name} lacks project")
        if raw and not all(_empty(v) for v in _project_fields(rt.get("raw"))):
            bad.append(f"{name} raw holds a project field with a value")
    return bad


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _in(s, lo, hi):
    try:
        t = parse_utc(s)
    except (TypeError, ValueError):
        return False
    return lo <= t <= hi


def _cmp_outcome(rec, out):
    if not isinstance(rec, dict):
        return ["missing"]
    mm = []
    want_keys = {"status", "P_e", "P_e_src", "P_e_minute_utc", "X", "Tg", "exit_minute_utc", "P_x", "reason", "fill",
                 "cost_usd", "gross_usd", "net_usd", "stress_net_usd", "R", "R_stress", "y"}
    if set(rec.keys()) != want_keys:
        mm.append("keys")
    if rec.get("status") != out["status"]:
        return mm + ["status"]
    if out["status"] != "final":
        for k in ("net_usd", "stress_net_usd", "R", "R_stress", "y", "cost_usd"):
            if not rel_eq(rec.get(k), out[k]) and not (out[k] == 0 and rec.get(k) in (0, 0.0)):
                mm.append(k)
        if rec.get("gross_usd") is not None and not rel_eq(rec.get("gross_usd"), out["net_usd"]):
            mm.append("gross_usd")
        return mm
    for k in ("P_e_src", "P_e_minute_utc", "exit_minute_utc", "reason", "fill"):
        if rec.get(k) != out[k]:
            mm.append(k)
    for k in ("P_e", "X", "Tg", "P_x"):
        if not price_eq(rec.get(k), out[k]):
            mm.append(k)
    for k in ("cost_usd", "gross_usd", "net_usd", "stress_net_usd", "R", "R_stress", "y"):
        a, b = rec.get(k), out[k]
        if not (rel_eq(a, b) or (isinstance(a, (int, float)) and abs(a - b) <= 1e-12)):
            mm.append(k)
    return mm


def _cmp_path(rec, ps):
    if not isinstance(rec, dict):
        return ["missing"]
    mm = []
    rb = rec.get("buckets")
    if not isinstance(rb, list) or len(rb) != 16:
        mm.append("buckets")
    else:
        for a, b in zip(rb, ps["buckets"]):
            if not isinstance(a, dict) or a.get("k") != b["k"] or a.get("n") != b["n"]:
                mm.append(f"buckets[{b['k']}]")
                continue
            if b["n"] and not all(price_eq(a.get(x), b[x]) for x in ("o", "h", "l", "c")):
                mm.append(f"buckets[{b['k']}]")
    for k in ("mfe_usd", "mae_usd", "range_mid_usd"):
        a, b = rec.get(k), ps[k]
        if not (rel_eq(a, b) or (a is not None and b is not None and abs(a - b) <= 1e-9)):
            mm.append(k)
    if rec.get("exit_after_min") not in (ps["exit_after_min"], ps["exit_after_min"] + 1):
        mm.append("exit_after_min")
    return mm
