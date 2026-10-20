# Gold support system v1: status

Updated 2026-12-05T03:20:00Z. Binding spec: xauusd-quant `research/system/SYSTEM_V1_PREREG.md` (with Amendment A1).

## Data and forecasts

- Raw Dukascopy days stored: 95 (missing sides: 0); complete through 2026-12-05 00:00 UTC (exclusive); lag 0 trading day(s)
- Revisions logged (never used): 0
- Forecast store: 1587 slots (1332 defined); 115 new this run
- START: 2026-11-02
- Event calendars cover through 2027-12-03 (the earliest of the last NFP, CPI and FOMC dates); extension lines accepted 0, rejected 0

## L1 green suppression (D1)

- l1_green_ok = 1 (as of 2026-12-05)
- Block 1 2026-11-02 .. 2027-02-01: complete 0, green origins 476, hit rate 10.1%

Descriptive (D2-D4 deferred, §8): base state counts and pooled mid k10 hit rates

| state | origins | hit rate |
|---|---|---|
| GREEN | 476 | 0.101 |
| YELLOW | 93 | 0.167 |
| RED | 6 | 0.000 |

## L3 calibration

- z* = 7.75 (reports/system/L3_ZSTAR.json); last update: none yet (first in 2027-01)
- Observations since START: 575

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

- State: RUNNING; lab_days 25; lab_n_paper 1; LIVE: 0; best progress E/E* over PAPER rules: 0.009
- INTERPRETER_NEEDED: no

What the status-file counts mean:

- `lab_days` = settled lab days (model-clock weekdays) on or after the lab's first first_day.
- `lab_n_paper` = promotable rules in state PAPER (S1 and proposer rules); REF streams (S1R, C1) and PENDING, LIVE, SUSPENDED, DEMOTED and RETIRED rules are not counted.
- The indicator's second lab row «عدد القواعد قيد الاختبار %d، وأيام التداول المحسوبة %d» shows lab_n_paper and lab_days, only when lab_days >= 1 and lab_n_paper >= 1 (Amendment A1 item 4).

A promoted rule (LIVE, SUSPENDED, DEMOTED) shows its post-promotion record and its demotion e-process K only (§3 item 11, A1 item 12).

| id | state | first_day | record | trades | sum net $/oz | evidence |
|---|---|---|---|---|---|---|
| S1 | PAPER | 2026-11-02 | since first_day | 7 | -7.96 | E 0.730 of E* 83.3 |
| S1R | REF | 2026-11-02 | since first_day | 7 | -3.86 | E 0.822 (REF) |
| C1 | REF | 2026-11-02 | since first_day | 23 | 6.61 | E 1.109 (REF) |
