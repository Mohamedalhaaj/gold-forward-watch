"""The judge's own lab execution and e-process (SYSTEM_V1_PREREG.md §3 items 2, 3, 7; L2 §6, §9.1; SYSTEM_V2_PREREG.md
§2.2, §2.3; IMPLEMENTATION_REGISTER R-V1-30, R-V1-31, R-V2-17, R-V2-19, R-V2-20).

Minute by minute on the exit side (bid for a long, ask for a short; the mid for the P4 twins): a minute with a
finite exit quote (open, close and low for a long / high for a short) whose open is through the stop X exits at that
open, else one whose low/high reaches X exits at X (the stop wins a tie, and is tested on every path minute, the
entry minute included); a minute is live iff it has a finite exit quote and volume on both sides, and the 15th
consecutive non-live minute ends the trade at X (reason gap); otherwise the time exit is the close of the last path
minute with a finite exit quote.
"""
import math

from .common import ALLOWANCE, LAMBDAS, STRESS_ADD


def _f(x):
    return x is not None and math.isfinite(x)


def _half(dm, m, kind):
    """Half spread at minute m of the open ('o') or close ('c'); 0 for a missing row or a non-finite side."""
    if m is None or not dm.has_row[m]:
        return 0.0
    a, b = dm[f"ask_{kind}"][m], dm[f"bid_{kind}"][m]
    if not (math.isfinite(a) and math.isfinite(b)):
        return 0.0
    return (a - b) / 2


def entry_price(dm, side, m_entry, mid=False):
    """(P_e, minute used, 'o'|'c') or None: the entry minute's open, else the close of the latest earlier minute of
    the model day with a finite close (A1 item 8)."""
    if mid:
        oc, cc = "o", "c"
    else:
        oc, cc = ("ask_o", "ask_c") if side > 0 else ("bid_o", "bid_c")
    if 0 <= m_entry < 1440 and math.isfinite(dm[oc][m_entry]):
        return float(dm[oc][m_entry]), m_entry, "o"
    for m in range(min(m_entry, 1440) - 1, -1, -1):
        if math.isfinite(dm[cc][m]):
            return float(dm[cc][m]), m, "c"
    return None


def path(dm, side, X, m_from, m_to, mid=False):
    """Walk the path minutes [m_from, m_to). Returns (P_x, exit minute, reason, exit spread kind)."""
    if mid:
        o, c, ext = dm["o"], dm["c"], dm["l"]
    elif side > 0:
        o, c, ext = dm["bid_o"], dm["bid_c"], dm["bid_l"]
    else:
        o, c, ext = dm["ask_o"], dm["ask_c"], dm["ask_h"]
    run, last_q = 0, None
    for m in range(m_from, min(m_to, 1440)):
        q = math.isfinite(o[m]) and math.isfinite(c[m]) and math.isfinite(ext[m])
        if q:
            if (side > 0 and o[m] <= X) or (side < 0 and o[m] >= X):
                return float(o[m]), m, "stop", "o"
            if (side > 0 and ext[m] <= X) or (side < 0 and ext[m] >= X):
                return X, m, "stop", "c"
            last_q = m
        live = q and dm.has_row[m] and dm["bid_vol"][m] > 0 and dm["ask_vol"][m] > 0
        if live:
            run = 0
        else:
            run += 1
            if run >= 15:
                return X, m, "gap", "c"
    if last_q is None:
        return X, None, "gap", "c"
    return float(c[last_q]), last_q, "time", "c"


def money(side, P_e, P_x, D, half_in, half_out):
    net = side * (P_x - P_e) - ALLOWANCE
    stress = net - STRESS_ADD
    cost = ALLOWANCE + half_in + half_out
    gross = net + cost
    R = net / D
    Rs = stress / D
    y = min(max(R, -2.0), 2.0)
    return {"gross_usd": gross, "cost_usd": cost, "net_usd": net, "net_stress_usd": stress, "R": R,
            "R_stress": Rs, "y": y}


def e_value(ys):
    """E(n) = (1/5) sum over lambda of prod (1 + lambda y_i) (L2 §9.1)."""
    tot = 0.0
    for lam in LAMBDAS:
        p = 1.0
        for y in ys:
            p *= 1 + lam * y
        tot += p
    return tot / len(LAMBDAS)


def k_value(ys):
    """K(m) = (1/5) sum over lambda of prod (1 - lambda y_i) (L2 §9.1, demotion)."""
    tot = 0.0
    for lam in LAMBDAS:
        p = 1.0
        for y in ys:
            p *= 1 - lam * y
        tot += p
    return tot / len(LAMBDAS)


def e_path(ys):
    """E after each y (running products)."""
    prods = [1.0] * len(LAMBDAS)
    out = []
    for y in ys:
        prods = [p * (1 + lam * y) for p, lam in zip(prods, LAMBDAS)]
        out.append(sum(prods) / len(LAMBDAS))
    return out


def k_path(ys):
    prods = [1.0] * len(LAMBDAS)
    out = []
    for y in ys:
        prods = [p * (1 - lam * y) for p, lam in zip(prods, LAMBDAS)]
        out.append(sum(prods) / len(LAMBDAS))
    return out
