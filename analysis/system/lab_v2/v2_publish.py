"""Publish lab v2 (SYSTEM_V2_PREREG.md §2.4 and §2.5 item 4). OPS.

- reports/system/lab_v2/summary.json: the state of lab v2 for v1's publisher, which copies four keys into
  VolMapSystem.csv on its next run (`lab2_state` = state, `lab2_days` = days, `lab2_n_paper` = n_paper,
  `lab2_best_progress` = best_progress with 3 decimals):
  - state: RUNNING, or PAUSED when the run halted (exception, FROZEN_V2 mismatch, store mismatch, audit failure,
    tripwire, inconsistent ledger);
  - days: settled lab v2 days on or after the v2 lab's first first_day;
  - n_paper: promotable seeds in state PAPER;
  - best_progress: max E/E* over PAPER seeds (0 when none), the same linear scale as v1's lab_best_progress;
  plus per-seed rows, START, the C1 comparison and INTERPRETER_NEEDED. UTF-8 JSON, strict (no NaN).
- reports/system/lab_v2/STATUS.md: a plain summary.
- reports/forward_site/system/lab_v2/index.html and lab_v2.json (rendered by v2_page, standard library only): the
  dashboard section «المختبر، الإصدار الثاني»: the v2 seeds with their record (trades, sum and mean net $/oz, progress
  E/E*) next to the v1 coin control C1 over the same days (C1's final trades in v1's reports/system/lab/trades.csv
  from the v2 lab's first first_day, read-only; dollars per ounce are compared, since R units differ between v1 and
  v2). S3 shows «في مرحلة الإحماء حتى تكتمل بياناتها» while fewer than 250 of its trend-flip flow values precede the
  day (its 250-day threshold window), and while it waits for an incomplete lookback store (its row's
  `waits_for_lookback`; v2_ledger.settle). While the state is not RUNNING the page shows only «المختبر الثاني متوقف
  مؤقتًا» (Amendment B2 item 3). v1's lab page (reports/forward_site/system/index.html) links to it (B2 item 2). The
  page is static HTML with the data written in; it is deployed by the next deploy of the site (v1's step or
  forward-watch).
- A promoted seed (LIVE, SUSPENDED, DEMOTED) shows only its post-promotion record and K (v1 §3 item 11, A1 item 12).
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import v2_ledger
import v2_page
import v2_signals
from lab import eproc
from v2_page import COIN_AR, PAUSED_AR, TITLE_AR, WARMUP_AR, page_html, site_json  # noqa: F401 (re-exported)

STATE_AR = {"PAPER": "قيد الاختبار", "LIVE": "مثبتة", "SUSPENDED": "معلّقة", "DEMOTED": "سُحبت",
            "RETIRED": "متوقفة", "PENDING": "لم تُسجَّل بعد"}
S3_QWIN = 250


def _clean(x):
    if isinstance(x, float):
        return None if not math.isfinite(x) else x
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return _clean(float(x))
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")


def s3_flow_count(bars_m15, day):
    """Finite trend-flip flow values of S3 before model day `day` (descriptive: its 250-day window)."""
    if bars_m15 is None or not len(bars_m15):
        return 0
    mod = v2_signals.load_seed("S3")
    idx = bars_m15.index
    hm = idx.hour * 60 + idx.minute
    at = hm == mod.CLOSE_BAR
    p = pd.Series(bars_m15.c.to_numpy()[at], index=idx.normalize()[at])
    p = p[~p.index.duplicated()].astype(float)
    lp = np.log(p)
    S = pd.concat([np.sign(lp - lp.shift(L)) for L in mod.LOOKS], axis=1).mean(axis=1, skipna=False)
    V = mod.TV / (lp.diff().rolling(mod.VOL_N, min_periods=mod.VOL_N).std() * np.sqrt(252))
    Ft = (S - S.shift(1)) * V.shift(1)
    return int(Ft[Ft.index < pd.Timestamp(day).normalize()].notna().sum())


def c1_record(v1_lab_dir, first_day):
    """The v1 coin control C1 over the same days (its final trades from the v2 lab's first first_day)."""
    if first_day is None:
        return {"n": 0, "net_sum": 0.0, "mean_R": None, "E": 1.0}
    tr = [t for t in v2_ledger.read(Path(v1_lab_dir) / "trades.csv")
          if t["id"] == "C1" and t["status"] == "final" and t["day"] >= first_day]
    R = [float(t["R"]) for t in tr]
    return {"n": len(tr), "net_sum": float(sum(float(t["net_usd"]) for t in tr)),
            "mean_R": float(np.mean(R)) if R else None, "E": eproc.e_value([float(t["y"]) for t in tr])}


def summary(lab_dir, recs, sts, events, state, asof, start, v1_lab_dir, bars_m15=None, halt=None, today=None,
            lookback_complete=True):
    lab_dir = Path(lab_dir)
    trades_all, twins_all = v2_ledger.read(lab_dir / "trades.csv"), v2_ledger.read(lab_dir / "twins.csv")
    days = v2_ledger.read(lab_dir / "lab_days.csv")
    first = v2_ledger.lab_first_day(sts)
    rules, best = [], 0.0
    interp = any(e["event"] == "PROMOTED" for e in events)
    flow_n = s3_flow_count(bars_m15, today) if (today is not None and bars_m15 is not None) else None
    for r in recs:
        s = sts[r["id"]]
        stt = v2_ledger.rule_stats(lab_dir, r, s, trades_all, twins_all)
        Es = float(r["E_star"])
        promoted = s["promoted_utc"] is not None
        interp = interp or eproc.interpreter_needed(stt["E"], Es, stt["n"], r["promotable"] and s["state"] == "PAPER",
                                                    False)
        row = {"id": r["id"], "title_ar": r["title_ar"], "tf": r["tf"], "hold_minutes": r["hold_minutes"],
               "state": s["state"], "state_ar": STATE_AR.get(s["state"], s["state"]), "first_day": s["first_day"],
               "registered_utc": s["registered_utc"], "n_post": len(stt["post"]), "E_star": Es,
               "E_star_exact": r["E_star_exact"]}
        if promoted:
            n_shown, net_shown = len(stt["post"]), float(sum(t["net_usd"] for t in stt["post"]))
            R_shown = [t["R"] for t in stt["post"]]
            row |= {"record": "post-promotion", "promoted_utc": s["promoted_utc"], "E": None, "progress": None,
                    "K": stt["K"], "K_demote": eproc.DEMOTE_K}
        else:
            n_shown, net_shown = stt["n"], stt["sum_net"]
            R_shown = [t["R"] for t in stt["trades"]]
            prog = float(min(max(stt["E"] / Es, 0.0), 1.0))
            if s["state"] == "PAPER":
                best = max(best, stt["E"] / Es)
            row |= {"record": "since first_day", "E": stt["E"], "progress": prog, "K": None}
        row |= {"n": n_shown, "net_sum": net_shown, "net_avg": net_shown / n_shown if n_shown else None,
                "mean_R": float(np.mean(R_shown)) if R_shown else None, "mu_bar": stt["mu_bar"]}
        waits = r["id"] in v2_signals.LOOKBACK_SEEDS and not lookback_complete
        if r["id"] == "S3" and flow_n is not None:
            row |= {"flow_values_before_today": flow_n, "warmup": flow_n < S3_QWIN or waits}
        if r["id"] in v2_signals.LOOKBACK_SEEDS:
            row["waits_for_lookback"] = waits
        rules.append(row)
    return {"version": 2, "asof_utc": asof, "state": state, "halted": bool(halt), "halt_reasons": list(halt or []),
            "start": start, "first_day": first,
            "days": sum(1 for d in days if first and d["day"] >= first),
            "n_paper": sum(1 for x in rules if x["state"] == "PAPER"),
            "n_live": sum(1 for x in rules if x["state"] == "LIVE"),
            "best_progress": float(best), "interpreter_needed": bool(interp), "rules": rules,
            "c1": c1_record(v1_lab_dir, first)}


# ---------------------------------------------------------------- STATUS.md
def _f(x, fmt):
    return "-" if x is None or (isinstance(x, float) and not math.isfinite(x)) else format(x, fmt)


def status_md(info, s):
    L = ["# Gold support system v2: lab v2 status", "",
         f"Updated {info['asof_utc']}. Binding spec: xauusd-quant `research/system/SYSTEM_V2_PREREG.md` with "
         f"SYSTEM_V1_PREREG.md and Amendment A1.", ""]
    if info.get("halt"):
        L += ["**HALTED** (lab v2 PAUSED; v1 is not affected):", ""] + [f"- {h}" for h in info["halt"]] + [""]
    if info.get("ops"):
        L += ["**Operational failures** (lab v2 not halted):", ""] + [f"- {o}" for o in info["ops"]] + [""]
    d = info.get("data", {})
    L += ["## Data", "",
          f"- Lookback store (UTC 2026-01-01 .. 2026-08-31): {d.get('lookback_ok', 0)} ok sides, "
          f"{d.get('lookback_missing', 0)} missing, complete: {d.get('lookback_complete')}",
          f"- v1 raw days read (from 2026-09-01, read-only): complete through {d.get('complete_utc', '-')} UTC",
          f"- v2 START: {s['start'] or 'not set (no successful lab v2 cloud run yet)'}", "",
          "## Seeds", "",
          f"- State: {s['state']}; lab2_days {s['days']}; lab2_n_paper {s['n_paper']}; LIVE {s['n_live']}; "
          f"best progress E/E* {s['best_progress']:.3f}",
          f"- INTERPRETER_NEEDED: {'YES' if s['interpreter_needed'] else 'no'}", "",
          "| id | state | first_day | record | trades | sum net $/oz | mean R | evidence |",
          "|---|---|---|---|---|---|---|---|"]
    for r in s["rules"]:
        ev = (f"K {_f(r['K'], '.3f')} (demote at {r['K_demote']:g})" if r["K"] is not None
              else f"E {_f(r['E'], '.3f')} of E* {r['E_star_exact']}")
        L.append(f"| {r['id']} | {r['state']} | {r['first_day'] or '-'} | {r['record']} | {r['n']} | "
                 f"{r['net_sum']:.2f} | {_f(r['mean_R'], '.3f')} | {ev} |")
    c = s["c1"]
    L += ["", f"- C1 (v1 coin control) over the same days: {c['n']} trades, sum net {c['net_sum']:.2f} $/oz, "
              f"mean R {_f(c['mean_R'], '.3f')}, E {c['E']:.3f}"]
    for r in s["rules"]:
        if "warmup" in r:
            L.append(f"- S3 trend-flip flow values before today: {r['flow_values_before_today']} of {S3_QWIN} "
                     f"({'warm-up' if r['warmup'] else 'window full'})")
    for r in s["rules"]:
        if r.get("waits_for_lookback"):
            L.append(f"- {r['id']} waits for the lookback store: it is not audited, settled or traded until the store "
                     "is complete (R-V2-42).")
    return "\n".join(L) + "\n"


def write_all(rep_dir, site_dir, info, s):
    write_json(Path(rep_dir) / "summary.json", s)
    (Path(rep_dir) / "STATUS.md").write_text(status_md(info, s), encoding="utf-8")
    v2_page.write_site(site_dir, _clean(s))
