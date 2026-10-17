"""Lab paper-trade execution and accounting (SYSTEM_V1_PREREG.md §3 items 2-3, Amendment A1 item 8). FROZEN: accounting.

For a trigger at T with side s (+1 long, -1 short), hold h, entry delay e (1 minute for every rule; 0 for the REF
stream S1R), stop multiplier k and forecast F (bp, finite and > 0):
- Quotes (A1 item 8): a non-finite executable price counts as no quote (a minute present on one side only has NaN
  prices on the other).
- Entry: the open of the M1 bar that starts at T + e, on the executable side (ask for a long, bid for a short).
  P_e is that minute's open; Dukascopy keeps zero-volume minutes, whose open is the standing quote. If that minute has
  no row or no finite executable open, P_e is the last finite executable quote before it: the close of the latest
  earlier minute of the day with a finite executable close. With no such quote at all the trade is "no_quote".
- Stop: X = P_e·exp(−s·k·F/1e4); D = |P_e − X|.
- Path: the minutes [T + e, T + 15h), in time order, on the executable exit side (bid for a long, ask for a short).
  In each minute with a finite executable quote: if its open is through X, exit at the open (gap fill; also in the
  entry minute, where the spread alone can put the bid below X); otherwise if its low (long) / high (short) reaches X,
  exit at X. The stop is checked before the time exit, so the stop wins a tie in the last minute.
- Data gaps (no outcome-dependent voids, §3 item 3): a minute without volume on both sides, without a row, or without
  a finite executable quote adds to a run; when a run reaches 15 consecutive minutes the trade is settled as stopped
  at X (conservative).
- Time exit: the close of the last minute before T + 15h on the exit side, i.e. the last minute of the path with a
  finite executable close (X, reason "gap", if the path has none).
- Money: net$ = s·(P_x − P_e) − 0.10 (round-trip allowance; the bid/ask is in the prices); stress net$ = net$ − 0.25;
  R = net$/D; R_stress = stress net$/D; y = clip(R, −2, 2).
- Cost split (proposer null, L2 §10.3): cost$ = 0.10 + half the spread at the entry quote + half the spread at the
  exit (the open's spread for an open exit, the close's otherwise); a half-spread whose bid or ask is not finite
  counts 0. gross$ = net$ + cost$ (the move on the mid).
- A trade with status "final" never holds a non-finite number (A1 item 8); trade() raises if it would.
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


def _half_spread(md, row, field):
    """Half the bid/ask spread at the `field` ("o" or "c") price of `row`; 0 without a row or a finite pair."""
    if row < 0:
        return 0.0
    a, b = getattr(md, "ask_" + field)[row], getattr(md, "bid_" + field)[row]
    return float((a - b) / 2) if np.isfinite(a) and np.isfinite(b) else 0.0


def trade(md, side, T, hold, k, F, delay=1, use_mid=False):
    """Settle one paper trade. Returns a dict (see module doc); status "no_quote" if there is no quote at all.

    Vectorised over the path minutes; tests/system/test_lab_grammar_execution.py checks it against a plain loop."""
    if not (np.isfinite(F) and F > 0 and np.isfinite(k) and k > 0):
        raise ValueError(f"trade() needs a finite F > 0 and k > 0, got F={F!r}, k={k!r}")
    t0, t1 = T + delay, T + 15 * hold
    out = {"side": side, "entry_min": t0}
    if use_mid:
        ent_o, ent_c = md.o, md.c
    else:
        ent_o, ent_c = (md.ask_o, md.ask_c) if side > 0 else (md.bid_o, md.bid_c)
    r0 = md.row(t0)
    if r0 >= 0 and np.isfinite(ent_o[r0]):
        e_row, e_field = r0, "o"
        P_e = float(ent_o[r0])
    else:
        # no finite executable open at T + e: the last finite executable quote before it (A1 item 8)
        before = md.pos[:t0]
        rb = before[before >= 0]
        rb = rb[np.isfinite(ent_c[rb])]
        if len(rb) == 0:
            out.update(P_e=np.nan, status="no_quote")
            return out
        e_row, e_field = int(rb[-1]), "c"
        P_e = float(ent_c[e_row])
    X = P_e * np.exp(-side * k * F / 1e4)
    D = abs(P_e - X)
    rows = md.pos[t0:t1]
    n = len(rows)
    present = rows >= 0
    r = np.where(present, rows, 0)
    if use_mid:
        o, h, l, c = md.o[r], md.h[r], md.l[r], md.c[r]
    elif side > 0:
        o, h, l, c = md.bid_o[r], md.bid_h[r], md.bid_l[r], md.bid_c[r]
    else:
        o, h, l, c = md.ask_o[r], md.ask_h[r], md.ask_l[r], md.ask_c[r]
    q = present & np.isfinite(o) & np.isfinite(c) & np.isfinite(l if side > 0 else h)    # a finite exit quote
    live = q & md.vol[r]                                    # volume on both sides and a finite exit quote
    ar = np.arange(n)
    run = ar - np.maximum.accumulate(np.where(live, ar, -1))
    with np.errstate(invalid="ignore"):
        if side > 0:
            open_hit, any_hit = q & (o <= X), q & ((o <= X) | (l <= X))
        else:
            open_hit, any_hit = q & (o >= X), q & ((o >= X) | (h >= X))
    event = any_hit | (run >= GAP_MINUTES)
    exit_row, exit_field = -1, "c"
    if event.any():
        i = int(np.argmax(event))
        if any_hit[i]:
            exit_field = "o" if open_hit[i] else "c"
            exit_px, reason, exit_row = (o[i] if open_hit[i] else X), "stop", int(rows[i])
        else:
            exit_px, reason, exit_row = X, "gap", int(rows[i])
        exit_min = t0 + i
    else:
        idx = np.flatnonzero(q)
        if len(idx) == 0:
            exit_px, exit_min, reason = X, t1 - 1, "gap"
        else:
            j = idx[-1]
            exit_px, exit_min, reason, exit_row = c[j], t0 + j, "time", int(rows[j])
    allowance = 0.0 if use_mid else ALLOWANCE
    net = side * (exit_px - P_e) - allowance
    hs_e = 0.0 if use_mid else _half_spread(md, e_row, e_field)
    hs_x = 0.0 if use_mid else _half_spread(md, exit_row, exit_field)
    cost = allowance + hs_e + hs_x
    R = net / D
    out.update(P_e=P_e, status="final", X=float(X), D=float(D), exit_min=int(exit_min), P_x=float(exit_px),
               reason=reason, net_usd=float(net), net_stress_usd=float(net - (0.0 if use_mid else STRESS_ADD)),
               cost_usd=float(cost), gross_usd=float(net + cost), R=float(R),
               R_stress=float((net - STRESS_ADD) / D), y=float(np.clip(R, -CLIP, CLIP)))
    nums = ("P_e", "X", "D", "P_x", "net_usd", "net_stress_usd", "cost_usd", "gross_usd", "R", "R_stress", "y")
    if not (D > 0 and all(np.isfinite(out[c]) for c in nums)):
        raise ValueError(f"a final trade would hold a non-finite number: {out}")
    return out
