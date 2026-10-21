"""Promotion, demotion, retirement and suspension as the judge recomputes them (L2 §9.3-§9.5 with SYSTEM_V1_PREREG.md
§3 items 7-8; SYSTEM_V2_PREREG.md §2.2 P4, §2.3; IMPLEMENTATION_REGISTER R-V1-34, R-V1-35, R-V2-19 .. R-V2-22)."""
import math
from fractions import Fraction

import pandas as pd

from . import execution
from .common import utc_to_model, weekdays_between


def rule_stats(trades, promoted_utc=None):
    """trades: final trade dicts in ledger order with day, side, R, y, net, stress, recorded (Timestamp)."""
    ys = [t["y"] for t in trades]
    Rs = [t["R"] for t in trades]
    post = [t for t in trades if promoted_utc is not None and t["recorded"] > promoted_utc]
    return {
        "n": len(trades), "E": execution.e_value(ys) if ys else 1.0,
        "sumR": sum(Rs), "maxR": max(Rs) if Rs else float("nan"),
        "net": sum(t["net"] for t in trades), "stress": sum(t["stress"] for t in trades),
        "span": (pd.Timestamp(trades[-1]["day"]) - pd.Timestamp(trades[0]["day"])).days if trades else 0,
        "post": post, "K": execution.k_value([t["y"] for t in post]) if post else 1.0,
    }


def promotable_now(rec, st, mu, lab_running, version):
    """P1-P5 and P7 (P6 replaced in v1 §3 item 8). mu: v1 mu_l, v2 mu-bar (P4)."""
    if version == 1:
        p1 = st["E"] >= float(rec["E_star"])
    else:
        p1 = Fraction(st["E"]) >= Fraction(rec["E_star_exact"])
    p2 = st["n"] >= 40 and st["span"] >= 56
    p3 = st["net"] > 0 and st["stress"] > 0
    p4 = mu is not None and math.isfinite(mu) and st["p4sum"] > 0
    p5 = st["n"] > 0 and st["sumR"] - st["maxR"] > 0
    return p1 and p2 and p3 and p4 and p5 and lab_running


def expected_transition(rec, state, st, mu, t, registered, demoted_utc, last_settled_day, lab_running, version):
    """The (event, reason) the state update must append at run time t for one rule, or None."""
    if state == "PAPER" and rec.get("promotable"):
        if promotable_now(rec, st, mu, lab_running, version):
            return ("PROMOTED", "P1-P5,P7")
        if st["n"] >= 150 and st["sumR"] <= 0:
            return ("RETIRED", "n150")
        if registered is not None and t >= registered + pd.DateOffset(months=24):
            return ("RETIRED", "age")
        return None
    if state in ("LIVE", "SUSPENDED"):
        post = st["post"]
        pr = [p["R"] for p in post]
        if st["K"] >= 10:
            return ("DEMOTED", "D1")
        if sum(pr) <= -5:
            return ("DEMOTED", "D2")
        for m in range(100, len(pr) + 1, 100):
            if sum(pr[:m]) <= 0:
                return ("DEMOTED", "D3")
        today = utc_to_model(t).normalize()
        stale = last_settled_day is None or weekdays_between(pd.Timestamp(last_settled_day), today) > 5
        if state == "LIVE" and (not lab_running or stale):
            return ("SUSPENDED", "S-a")
        if state == "SUSPENDED" and lab_running and not stale:
            return ("RESUMED", "S-a cleared")
        return None
    if state == "DEMOTED" and demoted_utc is not None:
        if weekdays_between(utc_to_model(demoted_utc).normalize(), utc_to_model(t).normalize()) >= 5:
            return ("RETIRED", "demoted")
    return None
