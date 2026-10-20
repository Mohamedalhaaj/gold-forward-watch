"""Pattern hunt: one fixed referee for every candidate. Pre-registration: research/hunt/HUNT_PREREG.md.

Searchers work on DISCOVERY (2015-2020) only. VALIDATION (2021-2024) and FRESH (GC=F 15m, Sep-Oct 2026)
are referee-only: they load only with HUNT_REFEREE=1. The sealed partition (2025-01..2026-08) is never read.

Clock: MT5 server time = New York + 7h; trading day 01:00 -> 24:00, Monday..Friday.

Candidate file interface (research/hunt/candidates/<name>.py):
    NAME = "short_name"; IDEA = "one sentence"; TF = "M5"; HOLD = 3   # hold HOLD bars
    def signal(df) -> pd.Series   # index = df.index, values in {-1, 0, +1}
        Decided at the CLOSE of each bar using rows <= that bar only. Entry = next bar's open,
        exit = close of the HOLD-th bar. One position at a time; trades spanning the weekend are skipped.
    Optional: USES_DXY = True -> df also carries dxy_o/dxy_h/dxy_l/dxy_c columns (same bars).

CLI (discovery only):
    uv run python -I research/hunt/harness.py eval  research/hunt/candidates/x.py
    uv run python -I research/hunt/harness.py audit research/hunt/candidates/x.py
"""
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HUNT = Path(__file__).resolve().parent
CACHE = HUNT / "cache"
SPLITS = {"discovery": ("2015-01-01", "2020-12-31"), "validation": ("2021-01-01", "2024-12-31")}
TFS = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}
COST = 0.25  # $/oz round trip, the client's own iteration-0 assumption (measured liquid-hours cost is $0.16)


def _guard(split):
    if split not in (*SPLITS, "fresh"):
        raise ValueError(split)
    if split != "discovery" and os.environ.get("HUNT_REFEREE") != "1":
        raise PermissionError(f"{split} data is referee-only")


def _to_server(idx):
    return idx.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)


def _slice(d, split):
    a, b = SPLITS[split]
    d = d[(d.index >= a) & (d.index < pd.Timestamp(b) + pd.Timedelta(days=1))]
    return d[d.index.dayofweek < 5]


def _bars(m, tf):
    if tf == "M1":
        out = m.copy()
        out["n"] = 1
        return out
    g = m.resample(f"{TFS[tf]}min", label="left", closed="left")
    return pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(),
                         "n": g.c.count()}).dropna()


def load(tf="M15", split="discovery", dxy=False):
    """Gold bars on the server clock with columns o h l c n day. dxy=True adds dxy_o/h/l/c (forward-filled
    within the bar grid, NaN where the dollar index had no data)."""
    _guard(split)
    if split == "fresh":
        return _load_fresh(tf)
    f = CACHE / f"xau_{tf}_{split}{'_dxy' if dxy else ''}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    m = pd.read_parquet(ROOT / "data/parquet/hist_m1.parquet", columns=["mid_o", "mid_h", "mid_l", "mid_c"])
    assert m.index.max() < pd.Timestamp("2025-01-01", tz="UTC"), "sealed partition must stay unread"
    m.index = _to_server(m.index)
    m = _slice(m.rename(columns={"mid_o": "o", "mid_h": "h", "mid_l": "l", "mid_c": "c"}), split)
    b = _bars(m, tf)
    if dxy:
        x = pd.read_parquet(ROOT / "data/parquet/usd_index_m1.parquet", columns=["dxy"])
        assert x.index.max() < pd.Timestamp("2025-01-01", tz="UTC")
        x.index = _to_server(x.index)
        x = _slice(x, split).dxy
        if tf == "M1":
            dx = pd.DataFrame({"dxy_o": x, "dxy_h": x, "dxy_l": x, "dxy_c": x})
        else:
            g = x.resample(f"{TFS[tf]}min", label="left", closed="left")
            dx = pd.DataFrame({"dxy_o": g.first(), "dxy_h": g.max(), "dxy_l": g.min(), "dxy_c": g.last()})
        b = b.join(dx, how="left")
    b["day"] = b.index.normalize()
    if split == "discovery":
        CACHE.mkdir(exist_ok=True)
        b.to_parquet(f)
    return b


def _load_fresh(tf):
    if TFS[tf] < 15:
        raise ValueError("fresh data is 15-minute; candidates below M15 cannot be checked on it")
    raw = json.load(open(HUNT / "fresh/gcf_15m.json"))["chart"]["result"][0]
    q = raw["indicators"]["quote"][0]
    d = pd.DataFrame({"o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"]},
                     index=pd.to_datetime(raw["timestamp"], unit="s", utc=True)).dropna()
    d.index = _to_server(d.index)
    d = d[~d.index.duplicated()]
    d = d[(d.index >= "2026-09-01") & (d.index.dayofweek < 5)]
    b = _bars(d, tf) if tf != "M15" else d.assign(n=1)
    b["day"] = b.index.normalize()
    return b


def _import(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def trades(mod, df, cost=COST):
    sig = mod.signal(df).reindex(df.index).fillna(0).clip(-1, 1).round().astype(int).to_numpy()
    o, c, idx = df.o.to_numpy(), df.c.to_numpy(), df.index
    hold, span = int(mod.HOLD), pd.Timedelta(minutes=TFS[mod.TF] * int(mod.HOLD) + 70)
    rows, i, n = [], 0, len(df)
    while i < n - 1:
        s = sig[i]
        if s != 0 and i + hold < n and idx[i + hold] - idx[i + 1] <= span:
            e, x = o[i + 1], c[i + hold]
            rows.append((idx[i + 1], s, e, s * (x - e), s * (x - e) - cost))
            i += hold
        else:
            i += 1
    return pd.DataFrame(rows, columns=["t", "side", "entry", "gross", "net"])


def stats(t):
    if len(t) < 2:
        return {"n": len(t)}
    r = t.net.to_numpy()
    sd = r.std(ddof=1)
    z = r.mean() / (sd / math.sqrt(len(r))) if sd > 0 else 0.0
    yr = t.groupby(t.t.dt.year).net.mean()
    return {"n": int(len(r)), "hit_gross": round(float((t.gross > 0).mean()), 4),
            "mean_gross": round(float(t.gross.mean()), 4), "mean_net": round(float(r.mean()), 4),
            "mean_net_bp": round(float((t.net / t.entry).mean() * 1e4), 3), "z": round(float(z), 3),
            "p_one_sided": float(0.5 * math.erfc(z / math.sqrt(2))), "total_net": round(float(r.sum()), 2),
            "years_pos": f"{int((yr > 0).sum())}/{len(yr)}", "per_year_net": {int(k): round(float(v), 3) for k, v in yr.items()},
            "long_share": round(float((t.side > 0).mean()), 3)}


def audit(mod, df, cuts=3, seed=0):
    """Truncation invariance: the signal at bar i must not change when later bars are removed."""
    full = mod.signal(df).reindex(df.index).fillna(0).to_numpy()
    for cut in np.random.default_rng(seed).integers(len(df) // 3, len(df) - 5, size=cuts):
        part = mod.signal(df.iloc[:cut]).reindex(df.index[:cut]).fillna(0).to_numpy()
        if not np.array_equal(part, full[:cut]):
            return False
    return True


def evaluate(path, split="discovery"):
    mod = _import(path)
    df = load(mod.TF, split, dxy=getattr(mod, "USES_DXY", False))
    return {"name": getattr(mod, "NAME", Path(path).stem), "tf": mod.TF, "hold": mod.HOLD, "split": split,
            **stats(trades(mod, df))}


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "eval":
        print(json.dumps(evaluate(path, "discovery"), indent=1))
    elif cmd == "audit":
        mod = _import(path)
        print("causal" if audit(mod, load(mod.TF, "discovery", dxy=getattr(mod, "USES_DXY", False))) else "LOOKAHEAD")
