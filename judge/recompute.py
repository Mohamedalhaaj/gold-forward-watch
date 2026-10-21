"""J5: recomputation from the system's committed raw files (SYSTEM_V2_PREREG.md §3.2 J5).

Forecasts (rel <= 1e-9), L1 states and blocks, L3 statistics, every lab trade of both versions (prices exact; R and y
at rel <= 1e-9), e-values, states, and the published status file. Every difference is a Finding; J5 turns findings
into a WARNING and the ADJUDICATIONS.csv rows (never a VIOLATION by itself).
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import bars, execution, forecasts, l1, l3, lab_v1, lab_v2, registry, states, store, vendored
from .common import (BUCKETS, K10_H, K10_S, day_str, hhmm, iso_s, load_json, model_to_utc, nyse_days, parse_utc, read_csv, read_dicts, rel_equal, sha256_file, utc_to_model)

TOL = 1e-9
EXACT_PRICE = ("P_e",)            # raw quotes: exact
V1_TRADE_NUM = ("X", "D", "P_x", "gross_usd", "cost_usd", "net_usd", "net_stress_usd", "R", "R_stress", "y",
                "F_RAW_H1", "F_RAW_S", "U")
V2_TRADE_NUM = ("D", "X", "P_x", "gross_usd", "cost_usd", "net_usd", "net_stress_usd", "R", "R_stress", "y",
                "F_RAW_S")


@dataclass
class Finding:
    area: str        # forecasts, l1, l3, v1, v2, status, vendor, registry, states
    subject: str     # stable key for adjudication, e.g. "v1 trades S1 2026-11-03"
    detail: str

    def key(self):
        return f"{self.area}|{self.subject}"


def _num_eq(a, b, tol=TOL):
    """a: recomputed float; b: ledger text."""
    if b == "":
        return not math.isfinite(a)
    try:
        bv = float(b)
    except ValueError:
        return False
    return rel_equal(a, bv, tol)


def _truthy(s):
    return str(s).strip() in ("1", "True", "true")


class Ctx:
    """Everything J5 reads, loaded once. data_root holds data/ and reports/; repo holds analysis/ (data files and
    manifests only) and git history."""

    def __init__(self, repo, data_root, now, pins=None):
        self.repo, self.root, self.now = Path(repo), Path(data_root), now
        self.pins = pins or {}
        self.v1 = store.Store(self.root / "data/system")
        self.lb = store.Store(self.root / "data/system/lab_v2/lookback")
        self.lab1 = registry.Lab(self.root, 1)
        self.lab2 = registry.Lab(self.root, 2)
        sysf = self.root / "reports/forward_site/system/VolMapSystem.csv"
        self.status_raw = sysf.read_bytes() if sysf.exists() else None
        self.asof = None
        if self.status_raw:
            for ln in self.status_raw.decode("utf-8", "replace").splitlines():
                if ln.startswith("asof_utc,"):
                    self.asof = parse_utc(ln.split(",", 1)[1])
        self.t_last = self.asof or now
        self.cu = store.complete_utc(self.v1, self.t_last)
        self._mf = None
        self._grid = None
        self._events = None
        self._hol = None

    # ------------------------------------------------------------ shared inputs
    def events(self):
        if self._events is None:
            self._events = forecasts.load_events(self.repo, self.root)
        return self._events

    def hol(self):
        if self._hol is None:
            self._hol = forecasts.holidays(self.now.year + 1)
        return self._hol

    def mf(self):
        """v1 model frame of every ok day loaded by the latest system run (R-V1-12)."""
        if self._mf is None:
            fr = store.load_frames(self.v1, store.v1_days_to_load(self.v1, self.t_last, self.cu))
            self._mf = bars.model_frame(bars.mid_m1(fr))
        return self._mf

    def grid(self):
        if self._grid is None:
            self._grid = forecasts.grid(self.mf(), self.events(), self.hol())
        return self._grid

    def store_map(self):
        return forecasts.store_map(forecasts.store_rows(self.root))


# ======================================================================== forecasts
def check_forecasts(ctx, out):
    rows = forecasts.store_rows(ctx.root)
    if not rows:
        return {"store_rows": 0}
    g = ctx.grid()
    gi = {(r.day, int(r.slot)): r for r in g.itertuples()}
    # R-V1-15/R-V1-17: a row was computed with the accepted extension lines first seen by its run time; rows whose
    # set differs from the full set are compared with a grid built from their own set
    ext = forecasts.ext_lines(ctx.root)
    gi_at = {}
    if ext:
        full = frozenset(ext)
        for r in rows:
            ct = parse_utc(r.get("computed_utc", "")) if r.get("computed_utc") else None
            mine = frozenset(e for e in ext if ct is not None and e[0] is not None and e[0] <= ct)
            if mine != full and mine not in gi_at:
                ev = forecasts.load_events(ctx.repo, ctx.root, at=ct)
                ga = forecasts.grid(ctx.mf(), ev, ctx.hol())
                gi_at[mine] = {(x.day, int(x.slot)): x for x in ga.itertuples()}
    n = 0
    for r in rows:
        key = (r["day"], int(r["slot"]))
        x = gi.get(key)
        if gi_at:
            ct = parse_utc(r.get("computed_utc", "")) if r.get("computed_utc") else None
            mine = frozenset(e for e in ext if ct is not None and e[0] is not None and e[0] <= ct)
            if mine in gi_at:
                x = gi_at[mine].get(key)
        subj = f"forecasts {r['day']}"
        if x is None:
            out.append(Finding("forecasts", subj, f"slot {r['slot']} is not in the recomputed grid"))
            continue
        n += 1
        if r["origin_model"] != x.origin_model or r["origin_utc"] != x.origin_utc_s:
            out.append(Finding("forecasts", subj, f"slot {r['slot']} origin {r['origin_model']} != {x.origin_model}"))
        for k in ("F_H1", "F_S", "price"):
            if not _num_eq(getattr(x, k), r[k]):
                out.append(Finding("forecasts", subj, f"slot {r['slot']} {k} {r[k]!r} != {getattr(x, k)!r}"))
        for k in ("nfp", "cpi", "fomc", "hol"):
            if int(r[k]) != int(getattr(x, k)):
                out.append(Finding("forecasts", subj, f"slot {r['slot']} flag {k} {r[k]} != {getattr(x, k)}"))
        if r.get("y_bp", "") != "":
            out.append(Finding("forecasts", subj, f"slot {r['slot']} y_bp is not empty"))
    have = {(r["day"], int(r["slot"])) for r in rows}
    due = g[g.origin_utc < ctx.cu]
    for x in due.itertuples():
        if (x.day, int(x.slot)) not in have:
            out.append(Finding("forecasts", f"forecasts {x.day}", f"slot {x.slot} final by the last run is not stored"))
    return {"store_rows": len(rows), "compared": n}


# ======================================================================== L1
def check_l1(ctx, out):
    start = ctx.lab1.start
    flags = load_json(ctx.root / "reports/system/l1_flags.json")
    h, rows = read_csv(ctx.root / "reports/system/l1_blocks.csv")
    if start is None:
        return {"blocks": 0}
    sm = ctx.store_map()
    trs = l1.trials(sm, ctx.mf(), start, ctx.cu)
    years = range(start.year, start.year + 3)
    _, models, _ = vendored.volmap()
    full = nyse_days(models, years, early=False)
    exp, green_ok = l1.blocks(trs, start, ctx.cu, full)
    got = [dict(zip(h, r)) for r in rows]
    if len(got) != len(exp):
        out.append(Finding("l1", "l1 blocks", f"{len(got)} block rows, {len(exp)} recomputed"))
    for e, g in zip(exp, got):
        subj = f"l1 block {e['block']}"
        for k in ("block", "start", "end", "complete", "n_origins", "expected", "n_green", "hits", "trials",
                  "green_ok_after"):
            gv = g.get(k, "")
            ev = e[k]
            if k == "complete":
                ok = _truthy(gv) == bool(ev)
            else:
                ok = str(gv) == str(ev)
            if not ok:
                out.append(Finding("l1", subj, f"{k} {gv!r} != {ev!r}"))
        if not _num_eq(e["hit_rate"], g.get("hit_rate", "")):
            out.append(Finding("l1", subj, f"hit_rate {g.get('hit_rate')!r} != {e['hit_rate']!r}"))
    if isinstance(flags, dict):
        if int(flags.get("l1_green_ok", -1)) != green_ok:
            out.append(Finding("l1", "l1 green_ok", f"l1_flags.json {flags.get('l1_green_ok')} != {green_ok}"))
    return {"blocks": len(exp), "green_ok": green_ok, "trials": len(trs)}


# ======================================================================== L3
def l3_chain(ctx):
    """Recomputed monthly rows (R-V1-26) through the month of the latest run."""
    start = ctx.lab1.start
    if start is None:
        return []
    core, _, _ = vendored.volmap()
    zs = load_json(ctx.root / "reports/system/L3_ZSTAR.json") or {}
    zstar = float(zs.get("zstar", zs.get("z_star", 7.75)))
    g = ctx.grid()
    gy = {(r.day, int(r.slot)): r.y for r in g.itertuples()}
    obs = l3.observations(ctx.store_map(), gy, start, ctx.cu, core.session_of_hour)
    rows, active = [], {}
    m = pd.Timestamp("2027-01-01")
    last = utc_to_model(ctx.t_last).normalize().replace(day=1)
    while m <= last:
        if model_to_utc(m) > ctx.cu:
            break
        rs = l3.update(obs, m, active, zstar)
        active = {r["bucket"]: bool(r["active_after"]) for r in rs}
        rows.extend(rs)
        m = m + pd.DateOffset(months=1)
    return rows


def check_l3(ctx, out):
    got = read_dicts(ctx.root / "reports/system/l3_updates.csv")
    exp = l3_chain(ctx)
    gi = {(r["month"][:7], r["bucket"]): r for r in got}
    ei = {(r["month"], r["bucket"]): r for r in exp}
    for k in sorted(set(gi) | set(ei)):
        subj = f"l3 {k[0]} {k[1]}"
        if k not in gi:
            out.append(Finding("l3", subj, "recomputed month row is not in l3_updates.csv"))
            continue
        if k not in ei:
            out.append(Finding("l3", subj, "l3_updates.csv row is not recomputed"))
            continue
        g, e = gi[k], ei[k]
        for f in ("n", "G"):
            if str(g.get(f)) != str(e[f]):
                out.append(Finding("l3", subj, f"{f} {g.get(f)!r} != {e[f]}"))
        for f in ("mean_r", "se", "z", "m"):
            if not _num_eq(e[f], g.get(f, "")):
                out.append(Finding("l3", subj, f"{f} {g.get(f)!r} != {e[f]!r}"))
        for f in ("eligible", "active_before", "active_after"):
            if _truthy(g.get(f, "")) != bool(e[f]):
                out.append(Finding("l3", subj, f"{f} {g.get(f)!r} != {e[f]}"))
    return {"months": len({r["month"] for r in exp}), "rows": len(exp)}


def l3_published(ctx):
    """(l3_asof, {bucket: (m, n)}) of the latest month (R-V1-27) from the recomputed chain."""
    exp = l3_chain(ctx)
    if not exp:
        return "-", {b: (1.0, 0) for b in BUCKETS}
    lastm = max(r["month"] for r in exp)
    return lastm + "-01", {r["bucket"]: (r["m"], r["n"]) for r in exp if r["month"] == lastm}


# ======================================================================== v1 lab
def _ledger(root, rel):
    return read_dicts(Path(root) / rel)


def _trade_list(rows, rid, first_day=None, upto=None, key_t=False):
    out = []
    for r in rows:
        if r["id"] != rid or r.get("status") != "final":
            continue
        if first_day is not None and pd.Timestamp(r["day"]) < first_day:
            continue
        rec = parse_utc(r["recorded_utc"])
        if upto is not None and rec > upto:
            continue
        out.append({"day": r["day"], "T": r["T"], "side": int(r["side"]), "R": float(r["R"]), "y": float(r["y"]),
                    "net": float(r["net_usd"]), "stress": float(r["net_stress_usd"]), "recorded": rec,
                    "y_text": r["y"]})
    return out


def check_v1_lab(ctx, out, cover=None):
    lab = ctx.lab1
    root = ctx.root
    L = "reports/system/lab/"
    lab_days = _ledger(root, L + "lab_days.csv")
    dec = _ledger(root, L + "decisions.csv")
    trd = _ledger(root, L + "trades.csv")
    tws = _ledger(root, L + "twins.csv")
    epr = _ledger(root, L + "eproc.csv")
    info = {"days": len(lab_days), "trades": 0}
    if not lab_days and not dec and not trd:
        return info
    sm = ctx.store_map()
    mf = ctx.mf()
    m15 = bars.lab_m15(mf)
    mc = bars.MinuteCache(mf)
    hol = ctx.hol()
    evd = set()
    for v in ctx.events().values():
        evd |= set(pd.DatetimeIndex(v).normalize())
    di = {(r["id"], r["day"]): r for r in dec}
    ti = {(r["id"], r["day"]): r for r in trd}
    wi = {(r["key"], r["day"]): r for r in tws}
    seen_d, seen_t, seen_w = set(), set(), set()
    code8 = _code_sha8(ctx, 1)
    lab_first = lab.lab_first_day()
    for ld in lab_days:
        day, s = ld["day"], parse_utc(ld["settled_utc"])
        d = pd.Timestamp(day)
        if lab.start is not None and d < lab.start:
            out.append(Finding("v1", f"v1 lab_days {day}", "settled day before START"))
        if lab_first is not None and d < lab_first:
            out.append(Finding("v1", f"v1 lab_days {day}", "settled day before the lab's first first_day"))
        if d.dayofweek >= 5:
            out.append(Finding("v1", f"v1 lab_days {day}", "settled day is not a model weekday"))
        if model_to_utc(d + pd.Timedelta(hours=23, minutes=30)) > store.complete_utc(ctx.v1, s):
            out.append(Finding("v1", f"v1 lab_days {day}", "settled before the day was complete"))
        db = lab_v1.DayBars(m15, d)
        dm = mc.day(d)
        keys_today = set()
        for rid in lab.order():
            rec = lab.records[rid]
            st = lab.state_at(rid, s)
            fd = lab.first_day(rid)
            if st not in ("PENDING", "RETIRED"):
                keys_today.add(lab_v1.twin_key(rec))     # R-V1-31: every key of the non-PENDING, non-RETIRED rules
            if st in ("PENDING", "RETIRED") or fd is None or d < fd:
                continue
            T = lab_v1.tmin(rec["spec"]["T"])
            dres = lab_v1.decide(rec, day, db, sm.get((day, T // 60 - 1)), hol, evd, fd)
            exp = lab_v1.fmt_decision(rid, day, dres, ld["settled_utc"])
            g = di.get((rid, day))
            seen_d.add((rid, day))
            subj = f"v1 decisions {rid} {day}"
            if g is None:
                out.append(Finding("v1", subj, "decision row missing"))
            else:
                for k in ("outcome", "side", "recorded_utc"):
                    if g[k] != exp[k]:
                        out.append(Finding("v1", subj, f"{k} {g[k]!r} != {exp[k]!r}"))
                for k, v in zip(("U", "feat1", "feat2", "F_RAW_H1", "F_RAW_S"),
                                (dres[2], (list(dres[3]) + [np.nan, np.nan])[0], (list(dres[3]) + [np.nan, np.nan])[1],
                                 dres[4], dres[5])):
                    if not _num_eq(v, g[k]):
                        out.append(Finding("v1", subj, f"{k} {g[k]!r} != {v!r}"))
            if dres[0] == "trigger":
                t = lab_v1.trade(rec, dm, dres[1], dres[2], dres[4], dres[5])
                seen_t.add((rid, day))
                g = ti.get((rid, day))
                subj = f"v1 trades {rid} {day}"
                info["trades"] += 1
                if g is None:
                    out.append(Finding("v1", subj, "trade row missing"))
                else:
                    _cmp_trade(out, "v1", subj, t, g, V1_TRADE_NUM, ("T", "side", "delay_min", "entry_model",
                                                                     "exit_model", "reason", "status"))
                    if g["recorded_utc"] != ld["settled_utc"]:
                        out.append(Finding("v1", subj, "recorded_utc is not the settlement run time"))
                    if code8 and g.get("code_sha8") != code8:
                        out.append(Finding("v1", subj, f"code_sha8 {g.get('code_sha8')!r} != {code8!r}"))
        # twins: every key of the active rules, on every settled day that is not an NYSE holiday (R-V1-31)
        for key in sorted(keys_today):
            Ts, hold, stop, delay = key.split("|")
            T = lab_v1.tmin(Ts)
            srow = sm.get((day, T // 60 - 1))
            F = (srow["F_H1"] if stop == "H10" else srow["F_S"]) if srow else float("nan")
            k = K10_H if stop == "H10" else K10_S
            if d in hol or not db.valid(T - 15) or not (math.isfinite(F) and F > 0):
                continue
            rt = lab_v1.twin(dm, T, int(delay), int(hold), k, F)
            if rt is None:
                continue
            seen_w.add((key, day))
            g = wi.get((key, day))
            subj = f"v1 twins {key} {day}"
            if g is None:
                out.append(Finding("v1", subj, "twin row missing"))
            elif not _num_eq(rt, g["R_twin"]):
                out.append(Finding("v1", subj, f"R_twin {g['R_twin']!r} != {rt!r}"))
    settled = {ld["day"] for ld in lab_days}
    for k in set(di) - seen_d:
        out.append(Finding("v1", f"v1 decisions {k[0]} {k[1]}", "decision row not recomputed (unexpected rule or day)"))
    for k in set(ti) - seen_t:
        out.append(Finding("v1", f"v1 trades {k[0]} {k[1]}", "trade row not recomputed"))
    for k in set(wi) - seen_w:
        if k[1] in settled or True:
            out.append(Finding("v1", f"v1 twins {k[0]} {k[1]}", "twin row not recomputed"))
    _check_eproc(ctx, out, lab, trd, epr, lab_days, version=1)
    return info


def _px_is_quote(t):
    """R-J5-3: P_x was read from a quote (a time exit, or a stop filled at a minute's open) by the judge's own
    recomputation of the exit; a stop reached inside the minute and a gap exit at X are computed prices."""
    return t["reason"] == "time" or (t["reason"] == "stop" and t["P_x"] != t["X"])


def _exact_eq(text, x):
    try:
        return text != "" and float(text) == x
    except ValueError:
        return False


def _cmp_trade(out, area, subj, t, g, numk, exactk):
    """Amendment B2 item 5, R-J5-1 .. R-J5-3: P_e and a quote-derived P_x exact; D, X, P_x at X and every derived
    number at rel <= 1e-9; categorical fields exact."""
    if t.get("status") != g.get("status"):
        out.append(Finding(area, subj, f"status {g.get('status')!r} != {t.get('status')!r}"))
        return
    for k in exactk:
        if k in t and str(t[k]) != g.get(k, ""):
            out.append(Finding(area, subj, f"{k} {g.get(k)!r} != {t[k]!r}"))
    if t.get("status") != "final":
        return
    for k in EXACT_PRICE:
        if not _exact_eq(g.get(k, ""), t[k]):
            out.append(Finding(area, subj, f"{k} {g.get(k)!r} != {t[k]!r} (prices exact)"))
    if _px_is_quote(t) and not _exact_eq(g.get("P_x", ""), t["P_x"]):
        out.append(Finding(area, subj, f"P_x {g.get('P_x')!r} != {t['P_x']!r} (prices exact)"))
    for k in numk:
        if k in t and not _num_eq(t[k], g.get(k, "")):
            out.append(Finding(area, subj, f"{k} {g.get(k)!r} != {t[k]!r}"))


def _code_sha8(ctx, version):
    rel = "analysis/system/FROZEN.sha256" if version == 1 else "analysis/system/lab_v2/FROZEN_V2.sha256"
    pin = ctx.pins.get("lab-v1-freeze" if version == 1 else "lab-v2-freeze")
    if pin:
        from . import gitio
        b = gitio.show_bytes(ctx.repo, pin, rel)
        if b is not None:
            from .common import sha256_bytes
            return sha256_bytes(b)[:8]
    p = ctx.repo / rel
    return sha256_file(p)[:8] if p.exists() else None


def _check_eproc(ctx, out, lab, trd, epr, lab_days, version):
    """eproc rows (E, K, E_star, state_after) recomputed from the ledger's final trades, in ledger order."""
    settled_at = {r["day"]: parse_utc(r["settled_utc"]) for r in lab_days}
    area = "v1" if version == 1 else "v2"
    by = {}
    for r in epr:
        by.setdefault(r["id"], []).append(r)
    for rid in lab.order():
        rec = lab.records[rid]
        fd = lab.first_day(rid)
        tl = _trade_list(trd, rid, fd)
        rows = by.get(rid, [])
        if len(rows) != len(tl):
            out.append(Finding(area, f"{area} eproc {rid}", f"{len(rows)} eproc rows for {len(tl)} final trades"))
        ys = [t["y"] for t in tl]
        Es = execution.e_path(ys)
        prom = lab.promoted_utc(rid)
        for i, (t, r) in enumerate(zip(tl, rows)):
            subj = f"{area} eproc {rid} {t['day']}"
            if str(r["trade_no"]) != str(i + 1) or r["day"] != t["day"] or r["y"] != t["y_text"]:
                out.append(Finding(area, subj, f"trade_no/day/y {r['trade_no']},{r['day']},{r['y']} do not follow "
                                                 "the trades ledger"))
                continue
            if version == 2 and r.get("T") != t["T"]:
                out.append(Finding(area, subj, f"T {r.get('T')!r} != {t['T']!r}"))
            if not _num_eq(Es[i], r["E"]):
                out.append(Finding(area, subj, f"E {r['E']!r} != {Es[i]!r}"))
            post = [x["y"] for x in tl[: i + 1] if prom is not None and x["recorded"] > prom]
            K = execution.k_value(post) if post else 1.0
            if not _num_eq(K, r["K"]):
                out.append(Finding(area, subj, f"K {r['K']!r} != {K!r}"))
            es = rec.get("E_star")
            if (es is None and r["E_star"] != "") or (es is not None and not _num_eq(float(es), r["E_star"], 0)):
                out.append(Finding(area, subj, f"E_star {r['E_star']!r} != {es!r}"))
            s = settled_at.get(t["day"])
            if s is not None:
                want = lab.state_at(rid, s)
                if r["state_after"] != want:
                    out.append(Finding(area, subj, f"state_after {r['state_after']!r} != {want!r}"))


# ======================================================================== v2 lab
class V2Inputs:
    """Seed bars per settlement run (data as of that run: lookback ok rows fetched by then, v1 days before its
    complete_utc)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.cache = {}
        self._full = None

    def frame_for(self, s):
        lbkey = tuple(sorted(k for k, r in self.ctx.lb.status(s).items() if r["status"] == "ok"))
        cu = store.complete_utc(self.ctx.v1, s)
        if lbkey not in self.cache:
            plan = store.v2_plan(self.ctx.lb, self.ctx.v1, self.ctx.t_last if self.ctx.t_last > s else s)
            plan = [p for p in plan if p[0] is not self.ctx.lb or (p[1], p[2]) in set(lbkey)]
            self.cache[lbkey] = bars.model_frame(bars.mid_m1(store.load_v2_frames(plan)))
        mf = self.cache[lbkey]
        return mf[mf["_utc"].values < np.datetime64(cu.tz_convert("UTC").tz_localize(None))], cu


def _rows_at(store_rows, s):
    """The forecast-store rows a run at time s read: computed_utc <= s (R-V2-27, R-C5)."""
    out = []
    for r in store_rows:
        try:
            t = parse_utc(r.get("computed_utc", ""))
        except (ValueError, TypeError):
            t = None
        if t is not None and t <= s:
            out.append(r)
    return out


def store_map_at(store_rows, s):
    return forecasts.store_map(_rows_at(store_rows, s))


def store_covers(keys, d):
    """R-V2-27 (b): the store keys {(day, slot)} cover model day d: all 23 slot rows of d, or no row of d at all while
    a row of a later model day exists (a day v1 passed over)."""
    if all((d, sl) in keys for sl in range(23)):
        return True
    return not any(k[0] == d for k in keys) and any(k[0] > d for k in keys)


def _check_v2_settlement(ctx, out, lab_days, store_rows):
    """R-V2-27: every settled day d (settled_utc s) was covered by v1's forecast store as the run at s read it, every
    earlier model weekday from the lab's first first_day was settled at or before s (the scan never skips a day), and
    a run settled at most 10 days."""
    lab = ctx.lab2
    lab_first = lab.lab_first_day()
    settled_at = {}
    per_run = {}
    for ld in lab_days:
        settled_at.setdefault(ld["day"], parse_utc(ld["settled_utc"]))
        per_run[ld["settled_utc"]] = per_run.get(ld["settled_utc"], 0) + 1
    for s_text, n in per_run.items():
        if n > 10:
            out.append(Finding("v2", f"v2 lab_days {s_text}", f"{n} days settled by one run (at most 10)"))
    keys_cache = {}
    for ld in lab_days:
        day, s_text = ld["day"], ld["settled_utc"]
        s = parse_utc(s_text)
        if s_text not in keys_cache:
            keys_cache[s_text] = {(r["day"], int(r["slot"])) for r in _rows_at(store_rows, s)}
        if not store_covers(keys_cache[s_text], day):
            out.append(Finding("v2", f"v2 lab_days {day}", "settled before v1's forecast store held all 23 rows of "
                                                         "the day with computed_utc <= settled_utc (R-V2-27)"))
        if pd.Timestamp(day).dayofweek >= 5:
            out.append(Finding("v2", f"v2 lab_days {day}", "settled day is not a model weekday"))
    if lab_first is None or not settled_at:
        return
    # no gap and no overtaking: along the model weekdays from the lab's first first_day, each is settled, and never
    # before an earlier one
    latest = max(settled_at)
    run_max = None
    for w in pd.bdate_range(lab_first, latest):
        ws = w.strftime("%Y-%m-%d")
        if ws not in settled_at:
            nxt = min(d for d in settled_at if d > ws)
            out.append(Finding("v2", f"v2 lab_days {nxt}", f"settled while the earlier weekday {ws} was not settled "
                                                         "(R-V2-27: the scan stops at the first day it cannot "
                                                         "settle)"))
            return
        if run_max is not None and settled_at[ws] < run_max:
            out.append(Finding("v2", f"v2 lab_days {ws}", "settled before an earlier weekday was settled (R-V2-27)"))
        run_max = settled_at[ws] if run_max is None else max(run_max, settled_at[ws])


def check_v2_lab(ctx, out, cover_days=None):
    """cover_days: set of days to recompute signals and trades for (None = every settled day)."""
    lab = ctx.lab2
    root = ctx.root
    L = "reports/system/lab_v2/"
    lab_days = _ledger(root, L + "lab_days.csv")
    aud = _ledger(root, L + "audit.csv")
    dec = _ledger(root, L + "decisions.csv")
    trd = _ledger(root, L + "trades.csv")
    tws = _ledger(root, L + "twins.csv")
    epr = _ledger(root, L + "eproc.csv")
    info = {"days": len(lab_days), "checked_days": [], "trades": 0}
    _check_v2_registry(ctx, out)
    if not lab_days and not dec and not trd and not aud:
        _check_eproc(ctx, out, lab, trd, epr, lab_days, version=2)
        return info
    store_rows = forecasts.store_rows(ctx.root)
    _check_v2_settlement(ctx, out, lab_days, store_rows)
    hol = ctx.hol()
    ai = {(r["day"], r["id"]): r for r in aud if r["result"] == "ok"}
    di = {}
    for r in dec:
        di.setdefault((r["id"], r["day"]), []).append(r)
    ti = {(r["id"], r["day"], r["T"]): r for r in trd}
    wi = {(r["id"], r["day"], r["T"]): r for r in tws}
    code8 = _code_sha8(ctx, 2)
    inputs = V2Inputs(ctx)
    lab_first = lab.lab_first_day()
    bydate = {}
    for ld in lab_days:
        bydate.setdefault(ld["settled_utc"], []).append(ld["day"])
    for s_text, days in bydate.items():
        s = parse_utc(s_text)
        todo = [d for d in days if cover_days is None or d in cover_days]
        for day in days:
            d = pd.Timestamp(day)
            if lab.start is not None and d < lab.start:
                out.append(Finding("v2", f"v2 lab_days {day}", "settled day before the v2 START"))
            if lab_first is not None and d < lab_first:
                out.append(Finding("v2", f"v2 lab_days {day}", "settled day before the lab's first first_day"))
        if not todo:
            continue
        sm = store_map_at(store_rows, s)          # R-V2-27: the run at s read the rows with computed_utc <= s
        mf, cu = inputs.frame_for(s)
        inp = bars.seed_input(mf)
        mc = bars.MinuteCache(mf)
        complete = store.lookback_complete(ctx.lb, s)
        runs = {}
        for day in todo:
            d = pd.Timestamp(day)
            info["checked_days"].append(day)
            if model_to_utc(d + pd.Timedelta(hours=23, minutes=30)) > cu:
                out.append(Finding("v2", f"v2 lab_days {day}", "settled before the day was complete"))
            for sid in lab.order():
                st = lab.state_at(sid, s)
                fd = lab.first_day(sid)
                active = st not in ("PENDING", "RETIRED") and fd is not None and fd <= d
                if sid == "S3" and not complete:
                    active = False
                subj = f"v2 audit {sid} {day}"
                if not active:
                    if (day, sid) in ai:
                        out.append(Finding("v2", subj, "audit row for a seed that is not active that day"))
                    if di.get((sid, day)):
                        out.append(Finding("v2", f"v2 decisions {sid} {day}", "decisions for an inactive seed"))
                    continue
                if sid not in runs:
                    runs[sid] = lab_v2.SeedRun(sid, inp)
                sr = runs[sid]
                hm = lab_v2.hold_minutes(sid)
                a, onl = lab_v2.audit_day(sr, day, hm)
                g = ai.get((day, sid))
                if g is None:
                    out.append(Finding("v2", subj, "audit row missing"))
                else:
                    for k, v in a.items():
                        if str(v) != g[k]:
                            out.append(Finding("v2", subj, f"{k} {g[k]!r} != {v!r}"))
                    if g["recorded_utc"] != s_text or g["tf"] != sr.mod.TF:
                        out.append(Finding("v2", subj, "tf or recorded_utc differs"))
                rows = lab_v2.decisions_day(sr, day, onl, hm, hol,
                                            lambda sl, _d=day, _sm=sm: _sm.get((_d, sl), {}).get("F_S", float("nan")))
                got = di.get((sid, day), [])
                subj = f"v2 decisions {sid} {day}"
                if len(got) != len(rows):
                    out.append(Finding("v2", subj, f"{len(got)} decision rows, {len(rows)} recomputed"))
                for e, g in zip(rows, got):
                    for k, v in (("bar_start", e["bar_start"]), ("T", hhmm(e["T"])), ("signal", str(e["signal"])),
                                 ("outcome", e["outcome"]), ("entry_model", e["entry_model"]),
                                 ("recorded_utc", s_text)):
                        if g[k] != v:
                            out.append(Finding("v2", subj, f"{e['bar_start']} {k} {g[k]!r} != {v!r}"))
                    if not _num_eq(e["F_RAW_S"], g["F_RAW_S"]):
                        out.append(Finding("v2", subj, f"{e['bar_start']} F_RAW_S {g['F_RAW_S']!r} != {e['F_RAW_S']!r}"))
                for e in rows:
                    if e["outcome"] != "trade":
                        continue
                    dm = mc.day(day)
                    t = lab_v2.trade(dm, e["signal"], e["T"], hm, e["F_RAW_S"])
                    tk = (sid, day, t["T"])
                    g = ti.get(tk)
                    subj = f"v2 trades {sid} {day}"
                    info["trades"] += 1
                    if g is None:
                        out.append(Finding("v2", subj, f"trade at {t['T']} missing"))
                        continue
                    _cmp_trade(out, "v2", subj, t, g, V2_TRADE_NUM, ("T", "side", "entry_model", "exit_model",
                                                                     "reason", "status"))
                    if g["recorded_utc"] != s_text:
                        out.append(Finding("v2", subj, "recorded_utc is not the settlement run time"))
                    if code8 and g.get("code_sha8") != code8:
                        out.append(Finding("v2", subj, f"code_sha8 {g.get('code_sha8')!r} != {code8!r}"))
                    if t["status"] != "final":
                        if wi.get(tk):
                            out.append(Finding("v2", f"v2 twins {sid} {day}", "twin for a no_quote trade"))
                        continue
                    w = lab_v2.twin(dm, e["T"], hm, t["D"])
                    gw = wi.get(tk)
                    subj = f"v2 twins {sid} {day}"
                    if gw is None:
                        out.append(Finding("v2", subj, f"twin at {t['T']} missing"))
                        continue
                    if w.get("status") != gw.get("status"):
                        out.append(Finding("v2", subj, f"status {gw.get('status')!r} != {w.get('status')!r}"))
                        continue
                    if w["status"] == "final":
                        for k in ("entry_model", "exit_model", "reason"):
                            if gw[k] != w[k]:
                                out.append(Finding("v2", subj, f"{k} {gw[k]!r} != {w[k]!r}"))
                        # R-J5-1: the twin's P_e (a mid of exact quotes) and a quote-derived P_x are exact
                        exact = ["P_e"] + (["P_x"] if _px_is_quote(w) else [])
                        for k in exact:
                            if not _exact_eq(gw.get(k, ""), w[k]):
                                out.append(Finding("v2", subj, f"{k} {gw.get(k)!r} != {w[k]!r} (prices exact)"))
                        for k in ("D", "X", "P_x", "R_twin"):
                            if k not in exact and not _num_eq(w[k], gw[k]):
                                out.append(Finding("v2", subj, f"{k} {gw[k]!r} != {w[k]!r}"))
    # rows of days that are not settled (only FAIL audit rows may be, R-V2-35)
    settled = {ld["day"] for ld in lab_days}
    for name, rows in (("audit", [r for r in aud if r["result"] == "ok"]), ("decisions", dec), ("trades", trd),
                       ("twins", tws), ("eproc", epr)):
        for r in rows:
            if r["day"] not in settled:
                out.append(Finding("v2", f"v2 {name} {r['day']}", "row of a day that is not in lab_days.csv"))
    _check_eproc(ctx, out, lab, trd, epr, lab_days, version=2)
    return info


def _check_v2_registry(ctx, out):
    for sid, rec in ctx.lab2.records.items():
        if sid not in vendored.SEED_FILES:
            out.append(Finding("registry", f"v2 registry {sid}", "not one of S2-S5"))
            continue
        if rec.get("seed_sha256") != vendored.seed_sha(sid) or rec.get("harness_sha256") != vendored.harness_sha():
            out.append(Finding("vendor", f"v2 registry {sid}", "seed or harness sha256 differs from the judge's vendor"))
        if not registry.e_star_ok(rec, 2):
            out.append(Finding("registry", f"v2 registry {sid}", "E_star does not follow alpha, gamma and D"))
    gs = [rec.get("gamma_exact") for rec in ctx.lab2.records.values()]
    if ctx.lab2.records:
        from fractions import Fraction
        if sum(Fraction(g) for g in gs if g) != 1:
            out.append(Finding("registry", "v2 registry gamma", "the gammas do not sum to 1"))


def check_v1_registry(ctx, out):
    for rid, rec in ctx.lab1.records.items():
        if rec.get("spec_sha256") != registry.spec_sha(rec.get("spec")):
            out.append(Finding("registry", f"v1 registry {rid}", "spec_sha256 does not match the spec"))
        if not registry.e_star_ok(rec, 1):
            out.append(Finding("registry", f"v1 registry {rid}", "E_star does not follow alpha, gamma and D"))


# ======================================================================== states (events)
def check_states(ctx, out, version):
    lab = ctx.lab1 if version == 1 else ctx.lab2
    L = "reports/system/lab/" if version == 1 else "reports/system/lab_v2/"
    trd = _ledger(ctx.root, L + "trades.csv")
    tws = _ledger(ctx.root, L + "twins.csv")
    lab_days = _ledger(ctx.root, L + "lab_days.csv")
    area = f"v{version}"
    runs = sorted({parse_utc(r["settled_utc"]) for r in lab_days} |
                  {e["_utc"] for e in lab.events if e["event"] != "REGISTERED" and e["_utc"] is not None})
    manual = ("judge_violation", "bug", "manual")
    for t in runs:
        last_day = None
        for r in lab_days:
            if parse_utc(r["settled_utc"]) <= t:
                last_day = r["day"]
        ev_t = [e for e in lab.events if e["_utc"] == t and e["event"] != "REGISTERED"]
        for rid in lab.order():
            rec = lab.records[rid]
            st0 = lab.state_at(rid, t)
            fd = lab.first_day(rid)
            tl = _trade_list(trd, rid, fd, upto=t)
            prom = lab.promoted_utc(rid, t)
            st = states.rule_stats(tl, prom)
            mu = _mu(version, rec, tl, tws, fd, upto=t)
            st["p4sum"] = sum(x["R"] - x["side"] * mu for x in tl) if mu is not None else float("nan")
            dem = next((e["_utc"] for e in lab.events if e["id"] == rid and e["event"] == "DEMOTED"
                        and e["_utc"] < t), None)
            running = not any(e["id"] == rid and e["event"] == "SUSPENDED" and "paused" in e["reason"] for e in ev_t)
            exp = states.expected_transition(rec, st0, st, mu, t, lab.registered_utc(rid), dem, last_day, running,
                                             version)
            got = [e for e in ev_t if e["id"] == rid]
            got_auto = [e for e in got if not any(m in e["reason"] for m in manual)]
            subj = f"{area} states {rid} {iso_s(t)}"
            if exp is None and got_auto:
                for e in got_auto:
                    out.append(Finding("states", subj, f"{e['event']} ({e['reason']}) is not justified at this run"))
            elif exp is not None:
                if not got_auto:
                    if exp[0] in ("PROMOTED", "DEMOTED") or (exp[0] == "RETIRED" and exp[1] != "age"):
                        out.append(Finding("states", subj, f"{exp[0]} ({exp[1]}) expected at this run, not recorded"))
                elif got_auto[0]["event"] != exp[0]:
                    out.append(Finding("states", subj, f"{got_auto[0]['event']} recorded, {exp[0]} expected"))
                elif exp[0] in ("PROMOTED", "DEMOTED", "RETIRED") and got_auto[0]["n"] != "":
                    if str(st["n"]) != got_auto[0]["n"] or not _num_eq(st["E"], got_auto[0]["E"]):
                        out.append(Finding("states", subj, "n or E of the event differ from the ledger"))


def _mu(version, rec, tl, tws, fd, upto=None):
    """P4 reference: v1 mu_l over the rule's twin key (R-V1-31), v2 mu-bar over its final twins (R-V2-19)."""
    if version == 1:
        key = lab_v1.twin_key(rec)
        days = int(rec["spec"]["days"])
        T = lab_v1.tmin(rec["spec"]["T"])
        hold = int(rec["spec"]["hold"])
        vals = []
        for r in tws:
            if r["key"] != key or fd is None or pd.Timestamp(r["day"]) < fd:
                continue
            if upto is not None and parse_utc(r["recorded_utc"]) > upto:
                continue
            d = pd.Timestamp(r["day"])
            if not (days >> d.dayofweek) & 1 or (d.dayofweek == 4 and T + 15 * hold > 1365):
                continue
            vals.append(float(r["R_twin"]))
        return float(np.mean(vals)) if vals else None
    keys = {(t["day"], t["T"]) for t in tl}
    vals = [float(r["R_twin"]) for r in tws if r["id"] == rec["id"] and r.get("status") == "final"
            and (r["day"], r["T"]) in keys]
    return float(np.mean(vals)) if vals else None


# ======================================================================== summary.json (v2) and the status file
def v1_snapshot(ctx, t):
    """The v1 lab numbers a run at time t publishes (R-V1-41)."""
    lab = ctx.lab1
    trd = _ledger(ctx.root, "reports/system/lab/trades.csv")
    lab_days = _ledger(ctx.root, "reports/system/lab/lab_days.csv")
    lf = lab.lab_first_day()
    days = sum(1 for r in lab_days if parse_utc(r["settled_utc"]) <= t and lf is not None
               and pd.Timestamp(r["day"]) >= lf)
    n_paper = n_live = 0
    best = 0.0
    live = []
    for rid in lab.order():
        rec = lab.records[rid]
        st = lab.state_at(rid, t, inclusive=True)
        tl = _trade_list(trd, rid, lab.first_day(rid), upto=t)
        if st == "PAPER" and rec.get("promotable"):
            n_paper += 1
            E = execution.e_value([x["y"] for x in tl]) if tl else 1.0
            best = max(best, E / float(rec["E_star"]))
        if st == "LIVE":
            n_live += 1
            prom = lab.promoted_utc(rid, t)
            live.append((rec.get("title_ar", ""), sum(1 for x in tl if prom is not None and x["recorded"] > prom)))
    return {"days": days, "n_paper": n_paper, "n_live": n_live, "best": best, "live": live}


def v2_snapshot(ctx, t):
    lab = ctx.lab2
    if not lab.records:
        return None
    trd = _ledger(ctx.root, "reports/system/lab_v2/trades.csv")
    lab_days = _ledger(ctx.root, "reports/system/lab_v2/lab_days.csv")
    lf = lab.lab_first_day()
    days = sum(1 for r in lab_days if parse_utc(r["settled_utc"]) <= t and lf is not None
               and pd.Timestamp(r["day"]) >= lf)
    n_paper = n_live = 0
    best = 0.0
    for sid in lab.order():
        rec = lab.records[sid]
        st = lab.state_at(sid, t, inclusive=True)
        if st == "PAPER":
            n_paper += 1
            tl = _trade_list(trd, sid, lab.first_day(sid), upto=t)
            E = execution.e_value([x["y"] for x in tl]) if tl else 1.0
            best = max(best, E / float(rec["E_star"]))
        if st == "LIVE":
            n_live += 1
    return {"days": days, "n_paper": n_paper, "n_live": n_live, "best": best}


def check_summary(ctx, out):
    sj = load_json(ctx.root / "reports/system/lab_v2/summary.json")
    if not isinstance(sj, dict):
        return {}
    t = parse_utc(sj.get("asof_utc", ""))
    if t is None:
        out.append(Finding("v2", "v2 summary", "summary.json has no asof_utc"))
        return {}
    snap = v2_snapshot(ctx, t)
    if snap is None:
        return {}
    lab = ctx.lab2
    for k, v in (("days", snap["days"]), ("n_paper", snap["n_paper"]), ("n_live", snap["n_live"])):
        if sj.get(k) != v:
            out.append(Finding("v2", f"v2 summary {day_str(t.tz_localize(None))}", f"{k} {sj.get(k)!r} != {v!r}"))
    if not rel_equal(float(sj.get("best_progress", float("nan"))), snap["best"], TOL):
        out.append(Finding("v2", f"v2 summary {day_str(t.tz_localize(None))}",
                           f"best_progress {sj.get('best_progress')!r} != {snap['best']!r}"))
    lf = lab.lab_first_day()
    if (sj.get("first_day") or None) != (day_str(lf) if lf is not None else None):
        out.append(Finding("v2", "v2 summary first_day", f"first_day {sj.get('first_day')!r} != {lf}"))
    if lab.start is not None and sj.get("start") != day_str(lab.start):
        out.append(Finding("v2", "v2 summary start", f"start {sj.get('start')!r} != {day_str(lab.start)}"))
    trd = _ledger(ctx.root, "reports/system/lab_v2/trades.csv")
    tws = _ledger(ctx.root, "reports/system/lab_v2/twins.csv")
    for r in sj.get("rules", []):
        sid = r.get("id")
        if sid not in lab.records:
            out.append(Finding("v2", f"v2 summary {sid}", "rule not in the registry"))
            continue
        fd = lab.first_day(sid)
        subj = f"v2 summary {sid}"
        st = lab.state_at(sid, t, inclusive=True)
        if r.get("state") != st:
            out.append(Finding("v2", subj, f"state {r.get('state')!r} != {st!r}"))
        if (r.get("first_day") or None) != (day_str(fd) if fd is not None else None):
            out.append(Finding("v2", subj, f"first_day {r.get('first_day')!r} != {fd}"))
        tl = _trade_list(trd, sid, fd, upto=t)
        if lab.promoted_utc(sid, t) is None:
            if r.get("n") != len(tl):
                out.append(Finding("v2", subj, f"n {r.get('n')!r} != {len(tl)}"))
            E = execution.e_value([x["y"] for x in tl]) if tl else 1.0
            if r.get("E") is None or not rel_equal(float(r["E"]), E, TOL):
                out.append(Finding("v2", subj, f"E {r.get('E')!r} != {E!r}"))
            ns = sum(x["net"] for x in tl)
            if tl and not rel_equal(float(r.get("net_sum", float("nan"))), ns, TOL):
                out.append(Finding("v2", subj, f"net_sum {r.get('net_sum')!r} != {ns!r}"))
            mu = _mu(2, lab.records[sid], tl, tws, fd)
            if mu is not None and (r.get("mu_bar") is None or not rel_equal(float(r["mu_bar"]), mu, TOL)):
                out.append(Finding("v2", subj, f"mu_bar {r.get('mu_bar')!r} != {mu!r}"))
        if sid == "S3":
            waits = not store.lookback_complete(ctx.lb, t)
            if r.get("waits_for_lookback") is not None and bool(r["waits_for_lookback"]) != waits:
                out.append(Finding("v2", subj, f"waits_for_lookback {r.get('waits_for_lookback')!r} != {waits}"))
            if r.get("flow_values_before_today") is not None:
                mf, _ = V2Inputs(ctx).frame_for(t)
                n = lab_v2.s3_flow_values(bars.seed_bars(bars.seed_input(mf), 15), utc_to_model(t).normalize())
                if r["flow_values_before_today"] != n:
                    out.append(Finding("v2", subj, f"flow_values_before_today {r['flow_values_before_today']!r} "
                                                   f"!= {n}"))
                if r.get("warmup") is not None and bool(r["warmup"]) != (n < 250 or waits):
                    out.append(Finding("v2", subj, f"warmup {r.get('warmup')!r} != {n < 250 or waits}"))
    c1 = sj.get("c1")
    if isinstance(c1, dict):
        tr1 = _ledger(ctx.root, "reports/system/lab/trades.csv")
        tl = [x for x in _trade_list(tr1, "C1", lf, upto=t)] if lf is not None else []
        if c1.get("n") != len(tl):
            out.append(Finding("v2", "v2 summary c1", f"n {c1.get('n')!r} != {len(tl)}"))
        E = execution.e_value([x["y"] for x in tl]) if tl else 1.0
        if not rel_equal(float(c1.get("E", float("nan"))), E, TOL):
            out.append(Finding("v2", "v2 summary c1", f"E {c1.get('E')!r} != {E!r}"))
    return {"asof": sj.get("asof_utc")}


def expected_status(ctx, t, prev_v2=None):
    """The lines a v1 run at time t publishes (R-V1-41, R-V1-60), from the judge's own recomputation."""
    lines = [("version", "1"), ("asof_utc", iso_s(t)), ("l1_green_ok", None), ("l1_asof", day_str(t.tz_localize(None)))]
    asof3, mult = l3_published(ctx)
    lines.append(("l3_asof", asof3))
    for b in BUCKETS:
        m, n = mult.get(b, (1.0, 0))
        lines.append((f"l3_m_{b}", "%.4f" % m))
        lines.append((f"l3_n_{b}", str(int(n))))
    snap = v1_snapshot(ctx, t)
    lines.append(("lab_state", None))
    lines += [("lab_days", str(snap["days"])), ("lab_n_paper", str(snap["n_paper"])),
              ("lab_n_live", str(snap["n_live"])), ("lab_best_progress", "%.3f" % snap["best"])]
    for i, (title, npost) in enumerate(snap["live"], 1):
        lines += [(f"lab_live_{i}_title_ar", title), (f"lab_live_{i}_npost", str(npost))]
    if prev_v2 is not None:
        lines += [("lab2_state", None), ("lab2_days", str(prev_v2["days"])), ("lab2_n_paper", str(prev_v2["n_paper"])),
                  ("lab2_best_progress", "%.3f" % prev_v2["best"])]
    return lines


def previous_v2_run(ctx, t):
    """The latest lab v2 run strictly before t (its summary is what v1 publishes at t, R-V1-60)."""
    lab = ctx.lab2
    times = {e["_utc"] for e in lab.events if e["_utc"] is not None}
    times |= {parse_utc(r["settled_utc"]) for r in _ledger(ctx.root, "reports/system/lab_v2/lab_days.csv")}
    sj = load_json(ctx.root / "reports/system/lab_v2/summary.json")
    if isinstance(sj, dict) and sj.get("asof_utc"):
        times.add(parse_utc(sj["asof_utc"]))
    times = sorted(x for x in times if x is not None and x < t)
    return times[-1] if times else None


def _summary_in_history(ctx, pv):
    """The committed reports/system/lab_v2/summary.json whose asof_utc is pv, from git history (None without it)."""
    from . import gitio
    rel = "reports/system/lab_v2/summary.json"
    if pv is None or not gitio.is_repo(ctx.repo) or ctx.repo.resolve() != ctx.root.resolve():
        return None
    for sha, _, _ in reversed(gitio.commits_touching(ctx.repo, rel)):
        b = gitio.show_bytes(str(ctx.repo), sha, rel)
        try:
            j = json.loads(b.decode("utf-8")) if b else None
        except ValueError:
            continue
        if isinstance(j, dict) and j.get("asof_utc") == iso_s(pv):
            return j
    return None


def check_status_file(ctx, out, l1_green_ok, status_md_halted=None):
    raw = ctx.status_raw
    if raw is None:
        return {}
    from . import status as stp
    parsed, probs = stp.parse(raw)
    for p in probs:
        out.append(Finding("status", "status format", p))
    if parsed is None or ctx.asof is None:
        return {}
    t = ctx.asof
    pv = previous_v2_run(ctx, t)
    gd0 = dict(parsed["lines"])
    prev = v2_snapshot(ctx, pv) if pv is not None and "lab2_state" in gd0 else None
    hist = _summary_in_history(ctx, pv) if prev is not None else None
    if hist is not None:
        # the summary.json v1 read (R-V1-60): the committed version whose asof_utc is the previous v2 run
        want = {"lab2_state": hist.get("state"), "lab2_days": str(hist.get("days")),
                "lab2_n_paper": str(hist.get("n_paper")),
                "lab2_best_progress": "%.3f" % float(hist.get("best_progress", float("nan")))}
        for k, v in want.items():
            if gd0.get(k) != v:
                out.append(Finding("status", f"status {day_str(t.tz_localize(None))}",
                                   f"{k} {gd0.get(k)!r} != {v!r} (summary.json of {iso_s(pv)})"))
    exp = expected_status(ctx, t, prev)
    subj = f"status {day_str(t.tz_localize(None))}"
    got_keys = [k for k, _ in parsed["lines"]]
    exp_keys = [k for k, _ in exp]
    if "lab2_state" in got_keys and prev is None:
        exp_keys = exp_keys + ["lab2_state", "lab2_days", "lab2_n_paper", "lab2_best_progress"]
    if got_keys != exp_keys:
        out.append(Finding("status", subj, f"keys {got_keys} != {exp_keys}"))
    gd = dict(parsed["lines"])
    for k, v in exp:
        if k == "l1_green_ok":
            v = str(l1_green_ok) if l1_green_ok is not None else None
        if k == "lab_state":
            v = None if status_md_halted is None else ("PAUSED" if status_md_halted else "RUNNING")
            if gd.get(k) not in ("RUNNING", "PAUSED"):
                out.append(Finding("status", subj, f"lab_state {gd.get(k)!r}"))
        if k == "lab2_state" and gd.get(k) not in ("RUNNING", "PAUSED"):
            out.append(Finding("status", subj, f"lab2_state {gd.get(k)!r}"))
        if v is not None and gd.get(k) != v:
            out.append(Finding("status", subj, f"{k} {gd.get(k)!r} != {v!r}"))
    return {"asof": iso_s(t), "lines": len(parsed["lines"])}


# ======================================================================== vendor cross-check
def check_vendor(ctx, out):
    """The judge's vendored volmap files against the system's pinned v1 manifest entries, by sha256 only."""
    probs = vendored.check()
    for p in probs:
        out.append(Finding("vendor", "judge vendor", p))
    for p in forecasts.system_calendar_problems(ctx.repo):
        out.append(Finding("vendor", "system calendars", p))
    from . import manifests
    man = manifests.read_manifest(ctx.repo, ctx.pins.get("lab-v1-freeze"), "analysis/system/FROZEN.sha256")
    if not man:
        return
    mine = vendored.sums()
    for suffix in ("volmap/core.py", "volmap/models.py", "discovery_params.json"):
        ent = [(p, h) for p, h in man.items() if p.endswith(suffix)]
        want = next((h for p, h in mine.items() if p.endswith(suffix)), None)
        if ent and want and ent[0][1] != want:
            out.append(Finding("vendor", f"vendor {suffix}", "the system's frozen copy differs from the judge's"))


# ======================================================================== all of J5
def run(ctx, v2_cover=None):
    out = []
    info = {}
    check_vendor(ctx, out)
    info["forecasts"] = check_forecasts(ctx, out)
    info["l1"] = check_l1(ctx, out)
    info["l3"] = check_l3(ctx, out)
    check_v1_registry(ctx, out)
    info["v1"] = check_v1_lab(ctx, out)
    info["v2"] = check_v2_lab(ctx, out, v2_cover)
    check_states(ctx, out, 1)
    check_states(ctx, out, 2)
    info["summary"] = check_summary(ctx, out)
    halted = None
    sm = ctx.root / "reports/system/STATUS.md"
    if sm.exists():
        txt = sm.read_text(encoding="utf-8")
        if ctx.asof is not None and f"Updated {iso_s(ctx.asof)}" in txt:
            halted = "**HALTED**" in txt
    info["status"] = check_status_file(ctx, out, info["l1"].get("green_ok"), halted)
    return out, info
