# Analyst judge report

- asof_utc: 2026-10-29T02:47:41Z
- head_sha (gold-analyst main checked): 34516b097fca95ae38854e9ad666c000ca8766b3
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

- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0100.json|6d77cc3c373c1fbe70cb145497cd274011f9e662` (outside 1e-3: XAUUSD 2026-10-28T18:00:00Z c td=4041.47299 dk=4033.105 rel=2.075e-03; within: XAUUSD 2026-10-28T00:00:00Z o td=4063.18978 dk=4062.85 rel=8.363e-05; XAUUSD 2026-10-28T00:00:00Z c td=4062.02552 dk=4062.007 rel=4.559e-06; XAUUSD 2026-10-28T01:00:00Z o td=4062.25686 dk=4062.165 rel=2.261e-05; XAUUSD 2026-10-28T01:00:00Z c td=4046.56333 dk=4048.805 rel=5.537e-04; XAUUSD 2026-10-28T02:00:00Z o td=4046.79101 dk=4048.897 rel=5.201e-04; XAUUSD 2026-10-28T02:00:00Z c td=4048.21918 dk=4046.435 rel=4.409e-04; XAUUSD 2026-10-28T03:00:00Z o td=4048.13708 dk=4046.488 rel=4.075e-04; XAUUSD 2026-10-28T03:00:00Z c td=4043.05227 dk=4042.91 rel=3.519e-05; XAUUSD 2026-10-28T04:00:00Z o td=4043.11146 dk=4042.897 rel=5.305e-05; XAUUSD 2026-10-28T04:00:00Z c td=4036.68891 dk=4036.678 rel=2.703e-06; XAUUSD 2026-10-28T05:00:00Z o td=4036.8744 dk=4036.645 rel=5.683e-05; XAUUSD 2026-10-28T05:00:00Z c td=4030.28331 dk=4030.283 rel=7.692e-08; XAUUSD 2026-10-28T06:00:00Z o td=4030.57482 dk=4030.207 rel=9.127e-05; XAUUSD 2026-10-28T06:00:00Z c td=4030.52849 dk=4030.748 rel=5.446e-05; XAUUSD 2026-10-28T07:00:00Z o td=4030.3151 dk=4030.688 rel=9.252e-05; XAUUSD 2026-10-28T07:00:00Z c td=4043.59476 dk=4044.678 rel=2.678e-04; XAUUSD 2026-10-28T08:00:00Z o td=4043.03979 dk=4044.635 rel=3.944e-04; XAUUSD 2026-10-28T08:00:00Z c td=4054.10038 dk=4053.0 rel=2.715e-04; XAUUSD 2026-10-28T09:00:00Z o td=4055.78736 dk=4053.0295 rel=6.804e-04; XAUUSD 2026-10-28T09:00:00Z c td=4054.50806 dk=4055.7 rel=2.939e-04; XAUUSD 2026-10-28T10:00:00Z o td=4053.24839 dk=4055.675 rel=5.983e-04; XAUUSD 2026-10-28T10:00:00Z c td=4044.69386 dk=4045.075 rel=9.422e-05; XAUUSD 2026-10-28T11:00:00Z o td=4044.80431 dk=4045.09 rel=7.063e-05; XAUUSD 2026-10-28T11:00:00Z c td=4046.46641 dk=4045.5145 rel=2.353e-04; XAUUSD 2026-10-28T12:00:00Z o td=4046.18553 dk=4045.505 rel=1.682e-04; XAUUSD 2026-10-28T12:00:00Z c td=4052.57537 dk=4053.3995 rel=2.033e-04; XAUUSD 2026-10-28T13:00:00Z o td=4051.96154 dk=4053.395 rel=3.536e-04; XAUUSD 2026-10-28T13:00:00Z c td=4048.68912 dk=4049.875 rel=2.928e-04; XAUUSD 2026-10-28T14:00:00Z o td=4049.04291 dk=4049.89 rel=2.092e-04; XAUUSD 2026-10-28T14:00:00Z c td=4041.80428 dk=4041.7155 rel=2.197e-05; XAUUSD 2026-10-28T15:00:00Z o td=4041.53464 dk=4041.74 rel=5.081e-05; XAUUSD 2026-10-28T15:00:00Z c td=4041.85362 dk=4041.955 rel=2.508e-05; XAUUSD 2026-10-28T16:00:00Z o td=4041.71592 dk=4041.975 rel=6.410e-05; XAUUSD 2026-10-28T16:00:00Z c td=4044.23565 dk=4042.51 rel=4.269e-04; XAUUSD 2026-10-28T17:00:00Z o td=4043.75174 dk=4042.4905 rel=3.120e-04; XAUUSD 2026-10-28T17:00:00Z c td=4041.01227 dk=4040.87 rel=3.521e-05; XAUUSD 2026-10-28T18:00:00Z o td=4040.88285 dk=4040.865 rel=4.417e-06; XAUUSD 2026-10-28T22:00:00Z c td=4051.96558 dk=4051.875 rel=2.236e-05; EURUSD 2026-10-28T23:00:00Z p1 td=1.11558 dk=1.11555 rel=2.689e-05; USDCAD 2026-10-28T21:00:00Z p0 td=1.39975 dk=1.399505 rel=1.751e-04; USDCAD 2026-10-28T23:00:00Z p1 td=1.3987 dk=1.398765 rel=4.647e-05; USDCHF 2026-10-28T21:00:00Z p0 td=0.82819 dk=0.82818 rel=1.207e-05; USDCHF 2026-10-28T23:00:00Z p1 td=0.82806 dk=0.827995 rel=7.850e-05; AUDJPY 2026-10-28T21:00:00Z p0 td=111.3316 dk=111.342 rel=9.341e-05; AUDJPY 2026-10-28T23:00:00Z p1 td=111.40042 dk=111.374 rel=2.372e-04)

## Adjudicated WARNINGs (5)

- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W1.json|43bbb42e58a4dd66e768a86e84b32a335c6eb79c`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W2.json|e6008594960ece17a99cd9837c68c4782900b8da`
- `A11|td_mismatch|analyst/canary/calls/2026-10-27_W2.json|80cbca5d9e610f5235c4c6dbecf2132d41881c26`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W1.json|453f6d4579a8e736d3909aca5af8a96a36186213`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W2.json|ac3f7065d54f8d49c5bfc8d46cdbd8a611f62d99`

## Run summary

- accepted_push_diffs_unverified: 0
- canary_expected_windows: 4
- canary_terminals: 7
- cc_version_records_checked: 13
- contexts_rebuilt: 6
- ga_runs_read: 128
- head: 34516b097fca95ae38854e9ad666c000ca8766b3
- inbox_activity_entries: 101
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-10-29T02:47:41Z
- live_expected_windows: 0
- live_terminals: 0
- probe_creations_max_day: 14
- probe_records: 10
- routine_config_versions_checked: 5
- run_log_calls_scanned: 0
- run_logs_scanned: 0
- settled_checked: 0
- td_compared: 308
- td_outside: 8
- td_pending: 14
- td_unchecked: 0
- witness_comments: 23
- witness_files: 23
