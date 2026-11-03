# Analyst judge report

- asof_utc: 2026-11-03T08:37:56Z
- head_sha (gold-analyst main checked): ee5bbb5557be0da2c0ddd95a273e6fa5cb692d03
- judge code_sha8: 166ed4de
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

## WARNINGs needing an ADJUDICATIONS row or a fix (2)

- `A11|td_mismatch|analyst/canary/attempts/2026-11-03_T0400_1.json|ee5bbb5557be0da2c0ddd95a273e6fa5cb692d03` (outside 1e-3: XAUUSD 2026-11-03T02:30:00Z c td=3950.59509 dk=3945.695 rel=1.242e-03; XAUUSD 2026-11-03T03:00:00Z o td=3950.56367 dk=3945.6215 rel=1.253e-03; within: XAUUSD 2026-11-02T23:00:00Z o td=3946.87039 dk=3950.65 rel=9.567e-04; XAUUSD 2026-11-02T23:00:00Z c td=3944.10958 dk=3945.195 rel=2.751e-04; XAUUSD 2026-11-02T23:30:00Z o td=3944.45308 dk=3945.2145 rel=1.930e-04; XAUUSD 2026-11-02T23:30:00Z c td=3947.85313 dk=3948.0505 rel=4.999e-05; XAUUSD 2026-11-03T00:00:00Z o td=3947.95891 dk=3948.0545 rel=2.421e-05; XAUUSD 2026-11-03T00:00:00Z c td=3958.94025 dk=3957.3605 rel=3.992e-04; XAUUSD 2026-11-03T00:30:00Z o td=3958.15931 dk=3957.28 rel=2.222e-04; XAUUSD 2026-11-03T00:30:00Z c td=3959.94461 dk=3958.3505 rel=4.027e-04; XAUUSD 2026-11-03T01:00:00Z o td=3959.81611 dk=3958.2635 rel=3.922e-04; XAUUSD 2026-11-03T01:00:00Z c td=3955.2025 dk=3956.55 rel=3.406e-04; XAUUSD 2026-11-03T01:30:00Z o td=3953.71532 dk=3956.57 rel=7.215e-04; XAUUSD 2026-11-03T01:30:00Z c td=3950.01792 dk=3950.9 rel=2.233e-04; XAUUSD 2026-11-03T02:00:00Z o td=3948.74204 dk=3950.9 rel=5.462e-04; XAUUSD 2026-11-03T02:00:00Z c td=3946.18586 dk=3947.6445 rel=3.695e-04; XAUUSD 2026-11-03T02:30:00Z o td=3946.70125 dk=3947.676 rel=2.469e-04; XAUUSD 2026-11-03T03:00:00Z c td=3936.74484 dk=3937.4805 rel=1.868e-04; XAUUSD 2026-11-03T03:30:00Z o td=3936.50787 dk=3937.5005 rel=2.521e-04; XAUUSD 2026-11-03T03:30:00Z c td=3926.76748 dk=3926.4135 rel=9.015e-05)
- `A11|td_mismatch|analyst/canary/calls/2026-11-03_T0400.json|ee5bbb5557be0da2c0ddd95a273e6fa5cb692d03` (outside 1e-3: XAUUSD 2026-11-02T13:00:00Z c td=3945.83078 dk=3937.4805 rel=2.121e-03; XAUUSD 2026-11-02T14:00:00Z o td=3942.80114 dk=3937.65 rel=1.308e-03; XAUUSD 2026-11-03T02:00:00Z c td=3950.59509 dk=3945.695 rel=1.242e-03; within: XAUUSD 2026-11-01T23:00:00Z o td=3875.35765 dk=3876.535 rel=3.037e-04; XAUUSD 2026-11-01T23:00:00Z c td=3897.31977 dk=3898.376 rel=2.709e-04; XAUUSD 2026-11-02T00:00:00Z o td=3897.65954 dk=3898.376 rel=1.838e-04; XAUUSD 2026-11-02T00:00:00Z c td=3902.08883 dk=3902.039 rel=1.277e-05; XAUUSD 2026-11-02T01:00:00Z o td=3901.68253 dk=3902.1145 rel=1.107e-04; XAUUSD 2026-11-02T01:00:00Z c td=3910.03013 dk=3909.304 rel=1.857e-04; XAUUSD 2026-11-02T02:00:00Z o td=3909.64596 dk=3909.249 rel=1.015e-04; XAUUSD 2026-11-02T02:00:00Z c td=3895.5762 dk=3894.874 rel=1.803e-04; XAUUSD 2026-11-02T03:00:00Z o td=3894.81404 dk=3894.874 rel=1.539e-05; XAUUSD 2026-11-02T03:00:00Z c td=3901.14092 dk=3902.379 rel=3.173e-04; XAUUSD 2026-11-02T04:00:00Z o td=3901.01098 dk=3902.374 rel=3.493e-04; XAUUSD 2026-11-02T04:00:00Z c td=3900.64064 dk=3901.1505 rel=1.307e-04; XAUUSD 2026-11-02T05:00:00Z o td=3900.15743 dk=3901.144 rel=2.529e-04; XAUUSD 2026-11-02T05:00:00Z c td=3913.52645 dk=3913.386 rel=3.589e-05; XAUUSD 2026-11-02T06:00:00Z o td=3913.84482 dk=3913.3465 rel=1.273e-04; XAUUSD 2026-11-02T06:00:00Z c td=3907.06156 dk=3906.7665 rel=7.553e-05; XAUUSD 2026-11-02T07:00:00Z o td=3906.88143 dk=3906.7415 rel=3.582e-05; XAUUSD 2026-11-02T07:00:00Z c td=3903.4339 dk=3903.4105 rel=5.995e-06; XAUUSD 2026-11-02T08:00:00Z o td=3903.43307 dk=3903.4555 rel=5.746e-06; XAUUSD 2026-11-02T08:00:00Z c td=3897.58302 dk=3897.665 rel=2.103e-05; XAUUSD 2026-11-02T09:00:00Z o td=3897.38699 dk=3897.7695 rel=9.814e-05; XAUUSD 2026-11-02T09:00:00Z c td=3898.97927 dk=3897.87 rel=2.846e-04; XAUUSD 2026-11-02T10:00:00Z o td=3898.72786 dk=3897.87 rel=2.201e-04; XAUUSD 2026-11-02T10:00:00Z c td=3899.03579 dk=3898.6135 rel=1.083e-04; XAUUSD 2026-11-02T11:00:00Z o td=3898.87339 dk=3898.52 rel=9.065e-05; XAUUSD 2026-11-02T11:00:00Z c td=3901.58455 dk=3901.3405 rel=6.256e-05; XAUUSD 2026-11-02T12:00:00Z o td=3901.75681 dk=3901.4 rel=9.146e-05; XAUUSD 2026-11-02T12:00:00Z c td=3901.39644 dk=3901.145 rel=6.445e-05; XAUUSD 2026-11-02T13:00:00Z o td=3901.17841 dk=3901.1915 rel=3.355e-06; XAUUSD 2026-11-02T14:00:00Z c td=3965.85 dk=3964.46 rel=3.506e-04; XAUUSD 2026-11-02T15:00:00Z c td=3957.18057 dk=3957.893 rel=1.800e-04; XAUUSD 2026-11-02T16:00:00Z o td=3957.63048 dk=3957.92 rel=7.315e-05; XAUUSD 2026-11-02T16:00:00Z c td=3967.56533 dk=3967.755 rel=4.780e-05; XAUUSD 2026-11-02T17:00:00Z o td=3966.87724 dk=3967.7695 rel=2.249e-04; XAUUSD 2026-11-02T17:00:00Z c td=3956.93967 dk=3958.0335 rel=2.764e-04; XAUUSD 2026-11-02T18:00:00Z o td=3957.1765 dk=3958.0335 rel=2.165e-04; XAUUSD 2026-11-02T18:00:00Z c td=3954.23962 dk=3953.65 rel=1.491e-04; XAUUSD 2026-11-02T19:00:00Z o td=3954.13104 dk=3953.645 rel=1.229e-04; XAUUSD 2026-11-02T19:00:00Z c td=3944.31429 dk=3946.0455 rel=4.387e-04; XAUUSD 2026-11-02T20:00:00Z o td=3942.99398 dk=3946.0245 rel=7.680e-04; XAUUSD 2026-11-02T20:00:00Z c td=3946.08142 dk=3946.0305 rel=1.290e-05; XAUUSD 2026-11-02T21:00:00Z o td=3945.87594 dk=3946.0195 rel=3.638e-05; XAUUSD 2026-11-02T21:00:00Z c td=3946.67674 dk=3946.76 rel=2.110e-05; XAUUSD 2026-11-02T23:00:00Z o td=3946.87039 dk=3950.65 rel=9.567e-04; XAUUSD 2026-11-02T23:00:00Z c td=3947.85313 dk=3948.0505 rel=4.999e-05; XAUUSD 2026-11-03T00:00:00Z o td=3947.95891 dk=3948.0545 rel=2.421e-05; XAUUSD 2026-11-03T00:00:00Z c td=3959.94461 dk=3958.3505 rel=4.027e-04; XAUUSD 2026-11-03T01:00:00Z o td=3959.81611 dk=3958.2635 rel=3.922e-04; XAUUSD 2026-11-03T01:00:00Z c td=3950.01792 dk=3950.9 rel=2.233e-04; XAUUSD 2026-11-03T02:00:00Z o td=3948.74204 dk=3950.9 rel=5.462e-04; EURUSD 2026-11-02T22:00:00Z p0 td=1.11877 dk=1.1187 rel=6.257e-05; EURUSD 2026-11-03T02:00:00Z p1 td=1.11857 dk=1.11852 rel=4.470e-05; USDJPY 2026-11-02T22:00:00Z p0 td=157.96468 dk=157.9435 rel=1.341e-04; USDJPY 2026-11-03T02:00:00Z p1 td=157.90645 dk=157.901 rel=3.452e-05; USDCAD 2026-11-03T02:00:00Z p1 td=1.39909 dk=1.399065 rel=1.787e-05; USDCHF 2026-11-02T22:00:00Z p0 td=0.81869 dk=0.8187 rel=1.221e-05; AUDJPY 2026-11-02T22:00:00Z p0 td=110.54859 dk=110.5065 rel=3.809e-04)

## Adjudicated WARNINGs (67)

- `A11|td_mismatch|analyst/canary/attempts/2026-11-02_T1500_1.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W1.json|43bbb42e58a4dd66e768a86e84b32a335c6eb79c`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W2.json|e6008594960ece17a99cd9837c68c4782900b8da`
- `A11|td_mismatch|analyst/canary/calls/2026-10-27_W2.json|80cbca5d9e610f5235c4c6dbecf2132d41881c26`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W1.json|453f6d4579a8e736d3909aca5af8a96a36186213`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W2.json|ac3f7065d54f8d49c5bfc8d46cdbd8a611f62d99`
- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0100.json|6d77cc3c373c1fbe70cb145497cd274011f9e662`
- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0600.json|8af0b8d4024d1763ef9c4f8aa034fc6df466e987`
- `A11|td_mismatch|analyst/canary/calls/2026-11-02_T1500.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6`
- `A11|td_mismatch|analyst/canary/calls/2026-11-02_W2b.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_0117UL6f45qWcGmYWLXvVHBf#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_0117UL6f45qWcGmYWLXvVHBf#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_011wdj8cc8kpVUXxKb3uQH86#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_011wdj8cc8kpVUXxKb3uQH86#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz54q9ekSz2V94xcb9Gd#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz54q9ekSz2V94xcb9Gd#10`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz55AdgJ5pqic7uKvGfd#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz55DCxB8QU1DhYXePpF#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz55SPx4aS2ohrLCkq8v#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz55SPx4aS2ohrLCkq8v#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz55XNbcJ3cJXsSQydDr#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz55fmsTYmBV72XwxqEo#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz55gRobzzUQRf8uFCNB#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56CFwGips6u7NLo28J#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56PWMWA8gKzbTFSWZo#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56PWMWA8gKzbTFSWZo#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56mHnh1fc3Y8S9vEyC#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56mHnh1fc3Y8S9vEyC#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56mct5SCa96onrsrVG#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56mct5SCa96onrsrVG#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56rMt5rSaXW9LgDMbA#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56rMt5rSaXW9LgDMbA#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56zFQHsJcJkFFMvvxG#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56zFQHsJcJkFFMvvxG#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz56zn9UJVSQdKX8cvKH#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz576ZuZPbkrD3pw9M4Q#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz576ZuZPbkrD3pw9M4Q#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz579qMQ7UJL9zzxABx8#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz579qMQ7UJL9zzxABx8#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz57ao3LvqSfC9jAfwtW#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz57ao3LvqSfC9jAfwtW#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz57fvMUZXuHTD2fdXew#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz57fvMUZXuHTD2fdXew#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz57mhNi5ehCvgU2engN#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz57mhNi5ehCvgU2engN#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58225jQWJtFuVHSkEx#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58225jQWJtFuVHSkEx#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58KLsrygD7QuFsgtYE#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58TW1aDY1eYk97cVpR#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58TW1aDY1eYk97cVpR#9`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58XdZVLGHpToWgkuh4#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58a3v4o9PF7h1hSuTM#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58cSXsAD8LkJdSxGkZ#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58cSXsAD8LkJdSxGkZ#9`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58goxVD6GWuKzFSNmU#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58mWVKkC1Gmy9qJuLx#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58mWVKkC1Gmy9qJuLx#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58mz1eCrQC86FfJYBE#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58mz1eCrQC86FfJYBE#8`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz58t3eQToNCCHDuTrYy#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz594frUofWYYdf6mKxP#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz594frUofWYYdf6mKxP#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz59G4TXQVAbBygM2u7G#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_018qMz59G4TXQVAbBygM2u7G#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_01NgnPZU2HxBRsNDJvGRmpyc#1`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_01NgnPZU2HxBRsNDJvGRmpyc#4`
- `A13|guard_denied_benign|analyst/runs/2026-W44.json|cse_01U5CnNJcvxmm11dLL3q25Dt#1`

## Run summary

- accepted_push_diffs_unverified: 0
- canary_expected_windows: 19
- canary_terminals: 26
- cc_version_records_checked: 45
- contexts_rebuilt: 22
- ga_runs_read: 57
- head: ee5bbb5557be0da2c0ddd95a273e6fa5cb692d03
- inbox_activity_entries: 221
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-11-03T08:37:56Z
- live_expected_windows: 0
- live_terminals: 0
- m30_compared: 7
- m30r_compared: 2
- probe_creations_max_day: 18
- probe_records: 26
- routine_config_versions_checked: 5
- run_log_calls_scanned: 292
- run_logs_scanned: 37
- settled_checked: 0
- td_compared: 1202
- td_outside: 21
- td_pending: 8
- td_unchecked: 0
- witness_comments: 74
- witness_files: 74
