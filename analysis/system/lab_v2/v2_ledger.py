"""Lab v2 settlement, append-only ledgers, the causality audit record, the tripwire and the state machine
(SYSTEM_V2_PREREG.md §2.2-§2.4; v1 §3 and L2 §6-§9 where v2 is silent). FROZEN (lab v2).

A lab v2 day d (model weekday on or after the v2 lab's first first_day) is settled once, at the first run where every
minute through d 23:30 model is final (bars.model_to_utc(d 23:30) <= complete_utc), at most MAX_DAYS_PER_RUN days a
run, oldest first. All of its rows are written then and never changed (reports/system/lab_v2/):
- audit.csv      one row per active seed per settled day: the online-vs-full causality audit (§2.2)
- decisions.csv  one row per bar of the day whose ONLINE value is non-zero, for each active seed with first_day <= d:
                 outcome trade | abstain_window | abstain_day | abstain_U | ignored_open, checked in that order:
                 abstain_window: T < 01:30 or T + HOLD·TF > 23:30 (22:45 on a Friday);
                 abstain_day: d is an NYSE full closure or early close (models.nyse_holidays, per year as v1);
                 abstain_U: the RAW F_S of the entry slot (slot = hour of T + 1 minus 1, model clock; v1's write-once
                 store data/system/forecasts.csv) is missing, not finite or <= 0;
                 ignored_open: T is before the scheduled end (T' + HOLD·TF) of the seed's previous traded signal of
                 the day (at most one open trade; the scheduled end, not an early stop, frees the seed);
                 trade: otherwise; side = the online value.
- trades.csv     one row per `trade` decision (status final, or no_quote when there is no executable quote at all)
- twins.csv      one row per final trade: its P4 mid twin μ_i (v2_exec)
- eproc.csv      one row per final trade: E (all final trades from first_day, in (day, T) order), K (post-promotion
                 trades) and E* after it
- lab_days.csv   day, settled_utc (written last)
Then promotions (registry order), demotions, retirements and suspensions, each a row of registry/events.csv, exactly
as v1 (P1-P3, P4 of §2.2, P5, P7; D1-D3; n150/age retirement; S-a suspensions), with P1 against the exact E*.

An incomplete lookback store: while v2_data.lookback_complete is false at the run time, the seeds in
v2_signals.LOOKBACK_SEEDS (S3) wait: on the days that run settles they get no audit, decision, trade, twin or eproc
row, and those days are never settled again (lab_days.csv is shared). The other seeds are settled as usual. From the
first run that sees the complete store, S3 is audited and settled like the others.

Audit failure: if any active seed's online and full-data values differ on a window bar of a pending day, nothing is
settled in that run, the failing seed's audit row (result FAIL) is written, the seed is voided (RETIRED, reason
"bug", L2 §7.3) and v2 halts for the run.

Tripwire (A1 item 7 as v1): every run re-derives the last settled day's decision and trade rows with the full-data
signal on the current data and compares them with the ledger (numbers at 1e-12 relative, the rest exactly); a
difference halts v2.

Lab outcomes are never computed for a day before the v2 START on real data (§0); synthetic dry runs set synthetic=True.
"""
import csv
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

import bars as v1bars
import v2_exec
import v2_signals
from lab import eproc, execution, registry as v1reg

DAY_COLS = ["day", "settled_utc"]
DECISION_COLS = ["id", "day", "bar_start", "T", "signal", "outcome", "entry_model", "F_RAW_S", "recorded_utc"]
TRADE_COLS = ["id", "day", "T", "side", "entry_model", "P_e", "D", "X", "exit_model", "P_x", "reason", "gross_usd",
              "cost_usd", "net_usd", "net_stress_usd", "R", "R_stress", "y", "F_RAW_S", "status", "recorded_utc",
              "code_sha8"]
TWIN_COLS = ["id", "day", "T", "entry_model", "exit_model", "P_e", "D", "X", "P_x", "reason", "R_twin", "status",
             "recorded_utc"]
EPROC_COLS = ["id", "trade_no", "day", "T", "y", "E", "K", "E_star", "state_after"]
AUDIT_COLS = ["day", "id", "tf", "n_bars", "n_window", "n_signals", "n_mismatch_window", "n_mismatch_outside",
              "first_mismatch", "result", "recorded_utc"]
OUTCOMES = ("trade", "abstain_window", "abstain_day", "abstain_U", "ignored_open")
SUSPEND_AFTER_DAYS = 5
DEMOTED_SHOWN_DAYS = 5
MAX_DAYS_PER_RUN = 10
REL_TOL = 1e-12
DEC_CAT = ("bar_start", "T", "signal", "outcome", "entry_model")
DEC_NUM = ("F_RAW_S",)
TRADE_CAT = ("T", "side", "entry_model", "exit_model", "reason", "status")
TRADE_NUM = ("P_e", "D", "X", "P_x", "gross_usd", "cost_usd", "net_usd", "net_stress_usd", "R", "R_stress", "y")
VOID_REASON = "bug"


@dataclass
class DayInputs:
    day: pd.Timestamp
    weekday: int
    holiday: bool
    md: execution.Minutes
    F_S: np.ndarray


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


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


def day_inputs(day, mf_day, slots, holidays):
    """Inputs of one model day: its M1 rows (model clock) and the stored RAW F_S per slot (NaN when undefined)."""
    day = pd.Timestamp(day).normalize()
    key = day.strftime("%Y-%m-%d")
    FS = np.array([slots.get((key, s), (np.nan, np.nan))[1] for s in range(23)], dtype=float)
    return DayInputs(day=day, weekday=int(day.dayofweek), holiday=day in holidays, md=execution.Minutes(mf_day),
                     F_S=FS)


# ---------------------------------------------------------------- decisions and trades of one seed on one day
def rule_day(rec, di, sigs, now_utc, code_sha8, values="online"):
    """(decision rows, trade rows, twin rows) of one seed on one day from its DaySignals."""
    vals = sigs.online if values == "online" else sigs.full
    day = di.day.strftime("%Y-%m-%d")
    decs, trades, twins = [], [], []
    busy_until = -1
    for k in range(len(sigs.T)):
        v = int(vals[k])
        if v == 0:
            continue
        T = sigs.T[k]
        slot = (T + 1) // 60 - 1
        F = di.F_S[slot] if 0 <= slot < 23 else np.nan
        if not sigs.window[k]:
            outcome = "abstain_window"
        elif di.holiday:
            outcome = "abstain_day"
        elif not (np.isfinite(F) and F > 0):
            outcome = "abstain_U"
        elif T < busy_until:
            outcome = "ignored_open"
        else:
            outcome = "trade"
        decs.append({"id": rec["id"], "day": day, "bar_start": hhmm(sigs.start[k]), "T": hhmm(T), "signal": v,
                     "outcome": outcome, "entry_model": hhmm(T + 1), "F_RAW_S": _num(F), "recorded_utc": now_utc})
        if outcome != "trade":
            continue
        busy_until = T + sigs.hold_min
        tr = v2_exec.trade(di.md, v, T, sigs.hold_min, F_S=F)
        trow = {"id": rec["id"], "day": day, "T": hhmm(T), "side": v, "entry_model": hhmm(tr["entry_min"]),
                "P_e": _num(tr.get("P_e")), "F_RAW_S": _num(F), "status": tr["status"], "recorded_utc": now_utc,
                "code_sha8": code_sha8}
        if tr["status"] == "final":
            trow.update({"D": _num(tr["D"]), "X": _num(tr["X"]), "exit_model": hhmm(tr["exit_min"]),
                         "P_x": _num(tr["P_x"]), "reason": tr["reason"], "gross_usd": _num(tr["gross_usd"]),
                         "cost_usd": _num(tr["cost_usd"]), "net_usd": _num(tr["net_usd"]),
                         "net_stress_usd": _num(tr["net_stress_usd"]), "R": _num(tr["R"]),
                         "R_stress": _num(tr["R_stress"]), "y": _num(tr["y"])})
            tw = v2_exec.trade(di.md, 1, T, sigs.hold_min, twin_D=tr["D"])
            wrow = {"id": rec["id"], "day": day, "T": hhmm(T), "entry_model": hhmm(tw["entry_min"]),
                    "status": tw["status"], "recorded_utc": now_utc}
            if tw["status"] == "final":
                wrow.update({"exit_model": hhmm(tw["exit_min"]), "P_e": _num(tw["P_e"]), "D": _num(tw["D"]),
                             "X": _num(tw["X"]), "P_x": _num(tw["P_x"]), "reason": tw["reason"],
                             "R_twin": _num(tw["R"])})
            twins.append(wrow)
        trades.append(trow)
    return decs, trades, twins


def audit_row(sigs, tf, now_utc):
    mw, mo = sigs.mismatches(True), sigs.mismatches(False)
    first = hhmm(sigs.start[mw[0]]) if mw else ""
    return {"day": sigs.day.strftime("%Y-%m-%d"), "id": sigs.sid, "tf": tf, "n_bars": len(sigs.T),
            "n_window": int(sum(sigs.window)), "n_signals": int(sum(1 for v in sigs.online if v)),
            "n_mismatch_window": len(mw), "n_mismatch_outside": len(mo), "first_mismatch": first,
            "result": "FAIL" if mw else "ok", "recorded_utc": now_utc}


# ---------------------------------------------------------------- which days, which seeds
def lab_first_day(sts):
    fds = [s["first_day"] for s in sts.values() if s["first_day"] and s["state"] != "PENDING"]
    return min(fds) if fds else None


def pending_days(lab_dir, sts, complete_utc, max_days=MAX_DAYS_PER_RUN):
    first = lab_first_day(sts)
    if first is None:
        return []
    done = {r["day"] for r in read(Path(lab_dir) / "lab_days.csv")}
    out, d = [], pd.Timestamp(first)
    while len(out) < max_days:
        if d.dayofweek < 5:
            if v1bars.model_to_utc(d + pd.Timedelta(hours=23, minutes=30)) > complete_utc:
                break
            if d.strftime("%Y-%m-%d") not in done:
                out.append(d)
        d += pd.Timedelta(days=1)
    return out


def active(rec, st, day):
    return (st["state"] not in ("PENDING", "RETIRED") and st["first_day"] is not None
            and pd.Timestamp(day) >= pd.Timestamp(st["first_day"]))


def waits(rec, lookback_complete):
    """True for a seed that reads the input-only lookback on forward days while the lookback store is incomplete."""
    return not lookback_complete and rec["id"] in v2_signals.LOOKBACK_SEEDS


# ---------------------------------------------------------------- settlement
def settle(lab_dir, recs, sts, days, signals_fn, inputs_fn, now_utc, code_sha8, start, synthetic=False,
           lookback_complete=True):
    """Audit, then settle the given pending days (in order).

    signals_fn(sid, day) -> DaySignals (online values); inputs_fn(day) -> DayInputs; lookback_complete: the lookback
    store is complete at this run's time (v2_data.lookback_complete), else the LOOKBACK_SEEDS wait.
    Returns (n_trades_written, failures) with failures = [(sid, audit row)] (then nothing was settled)."""
    lab_dir = Path(lab_dir)
    plan, failures = [], []
    for d in days:
        if not synthetic and (start is None or d < pd.Timestamp(start)):
            raise AssertionError("lab v2 outcomes are never computed before the v2 START on real data")
        per = []
        for rec in recs:
            st = sts[rec["id"]]
            if not active(rec, st, d) or waits(rec, lookback_complete):
                continue
            sg = signals_fn(rec["id"], d)
            arow = audit_row(sg, rec["tf"], now_utc)
            if arow["result"] == "FAIL":
                failures.append((rec["id"], arow))
            per.append((rec, st, sg, arow))
        plan.append((d, per))
    if failures:
        append(lab_dir / "audit.csv", AUDIT_COLS, [a for _, a in failures])
        return 0, failures
    trades_all = read(lab_dir / "trades.csv")
    ys = {}
    for t in trades_all:
        if t["status"] == "final":
            ys.setdefault(t["id"], []).append(float(t["y"]))
    n_new = 0
    for d, per in plan:
        di = inputs_fn(d)
        arows, drows, trows, wrows, erows = [], [], [], [], []
        for rec, st, sg, arow in per:
            arows.append(arow)
            decs, trs, tws = rule_day(rec, di, sg, now_utc, code_sha8)
            drows += decs
            wrows += tws
            for tr in trs:
                trows.append(tr)
                if tr["status"] != "final":
                    continue
                ys.setdefault(rec["id"], []).append(float(tr["y"]))
                post = _post_y(lab_dir, rec["id"], st, trows)
                erows.append({"id": rec["id"], "trade_no": len(ys[rec["id"]]), "day": tr["day"], "T": tr["T"],
                              "y": tr["y"], "E": _num(eproc.e_value(ys[rec["id"]])), "K": _num(eproc.k_value(post)),
                              "E_star": _num(rec["E_star"]), "state_after": st["state"]})
        append(lab_dir / "audit.csv", AUDIT_COLS, arows)
        append(lab_dir / "decisions.csv", DECISION_COLS, drows)
        append(lab_dir / "trades.csv", TRADE_COLS, trows)
        append(lab_dir / "twins.csv", TWIN_COLS, wrows)
        append(lab_dir / "eproc.csv", EPROC_COLS, erows)
        append(lab_dir / "lab_days.csv", DAY_COLS, [{"day": d.strftime("%Y-%m-%d"), "settled_utc": now_utc}])
        n_new += len(trows)
    return n_new, []


def _post_y(lab_dir, sid, st, new_rows):
    if st["promoted_utc"] is None:
        return []
    rows = [t for t in read(Path(lab_dir) / "trades.csv") + list(new_rows)
            if t["id"] == sid and t["status"] == "final" and t["recorded_utc"] > st["promoted_utc"]]
    return [float(t["y"]) for t in rows]


def void_events(failures, events, now_utc, run_id, head_sha):
    """RETIRED rows (reason "bug", L2 §7.3) for the seeds whose causality audit failed."""
    D_total = v1reg.promotions_count(events)
    seen, rows = set(), []
    for sid, _ in failures:
        if sid in seen:
            continue
        seen.add(sid)
        rows.append({"utc": now_utc, "id": sid, "event": "RETIRED", "reason": VOID_REASON, "n": "", "E": "", "K": "",
                     "D_total": D_total, "run_id": run_id, "head_sha": head_sha})
    return rows


def ledger_consistent(lab_dir):
    """Problems (empty = OK): a ledger row whose day is not in lab_days.csv (a run that died while appending; audit
    rows with result FAIL are written for days that were not settled, by design, and are exempt)."""
    lab_dir = Path(lab_dir)
    days = {r["day"] for r in read(lab_dir / "lab_days.csv")}
    bad = []
    for f in ("audit.csv", "decisions.csv", "trades.csv", "twins.csv", "eproc.csv"):
        extra = sorted({r["day"] for r in read(lab_dir / f) if r.get("result", "ok") != "FAIL"} - days)
        if extra:
            bad.append(f"{f} has rows of unsettled days {extra[:3]}")
    return bad


# ---------------------------------------------------------------- statistics per seed
def rule_stats(lab_dir, rec, st, trades_all=None, twins_all=None):
    lab_dir = Path(lab_dir)
    trades_all = read(lab_dir / "trades.csv") if trades_all is None else trades_all
    twins_all = read(lab_dir / "twins.csv") if twins_all is None else twins_all
    tr = [t for t in trades_all if t["id"] == rec["id"] and t["status"] == "final"]
    tl = [{"day": t["day"], "T": t["T"], "side": int(t["side"]), "y": float(t["y"]), "R": float(t["R"]),
           "net_usd": float(t["net_usd"]), "net_stress_usd": float(t["net_stress_usd"]),
           "recorded_utc": t["recorded_utc"]} for t in tr]
    tw = {(w["day"], w["T"]): float(w["R_twin"]) for w in twins_all
          if w["id"] == rec["id"] and w["status"] == "final"}
    mus = [tw[(t["day"], t["T"])] for t in tl if (t["day"], t["T"]) in tw]
    post = [t for t in tl if st["promoted_utc"] and t["recorded_utc"] > st["promoted_utc"]]
    return {"trades": tl, "n": len(tl), "E": eproc.e_value([t["y"] for t in tl]),
            "mu_bar": float(np.mean(mus)) if mus else np.nan, "n_twins": len(mus),
            "sum_R": float(sum(t["R"] for t in tl)), "sum_net": float(sum(t["net_usd"] for t in tl)),
            "post": post, "K": eproc.k_value([t["y"] for t in post])}


def e_star(rec):
    """The exact E* of a record (a Fraction)."""
    return Fraction(rec["E_star_exact"])


def trading_days_between(a, b):
    a, b = pd.Timestamp(a).normalize(), pd.Timestamp(b).normalize()
    if b <= a:
        return 0
    return int(np.busday_count((a + pd.Timedelta(days=1)).date(), (b + pd.Timedelta(days=1)).date()))


def update_states(lab_dir, recs, sts, events, now_utc, lab_running, run_id, head_sha, today_model):
    """Promotions, demotions, retirements, suspensions (v1's rules). Returns the new event rows (already appended)."""
    lab_dir = Path(lab_dir)
    trades_all, twins_all = read(lab_dir / "trades.csv"), read(lab_dir / "twins.csv")
    rows = []
    D_total = v1reg.promotions_count(events)
    days = read(lab_dir / "lab_days.csv")
    last_settled = days[-1]["day"] if days else None
    stale = last_settled is None or trading_days_between(last_settled, today_model) > SUSPEND_AFTER_DAYS

    def ev(sid, event, reason, s):
        rows.append({"utc": now_utc, "id": sid, "event": event, "reason": reason, "n": s["n"], "E": _num(s["E"]),
                     "K": _num(s["K"]), "D_total": D_total, "run_id": run_id, "head_sha": head_sha})

    for rec in recs:
        st = sts[rec["id"]]
        if st["state"] in ("PENDING", "REF", "RETIRED"):
            continue
        s = rule_stats(lab_dir, rec, st, trades_all, twins_all)
        if st["state"] == "PAPER":
            chk = eproc.promotion_checks(s["trades"], e_star(rec), s["mu_bar"], lab_running)
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
            dday = v1bars.to_model(pd.DatetimeIndex([pd.Timestamp(st["demoted_utc"])]))[0]
            if trading_days_between(dday, today_model) >= DEMOTED_SHOWN_DAYS:
                ev(rec["id"], "RETIRED", "demoted", s)
                st["state"] = "RETIRED"
    v1reg.append_events(lab_dir / "registry" / "events.csv", rows)
    return rows


def halt_suspensions(recs, sts, events, now_utc, run_id, head_sha):
    """A halted run suspends every LIVE seed (v1 L2 §12.9); it resumes when v2 runs again."""
    D_total = v1reg.promotions_count(events)
    return [{"utc": now_utc, "id": r["id"], "event": "SUSPENDED", "reason": "S-a: lab paused", "n": "", "E": "",
             "K": "", "D_total": D_total, "run_id": run_id, "head_sha": head_sha}
            for r in recs if sts[r["id"]]["state"] == "LIVE"]


# ---------------------------------------------------------------- tripwire
def same_number(a, b, rel_tol=REL_TOL):
    a, b = str(a), str(b)
    if a == "" or b == "":
        return a == b
    x, y = float(a), float(b)
    return x == y or abs(x - y) <= rel_tol * max(abs(x), abs(y))


def tripwire(lab_dir, recs, sts, di, full_sigs, code_sha8):
    """Re-derive the decision and trade rows of the settled day `di.day` from the full-data signal on the current
    data; full_sigs: {sid: DaySignals}. Returns the differences (empty = OK)."""
    lab_dir = Path(lab_dir)
    day = di.day.strftime("%Y-%m-%d")
    led_d = {(r["id"], r["bar_start"]): r for r in read(lab_dir / "decisions.csv") if r["day"] == day}
    led_t = {(r["id"], r["T"]): r for r in read(lab_dir / "trades.csv") if r["day"] == day}
    audited = {r["id"] for r in read(lab_dir / "audit.csv") if r["day"] == day and r["result"] == "ok"}
    diffs = []
    for rec in recs:
        if rec["id"] not in audited or rec["id"] not in full_sigs:
            continue
        recorded = next((r["recorded_utc"] for r in led_d.values() if r["id"] == rec["id"]), "")
        decs, trs, _ = rule_day(rec, di, full_sigs[rec["id"]], recorded, code_sha8, values="full")
        got_d = {(r["id"], r["bar_start"]): r for r in decs}
        got_t = {(r["id"], r["T"]): r for r in trs}
        want_d = {k: v for k, v in led_d.items() if k[0] == rec["id"]}
        want_t = {k: v for k, v in led_t.items() if k[0] == rec["id"]}
        if set(got_d) != set(want_d):
            diffs.append(f"{rec['id']} {day}: decision bars differ")
        if set(got_t) != set(want_t):
            diffs.append(f"{rec['id']} {day}: trades differ")
        for k in set(got_d) & set(want_d):
            for c in DEC_CAT:
                if str(got_d[k][c]) != str(want_d[k][c]):
                    diffs.append(f"{k} decision {c}: ledger {want_d[k][c]!r} vs recomputed {got_d[k][c]!r}")
            for c in DEC_NUM:
                if not same_number(got_d[k][c], want_d[k][c]):
                    diffs.append(f"{k} decision {c}: ledger {want_d[k][c]!r} vs recomputed {got_d[k][c]!r}")
        for k in set(got_t) & set(want_t):
            for c in TRADE_CAT:
                if str(got_t[k].get(c, "")) != str(want_t[k][c]):
                    diffs.append(f"{k} trade {c}: ledger {want_t[k][c]!r} vs recomputed {got_t[k].get(c)!r}")
            for c in TRADE_NUM:
                if not same_number(got_t[k].get(c, ""), want_t[k][c]):
                    diffs.append(f"{k} trade {c}: ledger {want_t[k][c]!r} vs recomputed {got_t[k].get(c)!r}")
    return diffs
