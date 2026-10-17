"""Publish the system status (SYSTEM_V1_PREREG.md §5, §8, Amendment A1 items 3, 4, 11, 12). OPS.

- reports/forward_site/system/VolMapSystem.csv: `key,value` lines: the header, version, asof_utc, the L1 keys, the L3
  keys for the 7 buckets, the lab keys, LIVE rules, then `end,<number of preceding lines>`. The file is UTF-8 without
  a BOM, LF line ends. Every line is ASCII except the value of `lab_live_<i>_title_ar`, which is the rule's Arabic
  title as UTF-8 (A1 item 3; the indicator opens the file with CP_UTF8). The title passes registry.title_ok; the
  writer refuses anything else.
- reports/forward_site/system/lab.json: the dashboard card's data. A rule that has been promoted (LIVE, SUSPENDED, and
  later DEMOTED or RETIRED) shows only its post-promotion evidence: its record since promotion and its demotion
  e-process K; its pre-promotion E and progress are not published (§3 item 11, A1 item 12). For PAPER rules,
  progress = min(E/E*, 1), the same linear scale as lab_best_progress.
- reports/system/STATUS.md: a plain summary for Claude and the client, written after the deploy so it includes the
  run's operational failures (A1 item 11), with the INTERPRETER_NEEDED flag (§8).

Lab counts in VolMapSystem.csv (the indicator's lab rows, A1 item 4):
- lab_days = the number of settled lab days (model-clock weekdays with their rows written) on or after the lab's first
  first_day;
- lab_n_paper = the number of promotable rules in state PAPER (the seed S1 and proposer rules); REF streams (S1R, C1)
  and PENDING, LIVE, SUSPENDED, DEMOTED and RETIRED rules are not counted.
"""
import json
from pathlib import Path

import numpy as np

import system_common as sc
from lab import eproc, ledger, registry

STATE_AR = {"PAPER": "قيد الاختبار", "LIVE": "مثبتة", "SUSPENDED": "معلّقة", "DEMOTED": "سُحبت",
            "RETIRED": "متوقفة: لم تنجح", "REF": "مرجع للمقارنة", "PENDING": "لم تُسجَّل بعد"}
SHORT_RECORD_AR = "سجلّها بعد اعتمادها ما زال قصيرًا"
SHORT_RECORD_N = 20
TITLE_KEY = "_title_ar"
LAB_COUNTS_DOC = [
    "- `lab_days` = settled lab days (model-clock weekdays) on or after the lab's first first_day.",
    "- `lab_n_paper` = promotable rules in state PAPER (S1 and proposer rules); REF streams (S1R, C1) and PENDING, "
    "LIVE, SUSPENDED, DEMOTED and RETIRED rules are not counted.",
    "- The indicator's second lab row «عدد القواعد قيد الاختبار %d، وأيام التداول المحسوبة %d» shows "
    "lab_n_paper and lab_days, only when lab_days >= 1 and lab_n_paper >= 1 (Amendment A1 item 4).",
]


def fmt_m(x):
    return f"{x:.4f}"


# ---------------------------------------------------------------- VolMapSystem.csv
def system_csv(asof_utc, l1, l3, lab):
    """Lines of VolMapSystem.csv (without the trailing newline)."""
    lines = ["key,value", "version,1", f"asof_utc,{asof_utc}",
             f"l1_green_ok,{int(l1['green_ok'])}", f"l1_asof,{l1['asof']}", f"l3_asof,{l3['asof'] or '-'}"]
    for b in sc.BUCKETS:
        m, n = l3["mult"][b]
        lines.append(f"l3_m_{b},{fmt_m(m)}")
        lines.append(f"l3_n_{b},{int(n)}")
    lines += [f"lab_state,{lab['state']}", f"lab_days,{int(lab['days'])}", f"lab_n_paper,{int(lab['n_paper'])}",
              f"lab_n_live,{int(lab['n_live'])}", f"lab_best_progress,{lab['best_progress']:.3f}"]
    for i, r in enumerate(lab["live"], start=1):
        if not registry.title_ok(r["title_ar"]):
            raise ValueError(f"LIVE rule {r.get('id')}: title {r['title_ar']!r} breaks the title rule (A1 item 3)")
        lines.append(f"lab_live_{i}_title_ar,{r['title_ar']}")
        lines.append(f"lab_live_{i}_npost,{int(r['n_post'])}")
    lines.append(f"end,{len(lines)}")
    for ln in lines:
        key, _, value = ln.partition(",")
        if ln.count(",") != 1 or not key.isascii() or "\r" in ln or "\n" in ln:
            raise ValueError(f"not a key,value line: {ln!r}")
        if not key.endswith(TITLE_KEY) and not value.isascii():
            raise ValueError(f"only a title value may be non-ASCII: {ln!r}")
    return lines


def encode_system_csv(lines):
    """The file's bytes: UTF-8 without a BOM, LF line ends, a final newline."""
    data = ("\n".join(lines) + "\n").encode("utf-8")
    assert not data.startswith(b"\xef\xbb\xbf")
    return data


def parse_system_csv(data):
    """The indicator's reading (VolMapBand.mq5 ParseSystem): None unless the header and the `end` count are valid;
    else {key: value}. `data` is the file's bytes (decoded as UTF-8, a BOM dropped) or text."""
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    if text.startswith("﻿"):
        text = text[1:]
    lines = [ln.replace("\r", "") for ln in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 2 or lines[0] != "key,value" or not lines[-1].startswith("end,"):
        return None
    try:
        n = int(lines[-1].split(",", 1)[1])
    except ValueError:
        return None
    if n != len(lines) - 1:
        return None
    out = {}
    for ln in lines[1:-1]:
        if "," not in ln or ln.index(",") == 0:
            return None
        k, v = ln.split(",", 1)
        out[k] = v
    return out


def write_system_csv(path, lines):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(encode_system_csv(lines))
    tmp.replace(path)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n")


# ---------------------------------------------------------------- lab summary (status file, dashboard, STATUS.md)
def lab_summary(lab_dir, recs, sts, events_l, state):
    """Per-rule rows and the lab counts. A promoted rule shows its post-promotion record and K only (A1 item 12)."""
    lab_dir = Path(lab_dir)
    twins = ledger.read(lab_dir / "twins.csv")
    days = ledger.read(lab_dir / "lab_days.csv")
    first = ledger.lab_first_day(sts)
    rules, best = [], 0.0
    interp = any(e["event"] == "PROMOTED" for e in events_l)
    for r in recs:
        s = sts[r["id"]]
        stt = ledger.rule_stats(lab_dir, r, s, twins)
        E, Es = stt["E"], (r["E_star"] if r["E_star"] is not None else float("inf"))
        promoted = s["promoted_utc"] is not None
        interp = interp or eproc.interpreter_needed(E, Es, stt["n"], r["promotable"] and s["state"] == "PAPER",
                                                    False)
        row = {"id": r["id"], "title_ar": r["title_ar"], "tier": r["tier"], "promotable": r["promotable"],
               "state": s["state"], "state_ar": STATE_AR[s["state"]], "first_day": s["first_day"],
               "registered_utc": s["registered_utc"], "n_post": len(stt["post"]), "spec": r["spec"]}
        if promoted:
            # §3 item 11 and A1 item 12: post-promotion evidence only (its record and the demotion e-process K)
            n_shown, net_shown = len(stt["post"]), float(sum(t["net_usd"] for t in stt["post"]))
            row |= {"record": "post-promotion", "promoted_utc": s["promoted_utc"], "E": None, "E_star": None,
                    "progress": None, "K": stt["K"], "K_demote": eproc.DEMOTE_K}
        else:
            n_shown, net_shown = stt["n"], stt["sum_net"]
            prog = None
            if r["promotable"] and np.isfinite(Es):
                prog = float(min(max(E / Es, 0.0), 1.0))
                if s["state"] == "PAPER":
                    best = max(best, E / Es)
            row |= {"record": "since first_day", "E": E, "E_star": Es if np.isfinite(Es) else None,
                    "progress": prog, "K": None}
        row |= {"n": n_shown, "net_sum": net_shown, "net_avg": net_shown / n_shown if n_shown else None}
        rules.append(row)
    live = [x for x in rules if x["state"] == "LIVE"]
    return {"state": state, "days": sum(1 for d in days if first and d["day"] >= first),
            "n_paper": sum(1 for x in rules if x["promotable"] and x["state"] == "PAPER"), "n_live": len(live),
            "best_progress": best, "live": live, "rules": rules, "interpreter_needed": bool(interp),
            "first_day": first}


def state_table(trials):
    """Descriptive (D2-D4 deferred, §8): per base state, origins with an entry and the pooled mid k10 hit rate."""
    if not len(trials):
        return []
    out = []
    for s_, g in trials[trials.entry == 1].groupby("state"):
        hr = (g.hit_long.sum() + g.hit_short.sum()) / (2 * len(g))
        out.append({"state": ["GREY", "GREEN", "YELLOW", "RED"][int(s_)], "n": len(g), "hit_rate": f"{hr:.3f}"})
    return out


def site_json(info):
    """lab.json for the card page: no NaN, Arabic texts as they are."""
    def clean(x):
        if isinstance(x, float):
            return None if not np.isfinite(x) else round(x, 6)
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.floating,)):
            return clean(float(x))
        return x
    lab = info["lab"]
    return clean({"generated_utc": info["asof_utc"], "lab_state": lab["state"], "halted": bool(info["halt"]),
                  "start": info["start"], "lab_days": lab["days"], "n_paper": lab["n_paper"], "n_live": lab["n_live"],
                  "interpreter_needed": lab["interpreter_needed"], "rules": [
                      {k: v for k, v in r.items() if k != "spec"} | {"T": r["spec"]["T"], "hold": r["spec"]["hold"]}
                      for r in lab["rules"]],
                  "proposer": lab.get("proposer"), "l1_green_ok": info["l1"]["green_ok"],
                  "l3": {"asof": info["l3"]["asof"], "zstar": info["l3"]["zstar"],
                         "mult": {b: {"m": m, "n": n} for b, (m, n) in info["l3"]["mult"].items()}},
                  "data": info["data"]})


# ---------------------------------------------------------------- STATUS.md
def _f(x, nd=3):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def status_md(info):
    L = ["# Gold support system v1: status", "",
         f"Updated {info['asof_utc']}. Binding spec: xauusd-quant `research/system/SYSTEM_V1_PREREG.md` "
         f"(with Amendment A1).", ""]
    if info.get("halt"):
        L += ["**HALTED** (lab PAUSED):", ""] + [f"- {h}" for h in info["halt"]] + [""]
    if info.get("ops"):
        L += ["**Operational failures** (the run exits non-zero so GitHub emails the owner; the lab is not halted):",
              ""] + [f"- {o}" for o in info["ops"]] + [""]
    d = info["data"]
    L += ["## Data and forecasts", "",
          f"- Raw Dukascopy days stored: {d['ok_days']} (missing sides: {len(d['missing'])}); complete through "
          f"{d['complete_through_utc']} UTC (exclusive); lag {d.get('lag_trading_days', 0)} trading day(s)",
          f"- Revisions logged (never used): {d['revisions']}",
          f"- Forecast store: {d['store_rows']} slots ({d['store_defined']} defined); "
          f"{d['store_new']} new this run",
          f"- START: {info['start'] or 'not set (no successful cloud run of the frozen code yet)'}"]
    cal = info.get("calendar")
    if cal:
        L.append(f"- Event calendars cover through {cal['horizon']} (the earliest of the last NFP, CPI and FOMC "
                 f"dates); extension lines accepted {cal['ext_accepted']}, rejected {cal['ext_rejected']}")
    L.append("")
    l1 = info["l1"]
    L += ["## L1 green suppression (D1)", "", f"- l1_green_ok = {l1['green_ok']} (as of {l1['asof']})"]
    for b in l1["blocks"]:
        hr = "-" if b["hit_rate"] is None else f"{100 * b['hit_rate']:.1f}%"
        L.append(f"- Block {b['block']} {b['start']} .. {b['end']}: complete {b['complete']}, green origins "
                 f"{b['n_green']}, hit rate {hr}")
    if l1.get("states"):
        L += ["", "Descriptive (D2-D4 deferred, §8): base state counts and pooled mid k10 hit rates", "",
              "| state | origins | hit rate |", "|---|---|---|"]
        for s in l1["states"]:
            L.append(f"| {s['state']} | {s['n']} | {s['hit_rate']} |")
    l3 = info["l3"]
    L += ["", "## L3 calibration", "", f"- z* = {l3['zstar']} (reports/system/L3_ZSTAR.json); last update: "
          f"{l3['asof'] or 'none yet (first in 2027-01)'}", f"- Observations since START: {l3['n_obs']}", "",
          "| bucket | n | m in force |", "|---|---|---|"]
    for b in sc.BUCKETS:
        m, n = l3["mult"][b]
        L.append(f"| {b} | {n} | {m:.4f} |")
    lab = info["lab"]
    L += ["", "## L2 lab", "", f"- State: {lab['state']}; lab_days {lab['days']}; lab_n_paper {lab['n_paper']}; "
          f"LIVE: {lab['n_live']}; best progress E/E* over PAPER rules: {lab['best_progress']:.3f}",
          f"- INTERPRETER_NEEDED: {'YES' if lab['interpreter_needed'] else 'no'}", "",
          "What the status-file counts mean:", ""] + LAB_COUNTS_DOC + [
          "", "A promoted rule (LIVE, SUSPENDED, DEMOTED) shows its post-promotion record and its demotion "
          "e-process K only (§3 item 11, A1 item 12).", "",
          "| id | state | first_day | record | trades | sum net $/oz | evidence |", "|---|---|---|---|---|---|---|"]
    for r in lab["rules"]:
        if r["K"] is not None:
            ev = f"K {r['K']:.3f} (demote at {r['K_demote']:g})"
        elif r["E_star"] is not None:
            ev = f"E {r['E']:.3f} of E* {r['E_star']:.1f}"
        else:
            ev = f"E {r['E']:.3f} (REF)"
        L.append(f"| {r['id']} | {r['state']} | {r['first_day'] or '-'} | {r['record']} | {r['n']} | "
                 f"{r['net_sum']:.2f} | {ev} |")
    if lab.get("proposer"):
        p = lab["proposer"]
        L += ["", f"- Last proposer run {p['run_date']}: {p['n_scored']} rules scored, q95 {p['q95']:.3f}, "
              f"proposed {len(p['chosen'])}"]
    return "\n".join(L) + "\n"
