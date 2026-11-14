# Gold support system v2: lab v2 status

Updated 2026-11-14T10:27:35Z. Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` with SYSTEM_V1_PREREG.md and Amendment A1.

## Data

- Lookback store (UTC 2026-01-01 .. 2026-08-31): 486 ok sides, 0 missing, complete: True
- v1 raw days read (from 2026-09-01, read-only): complete through 2026-11-14 00:00 UTC
- v2 START: 2026-11-02

## Seeds

- State: RUNNING; lab2_days 10; lab2_n_paper 4; LIVE 0; best progress E/E* 0.002
- INTERPRETER_NEEDED: no

| id | state | first_day | record | trades | sum net $/oz | mean R | evidence |
|---|---|---|---|---|---|---|---|
| S2 | PAPER | 2026-11-02 | since first_day | 12 | 107.47 | 0.237 | E 1.545 of E* 2000/3 |
| S3 | PAPER | 2026-11-02 | since first_day | 2 | 30.45 | 0.868 | E 1.250 of E* 2000/3 |
| S4 | PAPER | 2026-11-02 | since first_day | 4 | 3.42 | 0.012 | E 1.007 of E* 1000 |
| S5 | PAPER | 2026-11-02 | since first_day | 2 | 10.24 | 0.108 | E 1.029 of E* 1000 |

- C1 (v1 coin control) over the same days: 10 trades, sum net -53.14 $/oz, mean R -0.206, E 0.702
- S3 trend-flip flow values before today: 165 of 250 (warm-up)
