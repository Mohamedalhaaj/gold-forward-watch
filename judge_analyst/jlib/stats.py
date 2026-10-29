"""The test's arithmetic, recomputed independently: E_n and K (R-AN-52, lab L2 §9.1/§9.4 formulas), promotion
(R-AN-53), demotion (R-AN-54), retirement (R-AN-55) and the latched state events (R-AN-56).

§16.18 A15 (R-AN-94): a trade carries `wt` (its weight, 1.0 by default) and `cluster` (its cluster's first call_id;
its own call_id by default). Counts and sums are weighted; E_n and K take one factor per cluster, with the cluster's
mean y; P5 drops the best cluster. A trade of a model day before a15_from has weight 1.0 and is its own cluster, so
the formulas then give exactly the earlier values."""
from __future__ import annotations

import datetime as dt

from .clock import add_months_12, busday_count

LAMBDAS = (0.025, 0.05, 0.1, 0.2, 0.4)
E_STAR = 400.0


def e_path(ys, sign: float = 1.0):
    """E (sign +1) or K (sign −1) after each trade: mean over Λ of Π(1 + sign·λ·y_i)."""
    prods = [1.0] * len(LAMBDAS)
    out = []
    for y in ys:
        for j, lam in enumerate(LAMBDAS):
            prods[j] *= 1.0 + sign * lam * y
        out.append(sum(prods) / len(LAMBDAS))
    return out


def e_value(ys) -> float:
    p = e_path(ys)
    return p[-1] if p else 1.0


def k_value(ys) -> float:
    p = e_path(ys, -1.0)
    return p[-1] if p else 1.0


def wt(t) -> float:
    return t.get("wt", 1.0)


def clusters(trades):
    """[(cluster, [trades])] in the order of their first trades (R-AN-94: the clusters restricted to `trades`)."""
    out, idx = [], {}
    for t in trades:
        c = t.get("cluster") or t.get("call_id") or id(t)      # a trade without either: its own cluster
        if c not in idx:
            idx[c] = len(out)
            out.append((c, []))
        out[idx[c]][1].append(t)
    return out


def cluster_ys(trades):
    """y_C = Σ_{i∈C} w_i·y_i / Σ_{i∈C} w_i per cluster, in order."""
    return [sum(wt(t) * t["y"] for t in ts) / sum(wt(t) for t in ts) for _c, ts in clusters(trades)]


def e_trades(trades) -> float:
    return e_value(cluster_ys(trades))


def k_trades(trades) -> float:
    return k_value(cluster_ys(trades))


def n_weighted(trades) -> float:
    return sum(wt(t) for t in trades)


def wsum(trades, f) -> float:
    return sum(wt(t) * f(t) for t in trades)


def side_share(trades):
    """Σ w over counted trades with side +1 (or −1, the larger), over Σ w; None without trades."""
    n = n_weighted(trades)
    if not trades:
        return None
    return max(sum(wt(t) for t in trades if t["side"] == 1), sum(wt(t) for t in trades if t["side"] == -1)) / n


WINDOW_TYPES = ("W1", "W2", "W1b", "W2b", "T")     # §16.18 A14 (R-AN-47, R-AN-53): one type T for every trigger


def promotion(trades, twins, first_day: dt.date, e: dt.date):
    """P1-P5 over `trades` (counted, model day <= e, in window order). `twins` = [(model_day, W, d_W)] of final twins.
    Returns dict with P1..P5, n, E."""
    n = n_weighted(trades)
    E = e_trades(trades)
    out = {"n": n, "E": E}
    out["P1"] = E >= E_STAR
    span = (trades[-1]["model_day"] - trades[0]["model_day"]).days if n else 0
    out["P2"] = n >= 60 and span >= 56
    out["P3"] = bool(n) and wsum(trades, lambda t: t["stress"]) > 0 and \
        wsum(trades, lambda t: t["stress"] - 0.5 * t["cost"]) > 0
    mu = {}
    for w in WINDOW_TYPES:
        xs = [x for (d, ww, x) in twins if ww == w and first_day <= d <= e and x is not None]
        mu[w] = sum(xs) / len(xs) if xs else None
    if n and all(mu[t["w"]] is not None for t in trades):
        out["P4"] = wsum(trades, lambda t: t["net"] - t["side"] * mu[t["w"]]) > 0
    else:
        out["P4"] = False
    out["P5"] = bool(trades) and (wsum(trades, lambda t: t["R"]) -
                                  max(wsum(ts, lambda t: t["R"]) for _c, ts in clusters(trades))) > 0
    out["all"] = all(out[k] for k in ("P1", "P2", "P3", "P4", "P5"))
    out["mu"] = mu
    return out


def demotion(post):
    """(reason or None, K) over post-promotion trades in order (§16.18 A15: K per cluster, D2's sum weighted, D3 at the
    first trade at which the cumulative post weight reaches m = 100, 200, ...)."""
    K = k_trades(post)
    if K >= 10.0:
        return "D1", K
    if post and wsum(post, lambda t: t["R"]) <= -5.0:
        return "D2", K
    cw = cr = 0.0
    m = 100
    for t in post:
        cw += wt(t)
        cr += wt(t) * t["R"]
        if cw >= m:
            if cr <= 0:
                return "D3", K
            while cw >= m:
                m += 100
    return None, K


def weekdays_between(a: dt.date, b: dt.date) -> int:
    """R-V1-35: np.busday_count(a + 1 day, b + 1 day)."""
    return busday_count(a + dt.timedelta(days=1), b + dt.timedelta(days=1))


def replay_states(trades, twins, first_day: dt.date | None, processed_days):
    """Recompute the latched TESTING/PROMOTED/DEMOTED/RETIRED events (P7 assumed true; PAUSED/RESUMED and RETIRED
    `violation` are not replayed). Returns [(event, reason, model_day, n, E, K)]."""
    events = []
    if first_day is None:
        return events
    state = "SHAKEDOWN"
    promo_day = demo_day = None
    for e in sorted(processed_days):
        if e < first_day:
            continue
        upto = [t for t in trades if t["model_day"] <= e]
        n = n_weighted(upto)
        E = e_trades(upto)
        post = [t for t in upto if promo_day is not None and t["model_day"] > promo_day]
        K = k_trades(post) if promo_day is not None else 1.0
        if state == "SHAKEDOWN":
            state = "TESTING"
            events.append(("TESTING", "first_day", e, n, E, K))
        if state == "TESTING":
            p = promotion(upto, twins, first_day, e)
            if p["all"]:
                state, promo_day = "PROMOTED", e
                events.append(("PROMOTED", "P1-P5,P7", e, n, E, 1.0))
            elif n >= 150 and wsum(upto, lambda t: t["R"]) <= 0:
                state = "RETIRED"
                events.append(("RETIRED", "n150", e, n, E, K))
            elif e >= add_months_12(first_day):
                state = "RETIRED"
                events.append(("RETIRED", "age", e, n, E, K))
        elif state == "PROMOTED":
            reason, K = demotion(post)
            if reason:
                state, demo_day = "DEMOTED", e
                events.append(("DEMOTED", reason, e, n, E, K))
        elif state == "DEMOTED":
            if weekdays_between(demo_day, e) >= 5:
                state = "RETIRED"
                events.append(("RETIRED", "demoted", e, n, E, K))
        if state == "RETIRED":
            break
    return events
