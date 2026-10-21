"""Reading the system's committed raw stores (v1: data/system; lab v2: data/system/lab_v2/lookback), read-only.

IMPLEMENTATION_REGISTER R-V1-5 .. R-V1-12 (v1 store, complete_utc, which files a run loads) and R-V2-4, R-V2-5,
R-V2-40, R-V2-42 (lookback store, its completeness).
"""
from pathlib import Path

import numpy as np
import pandas as pd

from . import dukascopy
from .common import (LOOKBACK_FIRST, LOOKBACK_LAST, STORE_FIRST_DAY, parse_utc, read_dicts, sha256_bytes)

SIDES = ("BID", "ASK")


class StoreProblem(Exception):
    pass


def raw_path(base, day, side):
    d = pd.Timestamp(day)
    return Path(base) / "raw" / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}" / f"{side}.bi5"


class Store:
    """One days file with its raw folder. `base` = data/system (v1) or data/system/lab_v2/lookback (v2)."""

    def __init__(self, base):
        self.base = Path(base)
        self.rows = read_dicts(self.base / "days.csv")
        for r in self.rows:
            r["_fetched"] = parse_utc(r.get("fetched_utc", ""))

    def status(self, now=None):
        """{(day, side): row} of the latest row per (day, side) with fetched_utc <= now (a later row wins)."""
        out = {}
        for r in self.rows:
            if now is not None and (r["_fetched"] is None or r["_fetched"] > now):
                continue
            out[(r["day"], r["side"])] = r
        return out

    def path(self, day, side):
        return raw_path(self.base, day, side)

    def body(self, day, side, row=None):
        """The committed bytes of an ok (day, side), checked against its row's sha256 (StoreProblem if not)."""
        p = self.path(day, side)
        if not p.exists():
            raise StoreProblem(f"{p}: missing for an ok row")
        b = p.read_bytes()
        if row is not None and sha256_bytes(b) != row["sha256"]:
            raise StoreProblem(f"{p}: sha256 differs from its days row")
        return b


def complete_utc(store, now):
    """R-V1-11: end (exclusive, UTC midnight) of the run of UTC days from 2026-09-01 whose BID and ASK both have a
    final row (ok or missing) with fetched_utc <= now, among days with now >= D + 26 h."""
    st = store.status(now)
    d = STORE_FIRST_DAY
    while now >= (d + pd.Timedelta(hours=26)).tz_localize("UTC"):
        ds = d.strftime("%Y-%m-%d")
        if all(st.get((ds, s), {}).get("status") in ("ok", "missing") for s in SIDES):
            d += pd.Timedelta(days=1)
        else:
            break
    return d.tz_localize("UTC")


def v1_days_to_load(store, now, cu=None):
    """R-V1-12: UTC days with at least one ok side (rows with fetched_utc <= now), day start < complete_utc."""
    cu = complete_utc(store, now) if cu is None else cu
    st = store.status(now)
    days = sorted({d for (d, s), r in st.items() if r["status"] == "ok"
                   and pd.Timestamp(d).tz_localize("UTC") < cu and pd.Timestamp(d) >= STORE_FIRST_DAY})
    return [(d, [s for s in SIDES if st.get((d, s), {}).get("status") == "ok"], st) for d in days]


def load_frames(store, plan):
    """Decoded per-side frames: {side: [frame per day in day order]} for plan [(day, sides, status)]."""
    out = {s: [] for s in SIDES}
    for d, sides, st in plan:
        for s in sides:
            b = store.body(d, s, st[(d, s)])
            out[s].append(dukascopy.frame(b, d))
    return out


def lookback_days():
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(LOOKBACK_FIRST, LOOKBACK_LAST, freq="D")]


def lookback_complete(lb, t):
    """R-V2-42: complete at t iff each of the 486 (day, side) pairs has an ok or missing row with fetched_utc <= t."""
    st = lb.status(t)
    return all(st.get((d, s), {}).get("status") in ("ok", "missing") for d in lookback_days() for s in SIDES)


def v2_plan(lb, v1, now):
    """R-V2-4/5: lookback ok rows (fetched <= now) for 2026-01-01 .. 08-31, then v1 ok rows from 2026-09-01 with day
    start < v1's complete_utc at now. Returns [(store, day, side, row)] in (day, side) order."""
    out = []
    st = lb.status(now)
    for d in lookback_days():
        for s in SIDES:
            r = st.get((d, s))
            if r is not None and r["status"] == "ok":
                out.append((lb, d, s, r))
    cu = complete_utc(v1, now)
    st1 = v1.status(now)
    for (d, s), r in sorted(st1.items()):
        if r["status"] == "ok" and pd.Timestamp(d) >= STORE_FIRST_DAY and pd.Timestamp(d).tz_localize("UTC") < cu:
            out.append((v1, d, s, r))
    out.sort(key=lambda x: (x[1], 0 if x[2] == "BID" else 1))
    return out


def load_v2_frames(plan):
    out = {s: [] for s in SIDES}
    for store, d, s, r in plan:
        out[s].append(dukascopy.frame(store.body(d, s, r), d))
    return out


def verify_ok_rows(store):
    """Every ok row's file exists with its sha256 (problems listed, nothing raised)."""
    probs = []
    for (d, s), r in store.status(None).items():
        if r["status"] != "ok":
            continue
        p = store.path(d, s)
        if not p.exists():
            probs.append(f"{p.relative_to(store.base.parents[1]) if len(store.base.parents) > 1 else p}: missing")
        elif sha256_bytes(p.read_bytes()) != r["sha256"]:
            probs.append(f"{p}: sha256 differs from its days row")
    return probs


def first_seen_ok(store):
    """{(day, side): fetched_utc} of the first ok row (for the J1 'new since the last judge run' rule)."""
    out = {}
    for r in store.rows:
        if r["status"] == "ok" and (r["day"], r["side"]) not in out:
            out[(r["day"], r["side"])] = r["_fetched"]
    return out


def np_nan(n):
    return np.full(n, np.nan)
