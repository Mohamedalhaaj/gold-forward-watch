# Forward watch pre-registration — double-top sell (wick limit entry, small target, daily)

**Registered:** 2026-10-16, before the first tracked day (Mon 19 Oct 2026).
**Status:** FROZEN. Nothing below may change: not the rule, its parameters, the data source, the window or the
decision rule.

## Origin (disclosed honestly)
- Found in-sample on 2026 data in commit 090201f (`research/hunt/double_bottom/dbw_test.py`). Data: Tickmill MT5
  Jan–Aug plus GC=F Aug–Oct.
- It was chosen from a 72-cell grid. All 12 M15/M30 k=1.5 double-top cells beat random entries with the same geometry.
- Primary cell in-sample (M15, target 1 ATR): +$1,679/oz, avg day +$8.23, 64% of days positive, 9/10 months positive.
- Most of that profit came in Feb–Mar 2026. The M15 curve has been roughly flat since July.
- **Expect decay.** In-sample numbers are optimistic.

## The rule (exactly `dbw_test.run`, copied verbatim into `analysis/forward_doubletop_tracker.py`)
**Swings** use wicks, with ATR(14) of the signal timeframe.
- A swing high counts once a later bar's LOW reaches high − k·ATR.
- A swing low counts once a later bar's HIGH reaches low + k·ATR.
- k = 1.5.

**Setup.** A swing high H1, then the next confirmed swing low. From the next bar, a SELL LIMIT rests at
H1 − 0.1·ATR. ATR is taken at the swing-low confirmation. The order is active for MAXGAP/2 signal bars (48 on M15,
36 on M30).

**Fill.** The first 15-minute bar whose high reaches the limit fills it. A gap open above the limit fills at the open.
Fills at or after 23:00 server are skipped.

**Exits**
- Stop at H1 + 1.0·ATR.
- Target at fill − 1.0·ATR.
- Otherwise flat at the close of the last bar before 23:30 server the same day.
- If stop and target are inside the same bar, it counts as a stop.

**Other terms**
- One position at a time per timeframe.
- $0.25 per trade.
- 1 oz per trade for reporting.

**Timeframes**
- **PRIMARY = M15.**
- Secondary = M30, reported but not decisive.

## Data
- Yahoo `GC=F` (COMEX gold futures, continuous), 15-minute bars. These are also the execution bars.
- Server clock = New York + 7h.
- Every fetch is saved untouched in `data/forward_doubletop/raw/`.
- Earlier bars are used only to warm up swings and ATR. A trade counts only if it **fills on or after Mon 19 Oct 2026
  01:00 server**.
- **Window:** the first 20 complete trading days from 19 Oct 2026 (ends Fri 13 Nov 2026 if there are no gaps).
- **Ledger:** append-only (`reports/forward_doubletop/trades.csv`). A closed trade is written once and never
  recomputed.

## Decision (primary M15, after day 20)
Days without trades count as $0.

| Verdict | Condition |
|---|---|
| **PASS** | Mean daily net > 0 with a one-sided t-test p < 0.10 over the 20 days, **and** at least 50% of the days with trades are positive |
| **FAIL** | Anything else |

**What PASS means:** the 2026 edge carried into 4 unseen weeks. It is still not a trading recommendation: sizing,
broker execution and live slippage are untested.

**What FAIL means:** the in-sample result was a 2026 regime or selection effect. No re-tuned variant may be swapped in.

## Reporting
A static dashboard on Cloudflare Pages is refreshed daily by a local LaunchAgent (`com.xauusd.forwarddoubletop`).
The same page shows the US-data-hour wick watch (`reports/FORWARD_WICK_PREREG.md`).
