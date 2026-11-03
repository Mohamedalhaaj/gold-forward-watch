# Analyst judge report

- asof_utc: 2026-11-03T22:17:38Z
- head_sha (gold-analyst main checked): 985c6a90adaa1012568d0afba6c4d545fca100ea
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

## WARNINGs needing an ADJUDICATIONS row or a fix (3)

- `A11|td_mismatch|analyst/canary/calls/2026-11-03_W2.json|5b1e296386b35972cf35f59c57a777da68576c3f` (outside 1e-3: XAUUSD 2026-11-03T02:00:00Z c td=3950.59509 dk=3945.695 rel=1.242e-03; XAUUSD 2026-11-03T03:00:00Z o td=3950.56367 dk=3945.6215 rel=1.253e-03; within: XAUUSD 2026-11-03T00:00:00Z o td=3947.95891 dk=3948.0545 rel=2.421e-05; XAUUSD 2026-11-03T00:00:00Z c td=3959.94461 dk=3958.3505 rel=4.027e-04; XAUUSD 2026-11-03T01:00:00Z o td=3959.81611 dk=3958.2635 rel=3.922e-04; XAUUSD 2026-11-03T01:00:00Z c td=3950.01792 dk=3950.9 rel=2.233e-04; XAUUSD 2026-11-03T02:00:00Z o td=3948.74204 dk=3950.9 rel=5.462e-04; XAUUSD 2026-11-03T03:00:00Z c td=3926.76748 dk=3926.4135 rel=9.015e-05; XAUUSD 2026-11-03T04:00:00Z o td=3926.70783 dk=3926.344 rel=9.266e-05; XAUUSD 2026-11-03T04:00:00Z c td=3924.7392 dk=3923.6735 rel=2.716e-04; XAUUSD 2026-11-03T05:00:00Z o td=3924.52746 dk=3923.678 rel=2.165e-04; XAUUSD 2026-11-03T05:00:00Z c td=3918.73414 dk=3918.63 rel=2.658e-05; XAUUSD 2026-11-03T06:00:00Z o td=3918.8894 dk=3918.545 rel=8.789e-05; XAUUSD 2026-11-03T06:00:00Z c td=3912.27247 dk=3911.814 rel=1.172e-04; XAUUSD 2026-11-03T07:00:00Z o td=3912.37908 dk=3911.81 rel=1.455e-04; XAUUSD 2026-11-03T07:00:00Z c td=3908.35147 dk=3906.8255 rel=3.906e-04; XAUUSD 2026-11-03T08:00:00Z o td=3908.84583 dk=3906.82 rel=5.185e-04; XAUUSD 2026-11-03T08:00:00Z c td=3897.13364 dk=3897.01 rel=3.173e-05; XAUUSD 2026-11-03T09:00:00Z o td=3897.42511 dk=3897.1335 rel=7.483e-05; XAUUSD 2026-11-03T09:00:00Z c td=3909.38621 dk=3909.5595 rel=4.432e-05; XAUUSD 2026-11-03T10:00:00Z o td=3909.21193 dk=3909.5545 rel=8.762e-05; XAUUSD 2026-11-03T10:00:00Z c td=3904.61069 dk=3905.4145 rel=2.058e-04; XAUUSD 2026-11-03T11:00:00Z o td=3904.15253 dk=3905.41 rel=3.220e-04; XAUUSD 2026-11-03T11:00:00Z c td=3905.57975 dk=3906.0295 rel=1.151e-04; XAUUSD 2026-11-03T12:00:00Z o td=3905.3401 dk=3906.0065 rel=1.706e-04; XAUUSD 2026-11-03T12:00:00Z c td=3932.23768 dk=3932.7345 rel=1.263e-04; EURUSD 2026-11-02T22:00:00Z p0 td=1.11877 dk=1.1187 rel=6.257e-05; EURUSD 2026-11-03T12:00:00Z p1 td=1.1182 dk=1.118135 rel=5.813e-05; USDJPY 2026-11-02T22:00:00Z p0 td=157.96468 dk=157.9435 rel=1.341e-04; USDJPY 2026-11-03T12:00:00Z p1 td=158.22445 dk=158.229 rel=2.876e-05; GBPUSD 2026-11-02T22:00:00Z p0 td=1.34073 dk=1.34062 rel=8.205e-05; GBPUSD 2026-11-03T12:00:00Z p1 td=1.34126 dk=1.34121 rel=3.728e-05; USDCAD 2026-11-02T22:00:00Z p0 td=1.39859 dk=1.398735 rel=1.037e-04; USDCAD 2026-11-03T12:00:00Z p1 td=1.39755 dk=1.39756 rel=7.155e-06; USDCHF 2026-11-02T22:00:00Z p0 td=0.81869 dk=0.8187 rel=1.221e-05; USDCHF 2026-11-03T12:00:00Z p1 td=0.81984 dk=0.81986 rel=2.439e-05; AUDJPY 2026-11-02T22:00:00Z p0 td=110.54859 dk=110.5065 rel=3.809e-04; AUDJPY 2026-11-03T12:00:00Z p1 td=110.47465 dk=110.473 rel=1.494e-05)
- `A11|td_mismatch|analyst/canary/calls/2026-11-03_W2b.json|985c6a90adaa1012568d0afba6c4d545fca100ea` (outside 1e-3: XAUUSD 2026-11-03T02:00:00Z c td=3950.59509 dk=3945.695 rel=1.242e-03; XAUUSD 2026-11-03T03:00:00Z o td=3950.56367 dk=3945.6215 rel=1.253e-03; XAUUSD 2026-11-03T13:00:00Z c td=3965.293 dk=3960.915 rel=1.105e-03; within: XAUUSD 2026-11-03T00:00:00Z o td=3947.95891 dk=3948.0545 rel=2.421e-05; XAUUSD 2026-11-03T00:00:00Z c td=3959.94461 dk=3958.3505 rel=4.027e-04; XAUUSD 2026-11-03T01:00:00Z o td=3959.81611 dk=3958.2635 rel=3.922e-04; XAUUSD 2026-11-03T01:00:00Z c td=3950.01792 dk=3950.9 rel=2.233e-04; XAUUSD 2026-11-03T02:00:00Z o td=3948.74204 dk=3950.9 rel=5.462e-04; XAUUSD 2026-11-03T03:00:00Z c td=3926.76748 dk=3926.4135 rel=9.015e-05; XAUUSD 2026-11-03T04:00:00Z o td=3926.70783 dk=3926.344 rel=9.266e-05; XAUUSD 2026-11-03T04:00:00Z c td=3924.7392 dk=3923.6735 rel=2.716e-04; XAUUSD 2026-11-03T05:00:00Z o td=3924.52746 dk=3923.678 rel=2.165e-04; XAUUSD 2026-11-03T05:00:00Z c td=3918.73414 dk=3918.63 rel=2.658e-05; XAUUSD 2026-11-03T06:00:00Z o td=3918.8894 dk=3918.545 rel=8.789e-05; XAUUSD 2026-11-03T06:00:00Z c td=3912.27247 dk=3911.814 rel=1.172e-04; XAUUSD 2026-11-03T07:00:00Z o td=3912.37908 dk=3911.81 rel=1.455e-04; XAUUSD 2026-11-03T07:00:00Z c td=3908.35147 dk=3906.8255 rel=3.906e-04; XAUUSD 2026-11-03T08:00:00Z o td=3908.84583 dk=3906.82 rel=5.185e-04; XAUUSD 2026-11-03T08:00:00Z c td=3897.13364 dk=3897.01 rel=3.173e-05; XAUUSD 2026-11-03T09:00:00Z o td=3897.42511 dk=3897.1335 rel=7.483e-05; XAUUSD 2026-11-03T09:00:00Z c td=3909.38621 dk=3909.5595 rel=4.432e-05; XAUUSD 2026-11-03T10:00:00Z o td=3909.21193 dk=3909.5545 rel=8.762e-05; XAUUSD 2026-11-03T10:00:00Z c td=3904.61069 dk=3905.4145 rel=2.058e-04; XAUUSD 2026-11-03T11:00:00Z o td=3904.15253 dk=3905.41 rel=3.220e-04; XAUUSD 2026-11-03T11:00:00Z c td=3905.57975 dk=3906.0295 rel=1.151e-04; XAUUSD 2026-11-03T12:00:00Z o td=3905.3401 dk=3906.0065 rel=1.706e-04; XAUUSD 2026-11-03T12:00:00Z c td=3932.23768 dk=3932.7345 rel=1.263e-04; XAUUSD 2026-11-03T13:00:00Z o td=3931.40989 dk=3932.7115 rel=3.310e-04; XAUUSD 2026-11-03T14:00:00Z o td=3964.7532 dk=3960.9 rel=9.728e-04; XAUUSD 2026-11-03T14:00:00Z c td=3944.77697 dk=3944.6755 rel=2.572e-05; EURUSD 2026-11-02T22:00:00Z p0 td=1.11877 dk=1.1187 rel=6.257e-05; EURUSD 2026-11-03T14:00:00Z p1 td=1.11979 dk=1.11976 rel=2.679e-05; USDJPY 2026-11-02T22:00:00Z p0 td=157.96468 dk=157.9435 rel=1.341e-04; USDJPY 2026-11-03T14:00:00Z p1 td=158.28923 dk=158.277 rel=7.727e-05; GBPUSD 2026-11-02T22:00:00Z p0 td=1.34073 dk=1.34062 rel=8.205e-05; GBPUSD 2026-11-03T14:00:00Z p1 td=1.34308 dk=1.343105 rel=1.861e-05; USDCAD 2026-11-02T22:00:00Z p0 td=1.39859 dk=1.398735 rel=1.037e-04; USDCAD 2026-11-03T14:00:00Z p1 td=1.39885 dk=1.39882 rel=2.145e-05; USDCHF 2026-11-02T22:00:00Z p0 td=0.81869 dk=0.8187 rel=1.221e-05; AUDJPY 2026-11-02T22:00:00Z p0 td=110.54859 dk=110.5065 rel=3.809e-04)
- `A12|probe_incomplete|analyst/canary/calls/2026-11-03_W2b.json|985c6a90adaa1012568d0afba6c4d545fca100ea` (verdict; incomplete)

## Adjudicated WARNINGs (73)

- `A11|td_mismatch|analyst/canary/attempts/2026-11-02_T1500_1.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6`
- `A11|td_mismatch|analyst/canary/attempts/2026-11-03_T0400_1.json|ee5bbb5557be0da2c0ddd95a273e6fa5cb692d03`
- `A11|td_mismatch|analyst/canary/attempts/2026-11-03_T0830_1.json|9ae12d19765b63dce9f4e7658ec242d3ac94be69`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W1.json|43bbb42e58a4dd66e768a86e84b32a335c6eb79c`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W2.json|e6008594960ece17a99cd9837c68c4782900b8da`
- `A11|td_mismatch|analyst/canary/calls/2026-10-27_W2.json|80cbca5d9e610f5235c4c6dbecf2132d41881c26`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W1.json|453f6d4579a8e736d3909aca5af8a96a36186213`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W2.json|ac3f7065d54f8d49c5bfc8d46cdbd8a611f62d99`
- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0100.json|6d77cc3c373c1fbe70cb145497cd274011f9e662`
- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0600.json|8af0b8d4024d1763ef9c4f8aa034fc6df466e987`
- `A11|td_mismatch|analyst/canary/calls/2026-11-02_T1500.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6`
- `A11|td_mismatch|analyst/canary/calls/2026-11-02_W2b.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6`
- `A11|td_mismatch|analyst/canary/calls/2026-11-03_T0400.json|ee5bbb5557be0da2c0ddd95a273e6fa5cb692d03`
- `A11|td_mismatch|analyst/canary/calls/2026-11-03_T0830.json|9ae12d19765b63dce9f4e7658ec242d3ac94be69`
- `A11|td_mismatch|analyst/canary/calls/2026-11-03_W1.json|9ae12d19765b63dce9f4e7658ec242d3ac94be69`
- `A11|td_mismatch|analyst/canary/calls/2026-11-03_W1b.json|9ae12d19765b63dce9f4e7658ec242d3ac94be69`
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
- canary_expected_windows: 22
- canary_terminals: 31
- cc_version_records_checked: 57
- contexts_rebuilt: 27
- ga_runs_read: 78
- head: 985c6a90adaa1012568d0afba6c4d545fca100ea
- inbox_activity_entries: 245
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-11-03T22:17:38Z
- live_expected_windows: 0
- live_terminals: 0
- m30_compared: 7
- m30r_compared: 2
- probe_creations_max_day: 18
- probe_records: 31
- routine_config_versions_checked: 5
- run_log_calls_scanned: 292
- run_logs_scanned: 37
- settled_checked: 2
- td_compared: 1556
- td_outside: 38
- td_pending: 2
- td_unchecked: 0
- witness_comments: 93
- witness_files: 93
