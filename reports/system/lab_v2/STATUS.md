# Gold support system v2: lab v2 status

Updated 2026-11-10T11:19:46Z. Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` with SYSTEM_V1_PREREG.md and Amendment A1.

## Data

- Lookback store (UTC 2026-01-01 .. 2026-08-31): 486 ok sides, 0 missing, complete: True
- v1 raw days read (from 2026-09-01, read-only): complete through 2026-11-10 00:00 UTC
- v2 START: 2026-11-02

## Seeds

- State: RUNNING; lab2_days 6; lab2_n_paper 4; LIVE 0; best progress E/E* 0.002
- INTERPRETER_NEEDED: no

| id | state | first_day | record | trades | sum net $/oz | mean R | evidence |
|---|---|---|---|---|---|---|---|
| S2 | PAPER | 2026-11-02 | since first_day | 6 | 58.42 | 0.287 | E 1.292 of E* 2000/3 |
| S3 | PAPER | 2026-11-02 | since first_day | 1 | -4.49 | -0.231 | E 0.964 of E* 2000/3 |
| S4 | PAPER | 2026-11-02 | since first_day | 2 | -0.56 | -0.008 | E 0.998 of E* 1000 |
| S5 | PAPER | 2026-11-02 | since first_day | 0 | 0.00 | - | E 1.000 of E* 1000 |

- C1 (v1 coin control) over the same days: 6 trades, sum net -32.69 $/oz, mean R -0.179, E 0.831
- S3 trend-flip flow values before today: 161 of 250 (warm-up)
