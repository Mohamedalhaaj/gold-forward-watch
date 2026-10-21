"""Registry records, registration, first_day and rule states of both lab versions, as the judge reads them
(SYSTEM_V1_PREREG.md §3 items 5-8; L2 §7, §9.3-§9.5; IMPLEMENTATION_REGISTER R-V1-35 .. R-V1-38, R-V1-47, R-V2-21 ..
R-V2-26)."""
import json
from fractions import Fraction
from pathlib import Path

import pandas as pd

from .common import load_json, model_to_utc, parse_utc, read_dicts, utc_to_model

STATE_OF = {"PROMOTED": "LIVE", "SUSPENDED": "SUSPENDED", "RESUMED": "LIVE", "DEMOTED": "DEMOTED",
            "RETIRED": "RETIRED"}


class Lab:
    """One lab version's registry folder, events and START."""

    def __init__(self, data_root, version):
        root = Path(data_root)
        self.version = version
        self.dir = root / ("reports/system/lab" if version == 1 else "reports/system/lab_v2")
        self.records = {}
        for p in sorted((self.dir / "registry").glob("*.json")):
            rec = load_json(p)
            if isinstance(rec, dict) and "id" in rec:
                self.records[rec["id"]] = rec
        self.events = read_dicts(self.dir / "registry/events.csv")
        for e in self.events:
            e["_utc"] = parse_utc(e["utc"])
        sj = load_json(root / ("reports/system/START.json" if version == 1 else "reports/system/lab_v2/START.json"))
        self.start_json = sj
        self.start = pd.Timestamp(sj["start"]) if isinstance(sj, dict) and sj.get("start") else None

    def order(self):
        """Registry order: arrival, then id."""
        return sorted(self.records, key=lambda i: (self.records[i].get("arrival", 0), i))

    def registered_utc(self, rid):
        for e in self.events:
            if e["id"] == rid and e["event"] == "REGISTERED":
                return e["_utc"]
        return None

    def first_day(self, rid):
        reg = self.registered_utc(rid)
        if reg is None or self.start is None:
            return None
        return first_day(reg, self.start)

    def lab_first_day(self):
        fds = [self.first_day(r) for r in self.records]
        fds = [d for d in fds if d is not None]
        return min(fds) if fds else None

    def state_at(self, rid, t, inclusive=False):
        """State from the events with utc < t (<= t when inclusive); REGISTERED rows count up to and including t.
        PENDING before registration; PAPER (promotable) or REF after it."""
        rec = self.records.get(rid, {})
        st = "PENDING"
        for e in self.events:
            if e["id"] != rid or e["_utc"] is None:
                continue
            if e["event"] == "REGISTERED":
                if e["_utc"] <= t and st == "PENDING":
                    st = "PAPER" if rec.get("promotable") else "REF"
                continue
            if e["_utc"] < t or (inclusive and e["_utc"] <= t):
                st = STATE_OF.get(e["event"], st)
        return st

    def promoted_utc(self, rid, t=None):
        for e in self.events:
            if e["id"] == rid and e["event"] == "PROMOTED" and (t is None or e["_utc"] <= t):
                return e["_utc"]
        return None


def first_day(registered_utc, start):
    """R-V1-37: t = registered_utc + 1 h; from max(model date of t - 1 day, START), the first model weekday d with
    model_to_utc(d 01:00) >= t and d >= START."""
    t = registered_utc + pd.Timedelta(hours=1)
    d = max(utc_to_model(t).normalize() - pd.Timedelta(days=1), pd.Timestamp(start))
    for _ in range(4000):
        if d.dayofweek < 5 and d >= start and model_to_utc(d + pd.Timedelta(hours=1)) >= t:
            return d
        d += pd.Timedelta(days=1)
    raise RuntimeError("first_day not found")


def start_value(first_run_utc, floor):
    """START = max(floor, the first Monday on or after (UTC date of the run + 2 days)) (v1 §0, R-V1-38, R-V2-26)."""
    d = pd.Timestamp(first_run_utc).tz_convert("UTC").tz_localize(None).normalize() + pd.Timedelta(days=2)
    while d.dayofweek != 0:
        d += pd.Timedelta(days=1)
    return max(pd.Timestamp(floor), d)


def spec_sha(spec):
    import hashlib
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                          .encode()).hexdigest()


def e_star_ok(rec, version):
    """Registry E* against alpha, gamma and D (v1 §3 item 7, A1 item 5; v2 §2.3)."""
    if not rec.get("promotable"):
        return rec.get("E_star") is None and float(rec.get("gamma", 0)) == 0.0
    if version == 1:
        a = float(rec["alpha"]) * float(rec["gamma"]) * (int(rec.get("D_at_arrival", 0)) + 1)
        return abs(float(rec["E_star"]) - 1 / a) <= 1e-9 * (1 / a)
    exact = Fraction(rec["alpha_exact"]) * Fraction(rec["gamma_exact"]) * (int(rec.get("D_at_arrival", 0)) + 1)
    return Fraction(rec["E_star_exact"]) == 1 / exact and float(rec["E_star"]) == float(1 / exact)
