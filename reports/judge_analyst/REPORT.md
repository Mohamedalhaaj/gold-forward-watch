# Analyst judge report

- asof_utc: 2026-10-27T13:22:39Z
- head_sha (gold-analyst main checked): 80cbca5d9e610f5235c4c6dbecf2132d41881c26
- judge code_sha8: a75e5fde
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

- `A11|td_mismatch|analyst/canary/calls/2026-10-27_W2.json|80cbca5d9e610f5235c4c6dbecf2132d41881c26` (outside 1e-3: XAUUSD 2026-10-27T10:00:00Z o td=3998.38364 dk=4002.765 rel=1.095e-03; within: XAUUSD 2026-10-27T00:00:00Z o td=4005.89293 dk=4005.995 rel=2.548e-05; XAUUSD 2026-10-27T00:00:00Z c td=4009.42064 dk=4009.495 rel=1.855e-05; XAUUSD 2026-10-27T01:00:00Z o td=4009.40529 dk=4009.365 rel=1.005e-05; XAUUSD 2026-10-27T01:00:00Z c td=4011.33976 dk=4011.21 rel=3.235e-05; XAUUSD 2026-10-27T02:00:00Z o td=4011.05584 dk=4011.207 rel=3.768e-05; XAUUSD 2026-10-27T02:00:00Z c td=4009.83512 dk=4009.768 rel=1.674e-05; XAUUSD 2026-10-27T03:00:00Z o td=4009.63412 dk=4009.773 rel=3.464e-05; XAUUSD 2026-10-27T03:00:00Z c td=4016.63882 dk=4017.397 rel=1.887e-04; XAUUSD 2026-10-27T04:00:00Z o td=4016.25309 dk=4017.522 rel=3.158e-04; XAUUSD 2026-10-27T04:00:00Z c td=4011.19096 dk=4010.64 rel=1.374e-04; XAUUSD 2026-10-27T05:00:00Z o td=4011.09753 dk=4010.703 rel=9.837e-05; XAUUSD 2026-10-27T05:00:00Z c td=4010.88191 dk=4009.037 rel=4.602e-04; XAUUSD 2026-10-27T06:00:00Z o td=4010.8186 dk=4008.887 rel=4.818e-04; XAUUSD 2026-10-27T06:00:00Z c td=4000.88308 dk=4000.912 rel=7.228e-06; XAUUSD 2026-10-27T07:00:00Z o td=4000.75141 dk=4000.827 rel=1.889e-05; XAUUSD 2026-10-27T07:00:00Z c td=3997.59559 dk=3998.245 rel=1.624e-04; XAUUSD 2026-10-27T08:00:00Z c td=3993.51336 dk=3994.857 rel=3.363e-04; XAUUSD 2026-10-27T09:00:00Z c td=4001.25292 dk=4002.805 rel=3.877e-04; XAUUSD 2026-10-27T10:00:00Z c td=4010.34679 dk=4008.745 rel=3.996e-04; XAUUSD 2026-10-27T11:00:00Z o td=4009.88618 dk=4008.63 rel=3.134e-04; XAUUSD 2026-10-27T11:00:00Z c td=4012.60037 dk=4012.475 rel=3.125e-05; GBPUSD 2026-10-27T11:00:00Z p1 td=1.33195 dk=1.331905 rel=3.379e-05; USDCAD 2026-10-26T21:00:00Z p0 td=1.40132 dk=1.40131 rel=7.136e-06; USDCHF 2026-10-26T21:00:00Z p0 td=0.82774 dk=0.82756 rel=2.175e-04; USDCHF 2026-10-27T11:00:00Z p1 td=0.82888 dk=0.828745 rel=1.629e-04; AUDJPY 2026-10-26T21:00:00Z p0 td=110.50842 dk=110.5365 rel=2.540e-04; AUDJPY 2026-10-27T11:00:00Z p1 td=110.92075 dk=110.9125 rel=7.438e-05)

## Adjudicated WARNINGs (2)

- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W1.json|43bbb42e58a4dd66e768a86e84b32a335c6eb79c`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W2.json|e6008594960ece17a99cd9837c68c4782900b8da`

## Run summary

- accepted_push_diffs_unverified: 0
- canary_expected_windows: 0
- canary_terminals: 4
- cc_version_records_checked: 6
- contexts_rebuilt: 3
- ga_runs_read: 88
- head: 80cbca5d9e610f5235c4c6dbecf2132d41881c26
- inbox_activity_entries: 69
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-10-27T13:22:39Z
- live_expected_windows: 0
- live_terminals: 0
- probe_creations_max_day: 14
- probe_records: 7
- routine_config_versions_checked: 4
- run_log_calls_scanned: 0
- run_logs_scanned: 0
- settled_checked: 0
- td_compared: 92
- td_outside: 5
- td_pending: 8
- td_unchecked: 0
- witness_comments: 12
- witness_files: 12
