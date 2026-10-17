"""Publish the system status (SYSTEM_V1_PREREG.md §5, §8). OPS.

- reports/forward_site/system/VolMapSystem.csv: ASCII `key,value` lines: the header, version, asof_utc, the L1 keys,
  the L3 keys for the 7 buckets, the lab keys, LIVE rules, then `end,<number of preceding lines>`.
  `lab_live_<i>_title_ar` carries the Arabic title as UTF-16 code units, 4 uppercase hex digits each with no separator
  (e.g. 0642 0627 ... written as 06420627...), so the file stays ASCII as §5 requires.
- reports/forward_site/system/lab.json: the dashboard card's data.
- reports/system/STATUS.md: a plain summary for Claude and the client, with the INTERPRETER_NEEDED flag (§8).
"""
import json
from pathlib import Path

import numpy as np

import system_common as sc

STATE_AR = {"PAPER": "قيد الاختبار", "LIVE": "مثبتة", "SUSPENDED": "معلّقة", "DEMOTED": "سُحبت",
            "RETIRED": "متوقفة: لم تنجح", "REF": "مرجع للمقارنة", "PENDING": "لم تُسجَّل بعد"}
SHORT_RECORD_AR = "سجلّها بعد اعتمادها ما زال قصيرًا"
SHORT_RECORD_N = 20


def hex_utf16(s):
    return "".join(f"{u:04X}" for u in np.frombuffer(s.encode("utf-16-be"), dtype=">u2"))


def unhex_utf16(h):
    return bytes.fromhex(h).decode("utf-16-be")


def fmt_m(x):
    return f"{x:.4f}"


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
        lines.append(f"lab_live_{i}_title_ar,{hex_utf16(r['title_ar'])}")
        lines.append(f"lab_live_{i}_npost,{int(r['n_post'])}")
    lines.append(f"end,{len(lines)}")
    for ln in lines:
        if not ln.isascii() or ln.count(",") != 1:
            raise ValueError(f"not an ASCII key,value line: {ln!r}")
    return lines


def parse_system_csv(text):
    """The indicator's reading: None unless the last line is a valid `end` count; else {key: value}."""
    lines = text.rstrip("\n").split("\n")
    if not lines or not lines[-1].startswith("end,"):
        return None
    try:
        n = int(lines[-1].split(",", 1)[1])
    except ValueError:
        return None
    if n != len(lines) - 1 or lines[0] != "key,value":
        return None
    return dict(ln.split(",", 1) for ln in lines[1:-1])


def write_system_csv(path, lines):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="ascii")
    tmp.replace(path)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n")


def _f(x, nd=3):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def status_md(info):
    L = [f"# Gold support system v1: status", "",
         f"Updated {info['asof_utc']}. Binding spec: xauusd-quant `research/system/SYSTEM_V1_PREREG.md`.", ""]
    if info.get("halt"):
        L += ["**HALTED** (lab PAUSED):", ""] + [f"- {h}" for h in info["halt"]] + [""]
    d = info["data"]
    L += ["## Data and forecasts", "",
          f"- Raw Dukascopy days stored: {d['ok_days']} (missing sides: {len(d['missing'])}); complete through "
          f"{d['complete_through_utc']} UTC (exclusive)",
          f"- Revisions logged (never used): {d['revisions']}",
          f"- Forecast store: {d['store_rows']} slots ({d['store_defined']} defined); "
          f"{d['store_new']} new this run",
          f"- START: {info['start'] or 'not set (no successful cloud run of the frozen code yet)'}", ""]
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
    L += ["", "## L2 lab", "", f"- State: {lab['state']}; settled lab days: {lab['days']}; PAPER (promotable): "
          f"{lab['n_paper']}; LIVE: {lab['n_live']}; best progress E/E*: {lab['best_progress']:.3f}",
          f"- INTERPRETER_NEEDED: {'YES' if lab['interpreter_needed'] else 'no'}", "",
          "| id | state | first_day | trades | sum net $/oz | E | E* |", "|---|---|---|---|---|---|---|"]
    for r in lab["rules"]:
        L.append(f"| {r['id']} | {r['state']} | {r['first_day'] or '-'} | {r['n']} | {r['net_sum']:.2f} | "
                 f"{r['E']:.3f} | {'-' if r['E_star'] is None else round(r['E_star'], 1)} |")
    if lab.get("proposer"):
        p = lab["proposer"]
        L += ["", f"- Last proposer run {p['run_date']}: {p['n_scored']} rules scored, q95 {p['q95']:.3f}, "
              f"proposed {len(p['chosen'])}"]
    return "\n".join(L) + "\n"
