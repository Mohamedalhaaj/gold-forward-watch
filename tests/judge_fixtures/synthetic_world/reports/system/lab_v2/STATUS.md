# Gold support system v2: lab v2 status

Updated 2026-12-05T03:20:00Z. Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` with SYSTEM_V1_PREREG.md and Amendment A1.

## Data

- Lookback store (UTC 2026-01-01 .. 2026-08-31): 486 ok sides, 0 missing, complete: True
- v1 raw days read (from 2026-09-01, read-only): complete through 2026-12-05 00:00 UTC
- v2 START: 2026-11-09

## Seeds

- State: RUNNING; lab2_days 20; lab2_n_paper 4; LIVE 0; best progress E/E* 0.001
- INTERPRETER_NEEDED: no

| id | state | first_day | record | trades | sum net $/oz | mean R | evidence |
|---|---|---|---|---|---|---|---|
| S2 | PAPER | 2026-11-09 | since first_day | 1 | -1.43 | -0.127 | E 0.980 of E* 2000/3 |
| S3 | PAPER | 2026-11-09 | since first_day | 12 | -16.23 | -0.187 | E 0.670 of E* 2000/3 |
| S4 | PAPER | 2026-11-09 | since first_day | 3 | -46.11 | -0.698 | E 0.732 of E* 1000 |
| S5 | PAPER | 2026-11-09 | since first_day | 5 | -0.98 | -0.022 | E 0.975 of E* 1000 |

- C1 (v1 coin control) over the same days: 18 trades, sum net 2.65 $/oz, mean R 0.049, E 0.996
- S3 trend-flip flow values before today: 180 of 250 (warm-up)
