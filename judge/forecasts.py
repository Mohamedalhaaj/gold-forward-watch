"""Recomputation of the forecast store (v1 §1; IMPLEMENTATION_REGISTER R-V1-14 .. R-V1-20).

The grid is the vendored volmap's `models.build` on the model-frame mids of every loaded raw day, then
`predict(T, "T2")["M4"]` = F_H1 and `predict(T, "T3")["M4"]` = F_S (bp), with the frozen discovery parameters. Events:
the system's committed calendar data (the official NFP/CPI/FOMC dates, R-V1-15) read with the vendored
`models.load_events`, plus the extension lines the system accepted (R-V1-17, reports/system/calendar_ext.csv).
Holidays: R-V1-16.
"""
import csv
import io
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import vendored
from .common import nyse_days, read_dicts

CAL_DIR = "analysis/system/vendor/calendars"     # data files only (R-V1-15); nothing under analysis/ is executed
CAL_FILES = {"bls_2015_2024.csv": "bls_2026_2027.csv", "fomc_2015_2024.csv": "fomc_2026_2027.csv"}


class CalendarMissing(Exception):
    pass


def load_events(repo, data_root):
    """{"NFP", "CPI", "FOMC": model-clock DatetimeIndex} (R-V1-15, R-V1-17)."""
    core, models, _ = vendored.volmap()
    src = Path(repo) / CAL_DIR
    with tempfile.TemporaryDirectory() as td:
        for dst, name in CAL_FILES.items():
            if not (src / name).exists():
                raise CalendarMissing(f"{CAL_DIR}/{name} is missing")
            shutil.copyfile(src / name, Path(td) / dst)
        ev = models.load_events(td)
    for row in read_dicts(Path(data_root) / "reports/system/calendar_ext.csv"):
        if row.get("status") != "accepted":
            continue
        fields = next(csv.reader(io.StringIO(row["line"])))
        if len(fields) < 2 or fields[0] not in ev:
            continue
        t = core.to_server(pd.DatetimeIndex(pd.to_datetime([fields[1]], utc=True)))
        ev[fields[0]] = ev[fields[0]].append(t)
    return {k: pd.DatetimeIndex(v).unique().sort_values() for k, v in ev.items()}


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
