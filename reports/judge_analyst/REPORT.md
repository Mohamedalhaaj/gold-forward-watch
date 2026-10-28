# Analyst judge report

- asof_utc: 2026-10-28T14:04:57Z
- head_sha (gold-analyst main checked): ac3f7065d54f8d49c5bfc8d46cdbd8a611f62d99
- judge code_sha8: 1ba45fbb
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

- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W2.json|ac3f7065d54f8d49c5bfc8d46cdbd8a611f62d99` (outside 1e-3: XAUUSD 2026-10-27T10:00:00Z o td=3998.38364 dk=4002.765 rel=1.095e-03; within: XAUUSD 2026-10-27T00:00:00Z o td=4005.89293 dk=4005.995 rel=2.548e-05; XAUUSD 2026-10-27T00:00:00Z c td=4009.42064 dk=4009.495 rel=1.855e-05; XAUUSD 2026-10-27T01:00:00Z o td=4009.40529 dk=4009.365 rel=1.005e-05; XAUUSD 2026-10-27T01:00:00Z c td=4011.33976 dk=4011.21 rel=3.235e-05; XAUUSD 2026-10-27T02:00:00Z o td=4011.05584 dk=4011.207 rel=3.768e-05; XAUUSD 2026-10-27T02:00:00Z c td=4009.83512 dk=4009.768 rel=1.674e-05; XAUUSD 2026-10-27T03:00:00Z o td=4009.63412 dk=4009.773 rel=3.464e-05; XAUUSD 2026-10-27T03:00:00Z c td=4016.63882 dk=4017.397 rel=1.887e-04; XAUUSD 2026-10-27T04:00:00Z o td=4016.25309 dk=4017.522 rel=3.158e-04; XAUUSD 2026-10-27T04:00:00Z c td=4011.19096 dk=4010.64 rel=1.374e-04; XAUUSD 2026-10-27T05:00:00Z o td=4011.09753 dk=4010.703 rel=9.837e-05; XAUUSD 2026-10-27T05:00:00Z c td=4010.88191 dk=4009.037 rel=4.602e-04; XAUUSD 2026-10-27T06:00:00Z o td=4010.8186 dk=4008.887 rel=4.818e-04; XAUUSD 2026-10-27T06:00:00Z c td=4000.88308 dk=4000.912 rel=7.228e-06; XAUUSD 2026-10-27T07:00:00Z o td=4000.75141 dk=4000.827 rel=1.889e-05; XAUUSD 2026-10-27T07:00:00Z c td=3997.59559 dk=3998.245 rel=1.624e-04; XAUUSD 2026-10-27T08:00:00Z o td=3997.79333 dk=3998.213 rel=1.050e-04; XAUUSD 2026-10-27T08:00:00Z c td=3993.51336 dk=3994.857 rel=3.363e-04; XAUUSD 2026-10-27T09:00:00Z o td=3993.33298 dk=3994.86 rel=3.822e-04; XAUUSD 2026-10-27T09:00:00Z c td=4001.25292 dk=4002.805 rel=3.877e-04; XAUUSD 2026-10-27T10:00:00Z c td=4010.34679 dk=4008.745 rel=3.996e-04; XAUUSD 2026-10-27T11:00:00Z o td=4009.88618 dk=4008.63 rel=3.134e-04; XAUUSD 2026-10-27T11:00:00Z c td=4012.60037 dk=4012.475 rel=3.125e-05; XAUUSD 2026-10-27T12:00:00Z o td=4012.73716 dk=4012.562 rel=4.365e-05; XAUUSD 2026-10-27T12:00:00Z c td=4023.59303 dk=4023.255 rel=8.402e-05; XAUUSD 2026-10-27T13:00:00Z o td=4023.38864 dk=4023.29 rel=2.452e-05; XAUUSD 2026-10-27T13:00:00Z c td=4028.25212 dk=4029.79 rel=3.816e-04; XAUUSD 2026-10-27T14:00:00Z o td=4026.9311 dk=4029.715 rel=6.908e-04; XAUUSD 2026-10-27T14:00:00Z c td=4052.58302 dk=4052.345 rel=5.874e-05; XAUUSD 2026-10-27T15:00:00Z o td=4052.42704 dk=4052.465 rel=9.367e-06; XAUUSD 2026-10-27T15:00:00Z c td=4063.55638 dk=4063.585 rel=7.043e-06; XAUUSD 2026-10-27T16:00:00Z o td=4063.3928 dk=4063.685 rel=7.191e-05; XAUUSD 2026-10-27T16:00:00Z c td=4058.79986 dk=4059.205 rel=9.981e-05; XAUUSD 2026-10-27T17:00:00Z o td=4058.89894 dk=4059.2 rel=7.417e-05; XAUUSD 2026-10-27T17:00:00Z c td=4056.94859 dk=4056.78 rel=4.156e-05; XAUUSD 2026-10-27T18:00:00Z o td=4057.1802 dk=4056.77 rel=1.011e-04; XAUUSD 2026-10-27T18:00:00Z c td=4056.8309 dk=4056.685 rel=3.597e-05; XAUUSD 2026-10-27T19:00:00Z o td=4056.73354 dk=4056.705 rel=7.035e-06; XAUUSD 2026-10-27T19:00:00Z c td=4062.2879 dk=4061.602 rel=1.689e-04; XAUUSD 2026-10-27T20:00:00Z o td=4061.9842 dk=4061.567 rel=1.027e-04; XAUUSD 2026-10-27T20:00:00Z c td=4060.31624 dk=4060.54 rel=5.511e-05; XAUUSD 2026-10-27T22:00:00Z o td=4058.12386 dk=4061.795 rel=9.038e-04; XAUUSD 2026-10-27T22:00:00Z c td=4062.87713 dk=4063.605 rel=1.791e-04; XAUUSD 2026-10-27T23:00:00Z o td=4063.02566 dk=4063.745 rel=1.770e-04; XAUUSD 2026-10-27T23:00:00Z c td=4062.92239 dk=4062.868 rel=1.339e-05; XAUUSD 2026-10-28T00:00:00Z o td=4063.18978 dk=4062.85 rel=8.363e-05; XAUUSD 2026-10-28T00:00:00Z c td=4062.02552 dk=4062.007 rel=4.559e-06; XAUUSD 2026-10-28T01:00:00Z o td=4062.25686 dk=4062.165 rel=2.261e-05; XAUUSD 2026-10-28T01:00:00Z c td=4046.56333 dk=4048.805 rel=5.537e-04; XAUUSD 2026-10-28T02:00:00Z o td=4046.79101 dk=4048.897 rel=5.201e-04; XAUUSD 2026-10-28T02:00:00Z c td=4048.21918 dk=4046.435 rel=4.409e-04; XAUUSD 2026-10-28T03:00:00Z o td=4048.13708 dk=4046.488 rel=4.075e-04; XAUUSD 2026-10-28T03:00:00Z c td=4043.05227 dk=4042.91 rel=3.519e-05; XAUUSD 2026-10-28T04:00:00Z o td=4043.11146 dk=4042.897 rel=5.305e-05; XAUUSD 2026-10-28T04:00:00Z c td=4036.68891 dk=4036.678 rel=2.703e-06; XAUUSD 2026-10-28T05:00:00Z o td=4036.8744 dk=4036.645 rel=5.683e-05; XAUUSD 2026-10-28T05:00:00Z c td=4030.28331 dk=4030.283 rel=7.692e-08; XAUUSD 2026-10-28T06:00:00Z o td=4030.57482 dk=4030.207 rel=9.127e-05; XAUUSD 2026-10-28T06:00:00Z c td=4030.52849 dk=4030.748 rel=5.446e-05; XAUUSD 2026-10-28T07:00:00Z o td=4030.3151 dk=4030.688 rel=9.252e-05; XAUUSD 2026-10-28T07:00:00Z c td=4043.59476 dk=4044.678 rel=2.678e-04; USDJPY 2026-10-27T21:00:00Z p0 td=157.95173 dk=157.951 rel=4.622e-06; GBPUSD 2026-10-27T21:00:00Z p0 td=1.33069 dk=1.330555 rel=1.015e-04; GBPUSD 2026-10-28T11:00:00Z p1 td=1.32873 dk=1.328775 rel=3.387e-05; USDCAD 2026-10-27T21:00:00Z p0 td=1.40515 dk=1.405175 rel=1.779e-05; USDCHF 2026-10-27T21:00:00Z p0 td=0.82912 dk=0.828935 rel=2.232e-04; USDCHF 2026-10-28T11:00:00Z p1 td=0.82973 dk=0.829645 rel=1.025e-04; AUDJPY 2026-10-27T21:00:00Z p0 td=110.97149 dk=110.9745 rel=2.712e-05; AUDJPY 2026-10-28T11:00:00Z p1 td=111.08262 dk=111.085 rel=2.143e-05)

## Adjudicated WARNINGs (4)

- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W1.json|43bbb42e58a4dd66e768a86e84b32a335c6eb79c`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W2.json|e6008594960ece17a99cd9837c68c4782900b8da`
- `A11|td_mismatch|analyst/canary/calls/2026-10-27_W2.json|80cbca5d9e610f5235c4c6dbecf2132d41881c26`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W1.json|453f6d4579a8e736d3909aca5af8a96a36186213`

## Run summary

- accepted_push_diffs_unverified: 0
- canary_expected_windows: 2
- canary_terminals: 6
- cc_version_records_checked: 11
- contexts_rebuilt: 5
- ga_runs_read: 105
- head: ac3f7065d54f8d49c5bfc8d46cdbd8a611f62d99
- inbox_activity_entries: 91
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-10-28T14:04:57Z
- live_expected_windows: 0
- live_terminals: 0
- probe_creations_max_day: 14
- probe_records: 9
- routine_config_versions_checked: 5
- run_log_calls_scanned: 0
- run_logs_scanned: 0
- settled_checked: 0
- td_compared: 237
- td_outside: 7
- td_pending: 15
- td_unchecked: 0
- witness_comments: 20
- witness_files: 20
