# Analyst judge report

- asof_utc: 2026-10-26T04:37:03Z
- head_sha (gold-analyst main checked): cf9e822b9f44663a4d38d640d9e64df45b8df544
- judge code_sha8: 76e4473c
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

## Adjudicated WARNINGs (0)

- none

## Run summary

- accepted_push_diffs_unverified: 0
- canary_expected_windows: 0
- canary_terminals: 0
- cc_version_records_checked: 0
- ga_runs_read: 74
- head: cf9e822b9f44663a4d38d640d9e64df45b8df544
- inbox_activity_entries: 38
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-10-26T04:37:03Z
- live_expected_windows: 0
- live_terminals: 0
- probe_creations_max_day: 8
- probe_records: 4
- routine_config_versions_checked: 2
- run_log_calls_scanned: 0
- run_logs_scanned: 0
- settled_checked: 0
- witness_comments: 2
- witness_files: 2
