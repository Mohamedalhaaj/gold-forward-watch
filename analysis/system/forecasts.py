"""The shared forecast (SYSTEM_V1_PREREG.md §1). FROZEN: vendored volmap adapter and the write-once store rules.

F_H1 (T2 M4) and F_S (T3 M4), in bp, per model-clock H1 slot, from the vendored byte-identical core.py, models.py and
discovery_params.json, used exactly as frozen:
- events: the official NFP/CPI/FOMC dates (vendor/calendars, the shared CSVs built from mt5/make_volmap_events.py),
  read by models.load_events, which wants files named like the 2015-2024 ones, so they are copied under those names
  into a temporary folder;
- holidays: models.nyse_holidays over 2015-2027, the range VolMapCoef.mqh embeds.

Store (`data/system/forecasts.csv`): one row per slot, written once, when every M1 minute before the slot's origin is
final (its UTC day file committed, or a permanent missing_day), and never recomputed. Because every volmap feature
uses rows strictly before the origin, the value is the same whatever later data exist; the tripwire in run.py
recomputes the store from the raw files and halts on any difference.
"""
import csv
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

import bars
import models

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
PARAMS_PATH = VENDOR / "volmap" / "discovery_params.json"
CAL_DIR = VENDOR / "calendars"
HOLIDAY_RANGE = ("2015-01-01", "2027-12-31")
STORE_COLUMNS = ["day", "slot", "origin_model", "origin_utc", "F_H1", "F_S", "price", "y_bp", "nfp", "cpi", "fomc",
                 "hol", "computed_utc"]
K10_HOUR = 1.049036930300697
K10_SESS = 1.0540339626212611


def frozen_params():
    return json.loads(PARAMS_PATH.read_text())


def load_events(cal_dir=CAL_DIR):
    with tempfile.TemporaryDirectory() as d:
        shutil.copyfile(Path(cal_dir) / "bls_2026_2027.csv", Path(d) / "bls_2015_2024.csv")
        shutil.copyfile(Path(cal_dir) / "fomc_2026_2027.csv", Path(d) / "fomc_2015_2024.csv")
        return models.load_events(d)


def holidays():
    """NYSE full closures and early closes (models.nyse_holidays as frozen): D_HOL, and lab-ineligible days."""
    return models.nyse_holidays(*HOLIDAY_RANGE)


def full_closures():
    """NYSE full closures only (the closed part of models.nyse_holidays): L3 block expected-origin counts."""
    import pandas_market_calendars as mcal
    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(*HOLIDAY_RANGE)
    return set(pd.bdate_range(*HOLIDAY_RANGE).difference(sched.index.normalize()))


def event_days(events):
    """Model dates with an NFP, CPI or FOMC release."""
    return {pd.Timestamp(t).normalize() for k in ("NFP", "CPI", "FOMC") for t in events.get(k, [])}


def compute(m1, events, hol, fz=None):
    """models.build + predict on a model-clock M1 frame (o, h, l, c): one row per H1 grid slot, in grid order.

    y_bp is the realised T2 target of the slot (NaN unless >= 48 minutes and H > L); F_H1/F_S are NaN when undefined."""
    fz = fz or frozen_params()
    B = models.build(m1, events, hol)
    T = B["T"]
    t2, t3 = T["T2"], T["T3"]
    p = fz["params"]
    F2 = models.predict(T, "T2", p)["M4"].values
    F3 = models.predict(T, "T3", p)["M4"].values
    return pd.DataFrame({
        "day": t2.day.values, "wd": t2.wd.values, "slot": t2.slot.values, "origin": t2.start.values,
        "F_H1": F2, "F_S": F3, "price": t2.price.values.astype(float), "y_bp": t2.y.values.astype(float),
        "nfp": t2.D_NFP.values.astype(int), "cpi": t2.D_CPI.values.astype(int), "fomc": t2.D_FOMC.values.astype(int),
        "hol": t2.D_HOL.values.astype(int),
        "y3_bp": t3.y.values.astype(float),
    })


# ---------------------------------------------------------------- the write-once store
def _num(x):
    return "" if not np.isfinite(x) else repr(float(x))


def read_store(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=STORE_COLUMNS)
    df = pd.read_csv(path, dtype={"day": str, "origin_model": str, "origin_utc": str, "computed_utc": str},
                     keep_default_na=False, na_values=[""], float_precision="round_trip")
    return df


def new_rows(grid, store, complete_utc, now_utc):
    """Rows of `grid` (compute() output) whose origin is final and that are not in the store yet.

    y_bp is not stored here: it is known only after the slot ends; L3 reads it from the raw files."""
    have = set(zip(store.day.astype(str), store.slot.astype(int))) if len(store) else set()
    origin_utc = bars.model_to_utc(pd.DatetimeIndex(grid.origin))
    ready = origin_utc <= complete_utc
    rows = []
    for i in np.flatnonzero(ready):
        g = grid.iloc[i]
        key = (pd.Timestamp(g.day).strftime("%Y-%m-%d"), int(g.slot))
        if key in have:
            continue
        rows.append({
            "day": key[0], "slot": key[1], "origin_model": pd.Timestamp(g.origin).strftime("%Y-%m-%d %H:%M"),
            "origin_utc": origin_utc[i].strftime("%Y-%m-%dT%H:%MZ"), "F_H1": _num(g.F_H1), "F_S": _num(g.F_S),
            "price": _num(g.price), "y_bp": "", "nfp": int(g.nfp), "cpi": int(g.cpi), "fomc": int(g.fomc),
            "hol": int(g.hol), "computed_utc": now_utc,
        })
    return rows


def append_store(path, rows):
    path = Path(path)
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=STORE_COLUMNS, lineterminator="\n")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def tripwire(store, grid, last_days=5):
    """Recompute the last `last_days` stored days from the raw files: any F difference > 1e-9 relative, or a change of
    definedness, is non-determinism or code drift. Returns a list of differences (empty = OK)."""
    if not len(store):
        return []
    days = sorted(store.day.unique())[-last_days:]
    g = grid.assign(dkey=pd.DatetimeIndex(grid.day).strftime("%Y-%m-%d")).set_index(["dkey", "slot"])
    out = []
    for _, r in store[store.day.isin(days)].iterrows():
        k = (r.day, int(r.slot))
        if k not in g.index:
            out.append(f"{k}: not in the recomputed grid")
            continue
        for col in ("F_H1", "F_S"):
            a, b = float(r[col]) if pd.notna(r[col]) else np.nan, float(g.loc[k, col])
            if np.isfinite(a) != np.isfinite(b) or (np.isfinite(a) and abs(a - b) > 1e-9 * abs(a)):
                out.append(f"{k} {col}: store {a!r} vs recomputed {b!r}")
    return out
