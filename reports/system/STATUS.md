# Gold support system v1: status

Updated 2026-10-31T15:21:25Z. Binding spec: xauusd-quant `research/system/SYSTEM_V1_PREREG.md` (with Amendment A1).

## Data and forecasts

- Raw Dukascopy days stored: 60 (missing sides: 0); complete through 2026-10-31 00:00 UTC (exclusive); lag 0 trading day(s)
- Revisions logged (never used): 0
- Forecast store: 1012 slots (755 defined); 0 new this run
- START: 2026-11-02
- Event calendars cover through 2027-12-03 (the earliest of the last NFP, CPI and FOMC dates); extension lines accepted 0, rejected 0

## L1 green suppression (D1)

- l1_green_ok = 1 (as of 2026-10-31)

## L3 calibration

- z* = 7.75 (reports/system/L3_ZSTAR.json); last update: none yet (first in 2027-01)
- Observations since START: 0

| bucket | n | m in force |
|---|---|---|
| CPI | 0 | 1.0000 |
| FOMC | 0 | 1.0000 |
| NFP | 0 | 1.0000 |
| REOPEN | 0 | 1.0000 |
| N_ASIA | 0 | 1.0000 |
| N_LONDON | 0 | 1.0000 |
| N_NY | 0 | 1.0000 |

## L2 lab

- State: RUNNING; lab_days 0; lab_n_paper 1; LIVE: 0; best progress E/E* over PAPER rules: 0.012
- INTERPRETER_NEEDED: no

What the status-file counts mean:

- `lab_days` = settled lab days (model-clock weekdays) on or after the lab's first first_day.
- `lab_n_paper` = promotable rules in state PAPER (S1 and proposer rules); REF streams (S1R, C1) and PENDING, LIVE, SUSPENDED, DEMOTED and RETIRED rules are not counted.
- The indicator's second lab row «عدد القواعد قيد الاختبار %d، وأيام التداول المحسوبة %d» shows lab_n_paper and lab_days, only when lab_days >= 1 and lab_n_paper >= 1 (Amendment A1 item 4).

A promoted rule (LIVE, SUSPENDED, DEMOTED) shows its post-promotion record and its demotion e-process K only (§3 item 11, A1 item 12).

| id | state | first_day | record | trades | sum net $/oz | evidence |
|---|---|---|---|---|---|---|
| S1 | PAPER | 2026-11-02 | since first_day | 0 | 0.00 | E 1.000 of E* 83.3 |
| S1R | REF | 2026-11-02 | since first_day | 0 | 0.00 | E 1.000 (REF) |
| C1 | REF | 2026-11-02 | since first_day | 0 | 0.00 | E 1.000 (REF) |
