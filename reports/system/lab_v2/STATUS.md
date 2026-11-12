# Gold support system v2: lab v2 status

Updated 2026-11-12T11:16:53Z. Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` with SYSTEM_V1_PREREG.md and Amendment A1.

## Data

- Lookback store (UTC 2026-01-01 .. 2026-08-31): 486 ok sides, 0 missing, complete: True
- v1 raw days read (from 2026-09-01, read-only): complete through 2026-11-12 00:00 UTC
- v2 START: 2026-11-02

## Seeds

- State: RUNNING; lab2_days 8; lab2_n_paper 4; LIVE 0; best progress E/E* 0.002
- INTERPRETER_NEEDED: no

| id | state | first_day | record | trades | sum net $/oz | mean R | evidence |
|---|---|---|---|---|---|---|---|
| S2 | PAPER | 2026-11-02 | since first_day | 8 | 94.40 | 0.360 | E 1.584 of E* 2000/3 |
| S3 | PAPER | 2026-11-02 | since first_day | 1 | -4.49 | -0.231 | E 0.964 of E* 2000/3 |
| S4 | PAPER | 2026-11-02 | since first_day | 3 | 6.02 | 0.028 | E 1.013 of E* 1000 |
| S5 | PAPER | 2026-11-02 | since first_day | 1 | 22.79 | 0.436 | E 1.068 of E* 1000 |

- C1 (v1 coin control) over the same days: 8 trades, sum net -18.15 $/oz, mean R -0.108, E 0.821
- S3 trend-flip flow values before today: 163 of 250 (warm-up)
