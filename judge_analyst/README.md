# judge_analyst: the analyst judge (blind build)

The independent judge of Analyst v1 (xauusd-quant `research/analyst/ANALYST_V1_PREREG.md` DRAFT v0.6, §8 as amended
by "Change v0.5" M7 and "Change v0.6"; `research/system/IMPLEMENTATION_REGISTER.md` §16, R-AN-66..R-AN-70 and the items
they cite, with the dated amendment §16.18 A6, the agent inbox, as revised after its review, its second review, its
fourth review, its fifth review and its sixth review; xauusd-quant 62a0d80, fourth review 5d7fcdc, fifth review
166c6b0, sixth review decision 35; and the dated amendment §16.18 A7, the session guard, xauusd-quant f16708e, with
its first, second and third reviews, decisions 17 to 22; third review xauusd-quant 12ffdda; and the dated amendment
§16.18 A9, the model day's market data from Twelve Data, xauusd-quant b3816ca; and the dated amendment §16.18 A12,
`analyst-context/3` and `analyst-plan/2`, xauusd-quant a7c9989, with its addendum A12-D17..D21, the live event
calendar, xauusd-quant 55c0a4f). A6, A7, A9 and A12 bind once the client approves
their text; until then they are the build's target.
It was built **blind**: from the prereg, the register and the record locations the register names, without reading
the analyst code under `analyst/**`. Where the analyst code and the register differ, the judge reports a finding to
adjudicate (`spec_gap`, `judge_error` or `system_error`, as J5).

**Location (R-AN-1; prereg R1(a)).** The judge lives in gold-forward-watch, beside judge v1 (`judge/`, untouched),
on the branch `analyst-judge` until it is merged. It was moved here from gold-analyst on 2026-10-23 (review blocker
B3; register §16 dated note): the move changed only `run_judge.py` (paths and arguments), the workflow, this README and
the tests; `jlib/` is byte-identical to the blind build. gold-analyst holds no judge code and no judge outputs.

**Blind.** It reads the public gold-analyst as data only: a full clone named with `--repo`, read through git objects
(`cat-file`, `ls-tree`, `log`, `diff`), never from its working tree, never imported or executed. It reads records,
mirrored inputs, owner files and frozen inputs; an analyst code file is read only when the analyst's own
`FROZEN_ANALYST.sha256` lists it, and then only hashed against that line (A11 `frozen_drift`). Tests:
`tests/test_judge_location.py` (imports: standard library and `jlib` only) and `test_the_judge_reads_no_analyst_code`.

**The agent inbox (§16.18 A6).** Routine sessions push only to the public `Mohamedalhaaj/gold-analyst-inbox`
(PINS.inbox_repo, Actions off), whose main is a fast-forward copy of gold-analyst main. The judge reads the agent's
pushes from the inbox's activity log, counted only at or after PINS.inbox_from_utc, fetches their commits by sha from
the inbox into the gold-analyst clone (data only), and judges the repository boundary as check A12. Every A6 input is
a public read (GETs and `git ls-remote`); no write permission was added. Tests: `tests/test_judge_inbox.py` (the
planted cases of every new code, written from the register text) and `tests/test_judge_sources.py` (the reads).
After A6's second review (decisions 20-23; SEC-1, SEC-2, SEC-3) the judge also reports the App's repository list
(`app_scope`) and the routines' connectors (`routine_connectors`), both owner-attested, a flood of probe branches
(`probe_flood`), and a judge blind to the inbox for more than a day (A0 `inbox_blind`, a VIOLATION); the inbox's
activity is read for the last month only. Tests: `tests/test_judge_second_review.py`.
After A6's fourth review (decisions 24-32; J-3, J-4, N2, N3): `inbox_blind` needs at least two failed runs after a
last complete read more than a day old, counted from new `inbox_read_failed` evidence rows, and its key names its
episode; every VIOLATION key names its incident (`inbox_identity` what was seen, `inbox_runs` the run count, the
`probe_flood` day count its day); the deploy keys and the Actions switch are their own code, `inbox_config`;
`routine_connectors` also judges the version in force at PINS.inbox_from_utc; each runs export is judged by its own
path; A11 checks the analyst's pause, lift and retirement events against R-AN-55's pause rule (`resume_unsupported`,
`retire_unsupported`, `pause_early`); a Sunday backstop run. Tests: `tests/test_judge_fourth_review.py`.
After J-5 (fifth review, register decision 33): A10 judges calls as inbox main showed them. A pause interval runs from
when inbox main first held its PAUSED event (else the event's `utc`) to when it first held its RESUMED event, open while
that is unknown, and a run is not judged when an interval meets [its created_utc, its window's deadline_utc − T_run]
(J-D34). Tests: `tests/test_judge_fifth_review.py`.
After R6-2 (sixth review, register decision 35): the verdict carries each key's first-seen time
(`violation_first_seen`), and A11 `retire_unsupported` judges a retirement by time: an integrity key first seen
after the owner's earliest live clear row (J-D35). Tests: `tests/test_judge_sixth_review.py`.

**The session guard (§16.18 A7; R-AN-85, R-AN-86, R-AN-60, R-AN-67, R-AN-70).** gold-analyst carries a PreToolUse hook,
`.claude/settings.json` and `.claude/hooks/guard.py`, mirrored to the inbox, that refuses every tool call of a routine
session that is not one of its own steps. The judge never reads, parses or runs `guard.py` (A11 hashes it against
FROZEN_ANALYST.sha256); `jlib/sessionguard.py` re-implements the guard's string rules and R-AN-86's classes from the
register text. New check A13:
- from the owner's weekly copy of the run logs (`tool_log {form, project_dir, calls}` of each run of each runs export,
  file by file; owner-attested): a forbidden call the rules refuse, refused (`forbidden_attempt`) or run
  (`forbidden_executed`), both integrity VIOLATIONs; the guard not acting (`guard_not_enforced`: a harmless near-miss
  that ran, or a call something other than the guard refused), an operational VIOLATION; and the WARNINGs
  `guard_denied_benign`, `allowed_call_refused`, `scan_unclassifiable`, `probe_elsewhere`, `tool_log_missing`. A run
  of `analyst-probe` (C20's session, whose prompt asks for refused calls) gives nothing for a refused call that was
  refused, and `guard_not_enforced` for one that ran. The session root P is the log's `project_dir`, else C20.json's;
- `guard_config` (operational VIOLATION) at gold-analyst main's head: `.claude/settings.json` missing, not JSON or not
  R-AN-85's object, `.claude/hooks/guard.py` missing, any other path under a `.claude/` folder, or a `.mcp.json`,
  `CLAUDE.md`, `CLAUDE.local.md` or `AGENTS.md` anywhere (this replaces A3 `forbidden_file`: R-AN-2 now requires the
  guard's two files).

Also: A12 `inbox_hook` from the security log's events (`inbox_checks.security_log_events`, detection 2) and
`inbox_checks_missing` for missing or inconsistent security-log fields; A11 decision 15, a `lifted:` resume, a
RETIRED `violation` or a PROMOTED event on a verdict older than the newest `last_fresh_asof_utc` before it is
unsupported (`resume_unsupported`, `retire_unsupported`, the new `promote_unsupported`, with the judge's recompute of
P7, J-D37); A11 `frozen_unlisted` for a frozen manifest without the guard's files or the probe session's prompt
(R-AN-7). Tests: `tests/test_judge_session_guard.py`.

**A7's third review (decisions 21 and 22; notes N1 and N2; R-AN-25, R-AN-60, R-AN-61, R-AN-67, R-AN-85).** Three
new A13 codes, all operational VIOLATIONs (they pause the analyst while the verdict carries them and never retire it):
- `routine_project` (owner-attested; decision 21, no routine in a claude.ai project, whose cloud threads run no
  repository hook): in a version of `analyst/ROUTINE_CONFIG.json` that `routine_connectors` judges, a routine whose
  `project` is present and not null, or whose `raw` holds, at any depth, a key whose name contains `project` (case
  ignored) with a value other than null, `""`, `[]` or `{}`; in a version committed at or after PINS.inbox_from_utc,
  also a routine without `project`. In a runs export, file by file, an entry of `routines` without `project` (only in
  an export added at or after PINS.inbox_from_utc, J-D41) or with a `project` other than null. What cannot show
  `project` null where a missing key counts is reported too (J-D42). Key
  `A13|routine_project|<export path>|<commit>`. The routine export in force on gold-analyst main (d1725d7) has no
  `project` key, and that alone gives nothing;
- `cc_version_below` and `cc_version_unknown` (self-reported; decision 22, `onFailure` needs Claude Code 2.1.295 or
  later): the `*.json` attempt records and call files directly in `analyst/attempts/`, `analyst/calls/` and the same
  under `analyst/canary/`, at main's head, of a guarded session (its `repo_head_sha` names a commit whose tree holds
  `.claude/hooks/guard.py`, read from the tree entry only). R-AN-85's version rule (`jlib/sessionguard.py`
  `cc_version_class`): below 2.1.295 is `cc_version_below`; an attempt record's unknown version (missing, null, not a
  string, not of the form, or no `self_reported` object) is `cc_version_unknown`; a call file gives `cc_version_below`
  only. Key `A13|<code>|<record path>|<the commit that added it>`.

A probe record's `cc_version` (R-AN-84) is not judged here (C20 judges it); a probe record that carries one stays
readable, and A12 `probe_failed` and `probe_incomplete` are unchanged. Tests: `tests/test_judge_guard_third_review.py`.

**Twelve Data (§16.18 A9; R-AN-87, R-AN-17..R-AN-19, R-AN-23, R-AN-66..R-AN-69, R-AN-84).** Sessions now take the
model day's listed XAU hours, P_ref and the five FX pairs from Twelve Data hourly bars, through a network secret the
judge never sees; history still comes from the store mirror. `jlib/td.py` re-implements R-AN-87's rules from the
register text (never imported from gold-analyst). The judge never calls Twelve Data (it holds no key; a record must
stand on its own):
- A4 accepts only `analyst-context/2` (`context_schema`, a VIOLATION, for any other schema, since calls exist only
  from the first canary day on; since §16.18 A12 also `analyst-context/3`, paired with repo_head_sha, below).
  It rebuilds the context from the mirror at `repo_head_sha`, the recorded provenance
  objects of `files`, asof_utc and PARAMS: every request at its position must be R-AN-87's (XAUUSD only with listed
  hours, the five pairs, `fresh`), with the exact URL (no other parameter, no `apikey`), `status` and `reason`
  following `http`, `td_code` and `tries` by R-AN-87's table (`budget` iff no try, and nothing tried after a
  `budget`), and bars only at the hours R-AN-87 names (XAUUSD: listed hours; a pair: t0 and h_new; `fresh`: its one
  newest element), in time order, with o, h, l, c > 0, l <= min(o, c), h >= max(o, c), and none unless `ok`. The
  stops: nothing after an XAUUSD failure while a listed hour is required (`td_<reason>`) or after a required hour
  without a bar (`hour_absent`); none at all with `store_stale`. Listed-hour bars are `src` "td" with n null; P_ref is
  the newest one's c, timed at the hour's end; p0 and p1 are the o of the t0 bar and the c of the h_new bar; `fresh`
  and the fixed `sources` note are compared exactly. Twelve Data values are exact copies of the recorded bars
  (R-AN-68).
- A11 cross-checks the recorded values against the judge's own Dukascopy downloads on its runner (R-AN-16's URL and
  status rules; `hours.csv`): the o and the c of each XAUUSD bar against the first and last tick mid of that hour, and
  each pair's p0 and p1 against the first tick mid of t0 and the last of h_new, when both bars exist. Outside
  relative 1e-3: `A11|td_mismatch|<call path>|<commit>`, a WARNING that needs an ADJUDICATIONS row, listing every
  compared value with its Dukascopy value and relative difference. A value whose file is not `present` is fetched
  again at each run while the model day is at most 3 weekdays old, then gives `A11|td_unchecked|<call path>|<commit>`
  (an optional XAU hour whose file is `empty` is skipped). The run summary counts `td_compared`, `td_outside` (the
  freeze's 5% share, A9-D14), `td_pending` and `td_unchecked`.
- R-AN-84: `net.twelvedata` passes only on 200; in a canary its outcomes 0, −2, 429 and 500-599 are null, and it must
  equal what the context's first R-AN-87 request gives (XAUUSD, else `fresh`; 200 iff ok, −1 for `invalid`, else its
  td_code; −2 without one), or `probe_failed`. `net.dukascopy` 200 now fails in both kinds (J-D44).
- A12 `ga_tag` allows one more tag, `analyst-dukascopy-v0.6`, peeled to 79b9247901f15ee40d14d0f33cc8001f89bf31ce and
  to no other commit.
The judge's `analyst-context/1` rebuild (re-downloaded hour files, `A11 hour_sha`, `A0 hours_unavailable`,
`A4 inadmissible_hour`) is in gold-forward-watch's history before A9; an inadmissible hour is now a bar at an hour
R-AN-87 does not name (`context_differs`). Tests: `tests/test_judge_a9.py`; the world's contexts are
`analyst-context/2` and its probe records carry `net.twelvedata` 200 and `net.dukascopy` 0.

**Context 3 and plan 2 (§16.18 A12; R-AN-14, R-AN-16, R-AN-17, R-AN-19, R-AN-23, R-AN-26, R-AN-28, R-AN-67 A4 and
A5, R-AN-68, R-AN-87, R-AN-88; decisions A12-D6..D9).** A call at or after the A12 build commit carries
`analyst-context/3`: one more Twelve Data request, `AUDJPY` (symbol `AUD/JPY`, the pairs' URL form), after USD/CHF and
before `fresh`; the risk proxy `risk` after `fx`; the computed `levels` after `d_ref`; and `bars_d1` over 25 history
weekdays from start_lv. `jlib/levels.py` re-implements R-AN-88 from the register text (never imported from
gold-analyst). The judge never calls Twelve Data:
- A4 pairs each call's schema with its `repo_head_sha` through the pin `jlib/config.py` `A12_BUILD_COMMIT`: `/3` iff
  the pinned commit is repo_head_sha or one of its ancestors, `/2` otherwise; any other pairing is `context_schema`
  (detail: the schema and the one expected). The pin is None until the A12 build commit is on gold-analyst main, so
  until then every call must be `/2`. A `/3` context is rebuilt like a `/2` one plus: the `AUDJPY` request at its
  position (R-AN-87's URL, status/reason, bars at t0 and h_new only; none after an XAUUSD stop or a missing required
  hour); `risk` from its recorded bars (p0 the o at t0, p1 the c at h_new: exact; pct relative 1e-9; null when the
  request was not made, is not `ok` or lacks a bar, and then the window stands); `bars_d1` (25 weekdays, from the store
  at the mirror at repo_head_sha, loaded from start_lv's UTC date) and `bars_h1` (still from start_hist) exactly;
  `levels` recomputed from the recorded `bars_h1`, `bars_d1`, `levels.asia.hist`, `p_ref` and `d_ref`, prices exact and
  each rounded field within 0.5·10^−k + 1e-9 of the judge's unrounded value (k = 2 for dist_* and the ratios, 3 for
  ret_*), a null only against a null, and `levels.asia.hist` against the judge's own rebuild from the mirror. `levels`
  is null whenever the status is not `ok`.
- A5 judges a `/3` call's plan as `analyst-plan/2`: a stay_out has `stay_out_reason`, exactly one of `event_risk`,
  `no_setup`, `conflicting_signals`, `mid_range`; a trade has none. A `/2` call keeps the old key set. The judge does
  not check `event_risk` against `events` (the lock does not either; the canary report counts it, R-AN-73).
- A11 cross-checks AUDJPY's p0 and p1 against the first tick mid of the Dukascopy `AUDJPY` t0 hour and the last tick
  mid of its h_new hour (R-AN-16: 1000 points per unit), with the 1e-3 rule and the findings `td_mismatch` and
  `td_unchecked` unchanged.
Tests: `tests/test_judge_a12.py`; the world's `a12_from` option pushes an owner A12 build commit on that day, so its
later contexts are `analyst-context/3` (and its stay_out plans carry `stay_out_reason`), and `store_first` starts the
store early enough for 25 weekdays.

**The live event calendar (§16.18 A12-D17..D21; R-AN-10, R-AN-20, R-AN-23, R-AN-67 A4).** Decisions, as the judge
implements them:
- D17: the build's `analyst/calendars/macro_2026_2027.csv` (136 rows of PPI, JOLTS, GDP, PCE, RETAIL, ISM_MFG, ISM_SVC,
  CLAIMS and ECB, 2026-10-29..2027-12-30) is kept as the judge's own byte copy `calendars/macro_2026_2027_build.csv`,
  pinned to the register's sha256 68a4c46c... (`clock.MACRO_BUILD_SHA256`). NFP, CPI and FOMC stay in the frozen,
  sha256-pinned BLS and FOMC copies.
- D18: a `/3` context's `events` is rebuilt exactly: `today` and `next` carry twelve flags (`nfp`, `cpi`, `fomc`,
  `ppi`, `jolts`, `gdp`, `pce`, `retail`, `ism_mfg`, `ism_svc`, `claims`, `ecb`; 1, 0, or null after the kind's last
  event in the file read), and `today_times_utc`/`next_times_utc` are lists of `{"kind", "utc"}`, one per distinct
  (kind, time) of the model date, sorted by `utc` then `kind`. A `/2` context keeps three flags and time strings. The
  judge does not check `event_risk` against `events` (A12-D18: the lock checks the value only; `event_risk_unlisted`
  is the canary report's, which the judge does not compute).
- D19: the nine kinds come from the file at the call's `repo_head_sha` (read through the clone, never from main's
  head). A file there that cannot be read as rows (missing, not UTF-8, another header, a row of another width, an
  event outside the nine, a `ts_utc` not of D17's form) leaves the context unreproducible (`context_unreproducible`,
  detail `macro_calendar`). Once per such `repo_head_sha` of a `/3` call the judge checks D19's rules and reports a
  break as `A4|macro_calendar|analyst/calendars/macro_2026_2027.csv|<repo_head_sha>` (VIOLATION): `missing`,
  `unreadable`, `header`; `build_rows <n>` (build lines absent byte for byte); the first row breaking each format rule
  (`fields`, `date`, `weekday`, `event`, `time_local`, `tz`, `ts_utc` re-derived with zoneinfo, `source` empty,
  `order` by (ts_utc, event), `duplicate` (date, event)); `sha256` when the file's sha256 is neither the build's nor a
  `sha256` logged for that `file` in `analyst/ops_changes.csv` at the same commit. The macro calendar is outside
  FROZEN_ANALYST.sha256 (A11 `frozen_drift` reads only the manifest's list) and outside A7's `append_break` (J-D52).
- D20: the 2015-2024 calendar is deferred with the exam; nothing in the judge reads it.
- D21: a `/3` context's `sources` is `td.SOURCES_V3`, whose note is R-AN-23's new text ("bars_d1 cover the 25
  weekdays before the model day and are built from hourly bars made as bars_h1's are, ..."); `/2` keeps the old
  note. A12_from's wording changes no judge code.
Tests: `tests/test_judge_a12_calendar.py` (the register's example day 2026-10-29, the nulls after each kind's last
event, the refresh rule's codes, and a world whose owner refreshes, logs, skips a log and edits a build row on main
between windows); the world's A12 build commit adds the build file, and its `day` hook makes owner commits.

Script only. The judge job holds no secret and runs no model; only the publish job's deploy step gets the Cloudflare
token, as in judge v1. It executes nothing from an agent-pushed commit (pushed commits are fetched as data and read
with `git diff`/`git cat-file`), and prints only enums, counts, keys and hashes (no model text reaches stdout, a
report or a commit message).

## Run

From the gold-forward-watch root:

```
python -I judge_analyst/run_judge.py --repo ../ga --inbox ../inbox --fetch-pushes                # in CI
python -I judge_analyst/run_judge.py --repo ../gold-analyst --api none --hours none \
    --now 2026-12-07T12:00:00Z --out <scratch>/out --site none                                  # offline dry run
python -I judge_analyst/run_judge.py --write-manifest                                            # after a change
```

Inputs (R-AN-66): a full clone of gold-analyst `main` (`--repo`, required); the GitHub API for it (`/activity` for
its main pushes, the pinned witness issue's comments with `updated_at`, the witness runs; public data read with
`GITHUB_TOKEN`); Dukascopy re-downloads of the recorded hour files (cached once in `hours.csv`); gold-forward-watch at
HEAD, the system store (`--store`, default this checkout; `none` skips it and gives A0 `source_store_unavailable`);
PINS.json and the manifests. Relative `--out`, `--site` and `--store` are taken from the gold-forward-watch root.

Since A6, also these public reads (`jlib/sources.py`; each is complete or it fails, so a failed read never looks like
an empty list; the token first, and once without it if GitHub refuses it):

- the inbox: `GET /repos/{inbox}` (`id`, `private`); `/activity?per_page=100&time_period=month`, all pages (the last
  month, as analyst-merge reads it; older entries are the judge's `inbox_activity` evidence rows, so a flood cannot
  make the read grow without bound); `/actions/runs?per_page=1`
  (`total_count`); `/rules/branches/main`, `.../claude/x`, `.../x`; `git ls-remote https://github.com/{inbox}.git`;
- gold-analyst: `git ls-remote`; `/actions/runs?created=<day>&per_page=100`, all pages, one UTC day per query from D0
  (two days before the newest `judge_utc` of `VERDICTS.csv`, or the day of PINS.inbox_from_utc on a first run) to
  today; `/rules/branches/claude/x`;
- `--fetch-pushes`: pushed agent commits fetched by sha (else by their ref) from `--inbox` (a local clone of the
  inbox; else `https://github.com/<PINS.inbox_repo>.git`) into the gold-analyst clone, without credentials, 180 s per
  fetch, and no more fetches after 3 failed pushes; and one fresh fetch of gold-analyst main (FETCH_HEAD only), which
  A4 `repo_head_foreign` and A12 `inbox_main_foreign` retest against;
- the owner's runs exports' `inbox_checks` (webhooks, deploy keys, the Actions switch, security-log webhook events,
  and since the second review the App's `app_repositories`; R-AN-60), every version of `analyst/ROUTINE_CONFIG.json`
  on gold-analyst main (R-AN-61), both owner-attested, and the session's probe records (R-AN-84), self-reported;
- since A7, read as data from the gold-analyst clone: each exported run's `tool_log` and the security log's filter and
  events in `inbox_checks` (R-AN-60, R-AN-86; owner-attested); `analyst/canary/checks/C20.json` (its `project_dir`
  only); and at main's head the tree's paths (`.claude/`, the forbidden file names), `.claude/settings.json` parsed as
  JSON, and `.claude/hooks/guard.py` only hashed against FROZEN_ANALYST.sha256 (R-AN-66);
- since A7's third review, read as data from the gold-analyst clone: each judged version's routines' `project` and the
  `raw` fields named like `project`, and each runs export's `routines[].project` (R-AN-60, R-AN-61; owner-attested);
  the `self_reported.cc_version` and `repo_head_sha` of the attempt records and call files (R-AN-25, R-AN-29;
  self-reported); and, for each such `repo_head_sha`, whether that commit's tree has an entry for
  `.claude/hooks/guard.py` (`git ls-tree`; the file is not read).

A failed read is A0 `inbox_api_unreachable` (the inbox) or `api_unreachable` (gold-analyst): WARNING, never SOUND; push
times then come from the judge's own `inbox_activity` evidence rows. A run whose read of the inbox's activity failed
writes an `inbox_read_failed` evidence row (fourth review, J-3). When this run's read failed, the last complete read L
is more than 24 h old, and at least two runs after L failed that read (this one included), A0 `inbox_blind` is a
VIOLATION, key `A0|inbox_blind|api|<L>` (second review, SEC-3; fourth review, J-3): the verdict is VIOLATION, so P7 is
false and the analyst pauses its calls (an operational key, R-AN-55), for as long as the judge stays blind. One failed
run after a long gap, such as a Sunday's, stays the WARNING.

Workflow `.github/workflows/analyst-judge.yml`: after `analyst-export` (whose push starts analyst-settle in
gold-analyst), daily at 23:40 UTC, Sundays also at 11:40 UTC (fourth review, J-3: Sunday has no analyst-export run, so
no day has a single judge run; R-AN-70) and on dispatch. The judge job (contents, actions, issues: read; no secret)
checks out this repository (`gfw/`), gold-analyst (`ga/`, full, tags, no stored credentials) and the inbox (`inbox/`,
full with every branch, no stored credentials; data only, A6), runs the judge, refuses to publish if anything outside
its two folders, in the gold-analyst clone or in the inbox clone changed, and hands its folders to `publish`, which
commits them (group `forward-watch`) and deploys `reports/forward_site/`.

Tests (synthetic world + tamper suite; about 10 minutes, most of it building git worlds):

```
uv run --frozen --group dev pytest -p no:cacheprovider judge_analyst/tests
```

## Checks (R-AN-67) and what they implement

| Check | Prereg §8 item | Severity |
|---|---|---|
| A0 | "Shallow clone or unreachable run record: WARNING, never SOUND" (also: API, hour files or source store unreadable; the judge's own manifest differs; A6: `inbox_api_unreachable`, and `inbox_unpinned` when PINS lacks `inbox_repo`, `inbox_repo_id` or `inbox_from_utc`). Second review (SEC-3): `inbox_blind`, the last complete read of the inbox's activity more than 24 h before the run (kept across runs in the evidence file's `inbox_read` and `inbox_activity` rows; with none, counted from PINS.inbox_from_utc); fourth review (J-3): only when this run's read failed and at least two runs after that read failed it (`inbox_read_failed` rows, this run included), key `A0\|inbox_blind\|api\|<L>` | WARNING, never latched; `inbox_blind`: VIOLATION in force while it holds, never latched |
| A1 | server lock_time > entry − 15 on a call not recorded as `no_call:late` (lock recomputed as A2's push time) | VIOLATION |
| A2 | an attempt push outside [entry − 45, deadline] marked non-void; more than 2 accepted attempts; a call without an earlier accepted attempt for its attempt_n; a counted call whose attempt is void. A6: `time_source`, a witness of an agent push whose `push.repo` is not PINS.inbox_repo or whose `window.time_source` is not `activity`. A push's time is the earliest (timestamp, id) inbox entry at or after PINS.inbox_from_utc on a `claude/analyst-*` ref with the pushed sha (live API, else the `inbox_activity` evidence rows; other refs never count), else the witness run's created_at | VIOLATION |
| A3 | `agent_scope`, `rewrite`, `invalid_content`, `attempt_cap` witnesses; an accepted push whose diff breaks R-AN-33; a record on main without an accepted witness; an unwitnessed `claude/analyst-*` push after 24 h whose diff breaks R-AN-33 (conforming: WARNING); a push to main by an actor other than the workflow bot or the owner (`main_push_actor`, gold-analyst's log); a `CLAUDE.md`, `AGENTS.md` or `.claude/` anywhere (R1(a)); the other witness codes of R-AN-33. A6: the pushes are the inbox's entries at or after PINS.inbox_from_utc; a `claude/probe-*` push gives nothing; any other `claude/` ref is WARNING `other_claude_ref`. Since A7 a `CLAUDE.md`, `AGENTS.md` or `.claude/` file is A13 `guard_config`, no longer A3 `forbidden_file` | VIOLATION / WARNING as R-AN-33 |
| A4 | the context rebuilt from the mirror at `repo_head_sha`, the judge's re-downloads, the recorded asof_utc and PARAMS differs beyond R-AN-68; asof_utc > lock_utc + 60 s; an admitted hour with h + 1 h > asof − L; A6 `repo_head_foreign`: repo_head_sha not gold-analyst main's head or an ancestor of it (tested again after one fresh fetch of main). A9: `context_schema` (a context that is not `analyst-context/2`); the requests, URLs, status/reason, bars and stops of R-AN-87, and the rebuild from the recorded Twelve Data bars (`context_differs`). A12: `context_schema` also for a schema that does not match the call's repo_head_sha (`/3` iff it has the pinned A12 build commit as an ancestor, or is it); for `/3`, the `AUDJPY` request in R-AN-87's order, `risk`, `levels` and the 25-weekday `bars_d1` rebuilt within R-AN-68 | VIOLATION |
| A5 | S, T, D_ref, side or a plan field not derivable from the plan and the context (R-AN-21, R-AN-26, R-AN-27). A12: for an `analyst-context/3` call, a plan that breaks `analyst-plan/2`'s `stay_out_reason` rule (`plan_invalid`, detail `keys` or `stay_out_reason`) | VIOLATION |
| A6 | a broken prev_chain link; a witness file whose payload differs from its comment (`payload_differs`, R-AN-67's definition); a file without its comment or a bot comment without its file (after 24 h). A6: `comment_edited` (a bot comment with `updated_at` ≠ `created_at`); `comment_deleted` (now a VIOLATION: an evidence comment the API no longer returns, with or without its witness file); `witness_run_trigger` (a witness run with head branch ≠ main, or other than analyst-merge on schedule/workflow_dispatch or analyst-settle on push/schedule/workflow_dispatch) | VIOLATION |
| A7 | a create-only/write-once file modified or deleted in main's history; an append-only file changed other than by whole-line appends; a force push or deletion of main; main not descending from the judge's previous anchor | VIOLATION |
| A8 | an expected window (MODE.json periods) with zero or two terminal witnesses / no terminal record; a terminal outside the mode's period. A6 `closer_raced`: a closer terminal for window w while a counting inbox entry on a `claude/analyst-*` ref, timed at or before w's deadline, pushed a commit whose diff adds exactly w's call path (key `A8|closer_raced|<terminal path>|<after>`) | VIOLATION |
| A9 | START.json differs from R-AN-38 (first live called/stay_out, first_day rule, same commit as that terminal) | VIOLATION |
| A10 | owner-attested (`analyst/runs/*.json`): an in-span run without an attempt (R-AN-60), a run on another model. Calls are disabled as inbox main showed them (R-AN-67, A10's pause intervals; decision 33): from a PAUSED event to its RESUMED (`clear:` or, since the fourth review, `lifted:`) and after RETIRED, each event counted from when inbox main first held it (V); while V is unknown a PAUSED or RETIRED counts from its `utc` and the interval stays open past its RESUMED; in canary and live windows alike (J-D14, J-D31, J-D34). A run is not judged when an interval meets [its created_utc, deadline_utc − T_run] | VIOLATION (owner-attested) |
| A11 | A9: `td_mismatch` (a recorded Twelve Data value outside relative 1e-3 of the judge's Dukascopy value) and `td_unchecked` (a value without a present Dukascopy file once the model day is more than 3 weekdays old); settlement, opposite side, path summary, twin, ledger, E_n, state events or STATE.json recompute mismatch; mirror vs source; unmatched session id (`unverified_model`); vendored eproc/calendar/holiday table/frozen-manifest drift; record bytes not in the R-AN-3 form. Fourth review (J-4; R-AN-55, R-AN-56, R-AN-67): the analyst's state events replayed by seq against the pause rule, with P0 and LS from MODE.json in each event's commit: `resume_unsupported` (a `clear:` without an owner `pause` clear row dated from its PAUSED event to the RESUMED one, or of a mirrored pause or `judge_silent`; a `lifted:` whose commit's STATE.json shows no fresh verdict, of a live integrity pause or a `model:` pause, or of a latched key without the judge's clear row dated at or before it; a resume with no open pause), `retire_unsupported` (a RETIRED `violation` before LS, or with no earlier clear of a live integrity pause; sixth review, R6-2: or with no integrity key of FINDINGS.csv first seen after the earliest live clear row's utc and at most 10 min after the event, unpaused and not cleared with the judge before it, J-D35), `pause_early` (a PAUSED `judge_violation:` or `judge_silent` before P0, or with no P0). A7 (decision 15): a `lifted:` resume or a RETIRED `violation` whose commit's STATE.json shows a verdict older than the newest `last_fresh_asof_utc` of the versions before it; `promote_unsupported`, a PROMOTED event whose commit's STATE.json fails the judge's recompute of P7 (fresh, not VIOLATION, not older; J-D37); `frozen_unlisted`, a frozen manifest without the guard's files or the probe session's prompt (J-D39) | WARNING + ADJUDICATIONS row |
| A12 | A6, the repository boundary. gold-analyst: `ga_branch` (a branch other than main; pull refs ignored), `ga_tag` (a tag that is no `freeze_tag` of PINS.json in main's first-parent history, or whose peeled commit is not on main; A9: `analyst-dukascopy-v0.6` is allowed peeled to 79b9247901f15ee40d14d0f33cc8001f89bf31ce only), `ga_tag_moved` (an allowed tag away from its first `ga_ref` row), `ga_run_branch` (a run of the day range off main), `ga_run_trigger` (a run from PINS.inbox_from_utc on outside R-AN-75's trigger table), `ga_dynamic_run` (WARNING: a `dynamic/` run). The inbox: `inbox_identity` (404, another id than PINS.inbox_repo_id, or private; fourth review: key `inbox\|<seen>`, `404`, `id-<id read>` or `private`), `inbox_main_foreign` (a counting main entry, or the listed main, not on gold-analyst main after one fresh fetch), `inbox_rewrite` (a counting `force_push` or `branch_deletion`; sha `after`, or `before` for a deletion), `inbox_ref` (a branch other than main and `claude/**`, or any tag; pull refs ignored), `inbox_runs` (`total_count` > 0; fourth review: the count is the key's sha slot), `inbox_rules` (WARNING: rule types missing for `inbox/rules/{main,claude/x,x}`, or `rules/claude/x` of gold-analyst lacking creation), `inbox_stale` (WARNING: inbox main a strict ancestor of gold-analyst main whose oldest missing commit is more than 30 min old). Probes (R-AN-84, self-reported): `probe_failed` (a canary call's `canary_probe` or a `checks/PROBE_<tag>.json` with a pass false, verdict `fail`, or an outcome its probe fails), `probe_incomplete` (WARNING: a canary call whose verdict is not `pass`). Owner-attested (R-AN-60): `inbox_hook` (`inbox_checks` with hooks > 0 or security-log hook events > 0), `inbox_config` (fourth review, J-4: deploy_keys ≠ 1 or Actions on; operational, R-AN-55), `inbox_checks_missing` (WARNING: no complete `inbox_checks` for a week with expected windows; second review: also an `inbox_checks` without a readable `app_repositories`). Second review: `app_scope` (owner-attested, SEC-1: `app_repositories` with a `repository_selection` other than `selected`, or naming gold-analyst, gold-forward-watch or xauusd-quant), `routine_connectors` (owner-attested, SEC-2: a version of `analyst/ROUTINE_CONFIG.json` committed to main at or after PINS.inbox_from_utc, or (fourth review, N3) the version in force at PINS.inbox_from_utc, in which a routine's `raw` lacks `mcp_connections` or `enabled_plugins` or holds a non-empty one; key: that version's commit), `probe_flood` (SEC-3: a listed `claude/probe-*` ref first seen at or after PINS.inbox_from_utc whose name is not `claude/probe-<c3\|del\|wf\|result>-<call_id\|pYYYYMMDDTHHMMSSZ>`, or more than 40 `branch_creation` entries on probe refs in one UTC day, key `inbox/refs/heads/claude/probe-*\|<YYYY-MM-DD>` since the fourth review). Each runs export file is judged on its own, by its path (fourth review, N3). A7 (detection 2, R-AN-60): `inbox_hook` also for any entry of `security_log_events`; `inbox_checks_missing` also, while `security_log_hook_events` is not null, for `security_log_events` missing, not a list or of another length, an entry that is not `{action, created_utc, actor}`, or a `security_log_filter` other than `repo:<inbox> action:hook` (J-D38) | VIOLATION (the codes marked WARNING: WARNING) |
| A13 | A7, the session guard (R-AN-85, R-AN-86). From each runs export's `tool_log` (owner-attested; runs from PINS.inbox_from_utc on, file by file): each logged call decided by the guard's string rules (`jlib/sessionguard.py`; P from the log, else C20.json) and classed harmless or forbidden. `forbidden_attempt` (a forbidden call refused or of unknown outcome) and `forbidden_executed` (one that ran): integrity; `guard_not_enforced` (a harmless refused call that ran, or a refused call whose denial holds no guard message; in `analyst-probe`, any refused call that ran): operational; WARNINGs `guard_denied_benign` (a harmless call refused), `allowed_call_refused` (an allowed call refused), `scan_unclassifiable` (no decision can be formed, or a harmless refused call of unknown outcome), `probe_elsewhere` (the probe line run outside `analyst-probe`), `tool_log_missing` (a run without a readable log). Keys `A13\|<code>\|<export path>\|<run_id>#<seq>` (`<run_id>` alone for `tool_log_missing`). `guard_config` (operational, from git at main's head): the guard's settings missing or not R-AN-85's object, `guard.py` missing, any other `.claude/` file, a `.mcp.json`, `CLAUDE.md`, `CLAUDE.local.md` or `AGENTS.md` anywhere; key `<path>\|<blob sha or absent>` (J-D36, J-D40). Third review of A7 (decisions 21, 22), operational: `routine_project` (owner-attested: in a judged version of `analyst/ROUTINE_CONFIG.json`, a routine's `project` not null or a `raw` field named like `project` with a value, and, in a version committed at or after PINS.inbox_from_utc, a routine without `project`; in a runs export, a `routines` entry without `project` or with one not null; key `<export path>\|<commit>`; J-D41, J-D42); `cc_version_below` (self-reported: a guarded session's attempt record or call file whose `self_reported.cc_version` is below 2.1.295 by R-AN-85's rule) and `cc_version_unknown` (such an attempt record whose version is unknown); key `<record path>\|<commit that added it>` (J-D43) | VIOLATION (`guard_denied_benign`, `allowed_call_refused`, `scan_unclassifiable`, `probe_elsewhere`, `tool_log_missing`: WARNING) |
| A14 | §16.18 A14, watching (R-AN-89, R-AN-90; `jlib/watch.py`). E(T) and O(T) from main (accepted attempt witnesses, their attempt records, terminals). Integrity: `not_triggered` (a trigger window's first accepted attempt whose `wake` is not what R(T) gives, rebuilt from its own `wake.td.bars`: no window, another reason, a gate, a holiday day, a check outside G(d) or a scheduled one, or bars that are not `ok`), `trade_open` and `day_cap` (the first accepted attempt of a W1, W2, W1b or W2b window of a day >= a14_from while O(check) is not empty or \|E(check)\| >= 6), `wake_record` (an `analyst-attempt/2` `wake` that breaks R-AN-90, or, from a14_from on, a call attempt that is not `/2`). Operational: `skipped_wrong` (a `skipped:trade_open` or `skipped:day_cap` terminal whose condition does not hold, or a W1, W2, W1b or W2b `missed:trigger` while one holds) and `a14_from` (MODE.json `a14_from` not a weekday, changed after it was set, or not valid at 22:00Z of the day before; a W1b, W2b or trigger push accepted before it). WARNINGs: `wake_missed` (key `<model day>\|T<hhmm>`: the judge's R(T) on its own fetch gives a trigger where d has no window with that check; pause intervals and mode `off` left out), `m30_mismatch` (a trigger's recorded bars against the judge's fetch, 1e-3, and bars in [A, T − 30 min] in one set only), `m30_unchecked` (no `ok` fetch of d once it is more than 3 weekdays old). The o and c of d's recorded bars are cross-checked against Dukascopy half hours (A11 `td_mismatch`, `td_unchecked`). Also: `analyst-context/4` (A4, J-D53), W1b, W2b and trigger windows in A2's span, A8's expected windows and A10's run matching (J-D59) | VIOLATION (`wake_missed`, `m30_mismatch`, `m30_unchecked`: WARNING) |
| A15 | §16.18 A15, reviews and canary learning (R-AN-92..R-AN-95; `jlib/review.py`). The open sets recomputed from main's terminals and call files (a trade is a `called` window; a `review_close`, or a `called` reverse, closes the trades of its O that its context's `review.open` names; a stop never shortens a trade). Operational VIOLATIONs: `review_open` (a call of a model day >= a15_from whose `review` is null where O is not empty or the reverse, names other call_ids, or other `options`), `open_cap` (key `<model day>\|<mode>`: a window whose recomputed O has more than two trades), `a15_from` (MODE.json `a15_from` not a weekday, changed after it was set, not valid at 22:00Z of the day before by R-AN-5's rule with A15_BUILD_COMMIT, a14_from null or later; a non-null `review`, a `review_hold` or `review_close` terminal, a canary settled record or twin for a model day before it), `lesson_source` (a canary lesson pushed from a15_from on whose settled record is the fixture, or a canary lesson of a day >= a15_from without a canary settled record). WARNINGs: `unsettled` (a terminal of a day >= a15_from, either mode, without its settled record or twin more than 2 weekdays after d's final mirror rows), `m30r_mismatch` (a call's `XAUUSD_M30R` bars against the judge's own fetch, 1e-3, and bars in [A, B − 30 min] in one set only). Also: `analyst-context/5` and its `review` block (A4, J-D61), `analyst-plan/3` and `action_not_allowed` (A5, integrity, J-D62), A1's answers `review_hold` and `review_close`, A14's `trade_open` only before a15_from and R(T) without step 1 from it, and A11's managed exits, `unmanaged`, `reviews`, x_end, weights, clusters, the weighted statistics and canary settlement (J-D63, J-D65) | VIOLATION (`unsettled`, `m30r_mismatch`: WARNING) |

Independence: E_n and K are recomputed in pure Python (the test suite checks them against the lab's frozen
`eproc.py`, sha256 ee8d456a…, kept in `tests/fixtures/` only); the holiday rows are the register's own (R-AN-9), the
event calendars are the judge's sha-pinned copies (R-V1-15); windows come from zoneinfo and are unit-tested against the
register's R-AN-8 table.

## Outputs (`reports/judge_analyst/` and `reports/forward_site/judge_analyst/`, the only paths the workflow may commit)

- `reports/forward_site/judge_analyst/analyst_verdict.json`: a byte-identical copy of the verdict below, deployed with
  the gold-watch site, so analyst-settle reads it at `<PINS.judge_site_url>/judge_analyst/analyst_verdict.json`
  (R-AN-70; P7 and the pause rule). `--site none` skips it.

- `analyst_verdict.json` (`analyst-verdict/1`: schema, asof_utc, head_sha, analyst_verdict SOUND|WARNING|VIOLATION,
  violation_keys, cleared_keys; sixth review, R6-2: violation_first_seen, each key of violation_keys with a
  FINDINGS.csv row mapped to its `first_seen_utc`, so A0 keys and `system_error:` entries have none) and `REPORT.md`
  (snapshots).
- `FINDINGS.csv` (first time each key was seen), `VERDICTS.csv` (one row per run; its last head_sha is the A7 anchor),
  `evidence.csv` (R-AN-69, one row per item first seen: `activity` (gold-analyst's log), `inbox_activity` (the
  inbox's log), `comment` (bot comments), `run` (witness runs; since A6 with `ref` = refs/heads/<head_branch> and
  `push_after` = head_sha), `ga_ref` (a ref first seen at a sha: `refs/...` of gold-analyst, `inbox/refs/...` of the
  inbox; pull refs and HEAD not recorded), `ga_run` (a gold-analyst run that gave an A12 finding) and, since the
  second review, `inbox_read` (a complete read of the inbox's activity: `judge_utc` and `ref` = PINS.inbox_repo, one
  per run time; A0 `inbox_blind`), and since the fourth review `inbox_read_failed` (the same columns, one per run time
  whose read of the inbox's activity failed, written only while PINS.inbox_repo and PINS.inbox_from_utc are set; A0
  `inbox_blind` counts them)), `hours.csv` (the judge's hour-file cache): append-only.
- `ADJUDICATIONS.csv` (the owner's, append-only): `utc,ref,check,subject,decision,note`. A VIOLATION key is cleared by
  `ref=latch, decision=clear` with `utc` at or after its first_seen_utc (R-JV-2). A WARNING key is adjudicated by
  `ref=warning` with `judge_error`, `spec_gap`, `accepted` or `ops`; `system_error` puts a VIOLATION in force until a
  later `resolved` row for the same subject. Since the fourth review the judge also reads its own clear rows for A11's
  check of the analyst's `lifted:` resumes (R-AN-67).

Keys are `<check>|<code>|<path>|<commit>` (R-JV-1); the commit is the one that added the file on main (or the push
sha / anchor). VIOLATION keys latch until cleared, even when a later run cannot re-find them (an activity entry that
aged out); a cleared key never clears another (R-JV-4).

## Judge decisions (points the register leaves open; to be logged in the register before the freeze)

- J-D1 Check `A0` (inputs) is the judge's addition for "never SOUND" conditions; it is never latched or adjudicated.
- J-D2 R-AN-68 "exact" for prices built from integer points is grid-exact: |a − b| <= 1e-12·max(1, |a|, |b|), far below
  any grid step, so a last-bit difference between decimal-to-double routes is not a finding.
- J-D3 Grace times: a window must have its terminal 36 h after deadline + 20 min; a bot comment without a file and an
  unwitnessed claude push are findings after 24 h; a missing settled/twin record after 36 h from the exit.
- J-D4 Holidays: the register's rows up to 2027-12-31; the analyst table's rows only beyond that horizon (OPS appends).
- J-D5 A `no_call:data` context passes when its detail is any applicable one (`store_stale`, `hour_absent`,
  `store_mismatch`) and what it fetched is a prefix of the expected file sequence (none for `store_stale`).
- J-D6 memory.settled[].reason: the outcome's exit reason or the call's reason_ar are both accepted.
- J-D7 An unknown FX pair may be `null` or an object with a null `pair_pct`.
- J-D8 memory.playbook.version may be `k` or `"v<k>"`.
- J-D9 A runs-export status counts as success when it starts with "succe" or equals "completed".
- J-D10 Canary calls are judged like live ones (A4/A5/A6/A8) with keys naming the canary path; clear them before the
  freeze. Settlement, ledger and states are live only.
- J-D11 Server times: since A6, R-AN-34's one rule (the earliest counting inbox entry on a `claude/analyst-*` ref with
  the sha; an entry first seen keeps its first-seen timestamp), else the witness run's created_at. Before A6 (PINS
  without the inbox) the old rule on gold-analyst's own log.
- J-D12 path_summary.exit_after_min accepts exit − t0 or exit − t0 + 1 minutes; a void/no_quote `gross_usd` may be null
  or −S; a time exit with no quoted path minute uses t1 − 1 as its exit minute.
- J-D13 `analyst/canary/hours/<day>.csv` is a snapshot (R-AN-72 fills the re-check the next day), not create-only.
- J-D14 A10 uses PARAMS.json at HEAD for T_run and T_setup; calls count as disabled between PAUSED and its RESUMED and
  after RETIRED; MODE `off` periods are not reconstructed from history. (Fourth review, R-AN-67: a RESUMED's subject is
  its reason after its first `clear:` or `lifted:`, so a lift ends an interval too; J-D31. Amended in the register's
  fifth review, J-5, decision 33: calls count as disabled as inbox main showed them (R-AN-67, A10's pause intervals),
  no longer from a PAUSED event's utc to its RESUMED event's utc; J-D34.)
- J-D15 Only `analyst/START.json` is checked; a re-freeze's `START_<tag>.json` is not handled yet.
- J-D16 (A6) The runs day range starts at today's date when there is neither a `VERDICTS.csv` row nor a
  PINS.inbox_from_utc. The anonymous fallback of the public reads restarts the whole read once, as R-AN-32's merge.
- J-D17 (A6) `closer_raced` leaves out a push the merge witnessed as `rejected` for another reason than
  `window_closed` with a lower seq than the window's terminal witness: the closer's step 1 processed it before closing
  (its rejection is A3's). A push witnessed `window_closed`, or not at all, counts.
- J-D18 (A6) A canary call without a readable `canary_probe`, and an unreadable `PROBE_<tag>.json`, are
  `probe_incomplete` (WARNING). A `PROBE_<tag>.json` with verdict `incomplete` is no finding.
- J-D19 (A6) `probe_failed` also fires for an outcome its probe's "Pass iff" column plainly fails (an `accepted` push
  or ls-remote that must be refused, an `ok` REST write or admin probe, `rest.ga`/`rest.gfw` `ok`, `rest.hooks` > 0,
  `ga_push*` `refused_rule`, `net.google` 200-399, `net.raw_public` 200), whatever the record's pass flag says;
  `error`/`none` outcomes and the measured probes are never a failure.
- J-D20 (A6) A PINS.json without `inbox_repo`, `inbox_repo_id` or `inbox_from_utc` gives A0 `inbox_unpinned`; without
  `inbox_repo` the pushes are read from gold-analyst's own log as before A6, and the inbox checks are skipped. Without
  `inbox_from_utc` no inbox entry counts (and no run is checked against the trigger table).
- J-D21 (A6) `witness_run_trigger` from a run's evidence row (which has no workflow path): the head branch must be
  main and the event one of push, schedule or workflow_dispatch; the path is checked when the API returned the run.
- J-D22 (A6) `inbox_rewrite` is reported only for entries the API lists in that run (an evidence row keeps `after`
  only, so a deletion's `before` could not rebuild the same key); VIOLATIONs latch, so an aged-out entry stays in force.
- J-D23 (A6) `--fetch-pushes` also allows the one fresh fetch of gold-analyst main (into FETCH_HEAD only).
- J-D24 (second review) `app_scope` matches a `full_names` entry by its repository name (the part after `/`), case
  ignored as GitHub ignores it, for any owner; `gold-analyst-inbox` and `gold-analyst-exam` are other names (R-AN-67's
  row names only the three; the exam window of R-AN-60 is not judged). A `repository_selection` key present with any
  value but `selected` (null included) is `app_scope`; an absent one, a non-list `full_names` or a non-string name is
  `inbox_checks_missing` for a judged week.
- J-D25 (second review; confirmed and extended in the register's fourth review) The last complete read of the inbox's
  activity is kept in the evidence file: an `inbox_read` row for each complete read (one per `judge_utc`), and the
  `inbox_activity` rows, which only a complete read writes (so the rows of runs from before this change count). With
  neither, `inbox_blind` counts from PINS.inbox_from_utc; a run without an API client reads nothing. Since the fourth
  review the failed runs are kept too, as `inbox_read_failed` rows (J-D29).
- J-D26 (second review; confirmed and extended in the register's fourth review to the version in force at
  PINS.inbox_from_utc, J-D32) "Committed at or after PINS.inbox_from_utc" (`routine_connectors`) is the commit's
  committer time, for the commits of main's first-parent history that add or change the file. A version that is not a
  JSON record with a `routines` list, or a routine that is not an object with an object `raw`, is reported too (it
  cannot show the empty lists); any value other than the empty JSON list counts as non-empty.
- J-D27 (second review; confirmed with an amendment in the register's fourth review, J-4) `A0|inbox_blind|api|<L>` is
  in `violation_keys` (verdict VIOLATION) in every run that finds it, and only then: never written to FINDINGS.csv,
  latched or cleared. Its key names its episode by L, the last complete read, so no lift or clear of one episode
  mutes a later one; the analyst treats it as operational, paused while a fresh verdict carries it and lifted when one
  does not (R-AN-55).
- J-D28 (second review) `probe_flood` judges a listed probe ref by its earliest known entry (live list or evidence
  rows); a listed ref with no known entry is not judged (its entry predates the judge's reads, or this run's read
  failed, which `inbox_blind` covers after 24 h). Names are matched case-sensitively; `<tag>` is matched as a pattern
  (a call_id, or `p` + 8 digits + `T` + 6 digits + `Z`), not as a valid date. (Confirmed in the register's fourth
  review; the day count's key now carries its day, one key per day over the cap.)
- J-D29 (fourth review, J-3) `inbox_blind` counts the distinct `judge_utc` values of `inbox_read_failed` rows after L
  and at or before this run, plus this run. A run without an API client is a failed read (it writes the row); a run
  while PINS lacks `inbox_repo` or `inbox_from_utc` writes none and is never blind; a run time already recorded is
  not recorded twice. "More than 24 h" is strict: a read exactly 24 h old is not blindness.
- J-D30 (fourth review, J-4) The A11 state-event checks also report as `resume_unsupported` a RESUMED whose reason
  starts with neither `clear:` nor `lifted:`, or whose subject has no open pause; a `clear:judge_silent` (only
  `model:` and live integrity pauses are cleared, R-AN-55 step 1); and a `lifted:model:<run_id>` (only mirrored pauses
  and `judge_silent` are lifted, steps 3 and 4). A `clear:` of a live integrity pause arms retirement whether or not
  its row is valid (a bad row is `resume_unsupported` itself). Each event's P0 and LS come from MODE.json in the
  commit that added that event (HEAD when unknown); "earlier" means a lower seq. The analyst's ADJUDICATIONS.csv and
  the judge's are read at HEAD (both append-only) and their rows compared by `utc`; a judge clear row is
  `ref=latch, decision=clear` for the key (its `check` column is not compared). A PAUSED for a subject already open
  keeps the first one.
- J-D31 (fourth review, J-4) A10's pause intervals cover canary windows too: there is one STATE.json for both modes,
  `start` refuses `calls_disabled` in any mode, and the pause rule now pauses the canary's calls (R-AN-55), so a
  refused canary fire is not an in-span run without an attempt. (Confirmed in the register's fifth review, with
  decision 33's amendment: an interval ends when inbox main first held its RESUMED event, and a run is not judged when
  inbox main showed a pause at any time up to the end of its start interval; J-D34.)
- J-D32 (fourth review, N3) The `routine_connectors` version in force at PINS.inbox_from_utc is the last commit of
  main's first-parent history that adds or changes the file with a committer time before PINS.inbox_from_utc (none
  when a later such commit deletes it). It is judged whether or not a later version replaced it.
- J-D33 (fourth review, N3) Runs exports are judged file by file, by path. For `inbox_checks_missing` a file stands
  for the week of its name (`analyst/runs/<iso_week>.json`) and for the `iso_week` it claims; `unverified_model` counts
  a week as exported the same way.
- J-D34 (fifth review, blocker J-5; register decision 33 and R-AN-67 "A10's pause intervals, as inbox main showed
  them", xauusd-quant 166c6b0) `start` reads STATE.json at inbox main when it runs (R-AN-24), which holds a PAUSED,
  RESUMED or RETIRED event only once analyst-inbox-mirror has pushed a commit holding the analyst-settle commit that
  added it (R-AN-83): minutes after the event's `utc` (the settle run's t0), hours when GitHub starts the mirror late.
  So A10 judges calls as inbox main showed them:
  1. V(e), the event's time on inbox main: the timestamp of the earliest (timestamp, id) known inbox activity entry
     (live list or `inbox_activity` evidence rows) with timestamp >= PINS.inbox_from_utc, on `refs/heads/main`, whose
     `after` is the commit that added e (the first-parent commit that added its file, as J-D30) or has it as an
     ancestor. The `after` must be on gold-analyst main (the clone's main, else main after the one fresh fetch): one
     that is not (A12 `inbox_main_foreign`), or that the clone cannot find, gives no time. Main's first-parent order
     answers without git, any other commit is asked of git. None while no such entry is known.
  2. An interval runs from V(PAUSED), else the PAUSED event's `utc`, to V(RESUMED) of the RESUMED event that closes
     its subject (`clear:` and `lifted:` alike), and stays open while V(RESUMED) is none: the judge cannot show that
     any session saw the lift. After RETIRED, from V(RETIRED), else its `utc`, on. No fixed grace: the register
     considered one and did not adopt it (the mirror's backstop is a schedule GitHub has started hours late). A run
     left out while a V is unknown is judged again once the entry is known.
  3. A run of R-AN-60 is not judged `in_span_without_attempt` when an interval meets [its created_utc, its window's
     deadline_utc − T_run] (T_run from PARAMS.json at HEAD, J-D14): the interval starts at or before that range's end
     and ends after created_utc. Its `start` step read inbox main at some time in that range and may have met the
     pause.
  4. Without PINS.inbox_repo (J-D20: sessions read gold-analyst itself), and for an event dated before
     PINS.inbox_from_utc, the event's `utc` stands for V, as before J-5 (no grace either).
  Points the register's text leaves open, taken here (to confirm):
  (a) An empty interval (V(RESUMED) at or before its start: a late mirror pushed the pause and its lift at once, so
      inbox main never showed the pause) meets no range. Decision 33 excuses a run when inbox main "showed calls
      disabled", and it never did.
  (b) V is not bounded below by the event's `utc`: R-AN-67 defines V as the entry's timestamp. An entry earlier than
      its own event can only come from clocks that disagree.
  (c) With PINS.inbox_repo set but no PINS.inbox_from_utc no entry counts (J-D20), so V is always none: a PAUSED counts
      from its `utc` and a RESUMED leaves its interval open. A0 `inbox_unpinned` keeps such a verdict from SOUND.
  (d) An event whose adding commit is unknown (not in main's first-parent history) has no V.
  (e) In the cases of (4) the range rule (3) still applies: R-AN-67 keeps the event `utc`s there, not the test of
      created_utc alone, and `start` reads gold-analyst main at some time in the same range.
  The first J-5 build (49c655f), made before the register held J-5's text, ended an interval at the mirror push or 30
  minutes after the RESUMED event's `utc` (`LIFT_GRACE`), kept the PAUSED and RETIRED `utc`s as starts, and excused a
  run only when its created_utc lay inside an interval. All three are replaced by the rules above.
- J-D35 (sixth review, blocker R6-2; register decision 35, R-AN-55 step 2, R-AN-67, R-AN-70) A retirement is judged
  by time, not by the order in which analyst-settle runs applied a clear and saw a key. The verdict's
  `violation_first_seen` maps each key of `violation_keys` that has a FINDINGS.csv row to that row's `first_seen_utc`
  (a key first found in this run: the run's time). A11 `retire_unsupported` also reports a RETIRED `violation` that
  no key supports: a VIOLATION key of FINDINGS.csv (the file before this run), not operational, first seen strictly
  after the arming time A and no later than the RETIRED event's `utc` + 10 min (R-AN-70's tolerance for a verdict
  dated after the settle run), with no PAUSED event for `judge_violation:<K>` before the RETIRED event (a paused key
  waits for its own clear, R-AN-55 step 2) and no `ref=latch, decision=clear` row for K in the judge's
  ADJUDICATIONS.csv dated at or before it. A is the earliest clear time of the live integrity pauses that RESUMED
  `clear:` events with a lower seq closed; a pause's clear time is the `utc` of its earliest analyst/ADJUDICATIONS.csv
  clear row dated at or after its PAUSED event (no upper bound: the row step 1 applies), else the RESUMED event's `utc`
  (a resume without a row is `resume_unsupported` by itself, J-D30). A FINDINGS.csv row whose `first_seen_utc` is not
  an R-C4 time supports nothing. Not checked: a live integrity key first seen after A that the analyst paused instead
  of retiring (the register does not ask for it).
- J-D36 (§16.18 A7; R-AN-67 A13, R-AN-85, R-AN-86) Points of the run-log scan the register's text leaves open, taken
  here (to confirm):
  (a) A run of a routine other than `analyst-probe`, the four session routines included, follows the four routines'
      rows: every inbox session runs under the guard, so an unknown routine is judged strictly, never skipped.
  (b) A logged call with no input object and no usable `input_text` is decided only when its tool is neither Bash nor
      a file tool: check 5 refuses such a tool whatever its input, and its class needs none (`WebFetch` with no input
      is a forbidden attempt, `Glob` harmless). Bash, Read, Write, Edit, MultiEdit and NotebookEdit without it are
      `scan_unclassifiable`, as is a call whose fields break R-AN-86's schema (a non-string tool, an input neither an
      object nor null, an outcome outside the three, a non-string denial). A `tool_log` that is not an object, has
      another `form` or no `calls` list is `tool_log_missing` ("unreadable"). A logged object of Bash or a file
      tool that lacks a field the decision or the class turns on (`command`; `file_path`, with Write's `content`;
      `notebook_path`) is `scan_unclassifiable` too: an abbreviated log cannot show that such a call was refused,
      and taking the field as absent would turn every abbreviated Read that ran into `guard_not_enforced`.
  (c) P is taken only as an absolute path (trailing `/` dropped, as D0); anything else is an unknown root.
  *(Confirmed: the register's first review of A7 (V6-2) adopts (b)'s abbreviated objects and (c), `/` alone included,
  in R-AN-86, and gold-analyst's `scan_runs.py` now reads them the same way.)*
  (d) A run whose `created_utc` is not an R-C4 time is judged (it cannot be shown to precede PINS.inbox_from_utc).
  (e) A call without an integer `seq` is keyed `<run_id>#i<n>`, n its place in `calls` (1, 2, ...).
  (f) Check 2's 8 MiB limit is applied to the event's JSON as logged; a hashed Write `content` counts by its `bytes:`
      for check 8(d) only. "No control character" in class (c) is Unicode category Cc (U+0000-U+001F, U+007F-U+009F).
  (g) `probe_elsewhere` is the exact allowed line `python3 analyst/run_window.py probe` (spaces around it dropped),
      executed outside `analyst-probe`; another form of it is judged by the rows (a `cd` prefix that ran is
      `guard_not_enforced`).
  (h) A finding's detail names the tool only when it looks like a tool name (`[A-Za-z0-9_.:-]{1,80}`), else `other`;
      it never copies a command, a path or a denial.
- J-D37 (§16.18 A7 decision 15; R-AN-53, R-AN-67, R-AN-70) L_prev of an event is the largest
  `judge_verdict.last_fresh_asof_utc` among the versions of `analyst/STATE.json` in the commits of main's first-parent
  history before the commit that added the event (that commit's own version not counted); no condition while there is
  none. With L_prev set, an `asof_utc` that is not an R-C4 time counts as older (it cannot be shown not to be). The
  judge's recompute of P7 for a PROMOTED event (before A7 the replay assumed P7 true) reads `analyst/STATE.json` in the
  event's commit: P7 needs `judge_verdict.fresh` true, `value` not `VIOLATION`, and the verdict not older; otherwise
  A11 `promote_unsupported` (WARNING), keyed by the event's path and commit, a code the register does not name.
- J-D38 (§16.18 A7 detection 2; R-AN-60) While `security_log_hook_events` is not null, `inbox_checks_missing` also
  reports an entry of `security_log_events` that is not `{action, created_utc, actor}` with an R-C4 `created_utc`, and
  a `security_log_filter` other than `repo:<PINS.inbox_repo> action:hook`. These, and the register's own rule (the
  events missing, not a list, or of another length than the count), apply to every export, not only to weeks with
  windows. Any entry is `inbox_hook`, whatever its time (the owner records only those from PINS.inbox_from_utc on).
- J-D39 (§16.18 A7; R-AN-7, R-AN-66) A frozen manifest that does not list `.claude/settings.json`,
  `.claude/hooks/guard.py` or `analyst/PROBE_SESSION_PROMPT.md` gives A11 `frozen_unlisted` (WARNING) for that path:
  unlisted, a changed `guard.py` would be seen by nothing, since the judge never reads it otherwise.
- J-D40 (§16.18 A7; R-AN-2 as replaced, R-AN-67 `guard_config`) "A path under `.claude/` other than those two" is read
  at any depth (a `docs/.claude/...` file too), as the A3 check it replaces did; the forbidden names are matched
  exactly (case-sensitive). Before A7 the A3 `forbidden_file` key was an integrity key; `guard_config` is operational.
- J-D41 (third review of §16.18 A7, decision 21; R-AN-60, R-AN-67 `routine_project`) In a runs export an entry
  without `project` counts only when the export was added on main at or after PINS.inbox_from_utc (the committer time
  of the commit that added the file, as J-D26), the rule R-AN-67's row gives for the routine export in force; an entry
  with a `project` other than null counts in every export. The row names no time for runs exports. An export added
  before PINS.inbox_from_utc describes routines from before the inbox and the guard, and PINS.inbox_from_utc is set
  before the routines are repointed, so every export of a canary or live week is added after it. Without
  PINS.inbox_from_utc no export and no routine version is judged for `routine_project` (as J-D20).
- J-D42 (third review of §16.18 A7, decision 21; R-AN-61) Where a missing key counts (a version committed at or after
  PINS.inbox_from_utc, a runs export added then), what cannot show `project` null is reported too: a version that is
  not a JSON record with a `routines` list, a runs export whose `routines` is missing or not a list, and a `routines`
  entry that is not an object. This is the rule `routine_connectors` follows for its two lists (an unreadable runs
  export stays A10 `runs_export_form`). An empty `routines` list gives nothing. The top-level `project` must be null
  (`""` counts). A `raw` field is any key, at any depth of `raw` (objects and lists), whose name contains `project`
  once lowered (Python's `str.lower`). Its value counts unless it is null, `""`, `[]` or `{}`, compared by type, so
  `false` and `0` count. Details name routines and enums only, never a value.
- J-D43 (third review of §16.18 A7, decision 22; R-AN-25, R-AN-29, R-AN-85) A `repo_head_sha` names a gold-analyst
  commit when it is 40 hex digits (either case) naming a commit object in the clone; fetched agent commits count, and
  A4 reports one that is off main. Whether its tree holds `.claude/hooks/guard.py` is read from the tree entry (`git
  ls-tree <sha> -- <path>`, a blob), so the guard's code is never read. A record with no such sha gives neither key.
  The version rule splits V at its first U+0020 only, and its digits are ASCII. The records are the `*.json` files
  directly in the four folders at main's head; lesson records, revision records, probe records and C20.json are not
  judged (the row names attempt records and call files; C20 judges the probe record's version). The key names the
  commit that first added the record on main's first-parent history (as every record key).

- J-D44 (§16.18 A9; R-AN-84) A probe record without a `net.twelvedata` outcome was written by the pre-A9 code, whose
  `net.dukascopy` passed on 200: the A9 rule of `net.dukascopy` (200 fails) applies only to a record that has a
  `net.twelvedata` outcome, so an earlier `PROBE_<tag>.json` is not failed after the fact. In a canary
  `net.twelvedata` that is not an int is null (R-AN-84: an outcome of `error` or `none`); in `probe` any outcome but
  200 fails. A canary call whose context is `analyst-context/2` must carry the `net.twelvedata` outcome its context's
  first R-AN-87 request gives (`probe_failed` otherwise, including a missing one): the register says the outcome is
  read from that request, so a different one is an inconsistent record.
- J-D45 (§16.18 A9; R-AN-66, R-AN-67, R-AN-68) The cross-check:
  (a) uses the recorded provenance bars (XAUUSD's at listed hours; a pair's bar at t0, from the call_id, and its
  newest bar, at h_new) of `ok` requests with well-formed bars, in any mode and whatever the call's status; A4 ties
  them to the context's shown values;
  (b) "not `present` at any judge run" is read from the judge's `hours.csv`: a cached file that is not `present` is
  fetched again at each run while the model day is at most 3 weekdays old (`numpy.busday_count` convention: weekdays
  in [model day, the judge's UTC date)), a new status is appended (a later row wins), and a failed fetch keeps the
  cached row; once more than 3 weekdays old, the value is unchecked unless its XAU hour is optional (R-AN-15, the
  judge's holiday table) and its file is `empty`. A file never fetched (an error or the run's fetch cap) is unchecked
  even for an optional hour. FX hours are never optional;
  (c) the findings' details are not cut at 400 characters (they hold only judge-formatted numbers and labels, the hour
  re-formatted from the parsed time), since the row asks for every compared value; `td_mismatch` lists the values
  outside 1e-3 first, then those within;
  (d) the t0 hour is shared by a model day's two windows, so a bad t0 file gives a finding on both calls.
- J-D46 (§16.18 A9; R-AN-87, A4) Points R-AN-87 leaves open, taken as follows: a `budget` request (no try) needs
  `fetched_utc` null, `bytes` 0 and `sha256` ""; its `http` and `td_code` are not judged. A tried request needs
  `fetched_utc` an R-C4 time at or after asof_utc. `sha256` is "" or 64 lower-case hex digits; an `ok` request needs
  `bytes` in 1..262,144 and a hex sha256. An hourly response keeps at most `values_n` bars; `fresh` keeps exactly one
  when `values_n` >= 1, and none otherwise. A no_call:data context with `store_mismatch` may hold any prefix of the
  requests (the order of that stop and the requests is not written), as before A9. The pacing (8 s between tries) and
  the budget are not judged: the record keeps only the last try's time.
- J-D47 (§16.18 A11; R-AN-86 (a)(iv), (d)) Nothing is left open: (iv) is matched on S2, after the part rules and
  the character rule, so `git status\t-s`, `git status --porcelain=v2` and `git log -n5` stay forbidden; D is
  unchanged (the guard still refuses `git` with `bash_form` and `PushNotification` with `tool`), so a listed `git`
  form or `PushNotification` refused gives `guard_denied_benign` and run gives `guard_not_enforced`.

- J-D48 (§16.18 A12; R-AN-23, A4) The pin is `jlib/config.py` `A12_BUILD_COMMIT`, a full sha; None (the build's
  state until the A12 build commit is on gold-analyst main) makes every call `/2`, and a pinned commit absent from the
  clone is no one's ancestor, so a wrong pin shows as `context_schema` on every `/3` call. The order of A4's tests: a
  schema that is neither `/2` nor `/3` is `context_schema`; then `repo_head_foreign`; then the pairing
  (`context_schema`, detail: the schema and the one expected); only a paired context is rebuilt.
- J-D49 (§16.18 A12; R-AN-26, R-AN-28, A5) The judge keeps its own plan codes: a missing `stay_out_reason` on a
  stay_out, or one on a trade, is `keys` (the lock's `missing_keys` and `extra_keys`); another value or type is
  `stay_out_reason`. The plan rule follows the recorded context's schema (a mispaired call is A4's finding).
- J-D50 (§16.18 A12; R-AN-88, R-AN-68) Points R-AN-88 leaves open, taken as follows: a bar's model day and hour are
  taken from its `t_utc` (its `t_server` is compared exactly in `bars_h1`); a rounded field need not sit on its
  rounding grid, only within the tolerance; key order is not judged (the context hash is over the compact form,
  whose keys are sorted, R-AN-3); a recorded input that cannot be computed on gives `levels.inputs`; when the
  recorded `asia.hist` is not a list, width_ratio is recomputed from the judge's own hist. In a `no_call:data`
  context only `levels` (null) is judged beyond the status and the requests; `risk`, like `fx`, is not compared
  there (J-D46).
- J-D51 (§16.18 A12; R-AN-87, R-AN-19) The `AUDJPY` provenance follows J-D46 as a pair's; a `risk` object other than
  null when the judge's rebuild is null (or the reverse) is `context_differs` (`risk`). The t0 hour is shared by a
  model day's two windows, so a bad AUDJPY t0 file gives a finding on both calls (J-D45 (d)).
- J-D52 (§16.18 A12-D17, D19; R-AN-10, R-AN-67 A4) Points D19 leaves open, taken as follows: the build's rows are the
  judge's own copy pinned to the register's sha256, not the file at the pinned build commit (a build commit carrying
  another file shows as `macro_calendar` on every `/3` call); "a build row" is a whole line, compared byte for byte;
  `source` must be non-empty only (its issuer is not judged); a kind with no row is null on every day; the check runs
  at the repo_head_sha of `/3` calls only, so a break mended before the next call is not seen. The file is not an
  A7 `append_break` path: D17 keeps it sorted, so a refresh can insert rows before the last one, and its
  append-only rule is A4's `build_rows` and `sha256` instead.

- J-D53 (§16.18 A14; R-AN-23, R-AN-5, A4 and A14 `a14_from`) The pin is `jlib/config.py` `A14_BUILD_COMMIT`, a full
  sha; None until the A14 build commit is on gold-analyst main (every `/4` call is then A4 `context_schema`, and an
  `a14_from` that is set is the A0 WARNING `a14_unpinned`). A call descending from it needs `/4`, one descending from
  A12's but not A14's `/3`. "Inbox main at 22:00:00Z of the day before" is the `after` of the latest counting inbox main
  entry with a timestamp at or before that instant (without the inbox pins, gold-analyst main's latest first-parent
  commit committed by then); unknown, the A0 WARNING `a14_from_unverified`. Keys: the commit that first set a non-null
  value (a change: the changing commit; a push accepted before a14_from: the witness file's commit). The same
  `watcher/` tree is the tree object id of `watcher` at both commits.
- J-D54 (§16.18 A14; R-AN-89, R-AN-90, R-AN-67 A14) "The first accepted attempt" is the accepted attempt witness with
  the lowest seq; a trigger's `wake.reason` in E(T) is read from it. E(T) and O(T) take the mode's expected windows of
  d only. A `/2` record is judged for `wake_record` on any day (the A14 build writes `/2` before a14_from too); from
  a14_from on a call attempt that is not `/2` is `wake_record`. R-AN-90's "bars are every element with t_utc <= T − 30
  min" is checked as: every bar in [A, T − 30 min], in strict time order, and values_n − len(bars) in {0, 1} (B = T,
  and Twelve Data does not say whether end_date is inclusive, A9-D2). The request's fetched_utc must be at or after T
  (the 130 s wait is not judged). A `td` that is an error provenance passes `wake_record`; the trigger is then
  `not_triggered`. Records are key-sorted (R-AN-3), so the order of `wake`'s keys is not judged.
- J-D55 (§16.18 A14; R-AN-39, A14 `skipped_wrong`) A `skipped:trade_open` terminal's detail may be the call_id of any
  open trade; a `skipped:day_cap` detail is the count, as an integer or its decimal string. When both gates hold, a
  `skipped:day_cap` (R-AN-39's order gives `skipped:trade_open`) is the A11 WARNING `terminal_status`, not
  `skipped_wrong`, since its condition holds.
- J-D56 (§16.18 A14; R-AN-66, R-AN-69) The judge's fetch: one per model day >= a14_from of a mode's period, except days
  with a holiday-table row (no trigger window can open there), at most 3 per run, 8.0 s between try starts. The key is
  the `TWELVEDATA_API_KEY` environment variable, sent only as `Authorization: apikey`; User-Agent `Mozilla/5.0
  (gold-forward-watch analyst judge)`; no key, no fetch. Evidence rows: source `td_m30`, `ref` the model day,
  `push_after` the response's sha256, `activity_type` `ok` or `td_<reason>`, `activity_utc` the fetch time, `run_id`
  values_n. R-AN-69's columns cannot hold bars, so an `ok` fetch's bars are kept in
  `reports/judge_analyst/m30/<model day>.json` (`judge-m30/1`), which is also what makes it never repeated.
- J-D57 (§16.18 A14; R-AN-67 `wake_missed`) Only checks of G(d) that are not scheduled and have no window of d are
  recomputed; the mode at T is MODE.json's `mode` in the first-parent version committed (committer time) at or before T;
  A10's pause intervals are the judge's own (`pause_intervals`).
- J-D58 (§16.18 A14; R-AN-68) The Dukascopy cross-check of a trigger's bars of d uses the first and the last tick of
  the same half of the hour file (`reports/judge_analyst/halves.csv`, the judge's own cache); a half outside d's
  trading hours whose file is empty or has no tick is skipped, as an optional hour is (R-AN-15); inside them it is
  pending, then `td_unchecked`.
- J-D59 (§16.18 A14; R-AN-40, R-AN-60, R-AN-11) A model day >= a14_from is processed once all its expected windows are
  and now >= model_to_utc((d+1) 00:00). A10's model overlay for W1b, W2b and trigger windows matches by session id over
  `analyst-wake`, `analyst-w1` and `analyst-w2`, else an `analyst-wake` run without session id created in [entry − 30
  min, deadline]; the in-span rule skips windows closed `skipped:trade_open` or `skipped:day_cap`. The merge's new
  rejection code `window_order` is an A3 WARNING.
- J-D60 (§16.18 A14-D10; R-AN-12, R-AN-21, R-AN-23) `mirror/system/forecasts.csv` must be a byte prefix of the source's
  and its sha256 the latest `mirror/exports.csv` row's `forecasts_sha256` (A11 `mirror_forecasts`, WARNING). A `/4`
  context's `wake` is rebuilt from the call's own attempt record (`attempt_n`), whatever the context's status; with
  fewer than 20 prior days `r20_days` lists the days there are.
- J-D61 (§16.18 A15; R-AN-23, R-AN-92, R-AN-68, A4) The pin is `jlib/config.py` `A15_BUILD_COMMIT`, None until the A15
  build is on gold-analyst main: every `/5` call is then A4 `context_schema`, and an `a15_from` that is set gives the A0
  WARNING `a15_unpinned`. A4 rebuilds a `/5` context's `review` from the call files at main of the trades its recorded
  `review.open` names, in that order, with options for their number; a name that is not a `called` call at main is A4
  `context_differs` (`review.open.call_id`). Whether those are the right trades is A15 `review_open`, never A4. The
  `XAUUSD_M30R` request is expected last, after `fresh`, iff that list is not empty and an entry is at least 30 min
  before asof_utc; its URL has A = the list's earliest entry and B = asof floored to the half hour; its bars are judged
  as the trigger's (`watch.m30_bar_problems` over [A, B − 30 min]). The block is rebuilt whatever the context's status
  (with no request, M is empty). More than two open trades get the two-trade options (`hold`, `close`).
- J-D62 (§16.18 A15; R-AN-26, R-AN-27, R-AN-29, R-AN-36, A5) An action outside `review.options` (or, with `review`
  null, outside buy, sell and stay_out) is A5 `action_not_allowed`; it does not make the call underivable (R-AN-36
  step 4 is S, T and D_ref). `reverse` and `add` take their side from the one trade of the recorded `review.open`
  (`buy` +1, `sell` −1); with any other number of trades the side does not follow (A5 `st_underivable`). `hold` and
  `close` are judged as stay_out (side 0, no trade fields). A review status in a call without a `/5` context is A5
  `call_status`; a review action there is A5 `plan_invalid` (`action`).
- J-D63 (§16.18 A15; R-AN-93, R-AN-46) The managed exit's case 3 (no quote on the exit side in [t0, m]) has
  exit_minute_utc null, the exit half spread 0, exit_after_min null and mfe/mae over t0 .. m − 1. R-AN-42's gap rule
  makes it unreachable for an entry at least 30 min before m, so it is kept only for completeness. x_end_utc of a
  `void` or `no_quote` trade is m when a review closed it, else exit_utc; `unmanaged` is settled with the trade's own
  void flag. `reviews` lists every window C of d whose recomputed O(C) holds the trade, with C's terminal status and
  its plan's action, confidence and reason_ar (null without a plan). An `analyst-settled/2` record must have exactly
  R-AN-46's keys plus the seven new ones.
- J-D64 (§16.18 A15; R-AN-95, A15 `lesson_source`) A canary lesson's settled record is "the synthetic fixture" when its
  settled_sha256 is the sha256 of `analyst/tests/fixtures/canary_settled.json` at main, or is not the sha256 of the
  canary settled record of its call_id (none, or another). Its lesson attempt's push time is the accepted witness's of
  `analyst/canary/attempts/lesson-<call_id>_<attempt_n>.json` (server time, else the witness's window time or push
  activity time), else the commit time of the lesson file at main. With `a15_from` null the check does not run.
- J-D65 (§16.18 A15; R-AN-40, R-AN-58, R-AN-56, R-AN-94, A15 `unsettled`) For a model day >= a15_from the judge checks
  a day's records only once the day is processable as one unit (every expected window has a terminal, every `called`
  one a call file with S_dimes and a side, now >= model_to_utc((d+1) 00:00), final inputs of d − 1 and d); A11's
  `unsettled` and `untwinned` (36 h after exit) are replaced there by A15 `unsettled`, whose clock starts at the later
  `fetched_utc` of d's two final rows in main's `days.csv`, counted in weekdays (`td.weekdays_since` > 2). Weights and
  clusters are computed over the day's `called` windows (every class, overlays included). The ledger's E is checked on
  each cluster's last counted trade and must be empty on its other rows (every trade before a15_from is its own
  cluster, so those rows keep E); `n_w`, `weight`, `cluster`, `x_end_utc` and `closed_by` are checked on rows of model
  days >= a15_from only. STATE's `n` is the weighted count; `n_trades` and `n_clusters` are checked when its schema is
  `analyst-state/2`. The canary has no ledger or state; its settled records and twins are checked as live ones, with
  mode and class `canary`.

## Open points

1. **Location: resolved 2026-10-23.** Moved to gold-forward-watch as R-AN-1 says (review blocker B3). The store is
   this checkout, so `A0 source_store_unavailable` no longer fires in CI.
2. **Verdict feed: resolved 2026-10-23.** The verdict is copied to `reports/forward_site/judge_analyst/` and deployed
   by the publish job (R-AN-70), the URL analyst-settle already reads. It goes live only when this branch is merged
   into gold-forward-watch main (with `analyst-mirror`), which needs the owner's approval.
3. **Witness issue.** Anyone can comment on an issue of a public repository; the judge trusts only comments by
   `github-actions[bot]`. Locking the pinned issue to collaborators is recommended.
4. **Cross-run.** The judge has not yet judged records written by the analyst code. Before the freeze it runs on the
   canary records (C14), and every finding is adjudicated or fixed; the register items behind J-D5..J-D9 and J-D12 are
   amended in a dated edit.
5. Freeze: `FROZEN_JUDGE_ANALYST.sha256` lists every file of `judge_analyst/` and the workflow; the tag
   `judge-analyst-freeze` is set at the freeze (not now).
6. **A6 (2026-10-23), branch `analyst-judge-inbox`, not merged or pushed.** Built test-first from register §16.18 A6
   (as revised after its review) and prereg v0.6, without reading the analyst code. Not yet run against the analyst's
   A6 build or the real inbox: the first CI run will show whether the judge job's GITHUB_TOKEN can read the inbox's
   `/activity`, `/rules` and `/actions/runs` (else the anonymous fallback), and how GitHub fills `updated_at` on an
   unedited bot comment (C7 checks it before `canary_from`).
7. Not covered by a code of the register, so not reported: a gold-analyst branch created and deleted between two judge
   reads (`ga_branch` reads `git ls-remote` only; gold-analyst's own activity log would show it), and a webhook created
   and deleted inside one session (the residual risk A6 discloses). *(Since A7: the guard refuses such calls in the
   session; A13 finds any such call the run log shows, refused or not, and A12 `inbox_hook` any webhook event the
   security log records.)*
8. **A6 second review (2026-10-23), branch `analyst-judge-inbox`, not merged or pushed.** Built test-first from register
   §16.18 A6 decisions 20-23 and R-AN-60/61/66/67 at xauusd-quant 62a0d80, without reading the analyst code. To log in
   the register before the freeze: the `inbox_read` evidence source (R-AN-69 does not list it) and J-D24..J-D28, in
   particular that `inbox_blind` is never latched (J-D27). A ROUTINE_CONFIG.json version committed before
   PINS.inbox_from_utc and still at HEAD is not judged here (R-AN-67's row); R-AN-61's build test covers it.
   *(Resolved in the register's fourth review, decision 32: `inbox_read` is in R-AN-69, J-D16..J-D28 are recorded, and
   the version in force at PINS.inbox_from_utc is judged.)*
9. **A6 fourth review (2026-10-23), branch `analyst-judge-inbox`, not merged or pushed.** Built test-first from register
   §16.18 A6 decisions 24-32 and R-AN-55/56/60/62/66/67/69/70 at xauusd-quant 5d7fcdc, without reading the analyst
   code. To log in the register before the freeze: J-D29..J-D33. Not covered: a lift or clear lands in an
   analyst-settle commit, but sessions read STATE.json from inbox main, which the mirror updates afterwards; a fire in
   that gap is still refused, and A10 can then report it as an in-span run without an attempt (pre-existing, and
   longer when GitHub starts the mirror late). *(Resolved by J-D34, below.)*
10. **J-5 (2026-10-23), branch `analyst-judge-inbox`, not merged or pushed.** First built in 49c655f from the text at
    5d7fcdc, before the register held J-5's text; the verifier's sixth round (R6-1) found that it did not follow
    decision 33. Rebuilt test-first (`tests/test_judge_fifth_review.py`) from register decision 33 and R-AN-67's
    "A10's pause intervals, as inbox main showed them" (xauusd-quant 166c6b0), without reading the analyst code: J-D34
    as rewritten. To log in the register before the freeze: J-D34's points (a) to (e).
11. **R6-2 (2026-10-23, sixth review), not merged or pushed.** Built test-first (`tests/test_judge_sixth_review.py`,
    whose first case is the verifier's probe as the judge sees its events) from register decision 35 and R-AN-55,
    R-AN-62, R-AN-67 and R-AN-70 as amended there, without reading the analyst code: the verdict's
    `violation_first_seen` and A11 `retire_unsupported` by time (J-D35).
12. **A7, the session guard (2026-10-23), branch `analyst-judge-inbox`, not merged or pushed.** Built test-first
    (`tests/test_judge_session_guard.py`) from register §16.18 A7, R-AN-60, R-AN-66, R-AN-67, R-AN-70, R-AN-85 and
    R-AN-86 and prereg v0.6 R1 (f) and §8 (xauusd-quant f16708e), without reading the analyst code or its guard: A13,
    the security-log fields of A12, decision 15 in A11, `frozen_unlisted`. To log in the register before the freeze:
    J-D36..J-D40, in particular the new code `promote_unsupported` and the judge's P7 recompute (J-D37). Not verified:
    the run log's real shape (C20's first record shows it, R-AN-86); that the analyst's `scan_runs.py` classifies
    every call as this judge does (both follow R-AN-86, built apart; a difference is a finding to adjudicate); the
    guard's file-system rules, which no log shows.
13. **A7 first review (2026-10-24; V6-2, V6-3), not merged or pushed.** From register §16.18 A7 decisions 17 to 19
    and R-AN-86 as amended there, without reading the analyst code: R-AN-86 (a) cuts a Bash command at `&&`, `||`,
    `;` and `|` and calls it harmless when every part is (a local read-only command, the window script's line in
    another form, or a `cd`, each with at most one final ` 2>&1` or ` 2>/dev/null`), so the real probe run's first
    call `cat ...; ls -la; ls analyst` is `guard_denied_benign`, not `forbidden_attempt`; J-D36 (b) and (c) are the
    register's rule now (planted: a condensed log without Write's `content`, in a session run and in the probe run,
    gives only `scan_unclassifiable`). The probe session's step 7 is `cd /tmp && pwd` (V6-1; the world's C20 log).
14. **A7 second review (2026-10-24; V7-1), not merged or pushed.** From register §16.18 A7 decision 20 and R-AN-85 as
    amended there (the settings file, check 6(b)) and R-AN-86 (a): `GUARD_SETTINGS` holds the `env` block that sets
    `BASH_DEFAULT_TIMEOUT_MS` and `BASH_MAX_TIMEOUT_MS` to `"3600000"`, so A13 `guard_config` compares against it; the
    string rules refuse a Bash `timeout` that is not absent, null or a number of at least 3 600 000 (`bash_option`),
    which R-AN-86 (a)(i) classes harmless (planted: `guard_denied_benign` when refused, `guard_not_enforced` when it
    ran; the world's call session now passes `timeout` 3600000). Not judged: whether a call was moved to the
    background, which the runs export does not record (C20 checks step 1). Made in the same session as the analyst's
    side of the fix, from the register text; the session had read the analyst's guard earlier, so this change is not
    blind in the strict sense, though it follows the register's words only.
15. **A7 third review (2026-10-24; N1, N2), not merged or pushed.** Built test-first
    (`tests/test_judge_guard_third_review.py`) from register §16.18 A7 decisions 21 and 22 and R-AN-25, R-AN-55,
    R-AN-60, R-AN-61, R-AN-66, R-AN-67, R-AN-74, R-AN-84 and R-AN-85 as amended there (xauusd-quant 12ffdda), without
    reading the analyst code: A13 `routine_project`, `cc_version_below` and `cc_version_unknown`, operational; the
    world's fresh routine export and runs exports carry `project` null, and its probe records `cc_version`. To log in
    the register before the freeze: J-D41..J-D43, in particular J-D41 (a runs export added before
    PINS.inbox_from_utc is not judged for a missing key, which the row does not say) and J-D42 (an export that cannot
    show `project` null is reported). Not verified: which field of the RemoteTrigger get response, if any, names a
    project (the first export under decision 21 shows it); whether `claude` is on a routine session's PATH, so whether
    any guarded attempt record will carry a version at all (C20's first record shows it; if not, every guarded attempt
    record gives `cc_version_unknown` until a dated amendment names another source).
16. **A9 (2026-10-26), not merged or pushed.** Built test-first (`tests/test_judge_a9.py`) on the local branch
    `a9-judge` (worktree `gold-forward-watch-a9`, from origin/main 29f0be6) from register §16.18 A9 and the items it
    amends (R-AN-17..R-AN-19, R-AN-23, R-AN-66..R-AN-69, R-AN-84, R-AN-87; xauusd-quant b3816ca) and prereg v0.6's
    Change A9, without reading the analyst code. To log in the register before the freeze: J-D44..J-D46, in
    particular J-D44 (the `net.dukascopy` rule by record era, and the canary's `net.twelvedata` against its context)
    and J-D45 (b) (what "at any judge run" means). Not verified: how the session code writes a `budget` request's
    `http` and `td_code`, and whether a no_call context keeps `bars_h1`, `fx` and `fresh` (the comparison stops at the
    status and the requests for a no_call:data context, as before); the first canary records will show both.
17. **A11 (2026-10-26), not merged or pushed.** Built test-first (`tests/test_judge_a11.py`) on the local branch
    `a11-judge` (worktree `gold-forward-watch-a11`, from origin/main 0652b30) from register R-AN-86 as amended by
    §16.18 A11 (xauusd-quant a5eff94), without reading the analyst code: a `git status` or `git log` part of the
    listed forms is harmless by (a)(iv), and `PushNotification` joins class (d) (J-D47). The findings table is
    unchanged; the A7 unit test that classed `git status` forbidden now classes it harmless.
18. **A12 (2026-10-26), not merged or pushed.** Built test-first (`tests/test_judge_a12.py`) on the local branch
    `a12-judge` (worktree `gold-forward-watch-a12`, from origin/main b6614d7) from register §16.18 A12 and the items
    it marks (R-AN-14, R-AN-16, R-AN-17, R-AN-19, R-AN-23, R-AN-26, R-AN-28, R-AN-67 A4 and A5, R-AN-68, R-AN-87,
    R-AN-88; xauusd-quant a7c9989) and prereg Change A12, without reading the analyst code. To log in the register
    before the freeze: J-D48..J-D51. Before any push: the client's approval of A12's text, and `A12_BUILD_COMMIT` set
    to the A12 build commit once it is on gold-analyst main (with None the judge reports every `/3` call). Not
    verified: whether the session code keeps `risk` in a `no_call:data` context, and how it writes a `levels` field
    whose input is missing (R-AN-88 says null); the first `/3` records will show both. The addendum A12-D17..D21
    (xauusd-quant 55c0a4f; the live calendar, `macro_calendar`, the `/3` sources note) is built on the same branch,
    test-first and blind; J-D52 is to log in the register too.
19. **A14 (2026-10-27), not merged or pushed.** Built test-first (`tests/test_judge_a14.py`, a world that runs R-AN-89
    day by day) on the local branch `a14-judge` (worktree `gold-forward-watch-a14`, from origin/main 066fd56) from
    register §16.18 A14 and the items it marks (xauusd-quant 4c1dfc7) and prereg Change A14, without reading the
    analyst or its watcher. To log in the register before the freeze: J-D53..J-D60. Before any push: `A14_BUILD_COMMIT`
    set to the A14 build commit once it is on gold-analyst main (with None every `/4` call is reported). The workflow's
    judge step now receives `TWELVEDATA_API_KEY`. Not verified against real records: the session's `wake.td` (whether
    Twelve Data's end_date includes the element at T), and the first `/4` contexts.
20. **A15 (2026-10-29), not merged or pushed.** Built test-first (`tests/test_judge_a15.py`: unit tests of R-AN-92's
    open sets and block, R-AN-93's managed exits and x_end, R-AN-94's weights and the weighted statistics, and a world
    whose canary days 12-02 and 12-03 and live day 12-04 run reviews: add, close of two, reverse, hold) on the local
    branch `a15-judge` (worktree `gold-forward-watch-a15`, from origin/main 05a00b5) from register §16.18 A15 and the
    items it marks, and prereg Change A15, without reading the analyst or its watcher. To log in the register before
    the freeze: J-D61..J-D65. Before any push: `A15_BUILD_COMMIT` set to the A15 build commit once it is on gold-analyst
    main (with None every `/5` call is reported). The judge produces no canary report, so the report's `/4` fields
    (A15-D15) are not judged; the exam's reviews (A15-D19) wait for the exam. Not verified against real records: the
    session's `XAUUSD_M30R` request and the first `/5` contexts and `analyst-settled/2` records.
