"""Forward watch for the US-data-hour lower-wick rule. Pre-registration: reports/FORWARD_WICK_PREREG.md.

Append-only: a day is written to the ledger once, when its data is complete, and never recomputed.
Runs from the LaunchAgent com.xauusd.forwardwick; after the 20th day it writes VERDICT.md and removes
the LaunchAgent. Test mode (--start/--out) writes elsewhere and never touches the real ledger or agent.

Usage: uv run --with matplotlib python -I analysis/forward_wick_tracker.py [--start YYYY-MM-DD --out DIR]
"""
import argparse
import csv
import json
import math
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
START, N_DAYS, HARD_STOP = "2026-10-16", 20, "2026-11-27"
WICK_PCT = 0.0015
URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=15m&range=60d&includePrePost=true"
LABEL = "com.xauusd.forwardwick"
FIELDS = ["day", "status", "h1_open", "h1_close", "h1_low", "wick", "wick_pct", "trigger", "ref_1600",
          "px_1645", "px_2400", "A_pts", "B_pts", "B_up", "worst_after", "recorded_at"]


def fetch(rawdir):
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    body = urllib.request.urlopen(req, timeout=30).read()
    rawdir.mkdir(parents=True, exist_ok=True)
    (rawdir / f"gcf_15m_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json").write_bytes(body)
    r = json.loads(body)["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({"o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"]},
                      index=pd.to_datetime(r["timestamp"], unit="s", utc=True)).dropna()
    # MT5 server clock = New York wall clock + 7h
    df.index = df.index.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
    return df[~df.index.duplicated()]


def evaluate(df, day):
    bar = lambda hm: df.loc[day + pd.Timedelta(hm)] if day + pd.Timedelta(hm) in df.index else None
    need = ["15h", "15h15min", "15h30min", "15h45min", "16h", "16h30min", "23h45min"]
    if any(bar(t) is None for t in need):
        return None
    h1 = [bar(t) for t in need[:4]]
    o, c, lo = h1[0].o, h1[3].c, min(b.l for b in h1)
    wick = min(o, c) - lo
    ref = bar("16h").o
    after = df[(df.index >= day + pd.Timedelta("16h")) & (df.index < day + pd.Timedelta("24h"))]
    a, b = bar("16h30min").c - ref, bar("23h45min").c - ref
    return {"day": day.strftime("%Y-%m-%d"), "status": "complete", "h1_open": round(o, 2), "h1_close": round(c, 2),
            "h1_low": round(lo, 2), "wick": round(wick, 2), "wick_pct": round(wick / c, 5),
            "trigger": int(wick >= WICK_PCT * c), "ref_1600": round(ref, 2), "px_1645": round(bar("16h30min").c, 2),
            "px_2400": round(bar("23h45min").c, 2), "A_pts": round(a, 2), "B_pts": round(b, 2), "B_up": int(b > 0),
            "worst_after": round(after.l.min() - ref, 2),
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}


def needed_k(n):
    """Smallest k with P(X >= k | n, 0.5) < 0.10."""
    for k in range(n + 1):
        if sum(math.comb(n, j) for j in range(k, n + 1)) / 2 ** n < 0.10:
            return k
    return n + 1


def verdict(rows):
    done = [r for r in rows if r["status"] == "complete"]
    trig = [r for r in done if int(r["trigger"])]
    ctrl = [r for r in done if not int(r["trigger"])]
    n, k = len(trig), sum(int(r["B_up"]) for r in trig)
    ctrl_share = sum(int(r["B_up"]) for r in ctrl) / len(ctrl) if ctrl else 0.0
    if n < 6:
        v = "INCONCLUSIVE"
    elif k >= needed_k(n) and k / n > ctrl_share:
        v = "PASS"
    else:
        v = "FAIL"
    return v, n, k, ctrl_share, len(done)


def draw(rows, path):
    fig, ax = plt.subplots(figsize=(16, 3.2))
    for i in range(N_DAYS):
        r = rows[i] if i < len(rows) else None
        if r is None:
            col, txt = "white", "pending"
        elif r["status"] != "complete":
            col, txt = "#bdbdbd", "no data"
        elif int(r["trigger"]):
            col, txt = ("#26a69a" if int(r["B_up"]) else "#ef5350"), f"{float(r['B_pts']):+.1f}"
        else:
            col, txt = "#e8e8e8", "no wick"
        ax.add_patch(plt.Rectangle((i, 0), 0.9, 1, color=col, ec="#999", lw=0.6))
        ax.text(i + 0.45, 0.5, txt, ha="center", va="center", fontsize=8)
        if r is not None:
            ax.text(i + 0.45, -0.15, pd.Timestamp(r["day"]).strftime("%a\n%d %b"), ha="center", va="top", fontsize=7.5)
    v, n, k, cs, d = verdict(rows)
    ax.set_title(f"Forward watch, US-data wick rule (frozen 2026-10-16). Days recorded {d}/{N_DAYS}. "
                 f"Triggers {n}, up at 24:00 {k}" + (f", PASS needs {needed_k(n)}" if n >= 6 else ""), loc="left")
    ax.set_xlim(-0.2, N_DAYS)
    ax.set_ylim(-0.9, 1.1)
    ax.axis("off")
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=START)
    ap.add_argument("--out", default=str(ROOT / "reports/forward_wick"))
    args = ap.parse_args()
    test = args.start != START or Path(args.out) != ROOT / "reports/forward_wick"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / "ledger.csv"
    rows = list(csv.DictReader(open(ledger))) if ledger.exists() else []
    if len([r for r in rows if r["status"] == "complete"]) < N_DAYS:
        df = fetch(out / "raw" if test else ROOT / "data/forward_wick/raw")
        have = {r["day"] for r in rows}
        today = pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None).tz_localize("UTC").tz_convert(
            "America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
        for day in pd.bdate_range(args.start, HARD_STOP):
            if len([r for r in rows if r["status"] == "complete"]) >= N_DAYS:
                break
            key = day.strftime("%Y-%m-%d")
            if key in have or day + pd.Timedelta("24h") > today:
                continue
            res = evaluate(df, day)
            if res is None and (today - day).days >= 2:
                res = {f: "" for f in FIELDS} | {"day": key, "status": "no-data",
                                                   "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
            if res is not None:
                rows.append(res)
        rows.sort(key=lambda r: r["day"])
        with open(ledger, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
    shown = [r for r in rows if r["status"] in ("complete", "no-data")]
    draw(shown, out / "forward_strip.png")
    v, n, k, cs, d = verdict(rows)
    status = (f"# Forward watch status\n\nUpdated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Rule frozen in "
              f"`reports/FORWARD_WICK_PREREG.md`.\n\n- Days recorded: {d} of {N_DAYS}\n- Trigger days: {n}; "
              f"up at 24:00: {k}\n- Non-trigger days up at 24:00: {cs:.0%}\n- Verdict so far (final only at day {N_DAYS}): {v}\n")
    (out / "STATUS.md").write_text(status)
    print(status)
    if d >= N_DAYS and not (out / "VERDICT.md").exists():
        (out / "VERDICT.md").write_text(status.replace("Forward watch status", f"FINAL VERDICT: {v}"))
        if not test:
            plist = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
            plist.unlink(missing_ok=True)
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], check=False)


if __name__ == "__main__":
    main()
