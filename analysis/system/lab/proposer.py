"""The proposer (L2 §10 as amended by SYSTEM_V1_PREREG.md §3 item 10). FROZEN.

- Space P1 ("clock momentum or reversal"), exactly 1,920 rules: T = 03:00, 03:30, ..., 23:00; predicate
  ABSMOVE(T − 15w, T) GE θ with w in {1, 2, 4} and θ in {0.25, 0.50}; side FOLLOW or FADE of the same window;
  hold h in {1, 2, 4, 8} with T + 15h <= 23:30; stop H10 if h <= 4 else S10; days 31; skip_event 0.
- Training days: the last 60 settled lab days before the run (all of them while fewer exist), each on or after the
  lab's first first_day (asserted). Per rule: exactly what the ledger would record (entry T + 1 min at bid/ask,
  $0.10 allowance, Friday eligibility), then t = mean(R)/(sd(R)/√n), scored only with n >= 12.
- Null: B = 1,000 replicates, seed = the run date as YYYYMMDD. A replicate draws one sign per training day, shared by
  all rules that day; R* = s·gross_R − cost_R; M_b = max_j t*_j; q95 = the 95th percentile of M.
- Propose: rules with t >= q95 and mean R > 0, by t; at most 2, with distinct floor-hour(T); skip a rule whose
  question (spec without side mode) matches any existing candidate; never exceed 10 active proposer candidates.
- γ of the k-th proposal = 0.70/(k(k+1)); α_k and E*_k with the current number of promotions D.
- Schedule: first run on the first Saturday with >= 40 settled lab days, then every 28 days.
"""
import numpy as np
import pandas as pd

from lab import eproc, execution, grammar

B_REPLICATES = 1000
TRAIN_DAYS = 60
MIN_N = 12
MAX_PER_RUN = 2
FIRST_RUN_MIN_DAYS = 40
EVERY_DAYS = 28
TITLES = {("FADE", 1): "تعاكس حركة آخر ربع ساعة الكبيرة", ("FADE", 2): "تعاكس حركة آخر نصف ساعة الكبيرة",
          ("FADE", 4): "تعاكس حركة آخر ساعة الكبيرة", ("FOLLOW", 1): "تتبع حركة آخر ربع ساعة الكبيرة",
          ("FOLLOW", 2): "تتبع حركة آخر نصف ساعة الكبيرة", ("FOLLOW", 4): "تتبع حركة آخر ساعة الكبيرة"}


def space():
    """The 1,920 specs of space P1, in a fixed order."""
    out = []
    for T in range(180, 1381, 30):
        for w in (1, 2, 4):
            a = T - 15 * w
            for th in ("0.25", "0.50"):
                for mode in ("FOLLOW", "FADE"):
                    for h in (1, 2, 4, 8):
                        if T + 15 * h > grammar.EXIT_MAX:
                            continue
                        out.append({"T": grammar.hhmm(T), "side": [mode, grammar.hhmm(a), grammar.hhmm(T)],
                                    "when": [["ABSMOVE", grammar.hhmm(a), grammar.hhmm(T), "GE", th]], "hold": h,
                                    "stop": "H10" if h <= 4 else "S10", "days": 31, "skip_event": 0})
    assert len(out) == 1920, len(out)
    return out


def _meta(specs):
    T = np.array([grammar.minutes(s["T"]) for s in specs])
    w = np.array([(grammar.minutes(s["T"]) - grammar.minutes(s["side"][1])) // 15 for s in specs])
    th = np.array([float(s["when"][0][4]) for s in specs])
    mode = np.array([1 if s["side"][0] == "FOLLOW" else -1 for s in specs])
    h = np.array([s["hold"] for s in specs])
    stop = np.array([s["stop"] for s in specs])
    return T, w, th, mode, h, stop


def evaluate(specs, days):
    """R, gross_R and cost_R matrices (rules x days, NaN = no trade) on the training days.

    days: list of lab.ledger.DayInputs (day, weekday, holiday, event_day, db, md, F_H1, F_S)."""
    T, w, th, mode, h, stop = _meta(specs)
    J, D = len(specs), len(days)
    R = np.full((J, D), np.nan)
    G = np.full((J, D), np.nan)
    C = np.full((J, D), np.nan)
    for d, di in enumerate(days):
        if di.holiday:
            continue
        cache = {}
        for j in range(J):
            Tj, wj, hj = int(T[j]), int(w[j]), int(h[j])
            if di.weekday == 4 and Tj + 15 * hj > grammar.FRIDAY_EXIT_MAX:
                continue
            key = (Tj, wj)
            if key not in cache:
                a = Tj - 15 * wj
                F1 = di.F_H1[grammar.slot_of(Tj)]
                if not (di.db.ok(Tj - 15) and di.db.window_ok(a, Tj)) or not np.isfinite(F1):
                    cache[key] = None
                else:
                    U = di.db.C(Tj) * (np.exp(F1 / 1e4) - 1)
                    cache[key] = (di.db.C(Tj) - di.db.O(a)) / U if U > 0 else None
            mv = cache[key]
            if mv is None or abs(mv) < th[j] or mv == 0:
                continue
            side = int(np.sign(mv)) * int(mode[j])
            F = di.F_H1[grammar.slot_of(Tj)] if stop[j] == "H10" else di.F_S[grammar.slot_of(Tj)]
            if not np.isfinite(F):
                continue
            tkey = ("trade", Tj, hj, stop[j], side)
            if tkey not in cache:
                cache[tkey] = execution.trade(di.md, side, Tj, hj, grammar.STOPS[stop[j]], F, delay=1)
            tr = cache[tkey]
            if tr.get("status") != "final" or not tr["D"] > 0:
                continue
            R[j, d] = tr["R"]
            G[j, d] = tr["gross_usd"] / tr["D"]
            C[j, d] = tr["cost_usd"] / tr["D"]
    return R, G, C


def tstats(R):
    ok = np.isfinite(R)
    n = ok.sum(axis=1)
    X = np.where(ok, R, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = X.sum(axis=1) / n
        var = (np.where(ok, (R - mean[:, None]) ** 2, 0.0)).sum(axis=1) / (n - 1)
        t = mean / np.sqrt(var / n)
    t = np.where((n >= MIN_N) & np.isfinite(t), t, np.nan)
    return t, mean, n


def null_max(G, C, seed, B=B_REPLICATES):
    """M_b = max_j t*_j over B sign-flip replicates (one sign per day, shared across rules)."""
    ok = np.isfinite(G)
    n = ok.sum(axis=1).astype(float)
    use = n >= MIN_N
    G0, C0 = np.where(ok, G, 0.0)[use], np.where(ok, C, 0.0)[use]
    n = n[use]
    if len(n) == 0:
        return np.full(B, np.nan)
    rng = np.random.default_rng(seed)
    S = rng.choice(np.array([-1.0, 1.0]), size=(B, G.shape[1]))
    sums = G0 @ S.T - C0.sum(axis=1)[:, None]
    sumsq = (G0 ** 2).sum(axis=1)[:, None] - 2 * ((G0 * C0) @ S.T) + (C0 ** 2).sum(axis=1)[:, None]
    mean = sums / n[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (sumsq - n[:, None] * mean ** 2) / (n[:, None] - 1)
        t = mean / np.sqrt(np.maximum(var, 0) / n[:, None])
    t = np.where(np.isfinite(t), t, -np.inf)
    return t.max(axis=0)


def select(specs, t, mean, q95, existing_questions, active_proposals):
    """Indices of the accepted rules (at most 2, distinct floor-hour(T), new questions, cap 10)."""
    order = [j for j in np.argsort(-np.nan_to_num(t, nan=-np.inf), kind="stable")
             if np.isfinite(t[j]) and t[j] >= q95 and mean[j] > 0]
    chosen, hours, qs = [], set(), set(existing_questions)
    for j in order:
        if len(chosen) >= MAX_PER_RUN or active_proposals + len(chosen) >= eproc.MAX_ACTIVE_PROPOSALS:
            break
        hr = grammar.minutes(specs[j]["T"]) // 60
        q = grammar.question_key(specs[j])
        if hr in hours or q in qs:
            continue
        chosen.append(j)
        hours.add(hr)
        qs.add(q)
    return chosen


def run(days, run_date, lab_first_day, existing_questions, active_proposals, specs=None, B=B_REPLICATES):
    """One proposer run on the training days. Returns the report dict (selections as indices into `specs`)."""
    specs = specs or space()
    days = sorted(days, key=lambda d: d.day)[-TRAIN_DAYS:]
    for di in days:
        assert str(di.day)[:10] >= str(lab_first_day)[:10], "a training day before the lab's first first_day"
    seed = int(pd.Timestamp(run_date).strftime("%Y%m%d"))
    R, G, C = evaluate(specs, days)
    t, mean, n = tstats(R)
    M = null_max(G, C, seed, B)
    q95 = float(np.nanquantile(M, 0.95)) if np.isfinite(M).any() else float("inf")
    chosen = select(specs, t, mean, q95, existing_questions, active_proposals)
    rank = [int(j) for j in np.argsort(-np.nan_to_num(t, nan=-np.inf), kind="stable")[:20]]
    return {"run_date": str(pd.Timestamp(run_date).date()), "seed": seed, "B": B, "n_rules": len(specs),
            "train_days": [str(d.day)[:10] for d in days], "n_scored": int(np.isfinite(t).sum()),
            "q95": q95, "M_mean": float(np.nanmean(M)) if np.isfinite(M).any() else None,
            "top": [{"j": j, "spec": specs[j], "t": None if not np.isfinite(t[j]) else float(t[j]),
                     "mean_R": None if not np.isfinite(mean[j]) else float(mean[j]), "n": int(n[j])} for j in rank],
            "chosen": [int(j) for j in chosen], "chosen_specs": [specs[j] for j in chosen],
            "chosen_t": [float(t[j]) for j in chosen]}


def title_for(spec):
    w = (grammar.minutes(spec["T"]) - grammar.minutes(spec["side"][1])) // 15
    return TITLES[(spec["side"][0], w)]


def schedule_dates(anchor, upto):
    """Proposer Saturdays from the anchor every 28 days up to `upto` (dates)."""
    out, d = [], pd.Timestamp(anchor)
    while d <= pd.Timestamp(upto):
        out.append(d.strftime("%Y-%m-%d"))
        d += pd.Timedelta(days=EVERY_DAYS)
    return out


def due(run_date, n_settled, done_dates):
    """The scheduled proposer date this run executes, or None.

    Before the first proposer run: the run date, if it is a Saturday and >= 40 lab days are settled. After it: the
    latest scheduled date (anchor + 28k) up to the run date that has no report yet."""
    d = pd.Timestamp(run_date).normalize()
    if not done_dates:
        return d.strftime("%Y-%m-%d") if d.dayofweek == 5 and n_settled >= FIRST_RUN_MIN_DAYS else None
    pending = [x for x in schedule_dates(min(done_dates), d) if x not in set(done_dates)]
    return pending[-1] if pending else None
