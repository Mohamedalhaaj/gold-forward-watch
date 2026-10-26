# Analyst judge report

- asof_utc: 2026-10-26T11:01:58Z
- head_sha (gold-analyst main checked): 43bbb42e58a4dd66e768a86e84b32a335c6eb79c
- judge code_sha8: 76e4473c
- **analyst_verdict: WARNING**

Built blind from ANALYST_V1_PREREG.md section 8 (DRAFT v0.6) and IMPLEMENTATION_REGISTER section 16 (with amendments 16.18 A6, the agent inbox, and A7, the session guard). Model text is never printed here: findings carry enums, field names, hashes and numbers only. Findings marked (owner-attested) rest on the owner's weekly runs export (R-AN-60), with its copy of the run logs (A13, R-AN-86) and of the security log, or routine config export (R-AN-61). Session probe outcomes (A12 probe_failed, probe_incomplete) are self-reported by the session (R-AN-84), and so is the Claude Code version of A13 cc_version_below and cc_version_unknown (R-AN-25, R-AN-85).

## VIOLATION keys in force (0)

- none

## Cleared VIOLATION keys (5)

- `A12|probe_failed|analyst/canary/checks/PROBE_p20261024T024852Z.json|68c078cb5d0d52e5d53d2c2d9b9d711530add464` cleared 2026-10-26T04:50:00Z
- `A12|probe_failed|analyst/canary/checks/PROBE_p20261024T110641Z.json|e6a5b2dd02e8e7e27b6abe68c3a88de578d7c040` cleared 2026-10-26T04:50:00Z
- `A12|probe_failed|analyst/canary/checks/PROBE_p20261026T000513Z.json|79b9247901f15ee40d14d0f33cc8001f89bf31ce` cleared 2026-10-26T04:50:00Z
- `A3|agent_scope|analyst/canary/witness/000001.json|91a52ec7034425a14e27b68988b9dcabce266a9f` cleared 2026-10-26T04:50:00Z
- `A3|agent_scope|analyst/canary/witness/000002.json|91a52ec7034425a14e27b68988b9dcabce266a9f` cleared 2026-10-26T04:50:00Z

## WARNINGs needing an ADJUDICATIONS row or a fix (1)

- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W1.json|43bbb42e58a4dd66e768a86e84b32a335c6eb79c` (outside 1e-3: XAUUSD 2026-10-25T22:00:00Z o td=3993.61979 dk=4001.3 rel=1.919e-03; XAUUSD 2026-10-26T02:00:00Z o td=3984.88714 dk=3989.295 rel=1.105e-03; within: XAUUSD 2026-10-25T22:00:00Z c td=4001.01662 dk=4000.335 rel=1.704e-04; XAUUSD 2026-10-25T23:00:00Z o td=4000.90042 dk=4000.375 rel=1.313e-04; XAUUSD 2026-10-25T23:00:00Z c td=3997.96572 dk=3997.8 rel=4.145e-05; XAUUSD 2026-10-26T00:00:00Z o td=3997.72309 dk=3997.66 rel=1.578e-05; XAUUSD 2026-10-26T00:00:00Z c td=3987.05437 dk=3985.425 rel=4.088e-04; XAUUSD 2026-10-26T01:00:00Z o td=3986.7975 dk=3985.675 rel=2.816e-04; XAUUSD 2026-10-26T01:00:00Z c td=3987.87778 dk=3989.287 rel=3.533e-04; XAUUSD 2026-10-26T02:00:00Z c td=3998.32519 dk=4000.013 rel=4.220e-04; XAUUSD 2026-10-26T03:00:00Z o td=3998.89103 dk=3999.92 rel=2.572e-04; XAUUSD 2026-10-26T03:00:00Z c td=4008.51251 dk=4007.435 rel=2.689e-04; XAUUSD 2026-10-26T04:00:00Z o td=4008.65966 dk=4007.535 rel=2.806e-04; XAUUSD 2026-10-26T04:00:00Z c td=4015.34871 dk=4015.935 rel=1.460e-04; XAUUSD 2026-10-26T05:00:00Z o td=4015.39568 dk=4015.983 rel=1.462e-04; XAUUSD 2026-10-26T05:00:00Z c td=4011.3802 dk=4014.138 rel=6.870e-04; EURUSD 2026-10-25T21:00:00Z p0 td=1.1222 dk=1.122265 rel=5.792e-05; EURUSD 2026-10-26T05:00:00Z p1 td=1.12169 dk=1.12169 rel=0.000e+00; USDJPY 2026-10-25T21:00:00Z p0 td=157.00864 dk=157.06 rel=3.270e-04; USDJPY 2026-10-26T05:00:00Z p1 td=157.08307 dk=157.098 rel=9.504e-05; GBPUSD 2026-10-25T21:00:00Z p0 td=1.33687 dk=1.337165 rel=2.206e-04; GBPUSD 2026-10-26T05:00:00Z p1 td=1.33742 dk=1.337385 rel=2.617e-05; USDCAD 2026-10-25T21:00:00Z p0 td=1.40324 dk=1.404635 rel=9.931e-04; USDCAD 2026-10-26T05:00:00Z p1 td=1.40088 dk=1.40082 rel=4.283e-05; USDCHF 2026-10-25T21:00:00Z p0 td=0.82424 dk=0.824355 rel=1.395e-04; USDCHF 2026-10-26T05:00:00Z p1 td=0.82433 dk=0.824245 rel=1.031e-04)

## Adjudicated WARNINGs (0)

- none

## Run summary

- accepted_push_diffs_unverified: 0
- canary_expected_windows: 0
- canary_terminals: 1
- cc_version_records_checked: 2
- contexts_rebuilt: 1
- ga_runs_read: 84
- head: 43bbb42e58a4dd66e768a86e84b32a335c6eb79c
- inbox_activity_entries: 47
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-10-26T11:01:58Z
- live_expected_windows: 0
- live_terminals: 0
- probe_creations_max_day: 11
- probe_records: 5
- routine_config_versions_checked: 4
- run_log_calls_scanned: 0
- run_logs_scanned: 0
- settled_checked: 0
- td_compared: 26
- td_outside: 2
- td_pending: 0
- td_unchecked: 0
- witness_comments: 5
- witness_files: 5
