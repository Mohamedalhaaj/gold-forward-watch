# Forward watch amendment — CAUSAL double-top becomes PRIMARY (registered 2026-10-16, before Mon 19 Oct)

**Client instruction (verbatim):** "Pre-register the CAUSAL (first-touch) double-top version as the primary forward
watch from Monday 19 Oct, keep the frozen STRICT one only as a labeled secondary, and show both clearly on the
dashboard."

## Why
- `simulate()`, frozen in `reports/FORWARD_DOUBLETOP_PREREG.md` (commit e2a1012), resolves overlapping armed setups in
  SWING order. That priority needs future bars, so a live trader cannot follow it.
- It was found by the MT5 EA port (commit ba04855) and confirmed independently in RESEARCH_LOG iteration 35
  (commit 81158a9).
- The in-sample double-top edge came from that ordering:

| 2026 in-sample (204 days: Tickmill Jan–Aug + GC=F Aug–Oct) | avg day | days + | net/trade | win | trades/day |
|---|---|---|---|---|---|
| CAUSAL M15 (new primary) | +$0.48 | 50% | +$0.08 | 49% | 5.7 |
| CAUSAL M30 | +$1.25 | 52% | +$0.42 | 49% | 3.0 |
| STRICT M15 (frozen, non-executable) | +$8.23 | 64% | +$1.90 | 57% | 4.3 |
| STRICT M30 | +$6.04 | 58% | +$2.58 | 55% | 2.3 |

**Expected outcome for the primary: FAIL.** The causal in-sample z is about 0.3.

## Frozen from this commit
- **PRIMARY:** `simulate_causal()` in `analysis/forward_doubletop_tracker.py`, M15, k=1.5, stop 1 ATR, target 1 ATR.
  - Setups, swings, fills, exits, flat-by-23:30 and the $0.25 cost are identical to `simulate()`.
  - Only the execution order differs. Every armed limit rests from its start, the first touch in time fills while
    flat, and a limit touched during an open trade stays armed inside its window.
  - Parity: it reproduces the independent `causal_check.py` exactly (Tickmill M15 n 905, +128.7; GC=F M15 n 266, −30.6).
- **SECONDARY:**
  - STRICT M15, `simulate()` unchanged from e2a1012. It is labelled "non-executable reference" everywhere.
  - CAUSAL M30 and STRICT M30 are reported only.
- **Unchanged:** the data (GC=F 15m), window (first 20 complete trading days from Mon 19 Oct 2026), ledger rules
  (append-only, now with a `mode` column) and decision rule.
- **Decision on the primary (CAUSAL M15) after day 20:**

| Verdict | Condition |
|---|---|
| **PASS** | Mean daily net > 0 with a one-sided t-test p < 0.10, and at least 50% of days with trades positive |
| **FAIL** | Anything else |

- The original STRICT verdict is still computed and shown, labelled non-executable. It can never justify trading.

## Runner
GitHub Actions in the private repo `Mohamedalhaaj/gold-forward-watch` is the single writer
(`reports/FORWARD_RUNNER_MOVE.md`). This file and the updated tracker are copied there byte-identical.
