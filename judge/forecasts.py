"""Recomputation of the forecast store (v1 §1; IMPLEMENTATION_REGISTER R-V1-14 .. R-V1-20).

The grid is the vendored volmap's `models.build` on the model-frame mids of every loaded raw day, then
`predict(T, "T2")["M4"]` = F_H1 and `predict(T, "T3")["M4"]` = F_S (bp), with the frozen discovery parameters. Events
(R-V1-15, lab review MF5): the official NFP/CPI/FOMC calendars from the judge's own copies of xauusd-quant
research/system/calendars/ (judge/vendor/calendars/, pinned by the register's sha256 and SHA256SUMS), read with the
vendored `models.load_events`, plus the extension lines the system accepted (R-V1-17, reports/system/calendar_ext.csv;
a run uses the accepted rows with first_seen_utc <= its run time). Holidays: R-V1-16.
"""
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import vendored
from .common import VENDOR, nyse_days, parse_utc, read_dicts, sha256_file

CAL_DIR = "analysis/system/vendor/calendars"     # the system's copies: hashed only (R-V1-15), never read as input
CAL_FILES = {"bls_2015_2024.csv": "bls_2026_2027.csv", "fomc_2015_2024.csv": "fomc_2026_2027.csv"}
CAL_SHA256 = {   # IMPLEMENTATION_REGISTER R-V1-15
    "bls_2026_2027.csv": "7e829d6c5acd861c276552d4086a2c639cbec03fc66242b859cd9d4fabdef45d",
    "fomc_2026_2027.csv": "dd709aee9821d0e1b4a1e9e0a8939422e92bb9520961090e31e96f4d30dc10f5",
}


class CalendarMissing(Exception):
    pass


def ext_lines(data_root, at=None):
    """R-V1-15/R-V1-17: the accepted extension lines [(first_seen_utc, kind, UTC time)], those with
    first_seen_utc <= at when `at` is given. A line is split at commas into exactly event,ts_utc,source_url, fields
    stripped of spaces; ts_utc carries an explicit offset."""
    out = []
    for row in read_dicts(Path(data_root) / "reports/system/calendar_ext.csv"):
        if row.get("status") != "accepted":
            continue
        try:
            seen = parse_utc(row.get("first_seen_utc", ""))
        except (ValueError, TypeError):
            seen = None
        if at is not None and (seen is None or seen > at):
            continue
        fields = [f.strip() for f in row.get("line", "").split(",")]
        if len(fields) != 3 or fields[0] not in ("NFP", "CPI", "FOMC"):
            continue
        out.append((seen, fields[0], pd.Timestamp(fields[1]).tz_convert("UTC")))
    return out


def load_events(repo, data_root, at=None):
    """{"NFP", "CPI", "FOMC": model-clock DatetimeIndex} (R-V1-15, R-V1-17); `at`: the accepted extension lines a run
    at that time used (None: all of them)."""
    core, models, _ = vendored.volmap()
    src = VENDOR / "calendars"
    with tempfile.TemporaryDirectory() as td:
        for dst, name in CAL_FILES.items():
            if not (src / name).exists():
                raise CalendarMissing(f"judge/vendor/calendars/{name} is missing")
            if sha256_file(src / name) != CAL_SHA256[name]:
                raise CalendarMissing(f"judge/vendor/calendars/{name}: sha256 differs from R-V1-15")
            shutil.copyfile(src / name, Path(td) / dst)
        ev = models.load_events(td)
    for _, kind, t in ext_lines(data_root, at):
        ev[kind] = ev[kind].append(core.to_server(pd.DatetimeIndex([t])))
    return {k: pd.DatetimeIndex(v).unique().sort_values() for k, v in ev.items()}


def system_calendar_problems(repo):
    """The system's own calendar copies (analysis/system/vendor/calendars, R-V1-15) by sha256 only."""
    probs = []
    for name, h in CAL_SHA256.items():
        p = Path(repo) / CAL_DIR / name
        if p.exists() and sha256_file(p) != h:
            probs.append(f"{name}: the system's copy differs from the register's sha256 (R-V1-15)")
    return probs


def holidays(years_to):
    _, models, _ = vendored.volmap()
    return nyse_days(models, range(2015, int(years_to) + 1), early=True)


def grid(mf, events, hol):
    """Every T2 slot of the volmap grid: day, slot, origin (model), origin_utc, F_H1, F_S, price, flags, y (bp)."""
    _, models, params = vendored.volmap()
    m1 = mf[["o", "h", "l", "c"]]
    B = models.build(m1, events, hol)
    T = B["T"]
    t2 = T["T2"]
    fh = models.predict(T, "T2", params)["M4"].to_numpy(dtype=float)
    fs = models.predict(T, "T3", params)["M4"].to_numpy(dtype=float)
    origin = pd.DatetimeIndex(t2["start"])
    ou = (origin - pd.Timedelta(hours=7)).tz_localize("America/New_York", ambiguous="raise",
                                                      nonexistent="raise").tz_convert("UTC")
    out = pd.DataFrame({
        "day": pd.DatetimeIndex(t2["day"]).strftime("%Y-%m-%d"),
        "slot": t2["slot"].to_numpy(dtype=int),
        "origin": origin,
        "origin_utc": ou,
        "F_H1": fh,
        "F_S": fs,
        "price": t2["price"].to_numpy(dtype=float),
        "nfp": t2["D_NFP"].to_numpy(dtype=int),
        "cpi": t2["D_CPI"].to_numpy(dtype=int),
        "fomc": t2["D_FOMC"].to_numpy(dtype=int),
        "hol": t2["D_HOL"].to_numpy(dtype=int),
        "y": t2["y"].to_numpy(dtype=float),
    })
    out["origin_model"] = origin.strftime("%Y-%m-%d %H:%M")
    out["origin_utc_s"] = ou.strftime("%Y-%m-%dT%H:%MZ")
    return out


def store_rows(data_root):
    """data/system/forecasts.csv as dicts (floats parsed round-trip)."""
    return read_dicts(Path(data_root) / "data/system/forecasts.csv")


def store_map(rows):
    """{(day, slot): (F_H1, F_S, price, nfp, cpi, fomc)} with NaN for an empty field."""
    def f(r, k):
        return float(r[k]) if r[k] != "" else np.nan

    out = {}
    for r in rows:
        out[(r["day"], int(r["slot"]))] = {"F_H1": f(r, "F_H1"), "F_S": f(r, "F_S"), "price": f(r, "price"),
                                           "nfp": int(r["nfp"]), "cpi": int(r["cpi"]), "fomc": int(r["fomc"]),
                                           "hol": int(r["hol"]), "origin": r["origin_model"]}
    return out
