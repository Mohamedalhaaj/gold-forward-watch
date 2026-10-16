"""Forward watch: double-top sell, CAUSAL primary + STRICT reference. Dashboard: https://gold-watch-mq1dqc.xauusd-quant.workers.dev Pre-registration: reports/FORWARD_DOUBLETOP_PREREG.md.

wick_swings and walk are copied verbatim from research/hunt/double_bottom/dbw_test.py (commit 090201f), and the
setup loop is the same as dbw_test.run for one data segment. Append-only ledger: a closed trade is written once and
never recomputed. Writes reports/forward_site/data.json for the dashboard, optionally deploys it to Cloudflare Pages,
and after the 20th day writes the verdict and removes its LaunchAgent.

Usage:
  uv run python -I analysis/forward_doubletop_tracker.py            # live: fetch, update ledger, write data.json
  uv run python -I analysis/forward_doubletop_tracker.py --deploy   # ... and deploy the site
  uv run python -I analysis/forward_doubletop_tracker.py --replay research/hunt/double_bottom/gcf_15m_aug_oct.csv
"""
import csv
import heapq
import json
import math
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
START, N_DAYS = pd.Timestamp("2026-10-19"), 20
# PRIMARY = CAUSAL M15 (reports/FORWARD_DOUBLETOP_CAUSAL_PREREG.md); STRICT M15 = frozen, non-executable reference
PRIMARY, SECONDARY = "causal_M15", "strict_M15"
CONFIGS = {"M15": {"k": 1.5, "s": 1.0, "t": 1.0}, "M30": {"k": 1.5, "s": 1.0, "t": 1.0}}
TFS, MAXGAP = {"M15": "15min", "M30": "30min"}, {"M15": 96, "M30": 72}
COST, B, SIDE = 0.25, 0.1, -1
URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=15m&range=60d&includePrePost=true"
LABEL, PROJECT = "com.xauusd.forwarddoubletop", "gold-watch-mq1dqc"
LEDGER = ROOT / "reports/forward_doubletop/trades.csv"
SITE = ROOT / "reports/forward_site"
FIELDS = ["mode", "tf", "day", "fill_time", "fill", "stop", "target", "exit_time", "exit", "reason", "net", "recorded_at"]
# 2026 in-sample reference (204 days: Tickmill Jan-Aug M1 + GC=F Aug-Oct 15m), same code as below
IN_SAMPLE = {"causal_M15": {"avg_day": 0.48, "days_pos": 0.50, "net_trade": 0.08, "win": 0.49, "trades_per_day": 5.7, "worst_day": -143.8},
             "causal_M30": {"avg_day": 1.25, "days_pos": 0.52, "net_trade": 0.42, "win": 0.49, "trades_per_day": 3.0, "worst_day": -172.5},
             "strict_M15": {"avg_day": 8.23, "days_pos": 0.64, "net_trade": 1.90, "win": 0.57, "trades_per_day": 4.3, "worst_day": -71.3},
             "strict_M30": {"avg_day": 6.04, "days_pos": 0.58, "net_trade": 2.58, "win": 0.55, "trades_per_day": 2.3, "worst_day": -110.2}}


def to_server(idx):
    return pd.DatetimeIndex(idx).tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    body = urllib.request.urlopen(req, timeout=30).read()
    raw = ROOT / "data/forward_doubletop/raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"gcf_15m_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json").write_bytes(body)
    r = json.loads(body)["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    d = pd.DataFrame({"o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"]},
                     index=to_server(pd.to_datetime(r["timestamp"], unit="s", utc=True))).dropna()
    return d[~d.index.duplicated()].sort_index()


def read_csv(path, start):
    g = pd.read_csv(path)
    g.index = to_server(pd.to_datetime(g.timestamp_utc, utc=True))
    g = g.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c"})[["o", "h", "l", "c"]]
    g = g[g.index >= start]
    return g[~g.index.duplicated()].sort_index()


def bars(df, tf):
    r = df.resample(TFS[tf], label="left", closed="left")
    b = pd.DataFrame({"o": r.o.first(), "h": r.h.max(), "l": r.l.min(), "c": r.c.last()}).dropna()
    return b[b.index.dayofweek < 5]


def fine(df):
    f = df[df.index.dayofweek < 5]
    ts_ = f.index.values.astype("datetime64[ns]").astype(np.int64)
    dn = f.index.normalize()
    eod_idx = np.searchsorted(ts_, (dn + pd.Timedelta("23h30min")).values.astype("datetime64[ns]").astype(np.int64))
    return ("GC=F", f, ts_, f.o.to_numpy(), f.h.to_numpy(), f.l.to_numpy(), f.c.to_numpy(), dn, eod_idx)


# ---- verbatim from dbw_test.py (commit 090201f) ----------------------------------------------------------------
def wick_swings(b, k):
    h, l, c = b.h.to_numpy(), b.l.to_numpy(), b.c.to_numpy()
    tr = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    atr = np.concatenate([[np.nan], pd.Series(tr).rolling(14).mean().to_numpy()])
    out, mode, ext, ext_i = [], "down", l[0], 0
    for i in range(1, len(b)):
        a = atr[i]
        if np.isnan(a):
            continue
        if mode == "down":
            if i > ext_i and h[i] >= ext + k * a:
                out.append(("L", ext_i, ext, i, a))
                mode, ext, ext_i = "up", h[i], i
            elif l[i] < ext:
                ext, ext_i = l[i], i
        else:
            if i > ext_i and l[i] <= ext - k * a:
                out.append(("H", ext_i, ext, i, a))
                mode, ext, ext_i = "down", l[i], i
            elif h[i] > ext:
                ext, ext_i = h[i], i
    return out, atr


def walk(F, f0, side, stop, target):
    _, _, ts, o, h, l, c, day, eod = F
    end = max(eod[f0], f0 + 1)
    if (l[f0] <= stop) if side > 0 else (h[f0] >= stop):
        return stop, f0
    hs = (l[f0 + 1:end] <= stop) if side > 0 else (h[f0 + 1:end] >= stop)
    ht = (h[f0 + 1:end] >= target) if side > 0 else (l[f0 + 1:end] <= target)
    i_s = int(np.argmax(hs)) if hs.any() else 10**9
    i_t = int(np.argmax(ht)) if ht.any() else 10**9
    if i_s == 10**9 and i_t == 10**9:
        return c[end - 1], end - 1
    return (stop, f0 + 1 + i_s) if i_s <= i_t else (target, f0 + 1 + i_t)
# -----------------------------------------------------------------------------------------------------------------


def simulate(df, tf, k, s, t, side=SIDE):
    """dbw_test.run for one segment, returning full trade detail and whether each trade is final."""
    F = fine(df)
    _, _, ts, o, h, l, c, day, eod = F
    last_ts = ts[-1]
    b = bars(df, tf)
    sw, _ = wick_swings(b, k)
    bt = b.index.values.astype("datetime64[ns]").astype(np.int64)
    tf_ns = pd.Timedelta(TFS[tf]).value
    busy, out = -1, []
    first, second = ("L", "H") if side > 0 else ("H", "L")
    for n in range(len(sw) - 1):
        if sw[n][0] != first or sw[n + 1][0] != second:
            continue
        p1, ch, a = sw[n][2], sw[n + 1][3], sw[n + 1][4]
        if ch + 1 >= len(b):
            continue
        px = p1 + side * B * a
        stop = p1 - side * s * a
        start, end = bt[ch] + tf_ns, bt[min(ch + 1 + MAXGAP[tf] // 2, len(b) - 1)]
        f = np.searchsorted(ts, max(start, busy + 1))
        fend = np.searchsorted(ts, end)
        hits = np.flatnonzero((l[f:fend] <= px) if side > 0 else (h[f:fend] >= px))
        if not len(hits):
            continue
        f0 = f + hits[0]
        if pd.Timestamp(ts[f0]) - day[f0] >= pd.Timedelta("23h"):
            continue
        fill = min(px, o[f0]) if side > 0 else max(px, o[f0])
        if (fill <= stop) if side > 0 else (fill >= stop):
            continue
        target = fill + side * t * a
        xp, xi = walk(F, f0, side, stop, target)
        busy = ts[xi]
        reason = "stop" if xp == stop else "target" if xp == target else "close 23:30"
        eod_ts = (day[f0] + pd.Timedelta("23h30min")).value
        final = bool(reason != "close 23:30" or last_ts >= eod_ts)
        out.append({"tf": tf, "day": day[f0].strftime("%Y-%m-%d"), "fill_time": pd.Timestamp(ts[f0]).strftime("%Y-%m-%d %H:%M"),
                    "fill": round(fill, 2), "stop": round(stop, 2), "target": round(target, 2),
                    "exit_time": pd.Timestamp(ts[xi]).strftime("%Y-%m-%d %H:%M"), "exit": round(float(xp), 2),
                    "reason": reason if final else "open", "net": round(side * (xp - fill) - COST, 2), "final": final})
    return out


def simulate_causal(df, tf, k, s, t, side=SIDE):
    """CAUSAL execution of the same setups (reports/FORWARD_DOUBLETOP_CAUSAL_PREREG.md, primary from 2026-10-19).
    simulate() resolves overlapping armed setups in swing order, which needs future bars. Here every armed limit
    rests in the market from its start; the first touch in time fills while flat; a limit touched while a trade is
    open stays armed and can fill later inside its window. Same swings, setups, fills, exits and costs."""
    F = fine(df)
    _, _, ts, o, h, l, c, day, eod = F
    last_ts = ts[-1]
    b = bars(df, tf)
    sw, _ = wick_swings(b, k)
    bt = b.index.values.astype("datetime64[ns]").astype(np.int64)
    tf_ns = pd.Timedelta(TFS[tf]).value
    first, second = ("L", "H") if side > 0 else ("H", "L")
    S = []
    for n in range(len(sw) - 1):
        if sw[n][0] != first or sw[n + 1][0] != second:
            continue
        p1, ch, a = sw[n][2], sw[n + 1][3], sw[n + 1][4]
        if ch + 1 >= len(b):
            continue
        S.append((bt[ch] + tf_ns, bt[min(ch + 1 + MAXGAP[tf] // 2, len(b) - 1)], p1 + side * B * a, p1 - side * s * a, a))

    def touch(i, after):
        st, en, px, _, _ = S[i]
        f, fe = np.searchsorted(ts, max(st, after)), np.searchsorted(ts, en)
        for j in np.flatnonzero((l[f:fe] <= px) if side > 0 else (h[f:fe] >= px)):
            if pd.Timestamp(ts[f + j]) - day[f + j] < pd.Timedelta("23h"):
                return f + j
        return None

    q = []
    for i in range(len(S)):
        f0 = touch(i, -1)
        if f0 is not None:
            heapq.heappush(q, (ts[f0], i, f0))
    busy, out = -1, []
    while q:
        t0, i, f0 = heapq.heappop(q)
        if t0 <= busy:
            f1 = touch(i, busy + 1)
            if f1 is not None:
                heapq.heappush(q, (ts[f1], i, f1))
            continue
        _, _, px, stop, a = S[i]
        fill = min(px, o[f0]) if side > 0 else max(px, o[f0])
        if (fill <= stop) if side > 0 else (fill >= stop):
            continue
        target = fill + side * t * a
        xp, xi = walk(F, f0, side, stop, target)
        busy = ts[xi]
        reason = "stop" if xp == stop else "target" if xp == target else "close 23:30"
        final = bool(reason != "close 23:30" or last_ts >= (day[f0] + pd.Timedelta("23h30min")).value)
        out.append({"tf": tf, "day": day[f0].strftime("%Y-%m-%d"), "fill_time": pd.Timestamp(ts[f0]).strftime("%Y-%m-%d %H:%M"),
                    "fill": round(fill, 2), "stop": round(stop, 2), "target": round(target, 2),
                    "exit_time": pd.Timestamp(ts[xi]).strftime("%Y-%m-%d %H:%M"), "exit": round(float(xp), 2),
                    "reason": reason if final else "open", "net": round(side * (xp - fill) - COST, 2), "final": final})
    return sorted(out, key=lambda r: r["fill_time"])


def trading_days(df):
    cnt = df.groupby(df.index.normalize()).size()
    days = [d for d in cnt.index if d >= START and d.dayofweek < 5 and cnt[d] >= 40]
    last = df.index[-1]
    return [d for d in days if last >= d + pd.Timedelta("23h30min")][:N_DAYS]


def stats(daily_net, trades):
    x = np.array(daily_net, float)
    n = len(x)
    act = [v for v, k in zip(x, [len(tl) for tl in trades]) if k > 0]
    sd = x.std(ddof=1) if n > 1 else 0.0
    tt = x.mean() / (sd / math.sqrt(n)) if n > 1 and sd > 0 else 0.0
    p = 0.5 * math.erfc(tt / math.sqrt(2)) if n > 1 else 1.0
    return {"days": n, "total": round(float(x.sum()), 2), "avg_day": round(float(x.mean()), 2) if n else 0.0,
            "days_pos": round(float(np.mean(np.array(act) > 0)), 3) if act else None,
            "best_day": round(float(x.max()), 2) if n else None, "worst_day": round(float(x.min()), 2) if n else None,
            "t": round(tt, 2), "p": round(p, 4)}


def wick_status():
    led = ROOT / "reports/forward_wick/ledger.csv"
    if not led.exists():
        return None
    rows = [r for r in csv.DictReader(open(led)) if r["status"] == "complete"]
    trig = [r for r in rows if int(r["trigger"])]
    return {"days": len(rows), "triggers": len(trig), "up": sum(int(r["B_up"]) for r in trig),
            "rows": [{"day": r["day"], "trigger": int(r["trigger"]), "B_pts": float(r["B_pts"])} for r in rows]}


def main():
    modes = {"causal": simulate_causal, "strict": simulate}
    if "--replay" in sys.argv:
        df = read_csv(sys.argv[sys.argv.index("--replay") + 1], "2026-08-11")
        for tf, p in CONFIGS.items():
            for mode, fn in modes.items():
                tr = fn(df, tf, p["k"], p["s"], p["t"])
                print(f"replay {mode} {tf}: {len(tr)} trades, total net {sum(x['net'] for x in tr):+.2f}")
        return
    df = fetch()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(LEDGER))) if LEDGER.exists() else []
    for r in rows:
        r.setdefault("mode", "strict")          # rows written before the CAUSAL amendment were STRICT
        r["mode"] = r["mode"] or "strict"
    have = {(r["mode"], r["tf"], r["fill_time"]) for r in rows}
    days = trading_days(df)
    day_keys = {d.strftime("%Y-%m-%d") for d in days}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    open_trades = []
    for tf, p in CONFIGS.items():
        for mode, fn in modes.items():
            for tr in fn(df, tf, p["k"], p["s"], p["t"]):
                tr["mode"] = mode
                if pd.Timestamp(tr["fill_time"]) < START + pd.Timedelta("1h"):
                    continue
                if not tr["final"]:
                    open_trades.append(tr)
                    continue
                if tr["day"] in day_keys and (mode, tf, tr["fill_time"]) not in have:
                    rows.append({k: tr[k] for k in FIELDS if k in tr} | {"recorded_at": now})
                    have.add((mode, tf, tr["fill_time"]))
    rows.sort(key=lambda r: (r["mode"], r["tf"], r["fill_time"]))
    with open(LEDGER, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    out = {"updated_utc": now, "start": START.strftime("%Y-%m-%d"), "n_days": N_DAYS, "primary": PRIMARY,
           "secondary": SECONDARY, "last_price_time_server": df.index[-1].strftime("%Y-%m-%d %H:%M"),
           "last_price": round(float(df.c.iloc[-1]), 2), "days_done": len(days), "in_sample": IN_SAMPLE, "configs": {},
           "open_trades": open_trades, "wick": wick_status()}
    for mode in modes:
        for tf in CONFIGS:
            tl = [r for r in rows if r["tf"] == tf and r["mode"] == mode]
            per_day = [[r for r in tl if r["day"] == d.strftime("%Y-%m-%d")] for d in days]
            daily = [round(sum(float(r["net"]) for r in td), 2) for td in per_day]
            st = stats(daily, per_day)
            wins = [float(r["net"]) > 0 for r in tl]
            st |= {"trades": len(tl), "win": round(float(np.mean(wins)), 3) if wins else None}
            out["configs"][f"{mode}_{tf}"] = {"daily": [{"day": d.strftime("%Y-%m-%d"), "net": v, "trades": len(td)}
                                                        for d, v, td in zip(days, daily, per_day)],
                                              "trades": tl, "stats": st}

    def verdict_of(key):
        st = out["configs"][key]["stats"]
        return "PASS" if (st["avg_day"] > 0 and st["p"] < 0.10 and (st["days_pos"] or 0) >= 0.5) else "FAIL"

    verdict, verdict2 = verdict_of(PRIMARY), verdict_of(SECONDARY)
    out["verdict_so_far"] = verdict if len(days) >= 2 else "PENDING"
    out["verdict_secondary_so_far"] = verdict2 if len(days) >= 2 else "PENDING"
    out["final"] = len(days) >= N_DAYS
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "data.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    st = out["configs"][PRIMARY]["stats"]
    print(f"days {len(days)}/{N_DAYS}; CAUSAL M15 trades {st['trades']}, total {st['total']:+.2f}, verdict so far {out['verdict_so_far']}")

    if "--deploy" in sys.argv:
        env = os.environ | {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}
        # Cloudflare Pages is now served through Workers static assets (wrangler 4.151): deploy the site as a Worker
        r = subprocess.run(["npx", "--yes", "wrangler", "deploy", "--config", str(ROOT / "reports/forward_deploy/wrangler.jsonc")],
                           capture_output=True, text=True, env=env, cwd=ROOT)
        print("deploy:", "ok" if r.returncode == 0 else "FAILED", (r.stdout + r.stderr)[-400:])
    if out["final"] and not (ROOT / "reports/forward_doubletop/VERDICT.md").exists():
        st2 = out["configs"][SECONDARY]["stats"]
        (ROOT / "reports/forward_doubletop/VERDICT.md").write_text(
            f"# FINAL VERDICT (primary CAUSAL M15): {verdict}\n\n{json.dumps(st, indent=1)}\n\n"
            f"## Secondary, non-executable reference (STRICT M15, frozen e2a1012): {verdict2}\n\n{json.dumps(st2, indent=1)}\n")
        plist = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
        if plist.exists():
            plist.unlink()
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], check=False)


if __name__ == "__main__":
    main()
