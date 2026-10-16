# Forward watch pre-registration — "US-data hour lower wick"

**Registered:** 2026-10-16, about 04:00 Africa/Tripoli. That is before the first tracked day's 15:00 server bar,
which closes at 16:00 server = 15:00 Tripoli on Fri 16 Oct.
**Status:** FROZEN. Nothing below may change after this commit: not the rule, the threshold, the times, the
source, the window or the decision rule. A failed result is not to be rescued by tweaking. Any variant needs a
new pre-registration made before its own data.

## Where the rule came from (disclosed honestly)
- Found by eye in one week, 9–15 Oct 2026 (`reports/visual_2026-10-16/`). It fitted 4 of 4 trigger days there.
- On the 26 earlier days (1 Sep – 8 Oct 2026) it did **not** hold. There were 11 triggers: 3 up at both
  horizons, 4 down at both, 4 mixed.
- **Expected outcome: FAIL.** This watch exists because the client asked for a clean forward check that
  hindsight cannot touch, not because the evidence favours the rule.

## Data
- **Source:** Yahoo Finance `GC=F` (COMEX gold futures, continuous), 15-minute bars. This is the source the rule
  was found on; candle shapes match XAUUSD spot.
- **Clock:** MT5 server time = America/New_York wall clock + 7h. The trading day runs 01:00 → 24:00 server.
- **Record-keeping:** every fetch is saved untouched in `data/forward_wick/raw/`. The ledger is append-only: once
  a day is written it is never recomputed or edited, even if the source later revises a bar.

## The rule (mechanical, no judgement)
For each tracked day D (server date):
1. **H1 bar 15:00–16:00 server**, built from the four M15 bars 15:00, 15:15, 15:30 and 15:45:
   - open = 15:00 open
   - close = 15:45 close
   - low = lowest of the four lows
2. **Lower wick** = min(open, close) − low.
3. **TRIGGER** if lower wick ≥ 0.0015 × close (0.15% of close). Body and upper wick are ignored.
4. **Reference price** = open of the 16:00 M15 bar.
5. **Outcomes:**
   - **B (PRIMARY):** close of the 23:45 M15 bar (the 24:00 close) minus the reference. "Up" means strictly > 0.
   - **A (secondary):** close of the 16:30 M15 bar (price at 16:45) minus the reference.
   - **Also recorded:** the lowest low from 16:00 to 24:00 minus the reference, which is the drawdown a holder
     would have sat through.
6. Non-trigger days get the same outcomes recorded. They are the control.

## Window
- The first **20 complete trading days** on or after **Fri 16 Oct 2026**.
- A day is complete when all of these bars exist: 15:00, 15:15, 15:30, 15:45, 16:00, 16:30 and 23:45.
- A day still incomplete 2 calendar days later is logged as `no-data` and skipped. The window then extends,
  with a hard stop on Fri 27 Nov 2026.
- With no gaps the window ends on Thu 12 Nov 2026.

## Decision rule (primary outcome B, trigger days only)
Let n = number of trigger days and k = trigger days with B up.

| Verdict | Condition | Meaning |
|---|---|---|
| **INCONCLUSIVE** | n < 6 | There is no evidence either way. No trading, and no extension of this watch. |
| **PASS** | n ≥ 6, **and** a fair coin would reach k or more out of n less than 10% of the time (one-sided binomial, p = 0.5), **and** k/n is above the B-up share on non-trigger days | The rule has earned a larger pre-registered test on Tickmill bid/ask with real costs. **It is not a trading signal.** |
| **FAIL** | anything else | The rule is dropped. No rescue. |

For reference, the PASS level for each value of n:

| n | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|
| k needed | 6 | 6 | 7 | 7 | 8 | 8 | 9 | 9 | 10 |

The following are reported but not decisive: A, A and B together, average B in points, and the worst drawdown.

## Tracking
`analysis/forward_wick_tracker.py` runs daily from a macOS LaunchAgent (`com.xauusd.forwardwick`). It writes
three files:
- `reports/forward_wick/ledger.csv`
- `reports/forward_wick/STATUS.md`
- `reports/forward_wick/forward_strip.png`

After day 20 it writes `reports/forward_wick/VERDICT.md` and uninstalls its own LaunchAgent.
