# Analyst judge report

- asof_utc: 2026-10-30T15:59:34Z
- head_sha (gold-analyst main checked): 627bdfbae2ebddcfa9db6ba4eccdfaa561eb8145
- judge code_sha8: 166ed4de
- **analyst_verdict: SOUND**

Built blind from ANALYST_V1_PREREG.md section 8 (DRAFT v0.6) and IMPLEMENTATION_REGISTER section 16 (with amendments 16.18 A6, the agent inbox, and A7, the session guard). Model text is never printed here: findings carry enums, field names, hashes and numbers only. Findings marked (owner-attested) rest on the owner's weekly runs export (R-AN-60), with its copy of the run logs (A13, R-AN-86) and of the security log, or routine config export (R-AN-61). Session probe outcomes (A12 probe_failed, probe_incomplete) are self-reported by the session (R-AN-84), and so is the Claude Code version of A13 cc_version_below and cc_version_unknown (R-AN-25, R-AN-85).

## VIOLATION keys in force (0)

- none

## Cleared VIOLATION keys (5)

- `A12|probe_failed|analyst/canary/checks/PROBE_p20261024T024852Z.json|68c078cb5d0d52e5d53d2c2d9b9d711530add464` cleared 2026-10-26T04:50:00Z
- `A12|probe_failed|analyst/canary/checks/PROBE_p20261024T110641Z.json|e6a5b2dd02e8e7e27b6abe68c3a88de578d7c040` cleared 2026-10-26T04:50:00Z
- `A12|probe_failed|analyst/canary/checks/PROBE_p20261026T000513Z.json|79b9247901f15ee40d14d0f33cc8001f89bf31ce` cleared 2026-10-26T04:50:00Z
- `A3|agent_scope|analyst/canary/witness/000001.json|91a52ec7034425a14e27b68988b9dcabce266a9f` cleared 2026-10-26T04:50:00Z
- `A3|agent_scope|analyst/canary/witness/000002.json|91a52ec7034425a14e27b68988b9dcabce266a9f` cleared 2026-10-26T04:50:00Z

## WARNINGs needing an ADJUDICATIONS row or a fix (0)

- none

## Adjudicated WARNINGs (7)

- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W1.json|43bbb42e58a4dd66e768a86e84b32a335c6eb79c`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W2.json|e6008594960ece17a99cd9837c68c4782900b8da`
- `A11|td_mismatch|analyst/canary/calls/2026-10-27_W2.json|80cbca5d9e610f5235c4c6dbecf2132d41881c26`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W1.json|453f6d4579a8e736d3909aca5af8a96a36186213`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W2.json|ac3f7065d54f8d49c5bfc8d46cdbd8a611f62d99`
- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0100.json|6d77cc3c373c1fbe70cb145497cd274011f9e662`
- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0600.json|8af0b8d4024d1763ef9c4f8aa034fc6df466e987`

## Run summary

- accepted_push_diffs_unverified: 0
- canary_expected_windows: 7
- canary_terminals: 19
- cc_version_records_checked: 31
- contexts_rebuilt: 15
- ga_runs_read: 94
- head: 627bdfbae2ebddcfa9db6ba4eccdfaa561eb8145
- inbox_activity_entries: 161
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-10-30T15:59:34Z
- live_expected_windows: 0
- live_terminals: 0
- m30_compared: 3
- probe_creations_max_day: 18
- probe_records: 19
- routine_config_versions_checked: 5
- run_log_calls_scanned: 0
- run_logs_scanned: 0
- settled_checked: 0
- td_compared: 839
- td_outside: 15
- td_pending: 29
- td_unchecked: 0
- witness_comments: 53
- witness_files: 53
