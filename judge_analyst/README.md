# judge_analyst: the analyst judge (blind build)

The independent judge of Analyst v1 (xauusd-quant `research/analyst/ANALYST_V1_PREREG.md` DRAFT v0.6, §8 as amended
by "Change v0.5" M7 and "Change v0.6"; `research/system/IMPLEMENTATION_REGISTER.md` §16, R-AN-66..R-AN-70 and the items
they cite, with the dated amendment §16.18 A6, the agent inbox, as revised after its review; xauusd-quant 1994513).
A6 binds once the client approves its text; until then it is the build's target.
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

- the inbox: `GET /repos/{inbox}` (`id`, `private`); `/activity?per_page=100`, all pages; `/actions/runs?per_page=1`
  (`total_count`); `/rules/branches/main`, `.../claude/x`, `.../x`; `git ls-remote https://github.com/{inbox}.git`;
- gold-analyst: `git ls-remote`; `/actions/runs?created=<day>&per_page=100`, all pages, one UTC day per query from D0
  (two days before the newest `judge_utc` of `VERDICTS.csv`, or the day of PINS.inbox_from_utc on a first run) to
  today; `/rules/branches/claude/x`;
- `--fetch-pushes`: pushed agent commits fetched by sha (else by their ref) from `--inbox` (a local clone of the
  inbox; else `https://github.com/<PINS.inbox_repo>.git`) into the gold-analyst clone, without credentials, 180 s per
  fetch, and no more fetches after 3 failed pushes; and one fresh fetch of gold-analyst main (FETCH_HEAD only), which
  A4 `repo_head_foreign` and A12 `inbox_main_foreign` retest against;
- the owner's runs exports' `inbox_checks` (webhooks, deploy keys, the Actions switch, security-log webhook events;
  R-AN-60) and the session's probe records (R-AN-84), which are owner-attested and self-reported respectively.

A failed read is A0 `inbox_api_unreachable` (the inbox) or `api_unreachable` (gold-analyst): WARNING, never SOUND; push
times then come from the judge's own `inbox_activity` evidence rows.

Workflow `.github/workflows/analyst-judge.yml`: after `analyst-export` (whose push starts analyst-settle in
gold-analyst), daily at 23:40 UTC and on dispatch. The judge job (contents, actions, issues: read; no secret) checks out
this repository (`gfw/`), gold-analyst (`ga/`, full, tags, no stored credentials) and the inbox (`inbox/`, full with
every branch, no stored credentials; data only, A6), runs the judge, refuses to publish if anything outside its two
folders, in the gold-analyst clone or in the inbox clone changed, and hands its folders to `publish`, which commits
them (group `forward-watch`) and deploys `reports/forward_site/`.

Tests (synthetic world + tamper suite; about 10 minutes, most of it building git worlds):

```
uv run --frozen --group dev pytest -p no:cacheprovider judge_analyst/tests
```

## Checks (R-AN-67) and what they implement

| Check | Prereg §8 item | Severity |
|---|---|---|
| A0 | "Shallow clone or unreachable run record: WARNING, never SOUND" (also: API, hour files or source store unreadable; the judge's own manifest differs; A6: `inbox_api_unreachable`, and `inbox_unpinned` when PINS lacks `inbox_repo`, `inbox_repo_id` or `inbox_from_utc`) | WARNING, never latched |
| A1 | server lock_time > entry − 15 on a call not recorded as `no_call:late` (lock recomputed as A2's push time) | VIOLATION |
| A2 | an attempt push outside [entry − 45, deadline] marked non-void; more than 2 accepted attempts; a call without an earlier accepted attempt for its attempt_n; a counted call whose attempt is void. A6: `time_source`, a witness of an agent push whose `push.repo` is not PINS.inbox_repo or whose `window.time_source` is not `activity`. A push's time is the earliest (timestamp, id) inbox entry at or after PINS.inbox_from_utc on a `claude/analyst-*` ref with the pushed sha (live API, else the `inbox_activity` evidence rows; other refs never count), else the witness run's created_at | VIOLATION |
| A3 | `agent_scope`, `rewrite`, `invalid_content`, `attempt_cap` witnesses; an accepted push whose diff breaks R-AN-33; a record on main without an accepted witness; an unwitnessed `claude/analyst-*` push after 24 h whose diff breaks R-AN-33 (conforming: WARNING); a push to main by an actor other than the workflow bot or the owner (`main_push_actor`, gold-analyst's log); a `CLAUDE.md`, `AGENTS.md` or `.claude/` anywhere (R1(a)); the other witness codes of R-AN-33. A6: the pushes are the inbox's entries at or after PINS.inbox_from_utc; a `claude/probe-*` push gives nothing; any other `claude/` ref is WARNING `other_claude_ref` | VIOLATION / WARNING as R-AN-33 |
| A4 | the context rebuilt from the mirror at `repo_head_sha`, the judge's re-downloads, the recorded asof_utc and PARAMS differs beyond R-AN-68; asof_utc > lock_utc + 60 s; an admitted hour with h + 1 h > asof − L; A6 `repo_head_foreign`: repo_head_sha not gold-analyst main's head or an ancestor of it (tested again after one fresh fetch of main) | VIOLATION |
| A5 | S, T, D_ref, side or a plan field not derivable from the plan and the context (R-AN-21, R-AN-26, R-AN-27) | VIOLATION |
| A6 | a broken prev_chain link; a witness file whose payload differs from its comment (`payload_differs`, R-AN-67's definition); a file without its comment or a bot comment without its file (after 24 h). A6: `comment_edited` (a bot comment with `updated_at` ≠ `created_at`); `comment_deleted` (now a VIOLATION: an evidence comment the API no longer returns, with or without its witness file); `witness_run_trigger` (a witness run with head branch ≠ main, or other than analyst-merge on schedule/workflow_dispatch or analyst-settle on push/schedule/workflow_dispatch) | VIOLATION |
| A7 | a create-only/write-once file modified or deleted in main's history; an append-only file changed other than by whole-line appends; a force push or deletion of main; main not descending from the judge's previous anchor | VIOLATION |
| A8 | an expected window (MODE.json periods) with zero or two terminal witnesses / no terminal record; a terminal outside the mode's period. A6 `closer_raced`: a closer terminal for window w while a counting inbox entry on a `claude/analyst-*` ref, timed at or before w's deadline, pushed a commit whose diff adds exactly w's call path (key `A8|closer_raced|<terminal path>|<after>`) | VIOLATION |
| A9 | START.json differs from R-AN-38 (first live called/stay_out, first_day rule, same commit as that terminal) | VIOLATION |
| A10 | owner-attested (`analyst/runs/*.json`): an in-span run without an attempt (R-AN-60), a run on another model | VIOLATION (owner-attested) |
| A11 | a re-downloaded hour file whose sha256 differs (its hour is left out of A4); settlement, opposite side, path summary, twin, ledger, E_n, state events or STATE.json recompute mismatch; mirror vs source; unmatched session id (`unverified_model`); vendored eproc/calendar/holiday table/frozen-manifest drift; record bytes not in the R-AN-3 form | WARNING + ADJUDICATIONS row |
| A12 | A6, the repository boundary. gold-analyst: `ga_branch` (a branch other than main; pull refs ignored), `ga_tag` (a tag that is no `freeze_tag` of PINS.json in main's first-parent history, or whose peeled commit is not on main), `ga_tag_moved` (an allowed tag away from its first `ga_ref` row), `ga_run_branch` (a run of the day range off main), `ga_run_trigger` (a run from PINS.inbox_from_utc on outside R-AN-75's trigger table), `ga_dynamic_run` (WARNING: a `dynamic/` run). The inbox: `inbox_identity` (404, another id than PINS.inbox_repo_id, or private), `inbox_main_foreign` (a counting main entry, or the listed main, not on gold-analyst main after one fresh fetch), `inbox_rewrite` (a counting `force_push` or `branch_deletion`; sha `after`, or `before` for a deletion), `inbox_ref` (a branch other than main and `claude/**`, or any tag; pull refs ignored), `inbox_runs` (`total_count` > 0), `inbox_rules` (WARNING: rule types missing for `inbox/rules/{main,claude/x,x}`, or `rules/claude/x` of gold-analyst lacking creation), `inbox_stale` (WARNING: inbox main a strict ancestor of gold-analyst main whose oldest missing commit is more than 30 min old). Probes (R-AN-84, self-reported): `probe_failed` (a canary call's `canary_probe` or a `checks/PROBE_<tag>.json` with a pass false, verdict `fail`, or an outcome its probe fails), `probe_incomplete` (WARNING: a canary call whose verdict is not `pass`). Owner-attested (R-AN-60): `inbox_hook` (`inbox_checks` with hooks > 0, security-log hook events > 0, deploy_keys ≠ 1 or Actions on), `inbox_checks_missing` (WARNING: no complete `inbox_checks` for a week with expected windows) | VIOLATION (the codes marked WARNING: WARNING) |

Independence: E_n and K are recomputed in pure Python (the test suite checks them against the lab's frozen
`eproc.py`, sha256 ee8d456a…, kept in `tests/fixtures/` only); the holiday rows are the register's own (R-AN-9), the
event calendars are the judge's sha-pinned copies (R-V1-15); windows come from zoneinfo and are unit-tested against the
register's R-AN-8 table.

## Outputs (`reports/judge_analyst/` and `reports/forward_site/judge_analyst/`, the only paths the workflow may commit)

- `reports/forward_site/judge_analyst/analyst_verdict.json`: a byte-identical copy of the verdict below, deployed with
  the gold-watch site, so analyst-settle reads it at `<PINS.judge_site_url>/judge_analyst/analyst_verdict.json`
  (R-AN-70; P7 and the pause rule). `--site none` skips it.

- `analyst_verdict.json` (`analyst-verdict/1`: schema, asof_utc, head_sha, analyst_verdict SOUND|WARNING|VIOLATION,
  violation_keys, cleared_keys) and `REPORT.md` (snapshots).
- `FINDINGS.csv` (first time each key was seen), `VERDICTS.csv` (one row per run; its last head_sha is the A7 anchor),
  `evidence.csv` (R-AN-69, one row per item first seen: `activity` (gold-analyst's log), `inbox_activity` (the
  inbox's log), `comment` (bot comments), `run` (witness runs; since A6 with `ref` = refs/heads/<head_branch> and
  `push_after` = head_sha), `ga_ref` (a ref first seen at a sha: `refs/...` of gold-analyst, `inbox/refs/...` of the
  inbox; pull refs and HEAD not recorded) and `ga_run` (a gold-analyst run that gave an A12 finding)), `hours.csv` (the
  judge's hour-file cache): append-only.
- `ADJUDICATIONS.csv` (the owner's, append-only): `utc,ref,check,subject,decision,note`. A VIOLATION key is cleared by
  `ref=latch, decision=clear` with `utc` at or after its first_seen_utc (R-JV-2). A WARNING key is adjudicated by
  `ref=warning` with `judge_error`, `spec_gap`, `accepted` or `ops`; `system_error` puts a VIOLATION in force until a
  later `resolved` row for the same subject.

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
  after RETIRED; MODE `off` periods are not reconstructed from history.
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
   and deleted inside one session (the residual risk A6 discloses).
