# Analyst judge report

- asof_utc: 2026-11-02T23:52:09Z
- head_sha (gold-analyst main checked): 172d3be7f38f8a3ed966d4cff40d29c59d7274e6
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

- `A11|td_mismatch|analyst/canary/attempts/2026-11-02_T1500_1.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6` (outside 1e-3: XAUUSD 2026-11-02T13:30:00Z c td=3945.83078 dk=3937.4805 rel=2.121e-03; XAUUSD 2026-11-02T14:00:00Z o td=3942.80114 dk=3937.65 rel=1.308e-03; within: XAUUSD 2026-11-01T23:00:00Z o td=3875.35765 dk=3876.535 rel=3.037e-04; XAUUSD 2026-11-01T23:00:00Z c td=3899.70035 dk=3898.44 rel=3.233e-04; XAUUSD 2026-11-01T23:30:00Z o td=3900.59091 dk=3898.4695 rel=5.442e-04; XAUUSD 2026-11-01T23:30:00Z c td=3897.31977 dk=3898.376 rel=2.709e-04; XAUUSD 2026-11-02T00:30:00Z o td=3898.85615 dk=3899.492 rel=1.631e-04; XAUUSD 2026-11-02T00:30:00Z c td=3902.08883 dk=3902.039 rel=1.277e-05; XAUUSD 2026-11-02T01:00:00Z o td=3901.68253 dk=3902.1145 rel=1.107e-04; XAUUSD 2026-11-02T01:00:00Z c td=3906.11283 dk=3907.085 rel=2.488e-04; XAUUSD 2026-11-02T01:30:00Z o td=3906.47985 dk=3907.0705 rel=1.512e-04; XAUUSD 2026-11-02T01:30:00Z c td=3910.03013 dk=3909.304 rel=1.857e-04; XAUUSD 2026-11-02T04:30:00Z o td=3905.14395 dk=3904.072 rel=2.746e-04; XAUUSD 2026-11-02T04:30:00Z c td=3900.64064 dk=3901.1505 rel=1.307e-04; XAUUSD 2026-11-02T05:00:00Z o td=3900.15743 dk=3901.144 rel=2.529e-04; XAUUSD 2026-11-02T05:00:00Z c td=3907.3403 dk=3909.718 rel=6.082e-04; XAUUSD 2026-11-02T05:30:00Z o td=3906.67793 dk=3909.706 rel=7.745e-04; XAUUSD 2026-11-02T05:30:00Z c td=3913.52645 dk=3913.386 rel=3.589e-05; XAUUSD 2026-11-02T06:00:00Z o td=3913.84482 dk=3913.3465 rel=1.273e-04; XAUUSD 2026-11-02T06:00:00Z c td=3908.2659 dk=3908.569 rel=7.755e-05; XAUUSD 2026-11-02T06:30:00Z o td=3908.31922 dk=3908.556 rel=6.058e-05; XAUUSD 2026-11-02T06:30:00Z c td=3907.06156 dk=3906.7665 rel=7.553e-05; XAUUSD 2026-11-02T07:00:00Z o td=3906.88143 dk=3906.7415 rel=3.582e-05; XAUUSD 2026-11-02T07:00:00Z c td=3906.099 dk=3907.623 rel=3.900e-04; XAUUSD 2026-11-02T07:30:00Z o td=3906.23893 dk=3907.6305 rel=3.561e-04; XAUUSD 2026-11-02T07:30:00Z c td=3903.4339 dk=3903.4105 rel=5.995e-06; XAUUSD 2026-11-02T08:00:00Z o td=3903.43307 dk=3903.4555 rel=5.746e-06; XAUUSD 2026-11-02T08:00:00Z c td=3894.12315 dk=3895.44 rel=3.380e-04; XAUUSD 2026-11-02T08:30:00Z o td=3892.49339 dk=3895.405 rel=7.474e-04; XAUUSD 2026-11-02T08:30:00Z c td=3897.58302 dk=3897.665 rel=2.103e-05; XAUUSD 2026-11-02T09:00:00Z o td=3897.38699 dk=3897.7695 rel=9.814e-05; XAUUSD 2026-11-02T09:00:00Z c td=3900.17827 dk=3899.525 rel=1.675e-04; XAUUSD 2026-11-02T09:30:00Z o td=3899.88878 dk=3899.5795 rel=7.931e-05; XAUUSD 2026-11-02T09:30:00Z c td=3898.97927 dk=3897.87 rel=2.846e-04; XAUUSD 2026-11-02T10:00:00Z o td=3898.72786 dk=3897.87 rel=2.201e-04; XAUUSD 2026-11-02T10:00:00Z c td=3896.32461 dk=3894.8845 rel=3.697e-04; XAUUSD 2026-11-02T10:30:00Z o td=3896.15974 dk=3895.0195 rel=2.927e-04; XAUUSD 2026-11-02T10:30:00Z c td=3899.03579 dk=3898.6135 rel=1.083e-04; XAUUSD 2026-11-02T11:00:00Z o td=3898.87339 dk=3898.52 rel=9.065e-05; XAUUSD 2026-11-02T11:00:00Z c td=3904.37325 dk=3903.9845 rel=9.958e-05; XAUUSD 2026-11-02T11:30:00Z o td=3904.2042 dk=3903.8505 rel=9.060e-05; XAUUSD 2026-11-02T11:30:00Z c td=3901.58455 dk=3901.3405 rel=6.256e-05; XAUUSD 2026-11-02T12:00:00Z o td=3901.75681 dk=3901.4 rel=9.146e-05; XAUUSD 2026-11-02T12:00:00Z c td=3903.17087 dk=3903.445 rel=7.023e-05; XAUUSD 2026-11-02T12:30:00Z o td=3903.43074 dk=3903.43 rel=1.896e-07; XAUUSD 2026-11-02T12:30:00Z c td=3901.39644 dk=3901.145 rel=6.445e-05; XAUUSD 2026-11-02T13:00:00Z o td=3901.17841 dk=3901.1915 rel=3.355e-06; XAUUSD 2026-11-02T13:00:00Z c td=3907.08668 dk=3909.439 rel=6.017e-04; XAUUSD 2026-11-02T13:30:00Z o td=3905.74728 dk=3909.355 rel=9.228e-04; XAUUSD 2026-11-02T14:00:00Z c td=3947.71782 dk=3947.9055 rel=4.754e-05; XAUUSD 2026-11-02T14:30:00Z o td=3947.08856 dk=3947.99 rel=2.283e-04; XAUUSD 2026-11-02T14:30:00Z c td=3965.85 dk=3964.46 rel=3.506e-04)
- `A11|td_mismatch|analyst/canary/calls/2026-11-02_T1500.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6` (outside 1e-3: XAUUSD 2026-11-02T13:00:00Z c td=3945.83078 dk=3937.4805 rel=2.121e-03; within: XAUUSD 2026-11-01T23:00:00Z o td=3875.35765 dk=3876.535 rel=3.037e-04; XAUUSD 2026-11-01T23:00:00Z c td=3897.31977 dk=3898.376 rel=2.709e-04; XAUUSD 2026-11-02T00:00:00Z o td=3897.65954 dk=3898.376 rel=1.838e-04; XAUUSD 2026-11-02T00:00:00Z c td=3902.08883 dk=3902.039 rel=1.277e-05; XAUUSD 2026-11-02T02:00:00Z o td=3909.64596 dk=3909.249 rel=1.015e-04; XAUUSD 2026-11-02T02:00:00Z c td=3895.5762 dk=3894.874 rel=1.803e-04; XAUUSD 2026-11-02T04:00:00Z o td=3901.01098 dk=3902.374 rel=3.493e-04; XAUUSD 2026-11-02T04:00:00Z c td=3900.64064 dk=3901.1505 rel=1.307e-04; XAUUSD 2026-11-02T05:00:00Z o td=3900.15743 dk=3901.144 rel=2.529e-04; XAUUSD 2026-11-02T05:00:00Z c td=3913.52645 dk=3913.386 rel=3.589e-05; XAUUSD 2026-11-02T06:00:00Z o td=3913.84482 dk=3913.3465 rel=1.273e-04; XAUUSD 2026-11-02T06:00:00Z c td=3907.06156 dk=3906.7665 rel=7.553e-05; XAUUSD 2026-11-02T07:00:00Z o td=3906.88143 dk=3906.7415 rel=3.582e-05; XAUUSD 2026-11-02T07:00:00Z c td=3903.4339 dk=3903.4105 rel=5.995e-06; XAUUSD 2026-11-02T09:00:00Z o td=3897.38699 dk=3897.7695 rel=9.814e-05; XAUUSD 2026-11-02T09:00:00Z c td=3898.97927 dk=3897.87 rel=2.846e-04; XAUUSD 2026-11-02T10:00:00Z o td=3898.72786 dk=3897.87 rel=2.201e-04; XAUUSD 2026-11-02T10:00:00Z c td=3899.03579 dk=3898.6135 rel=1.083e-04; XAUUSD 2026-11-02T11:00:00Z o td=3898.87339 dk=3898.52 rel=9.065e-05; XAUUSD 2026-11-02T11:00:00Z c td=3901.58455 dk=3901.3405 rel=6.256e-05; XAUUSD 2026-11-02T12:00:00Z o td=3901.75681 dk=3901.4 rel=9.146e-05; XAUUSD 2026-11-02T12:00:00Z c td=3901.39644 dk=3901.145 rel=6.445e-05; XAUUSD 2026-11-02T13:00:00Z o td=3901.17841 dk=3901.1915 rel=3.355e-06; EURUSD 2026-11-01T22:00:00Z p0 td=1.11603 dk=1.11621 rel=1.613e-04; EURUSD 2026-11-02T13:00:00Z p1 td=1.12154 dk=1.121425 rel=1.025e-04; USDJPY 2026-11-01T22:00:00Z p0 td=157.53466 dk=157.49 rel=2.836e-04; USDJPY 2026-11-02T13:00:00Z p1 td=157.83171 dk=157.824 rel=4.885e-05; GBPUSD 2026-11-01T22:00:00Z p0 td=1.33894 dk=1.338985 rel=3.361e-05; GBPUSD 2026-11-02T13:00:00Z p1 td=1.34118 dk=1.341155 rel=1.864e-05; USDCAD 2026-11-01T22:00:00Z p0 td=1.39675 dk=1.396615 rel=9.666e-05; USDCAD 2026-11-02T13:00:00Z p1 td=1.39874 dk=1.39866 rel=5.720e-05; USDCHF 2026-11-01T22:00:00Z p0 td=0.82372 dk=0.823625 rel=1.153e-04; USDCHF 2026-11-02T13:00:00Z p1 td=0.82 dk=0.819995 rel=6.098e-06; AUDJPY 2026-11-01T22:00:00Z p0 td=110.70115 dk=110.7125 rel=1.025e-04; AUDJPY 2026-11-02T13:00:00Z p1 td=110.53798 dk=110.5045 rel=3.030e-04)
- `A11|td_mismatch|analyst/canary/calls/2026-11-02_W2b.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6` (outside 1e-3: XAUUSD 2026-11-02T13:00:00Z c td=3945.83078 dk=3937.4805 rel=2.121e-03; XAUUSD 2026-11-02T14:00:00Z o td=3942.80114 dk=3937.65 rel=1.308e-03; within: XAUUSD 2026-11-01T23:00:00Z o td=3875.35765 dk=3876.535 rel=3.037e-04; XAUUSD 2026-11-01T23:00:00Z c td=3897.31977 dk=3898.376 rel=2.709e-04; XAUUSD 2026-11-02T00:00:00Z o td=3897.65954 dk=3898.376 rel=1.838e-04; XAUUSD 2026-11-02T00:00:00Z c td=3902.08883 dk=3902.039 rel=1.277e-05; XAUUSD 2026-11-02T01:00:00Z o td=3901.68253 dk=3902.1145 rel=1.107e-04; XAUUSD 2026-11-02T01:00:00Z c td=3910.03013 dk=3909.304 rel=1.857e-04; XAUUSD 2026-11-02T02:00:00Z o td=3909.64596 dk=3909.249 rel=1.015e-04; XAUUSD 2026-11-02T02:00:00Z c td=3895.5762 dk=3894.874 rel=1.803e-04; XAUUSD 2026-11-02T03:00:00Z o td=3894.81404 dk=3894.874 rel=1.539e-05; XAUUSD 2026-11-02T03:00:00Z c td=3901.14092 dk=3902.379 rel=3.173e-04; XAUUSD 2026-11-02T04:00:00Z o td=3901.01098 dk=3902.374 rel=3.493e-04; XAUUSD 2026-11-02T04:00:00Z c td=3900.64064 dk=3901.1505 rel=1.307e-04; XAUUSD 2026-11-02T05:00:00Z o td=3900.15743 dk=3901.144 rel=2.529e-04; XAUUSD 2026-11-02T05:00:00Z c td=3913.52645 dk=3913.386 rel=3.589e-05; XAUUSD 2026-11-02T06:00:00Z o td=3913.84482 dk=3913.3465 rel=1.273e-04; XAUUSD 2026-11-02T06:00:00Z c td=3907.06156 dk=3906.7665 rel=7.553e-05; XAUUSD 2026-11-02T07:00:00Z o td=3906.88143 dk=3906.7415 rel=3.582e-05; XAUUSD 2026-11-02T07:00:00Z c td=3903.4339 dk=3903.4105 rel=5.995e-06; XAUUSD 2026-11-02T08:00:00Z o td=3903.43307 dk=3903.4555 rel=5.746e-06; XAUUSD 2026-11-02T08:00:00Z c td=3897.58302 dk=3897.665 rel=2.103e-05; XAUUSD 2026-11-02T09:00:00Z o td=3897.38699 dk=3897.7695 rel=9.814e-05; XAUUSD 2026-11-02T09:00:00Z c td=3898.97927 dk=3897.87 rel=2.846e-04; XAUUSD 2026-11-02T10:00:00Z o td=3898.72786 dk=3897.87 rel=2.201e-04; XAUUSD 2026-11-02T10:00:00Z c td=3899.03579 dk=3898.6135 rel=1.083e-04; XAUUSD 2026-11-02T11:00:00Z o td=3898.87339 dk=3898.52 rel=9.065e-05; XAUUSD 2026-11-02T11:00:00Z c td=3901.58455 dk=3901.3405 rel=6.256e-05; XAUUSD 2026-11-02T12:00:00Z o td=3901.75681 dk=3901.4 rel=9.146e-05; XAUUSD 2026-11-02T12:00:00Z c td=3901.39644 dk=3901.145 rel=6.445e-05; XAUUSD 2026-11-02T13:00:00Z o td=3901.17841 dk=3901.1915 rel=3.355e-06; XAUUSD 2026-11-02T14:00:00Z c td=3965.85 dk=3964.46 rel=3.506e-04; EURUSD 2026-11-01T22:00:00Z p0 td=1.11603 dk=1.11621 rel=1.613e-04; EURUSD 2026-11-02T14:00:00Z p1 td=1.12127 dk=1.121305 rel=3.121e-05; USDJPY 2026-11-01T22:00:00Z p0 td=157.53466 dk=157.49 rel=2.836e-04; USDJPY 2026-11-02T14:00:00Z p1 td=157.66209 dk=157.64 rel=1.401e-04; GBPUSD 2026-11-01T22:00:00Z p0 td=1.33894 dk=1.338985 rel=3.361e-05; GBPUSD 2026-11-02T14:00:00Z p1 td=1.34248 dk=1.34239 rel=6.704e-05; USDCAD 2026-11-01T22:00:00Z p0 td=1.39675 dk=1.396615 rel=9.666e-05; USDCAD 2026-11-02T14:00:00Z p1 td=1.39632 dk=1.396165 rel=1.110e-04; USDCHF 2026-11-01T22:00:00Z p0 td=0.82372 dk=0.823625 rel=1.153e-04; USDCHF 2026-11-02T14:00:00Z p1 td=0.8191 dk=0.818995 rel=1.282e-04; AUDJPY 2026-11-01T22:00:00Z p0 td=110.70115 dk=110.7125 rel=1.025e-04; AUDJPY 2026-11-02T14:00:00Z p1 td=110.65356 dk=110.6495 rel=3.669e-05)

## Adjudicated WARNINGs (64)

- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W1.json|43bbb42e58a4dd66e768a86e84b32a335c6eb79c`
- `A11|td_mismatch|analyst/canary/calls/2026-10-26_W2.json|e6008594960ece17a99cd9837c68c4782900b8da`
- `A11|td_mismatch|analyst/canary/calls/2026-10-27_W2.json|80cbca5d9e610f5235c4c6dbecf2132d41881c26`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W1.json|453f6d4579a8e736d3909aca5af8a96a36186213`
- `A11|td_mismatch|analyst/canary/calls/2026-10-28_W2.json|ac3f7065d54f8d49c5bfc8d46cdbd8a611f62d99`
- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0100.json|6d77cc3c373c1fbe70cb145497cd274011f9e662`
- `A11|td_mismatch|analyst/canary/calls/2026-10-29_T0600.json|8af0b8d4024d1763ef9c4f8aa034fc6df466e987`
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
- canary_terminals: 25
- cc_version_records_checked: 43
- contexts_rebuilt: 21
- ga_runs_read: 72
- head: 172d3be7f38f8a3ed966d4cff40d29c59d7274e6
- inbox_activity_entries: 204
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-11-02T23:52:09Z
- live_expected_windows: 0
- live_terminals: 0
- m30_compared: 7
- m30r_compared: 2
- probe_creations_max_day: 18
- probe_records: 25
- routine_config_versions_checked: 5
- run_log_calls_scanned: 292
- run_logs_scanned: 37
- settled_checked: 0
- td_compared: 1074
- td_outside: 18
- td_pending: 48
- td_unchecked: 0
- witness_comments: 71
- witness_files: 71
