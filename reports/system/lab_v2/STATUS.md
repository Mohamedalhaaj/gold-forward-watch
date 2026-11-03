# Gold support system v2: lab v2 status

Updated 2026-11-03T17:09:44Z. Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` with SYSTEM_V1_PREREG.md and Amendment A1.

## Data

- Lookback store (UTC 2026-01-01 .. 2026-08-31): 486 ok sides, 0 missing, complete: True
- v1 raw days read (from 2026-09-01, read-only): complete through 2026-11-03 00:00 UTC
- v2 START: 2026-11-02

## Seeds

- State: RUNNING; lab2_days 1; lab2_n_paper 4; LIVE 0; best progress E/E* 0.002
- INTERPRETER_NEEDED: no

| id | state | first_day | record | trades | sum net $/oz | mean R | evidence |
|---|---|---|---|---|---|---|---|
| S2 | PAPER | 2026-11-02 | since first_day | 0 | 0.00 | - | E 1.000 of E* 2000/3 |
| S3 | PAPER | 2026-11-02 | since first_day | 0 | 0.00 | - | E 1.000 of E* 2000/3 |
| S4 | PAPER | 2026-11-02 | since first_day | 1 | 0.66 | 0.011 | E 1.002 of E* 1000 |
| S5 | PAPER | 2026-11-02 | since first_day | 0 | 0.00 | - | E 1.000 of E* 1000 |

- C1 (v1 coin control) over the same days: 1 trades, sum net -20.50 $/oz, mean R -1.005, E 0.844
- S3 trend-flip flow values before today: 156 of 250 (warm-up)
