"""Lab settlement, append-only ledgers and the state machine (L2 §6-§9 with SYSTEM_V1_PREREG.md §3). FROZEN.

A lab day d (model-clock weekday on or after the lab's first first_day) is settled once, at the first run where every
minute through d 23:30 model is final; all its rows are written then and never changed:
- reports/system/lab/lab_days.csv     day, settled_utc
- reports/system/lab/decisions.csv    one row per registered rule per lab day on or after its first_day
- reports/system/lab/trades.csv       one row per triggered trade (every trigger is settled, §3 item 3)
- reports/system/lab/eproc.csv        one row per trade: E, K and E* after it
- reports/system/lab/twins.csv        long drift twin on the mid (no cost) per (T, hold, stop, delay) and day (P4)
After the new days: promotions (registry order), demotions, retirements and suspensions, each an event row.
Lab outcomes are never computed for a day before START on real data (§0); synthetic dry runs set synthetic=True.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import bars
from lab import eproc, execution, grammar, registry

DECISION_COLS = ["id", "day", "outcome", "side", "U", "feat1", "feat2", "F_RAW_H1", "F_RAW_S", "recorded_utc"]
TRADE_COLS = ["id", "day", "T", "side", "delay_min", "entry_model", "P_e", "X", "D", "exit_model", "P_x", "reason",
              "gross_usd", "cost_usd", "net_usd", "net_stress_usd", "R", "R_stress", "y", "F_RAW_H1", "F_RAW_S", "U",
              "status", "recorded_utc", "code_sha8"]
EPROC_COLS = ["id", "trade_no", "day", "y", "E", "K", "E_star", "state_after"]
TWIN_COLS = ["key", "day", "R_twin", "recorded_utc"]
DAY_COLS = ["day", "settled_utc"]
SUSPEND_AFTER_DAYS = 5
DEMOTED_SHOWN_DAYS = 5


@dataclass
class DayInputs:
    day: pd.Timestamp
    weekday: int
    holiday: bool
    event_day: bool
    db: grammar.DayBars
    md: execution.Minutes
    F_H1: np.ndarray
    F_S: np.ndarray


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return ""
    return repr(x) if np.isfinite(x) else ""


def read(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def append(path, cols, rows):
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def mmhh(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def day_inputs(day, mf, lbars, store, holidays, event_days):
    """Inputs of one model day: its M15 bars, its M1 rows and the stored raw forecasts per slot."""
    day = pd.Timestamp(day).normalize()
    md = execution.Minutes(mf[(mf.index >= day) & (mf.index < day + pd.Timedelta(days=1))])
    db = grammar.DayBars(lbars[lbars.day == day])
    F1, FS = np.full(23, np.nan), np.full(23, np.nan)
    s = store[store.day == day.strftime("%Y-%m-%d")]
    for r in s.itertuples():
        F1[int(r.slot)] = float(r.F_H1) if pd.notna(r.F_H1) and r.F_H1 != "" else np.nan
        FS[int(r.slot)] = float(r.F_S) if pd.notna(r.F_S) and r.F_S != "" else np.nan
    return DayInputs(day=day, weekday=int(day.dayofweek), holiday=day in holidays, event_day=day in event_days,
                     db=db, md=md, F_H1=F1, F_S=FS)


def rule_rows(rec, st, di, now_utc, code_sha8):
    """(decision row, trade row or None) of one rule on one day."""
    spec = rec["spec"]
    T = grammar.minutes(spec["T"])
    slot = grammar.slot_of(T)
    F1, FS = di.F_H1[slot], di.F_S[slot]
    dec = grammar.decide(spec, di.db, di.day, di.weekday, st["first_day"], di.holiday, di.event_day, F1, FS)
    feats = dec["feats"] + [np.nan, np.nan]
    drow = {"id": rec["id"], "day": di.day.strftime("%Y-%m-%d"), "outcome": dec["outcome"], "side": dec["side"],
            "U": _num(dec["U"]), "feat1": _num(feats[0]), "feat2": _num(feats[1]), "F_RAW_H1": _num(F1),
            "F_RAW_S": _num(FS), "recorded_utc": now_utc}
    if dec["outcome"] != "trigger":
        return drow, None
    k = grammar.STOPS[spec["stop"]]
    F = F1 if spec["stop"] == "H10" else FS
    tr = execution.trade(di.md, dec["side"], T, spec["hold"], k, F, delay=rec.get("entry_delay_min", 1))
    trow = {"id": rec["id"], "day": drow["day"], "T": spec["T"], "side": dec["side"],
            "delay_min": rec.get("entry_delay_min", 1), "entry_model": mmhh(tr["entry_min"]),
            "P_e": _num(tr.get("P_e")), "F_RAW_H1": _num(F1), "F_RAW_S": _num(FS), "U": _num(dec["U"]),
            "status": tr["status"], "recorded_utc": now_utc, "code_sha8": code_sha8}
    if tr["status"] == "final":
        trow.update({"X": _num(tr["X"]), "D": _num(tr["D"]), "exit_model": mmhh(tr["exit_min"]),
                     "P_x": _num(tr["P_x"]), "reason": tr["reason"], "gross_usd": _num(tr["gross_usd"]),
                     "cost_usd": _num(tr["cost_usd"]), "net_usd": _num(tr["net_usd"]),
                     "net_stress_usd": _num(tr["net_stress_usd"]), "R": _num(tr["R"]),
                     "R_stress": _num(tr["R_stress"]), "y": _num(tr["y"])})
    return drow, trow


def twin_key(rec):
    s = rec["spec"]
    return f"{s['T']}|{s['hold']}|{s['stop']}|{rec.get('entry_delay_min', 1)}"


def twin_row(key, di, now_utc):
    T_s, h, stop, delay = key.split("|")
    T, h, delay = grammar.minutes(T_s), int(h), int(delay)
    slot = grammar.slot_of(T)
    F = di.F_H1[slot] if stop == "H10" else di.F_S[slot]
    if di.holiday or not di.db.ok(T - 15) or not np.isfinite(F):
        return None
    tr = execution.trade(di.md, 1, T, h, grammar.STOPS[stop], F, delay=delay, use_mid=True)
    if tr["status"] != "final" or not tr["D"] > 0:
        return None
    return {"key": key, "day": di.day.strftime("%Y-%m-%d"), "R_twin": _num(tr["R"]), "recorded_utc": now_utc}


def lab_first_day(sts):
    fds = [s["first_day"] for s in sts.values() if s["first_day"] and s["state"] != "PENDING"]
    return min(fds) if fds else None


def pending_days(lab_dir, sts, complete_utc, upto_model_day=None):
    """Model weekdays on or after the lab's first first_day, not settled yet, whose minutes through 23:30 are final."""
    first = lab_first_day(sts)
    if first is None:
        return []
    done = {r["day"] for r in read(Path(lab_dir) / "lab_days.csv")}
    out = []
    d = pd.Timestamp(first)
    while True:
        if d.dayofweek < 5:
            if bars.model_to_utc(d + pd.Timedelta(hours=23, minutes=30)) > complete_utc:
                break
            if upto_model_day is not None and d > pd.Timestamp(upto_model_day):
                break
            if d.strftime("%Y-%m-%d") not in done:
                out.append(d)
        d += pd.Timedelta(days=1)
    return out


def settle_days(lab_dir, recs, sts, days_inputs, now_utc, code_sha8, start, synthetic=False):
    """Write the rows of the given lab days (DayInputs, in order). Returns the number of trades written."""
    lab_dir = Path(lab_dir)
    trades_all = read(lab_dir / "trades.csv")
    counts = {}
    for t in trades_all:
        counts[t["id"]] = counts.get(t["id"], 0) + 1
    ys = {}
    for t in trades_all:
        if t["status"] == "final":
            ys.setdefault(t["id"], []).append(float(t["y"]))
    n_new = 0
    keys = sorted({twin_key(r) for r in recs if sts[r["id"]]["state"] not in ("PENDING", "RETIRED")})
    for di in days_inputs:
        if not synthetic and (start is None or di.day < pd.Timestamp(start)):
            raise AssertionError("lab outcomes are never computed before START on real data")
        drows, trows, erows, wrows = [], [], [], []
        for rec in recs:
            st = sts[rec["id"]]
            if st["state"] in ("PENDING", "RETIRED") or st["first_day"] is None or di.day < pd.Timestamp(st["first_day"]):
                continue
            drow, trow = rule_rows(rec, st, di, now_utc, code_sha8)
            drows.append(drow)
            if trow is None:
                continue
            trows.append(trow)
            counts[rec["id"]] = counts.get(rec["id"], 0) + 1
            if trow["status"] == "final":
                ys.setdefault(rec["id"], []).append(float(trow["y"]))
                y = ys[rec["id"]]
                post = _post_y(lab_dir, rec["id"], st, trows)
                erows.append({"id": rec["id"], "trade_no": len(y), "day": trow["day"], "y": trow["y"],
                              "E": _num(eproc.e_value(y)), "K": _num(eproc.k_value(post)),
                              "E_star": _num(rec["E_star"]), "state_after": st["state"]})
        for key in keys:
            w = twin_row(key, di, now_utc)
            if w:
                wrows.append(w)
        append(lab_dir / "decisions.csv", DECISION_COLS, drows)
        append(lab_dir / "trades.csv", TRADE_COLS, trows)
        append(lab_dir / "eproc.csv", EPROC_COLS, erows)
        append(lab_dir / "twins.csv", TWIN_COLS, wrows)
        append(lab_dir / "lab_days.csv", DAY_COLS, [{"day": di.day.strftime("%Y-%m-%d"), "settled_utc": now_utc}])
        n_new += len(trows)
    return n_new


def _post_y(lab_dir, cid, st, new_rows):
    if st["promoted_utc"] is None:
        return []
    rows = [t for t in read(Path(lab_dir) / "trades.csv") + list(new_rows)
            if t["id"] == cid and t["status"] == "final" and t["recorded_utc"] > st["promoted_utc"]]
    return [float(t["y"]) for t in rows]


# ---------------------------------------------------------------- statistics per rule
def rule_stats(lab_dir, rec, st, twins=None):
    lab_dir = Path(lab_dir)
    tr = [t for t in read(lab_dir / "trades.csv") if t["id"] == rec["id"] and t["status"] == "final"]
    tl = [{"day": t["day"], "side": int(t["side"]), "y": float(t["y"]), "R": float(t["R"]),
           "net_usd": float(t["net_usd"]), "net_stress_usd": float(t["net_stress_usd"]),
           "recorded_utc": t["recorded_utc"]} for t in tr]
    twins = read(lab_dir / "twins.csv") if twins is None else twins
    mu = mu_long(rec, st, twins)
    post = [t for t in tl if st["promoted_utc"] and t["recorded_utc"] > st["promoted_utc"]]
    return {"trades": tl, "n": len(tl), "E": eproc.e_value([t["y"] for t in tl]), "mu_long": mu,
            "sum_R": float(sum(t["R"] for t in tl)), "sum_net": float(sum(t["net_usd"] for t in tl)),
            "post": post, "K": eproc.k_value([t["y"] for t in post])}


def mu_long(rec, st, twins):
    """Mean long-twin R over the rule's eligible days from its first_day (L2 §6.7, P4)."""
    if st["first_day"] is None:
        return np.nan
    key = twin_key(rec)
    spec = rec["spec"]
    vals = []
    for w in twins:
        if w["key"] != key or w["day"] < st["first_day"]:
            continue
        d = pd.Timestamp(w["day"])
        if not (spec["days"] >> d.dayofweek) & 1:
            continue
        if d.dayofweek == 4 and grammar.minutes(spec["T"]) + 15 * spec["hold"] > grammar.FRIDAY_EXIT_MAX:
            continue
        vals.append(float(w["R_twin"]))
    return float(np.mean(vals)) if vals else np.nan


def trading_days_between(a, b):
    """Model weekdays in (a, b]."""
    a, b = pd.Timestamp(a).normalize(), pd.Timestamp(b).normalize()
    if b <= a:
        return 0
    return int(np.busday_count((a + pd.Timedelta(days=1)).date(), (b + pd.Timedelta(days=1)).date()))


def update_states(lab_dir, recs, sts, events, now_utc, lab_running, run_id, head_sha, today_model):
    """Promotions, demotions, retirements, suspensions. Returns the new event rows (already appended)."""
    lab_dir = Path(lab_dir)
    twins = read(lab_dir / "twins.csv")
    rows = []
    D_total = registry.promotions_count(events)
    days = read(lab_dir / "lab_days.csv")
    last_settled = days[-1]["day"] if days else None
    stale = last_settled is None or trading_days_between(last_settled, today_model) > SUSPEND_AFTER_DAYS

    def ev(cid, event, reason, s):
        rows.append({"utc": now_utc, "id": cid, "event": event, "reason": reason, "n": s["n"],
                     "E": _num(s["E"]), "K": _num(s["K"]), "D_total": D_total, "run_id": run_id,
                     "head_sha": head_sha})

    for rec in recs:
        st = sts[rec["id"]]
        if st["state"] in ("PENDING", "REF", "RETIRED"):
            continue
        s = rule_stats(lab_dir, rec, st, twins)
        if st["state"] == "PAPER":
            chk = eproc.promotion_checks(s["trades"], rec["E_star"], s["mu_long"], lab_running)
            if rec["promotable"] and chk["all"]:
                D_total += 1
                ev(rec["id"], "PROMOTED", "P1-P5,P7", s)
                st["state"], st["promoted_utc"] = "LIVE", now_utc
                continue
            why = eproc.retirement_check(s["n"], s["sum_R"], st["registered_utc"], now_utc)
            if why:
                ev(rec["id"], "RETIRED", why, s)
                st["state"] = "RETIRED"
        elif st["state"] in ("LIVE", "SUSPENDED"):
            why, _ = eproc.demotion_check([t["R"] for t in s["post"]], [t["y"] for t in s["post"]])
            if why:
                ev(rec["id"], "DEMOTED", why, s)
                st["state"], st["demoted_utc"] = "DEMOTED", now_utc
                continue
            if st["state"] == "LIVE" and (not lab_running or stale):
                ev(rec["id"], "SUSPENDED", "S-a: lab paused" if not lab_running else "S-a: no settled day", s)
                st["state"] = "SUSPENDED"
            elif st["state"] == "SUSPENDED" and lab_running and not stale:
                ev(rec["id"], "RESUMED", "S-a cleared", s)
                st["state"] = "LIVE"
        elif st["state"] == "DEMOTED":
            dday = bars.to_model(pd.DatetimeIndex([pd.Timestamp(st["demoted_utc"])]))[0]
            if trading_days_between(dday, today_model) >= DEMOTED_SHOWN_DAYS:
                ev(rec["id"], "RETIRED", "demoted", s)
                st["state"] = "RETIRED"
    registry.append_events(lab_dir / "registry" / "events.csv", rows)
    return rows


def tripwire(lab_dir, recs, sts, di, code_sha8):
    """Re-derive one settled day's decision and trade rows from the store; differences mean non-determinism."""
    lab_dir = Path(lab_dir)
    day = di.day.strftime("%Y-%m-%d")
    led_d = {(r["id"], r["day"]): r for r in read(lab_dir / "decisions.csv") if r["day"] == day}
    led_t = {(r["id"], r["day"]): r for r in read(lab_dir / "trades.csv") if r["day"] == day}
    diffs = []
    for rec in recs:
        key = (rec["id"], day)
        if key not in led_d:
            continue
        st = dict(sts[rec["id"]])
        d2, t2 = rule_rows(rec, st, di, led_d[key]["recorded_utc"], code_sha8)
        for c in ("outcome", "side", "U", "feat1", "feat2", "F_RAW_H1", "F_RAW_S"):
            if str(d2[c]) != str(led_d[key][c]):
                diffs.append(f"{key} decision {c}: ledger {led_d[key][c]!r} vs recomputed {d2[c]!r}")
        if (t2 is None) != (key not in led_t):
            diffs.append(f"{key}: trade presence differs")
        elif t2 is not None:
            for c in ("P_e", "X", "P_x", "reason", "net_usd", "R"):
                if str(t2.get(c, "")) != str(led_t[key][c]):
                    diffs.append(f"{key} trade {c}: ledger {led_t[key][c]!r} vs recomputed {t2.get(c)!r}")
    return diffs
