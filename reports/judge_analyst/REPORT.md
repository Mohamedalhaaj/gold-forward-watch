# Analyst judge report

- asof_utc: 2026-11-07T03:10:16Z
- head_sha (gold-analyst main checked): d64c79e825948c49680330dd0dffde1d36d280af
- judge code_sha8: ec8d88bf
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

## Adjudicated WARNINGs (88)

- `A11|td_mismatch|analyst/canary/attempts/2026-11-02_T1500_1.json|172d3be7f38f8a3ed966d4cff40d29c59d7274e6`
- `A11|td_mismatch|analyst/canary/attempts/2026-11-03_T0400_1.json|ee5bbb5557be0da2c0ddd95a273e6fa5cb692d03`
- `A11|td_mismatch|analyst/canary/attempts/2026-11-03_T0830_1.json|9ae12d19765b63dce9f4e7658ec242d3ac94be69`
- `A11|td_mismatch|analyst/canary/attempts/2026-11-04_T0830_1.json|bbcdf88435fd170fe16582de03eab6c60aadc6aa`
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
- `A11|td_mismatch|analyst/canary/calls/2026-11-03_W2.json|5b1e296386b35972cf35f59c57a777da68576c3f`
- `A11|td_mismatch|analyst/canary/calls/2026-11-03_W2b.json|985c6a90adaa1012568d0afba6c4d545fca100ea`
- `A11|td_mismatch|analyst/canary/calls/2026-11-04_T0130.json|2bc7394210d682bcad0993caea7f65bbd67162e3`
- `A11|td_mismatch|analyst/canary/calls/2026-11-04_T0600.json|bbcdf88435fd170fe16582de03eab6c60aadc6aa`
- `A11|td_mismatch|analyst/canary/calls/2026-11-04_T0830.json|bbcdf88435fd170fe16582de03eab6c60aadc6aa`
- `A11|td_mismatch|analyst/canary/calls/2026-11-04_W1.json|bbcdf88435fd170fe16582de03eab6c60aadc6aa`
- `A11|td_mismatch|analyst/canary/calls/2026-11-04_W1b.json|bbcdf88435fd170fe16582de03eab6c60aadc6aa`
- `A11|td_mismatch|analyst/canary/calls/2026-11-04_W2.json|1c4d81b761cef8b1d67c588745419bed44f973ba`
- `A11|td_mismatch|analyst/canary/calls/2026-11-05_T0100.json|3805ef85b7947c89318077d13c7415765c68f7bb`
- `A11|td_mismatch|analyst/canary/calls/2026-11-05_T2300.json|f8ea7f9853b9b722b8a993f40c69991cf54a56d8`
- `A11|td_mismatch|analyst/canary/calls/2026-11-05_W1.json|0d773ca669638f219bd5bd7e9d0a602f20757330`
- `A11|td_mismatch|analyst/canary/calls/2026-11-05_W1b.json|0d773ca669638f219bd5bd7e9d0a602f20757330`
- `A12|probe_incomplete|analyst/canary/calls/2026-11-03_W2b.json|985c6a90adaa1012568d0afba6c4d545fca100ea`
- `A12|probe_incomplete|analyst/canary/calls/2026-11-05_W2b.json|ce22bf8b9740e7db82243bbe32dec424e2fe58f0`
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
- canary_expected_windows: 43
- canary_terminals: 50
- cc_version_records_checked: 97
- contexts_rebuilt: 45
- ga_runs_read: 104
- head: d64c79e825948c49680330dd0dffde1d36d280af
- inbox_activity_entries: 362
- inbox_activity_oldest_listed_utc: 2026-10-23T09:52:15Z
- inbox_last_complete_read_utc: 2026-11-07T03:10:16Z
- live_expected_windows: 0
- live_terminals: 0
- m30_compared: 16
- m30r_compared: 7
- probe_creations_max_day: 21
- probe_records: 49
- routine_config_versions_checked: 5
- run_log_calls_scanned: 292
- run_logs_scanned: 37
- settled_checked: 6
- td_compared: 2739
- td_outside: 60
- td_pending: 3
- td_unchecked: 0
- witness_comments: 156
- witness_files: 156
