"""The pre-START synthetic simulation that sets L3's z* (SYSTEM_V1_PREREG.md §4 and §9). Synthetic data only.

Null: the forecast is calibrated (E[r] = 1 in every bucket). ln r = −σ²/2 + σ·√ICC·w_week + σ·√(1 − ICC)·ε, where
w is a unit-variance AR(1) series over ISO weeks with coefficient ρ and ε is i.i.d. N(0, 1), so E[r] = 1 exactly.
σ per bucket: 0.424 for the normal session buckets (√(2 × 0.0899), the T2 validation QLIKE, L3 draft §8), 0.55 for
REOPEN (the larger of the draft's two values) and 0.60 for the event buckets.
Calendar: model-clock weekdays from START = 2026-11-02 to 2028-01-31 without 2026-12-25 and 2027-01-01 (no gold
trading); 23 hours a day; each hour in its system_common.bucket from the official NFP/CPI/FOMC times of the shared
calendars (plus 2028-01: NFP 01-07, CPI 01-12, FOMC 01-26 at the usual times), so every bucket has its realistic count.
Updates: the first day of each month 2027-01 .. 2028-02 (14), each over the observations before it, with exactly the
estimator of l3.py (m, ISO-week cluster SE or sd/√n, eligibility G >= 8 / n >= 6).
Cells: ρ in {0, 0.3, 0.6} × ICC in {0.05, 0.15, 0.30} × week effect shared by all buckets or independent per bucket.
P(any bucket ever active over the 14 updates) = P(max over eligible (update, bucket) of |z| >= z*), since a bucket
turns active the first time |z| >= z* while eligible.
z* = 3.5 unless the worst cell has P > 10%; then z* rises in 0.25 steps until it does not.

Usage: uv run --frozen python -I analysis/system/l3_sim.py [--paths 20000] [--out reports/system/L3_ZSTAR.json]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import syspath  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import forecasts  # noqa: E402
import l3  # noqa: E402
import system_common as sc  # noqa: E402

SEED = 20261017
START = pd.Timestamp("2026-11-02")
END = pd.Timestamp("2028-01-31")
UPDATES = [m.strftime("%Y-%m") for m in pd.date_range("2027-01-01", "2028-02-01", freq="MS")]
CLOSED = {pd.Timestamp("2026-12-25"), pd.Timestamp("2027-01-01")}
SIGMA = {"N_ASIA": 0.424, "N_LONDON": 0.424, "N_NY": 0.424, "REOPEN": 0.55, "CPI": 0.60, "FOMC": 0.60, "NFP": 0.60}
RHOS = (0.0, 0.3, 0.6)
ICCS = (0.05, 0.15, 0.30)
DEPS = ("shared", "independent")
Z0, ZSTEP, ZMAX = 3.5, 0.25, 12.0
LIMIT = 0.10
EXTRA_2028 = {"NFP": "2028-01-07 13:30", "CPI": "2028-01-12 13:30", "FOMC": "2028-01-26 19:00"}  # UTC


def calendar():
    """Observation layout: one row per (day, slot) with its bucket, ISO-week index and month index."""
    ev = forecasts.load_events()
    for k, t in EXTRA_2028.items():
        ev[k] = ev[k].append(forecasts.bars.to_model(pd.DatetimeIndex([pd.Timestamp(t, tz="UTC")])))
    flags = {k: {(t.normalize(), t.hour - 1) for t in ev[k]} for k in ("NFP", "CPI", "FOMC")}
    rows = []
    for d in pd.date_range(START, END, freq="D"):
        if d.dayofweek >= 5 or d in CLOSED:
            continue
        iso = d.isocalendar()
        for s in range(23):
            b = sc.bucket(s, (d, s) in flags["NFP"], (d, s) in flags["CPI"], (d, s) in flags["FOMC"])
            rows.append((d, s, b, iso[0] * 100 + iso[1], d.strftime("%Y-%m")))
    cal = pd.DataFrame(rows, columns=["day", "slot", "bucket", "week", "month"])
    weeks = sorted(cal.week.unique())
    cal["wi"] = cal.week.map({w: i for i, w in enumerate(weeks)})
    return cal, len(weeks)


def ar1(rng, P, W, rho):
    w = np.empty((P, W))
    w[:, 0] = rng.standard_normal(P)
    e = rng.standard_normal((P, W))
    for t in range(1, W):
        w[:, t] = rho * w[:, t - 1] + np.sqrt(1 - rho ** 2) * e[:, t]
    return w


def max_abs_z(cal, W, rho, icc, dep, P, rng):
    """Per path: max |z| over eligible (update, bucket), and the per-bucket maxima."""
    out = np.zeros(P)
    per = {}
    common = ar1(rng, P, W, rho) if dep == "shared" else None
    for b in sc.BUCKETS:
        cb = cal[cal.bucket == b]
        sig = SIGMA[b]
        wk = common if dep == "shared" else ar1(rng, P, W, rho)
        lr = (-sig ** 2 / 2 + sig * np.sqrt(icc) * wk[:, cb.wi.values]
              + sig * np.sqrt(1 - icc) * rng.standard_normal((P, len(cb))))
        r = np.exp(lr)
        best = np.zeros(P)
        event = b in l3.EVENT_BUCKETS
        months, wi_all = cb.month.values, cb.wi.values
        for m in UPDATES:
            n = int(np.searchsorted(months, m))        # observations are in time order: a prefix
            if n == 0:
                continue
            rs = r[:, :n]
            mean = rs.mean(axis=1)
            wi = wi_all[:n]
            starts = np.flatnonzero(np.r_[True, wi[1:] != wi[:-1]])
            G = len(starts)
            if not l3.eligible(b, n, G):
                continue
            if event:
                se = rs.std(axis=1, ddof=1) / np.sqrt(n)
            else:
                cnt = np.diff(np.r_[starts, n])
                wm = np.add.reduceat(rs, starts, axis=1) / cnt
                se = wm.std(axis=1, ddof=1) / np.sqrt(G)
            with np.errstate(divide="ignore", invalid="ignore"):
                z = np.abs((mean - 1) / se)
            best = np.maximum(best, np.nan_to_num(z, nan=0.0))
        per[b] = best
        out = np.maximum(out, best)
    return out, per


def choose(pmax_by_z):
    z = Z0
    while z <= ZMAX:
        if pmax_by_z(z) <= LIMIT:
            return z
        z += ZSTEP
    return float("inf")


def run(paths=20000, chunk=2000, seed=SEED):
    cal, W = calendar()
    counts = {b: int((cal.bucket == b).sum()) for b in sc.BUCKETS}
    grid = np.arange(Z0, ZMAX + 1e-9, ZSTEP)
    cells = []
    ss = np.random.SeedSequence(seed)
    children = ss.spawn(len(RHOS) * len(ICCS) * len(DEPS))
    k = 0
    for rho in RHOS:
        for icc in ICCS:
            for dep in DEPS:
                rng = np.random.default_rng(children[k])
                k += 1
                mx, per = [], {b: [] for b in sc.BUCKETS}
                for c0 in range(0, paths, chunk):
                    P = min(chunk, paths - c0)
                    m, pb = max_abs_z(cal, W, rho, icc, dep, P, rng)
                    mx.append(m)
                    for b in sc.BUCKETS:
                        per[b].append(pb[b])
                mx = np.concatenate(mx)
                mxn = np.max([np.concatenate(per[b]) for b in sc.BUCKETS if b not in l3.EVENT_BUCKETS], axis=0)
                cells.append({"rho": rho, "icc": icc, "dependence": dep,
                              "p_any_by_z": {f"{z:.2f}": float((mx >= z).mean()) for z in grid},
                              "p_bucket_at_3.50": {b: float((np.concatenate(per[b]) >= 3.5).mean())
                                                   for b in sc.BUCKETS},
                              "_mx": mx, "_mx_normal": mxn})
    def worst(z):
        return max(float((c["_mx"] >= z).mean()) for c in cells)
    zstar = choose(worst)
    p_z, p_35 = (worst(zstar) if np.isfinite(zstar) else None), worst(3.5)
    by_dep = {dep: choose(lambda z, dep=dep: max(float((c["_mx"] >= z).mean()) for c in cells
                                                if c["dependence"] == dep)) for dep in DEPS}
    no_events = choose(lambda z: max(float((c["_mx_normal"] >= z).mean()) for c in cells))
    worst_cell = max(cells, key=lambda c: float((c["_mx"] >= (zstar if np.isfinite(zstar) else ZMAX)).mean()))
    worst_cell = {k: worst_cell[k] for k in ("rho", "icc", "dependence")}
    for c in cells:
        c.pop("_mx")
        c.pop("_mx_normal")
    return {
        "zstar": zstar, "rule": "z* = 3.5 unless the worst cell has P(any bucket ever active over 14 updates | "
                                 "calibrated) > 10%; then +0.25 steps until it does not (SYSTEM_V1_PREREG.md §4)",
        "p_worst_at_zstar": p_z,
        "p_worst_at_3.50": p_35,
        "diagnostics": {"zstar_if_only_" + k: v for k, v in by_dep.items()} | {"zstar_without_event_buckets": no_events},
        "worst_cell_at_zstar": worst_cell,
        "paths_per_cell": paths, "seed": seed, "start": str(START.date()), "end": str(END.date()),
        "updates": UPDATES, "sigma": SIGMA, "obs_per_bucket": counts, "weeks": W,
        "estimator": "analysis/system/l3.py (bucket_stats, eligible)",
        "l3_sha256": hashlib.sha256((Path(l3.__file__)).read_bytes()).hexdigest(),
        "sim_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cells": cells,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=20000)
    ap.add_argument("--out", default=str(syspath.ROOT / "reports" / "system" / "L3_ZSTAR.json"))
    a = ap.parse_args(argv)
    res = run(a.paths)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"z* = {res['zstar']}  worst P at z*: {res['p_worst_at_zstar']}  worst P at 3.50: {res['p_worst_at_3.50']}")
    print("worst cell:", res["worst_cell_at_zstar"], "obs per bucket:", res["obs_per_bucket"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
