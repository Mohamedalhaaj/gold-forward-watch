"""Lab paper-trade execution and accounting (SYSTEM_V1_PREREG.md §3 items 2-3). FROZEN: accounting.

For a trigger at T with side s (+1 long, -1 short), hold h, entry delay e (1 minute for every rule; 0 for the REF
stream S1R), stop multiplier k and forecast F (bp):
- Entry: the open of the M1 bar that starts at T + e, on the executable side (ask for a long, bid for a short).
  P_e is that minute's open; Dukascopy keeps zero-volume minutes, whose open is the standing quote.
- Stop: X = P_e·exp(−s·k·F/1e4); D = |P_e − X|.
- Path: the minutes [T + e, T + 15h), in time order, on the executable exit side (bid for a long, ask for a short).
  In each minute: if its open is through X, exit at the open (gap fill; also in the entry minute, where the spread
  alone can put the bid below X); otherwise if its low (long) / high (short) reaches X, exit at X. The stop is checked
  before the time exit, so the stop wins a tie in the last minute.
- Data gaps (no outcome-dependent voids, §3 item 3): a minute without volume on both sides, or without a row, adds
  to a run; when a run reaches 15 consecutive minutes the trade is settled as stopped at X (conservative). A missing
  row is skipped otherwise.
- Time exit: the close of the last minute before T + 15h on the exit side (the last present minute of the path).
- Money: net$ = s·(P_x − P_e) − 0.10 (round-trip allowance; the bid/ask is in the prices); stress net$ = net$ − 0.25;
  R = net$/D; R_stress = stress net$/D; y = clip(R, −2, 2).
- Cost split (proposer null, L2 §10.3): cost$ = 0.10 + half the spread at entry + half the spread at exit (the
  open's spread for an open exit, the close's otherwise); gross$ = net$ + cost$ (the move on the mid).
"""
import numpy as np

ALLOWANCE = 0.10
STRESS_ADD = 0.25
GAP_MINUTES = 15
CLIP = 2.0


class Minutes:
    """One model day's M1 rows as arrays keyed by minute of day (0..1439)."""

    def __init__(self, mf_day):
        t = mf_day.index
        m = (t.hour * 60 + t.minute).values
        self.pos = np.full(1440, -1, dtype=int)
        self.pos[m] = np.arange(len(m))
        g = {c: mf_day[c].values.astype(float) for c in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h",
                                                       "ask_l", "ask_c", "o", "h", "l", "c")}
        self.__dict__.update(g)
        self.vol = ((mf_day["bid_vol"].values > 0) & (mf_day["ask_vol"].values > 0))

    def row(self, minute):
        return self.pos[minute] if 0 <= minute < 1440 else -1


def trade(md, side, T, hold, k, F, delay=1, use_mid=False):
    """Settle one paper trade. Returns a dict (see module doc); status "no_quote" if there is no quote at all.

    Vectorised over the path minutes; tests/system/test_execution.py checks it against a plain minute loop."""
    t0, t1 = T + delay, T + 15 * hold
    out = {"side": side, "entry_min": t0}
    r0 = md.row(t0)
    if r0 >= 0:
        P_e = float(md.o[r0] if use_mid else (md.ask_o[r0] if side > 0 else md.bid_o[r0]))
    else:
        # no row at the entry minute: the standing quote is the last present minute's close before it
        before = md.pos[:t0]
        rb = before[before >= 0]
        if len(rb) == 0:
            out.update(P_e=np.nan, status="no_quote")
            return out
        rb = rb[-1]
        P_e = float(md.c[rb] if use_mid else (md.ask_c[rb] if side > 0 else md.bid_c[rb]))
    X = P_e * np.exp(-side * k * F / 1e4)
    D = abs(P_e - X)
    rows = md.pos[t0:t1]
    n = len(rows)
    present = rows >= 0
    r = np.where(present, rows, 0)
    vol = present & md.vol[r]
    if use_mid:
        o, h, l, c = md.o[r], md.h[r], md.l[r], md.c[r]
    elif side > 0:
        o, h, l, c = md.bid_o[r], md.bid_h[r], md.bid_l[r], md.bid_c[r]
    else:
        o, h, l, c = md.ask_o[r], md.ask_h[r], md.ask_l[r], md.ask_c[r]
    ar = np.arange(n)
    run = ar - np.maximum.accumulate(np.where(vol, ar, -1))
    if side > 0:
        open_hit, any_hit = present & (o <= X), present & ((o <= X) | (l <= X))
    else:
        open_hit, any_hit = present & (o >= X), present & ((o >= X) | (h >= X))
    event = any_hit | (run >= GAP_MINUTES)
    exit_row, exit_at_open = -1, False
    if event.any():
        i = int(np.argmax(event))
        if any_hit[i]:
            exit_at_open = bool(open_hit[i])
            exit_px, reason, exit_row = (o[i] if exit_at_open else X), "stop", rows[i]
        else:
            exit_px, reason, exit_row = X, "gap", rows[i]
        exit_min = t0 + i
    else:
        idx = np.flatnonzero(present)
        if len(idx) == 0:
            exit_px, exit_min, reason = X, t1 - 1, "gap"
        else:
            j = idx[-1]
            exit_px, exit_min, reason, exit_row = c[j], t0 + j, "time", rows[j]
    allowance = 0.0 if use_mid else ALLOWANCE
    net = side * (exit_px - P_e) - allowance
    hs_e = 0.0 if (use_mid or r0 < 0) else (md.ask_o[r0] - md.bid_o[r0]) / 2
    if use_mid or exit_row < 0:
        hs_x = 0.0
    elif exit_at_open:
        hs_x = (md.ask_o[exit_row] - md.bid_o[exit_row]) / 2
    else:
        hs_x = (md.ask_c[exit_row] - md.bid_c[exit_row]) / 2
    cost = allowance + hs_e + hs_x
    R = net / D if D > 0 else np.nan
    out.update(P_e=P_e, status="final", X=float(X), D=float(D), exit_min=int(exit_min), P_x=float(exit_px),
               reason=reason, net_usd=float(net), net_stress_usd=float(net - (0.0 if use_mid else STRESS_ADD)),
               cost_usd=float(cost), gross_usd=float(net + cost), R=float(R),
               R_stress=float((net - STRESS_ADD) / D) if D > 0 else np.nan, y=float(np.clip(R, -CLIP, CLIP)))
    return out
