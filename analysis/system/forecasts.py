"""The shared forecast (SYSTEM_V1_PREREG.md §1, Amendment A1 items 7 and 10). FROZEN: vendored volmap adapter,
calendars and the write-once store rules.

F_H1 (T2 M4) and F_S (T3 M4), in bp, per model-clock H1 slot, from the vendored byte-identical core.py, models.py and
discovery_params.json, used exactly as frozen:
- events: the official NFP/CPI/FOMC dates of the FROZEN calendars for 2026-2027 (vendor/calendars, the shared CSVs
  built from mt5/make_volmap_events.py), read by models.load_events, which wants files named like the 2015-2024 ones,
  so they are copied under those names into a temporary folder; plus the accepted rows of the calendar extension;
- holidays: models.nyse_holidays (pandas_market_calendars), computed per calendar year from 2015 through the year
  after the run, so a later year never changes an earlier one (for 2015-2027 it equals the range VolMapCoef.mqh
  embeds).

Calendar extension (A1 item 10; the file is append-only and not FROZEN): analysis/system/calendars_ext/events.csv,
lines `event,ts_utc,source_url`. The cloud run reviews a line the first time it sees it and records it in the
append-only reports/system/calendar_ext.csv, with that first-seen time, as accepted or rejected for good. A line is
accepted iff its event is NFP, CPI or FOMC, ts_utc carries an explicit offset, the source is the official page
(https://www.bls.gov/ for NFP and CPI, https://www.federalreserve.gov/ for FOMC), the event lies after the last event of
its kind in the frozen calendar, and it is at least 14 days after the line was first seen (so at least 14 days after
its commit). Accepted lines stay in use even if the file later loses them; that, and every rejection, is reported.
The calendar horizon is the earliest of the last NFP, CPI and FOMC dates; run.py warns from 60 days before it.

Store (`data/system/forecasts.csv`): one row per slot, written once, when every M1 minute of the slot's origin hour
is final: origin_utc < complete_utc (A1 item 7), so the stored price is the origin's own open; and never recomputed.
Because every volmap feature uses rows strictly before the origin, the value is the same whatever later data exist;
the tripwire recomputes the store's last days from the raw files and halts on a difference of F_H1, F_S or price
beyond 1e-12 relative, or of definedness.
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
HOLIDAY_FIRST_YEAR = 2015
EVENT_KINDS = ("NFP", "CPI", "FOMC")
EXT_FILE = HERE / "calendars_ext" / "events.csv"
EXT_HEADER = "event,ts_utc,source_url"
EXT_SEEN_COLS = ["line", "first_seen_utc", "status", "reason", "run_id", "head_sha"]
EXT_LEAD = pd.Timedelta(days=14)
EXT_SOURCE = {"NFP": "https://www.bls.gov/", "CPI": "https://www.bls.gov/", "FOMC": "https://www.federalreserve.gov/"}
REL_TOL = 1e-12
STORE_COLUMNS = ["day", "slot", "origin_model", "origin_utc", "F_H1", "F_S", "price", "y_bp", "nfp", "cpi", "fomc",
                 "hol", "computed_utc"]
K10_HOUR = 1.049036930300697
K10_SESS = 1.0540339626212611


def frozen_params():
    return json.loads(PARAMS_PATH.read_text())


def load_events(cal_dir=CAL_DIR, ext=None):
    """{kind: model-clock DatetimeIndex} of the frozen calendars, plus `ext` ({kind: [UTC timestamps]}, the accepted
    extension rows from ext_review)."""
    with tempfile.TemporaryDirectory() as d:
        shutil.copyfile(Path(cal_dir) / "bls_2026_2027.csv", Path(d) / "bls_2015_2024.csv")
        shutil.copyfile(Path(cal_dir) / "fomc_2026_2027.csv", Path(d) / "fomc_2015_2024.csv")
        ev = models.load_events(d)
    for k, ts in (ext or {}).items():
        if len(ts):
            add = bars.to_model(pd.DatetimeIndex([pd.Timestamp(t).tz_convert("UTC") for t in ts]))
            ev[k] = ev[k].append(add).unique().sort_values()
    return ev


def holidays(through_year=None):
    """NYSE full closures and early closes (models.nyse_holidays as frozen), per calendar year from 2015 through
    `through_year` (default: the year after the current UTC year): D_HOL, and lab-ineligible days."""
    y1 = int(through_year) if through_year else pd.Timestamp.now(tz="UTC").year + 1
    out = None
    for y in range(HOLIDAY_FIRST_YEAR, y1 + 1):
        h = models.nyse_holidays(f"{y}-01-01", f"{y}-12-31")
        out = h if out is None else out.union(h)
    return out


def full_closures(through_year=None):
    """NYSE full closures only (the closed part of models.nyse_holidays), per year: L3 block expected-origin counts."""
    import pandas_market_calendars as mcal
    cal = mcal.get_calendar("NYSE")
    y1 = int(through_year) if through_year else pd.Timestamp.now(tz="UTC").year + 1
    out = set()
    for y in range(HOLIDAY_FIRST_YEAR, y1 + 1):
        a, b = f"{y}-01-01", f"{y}-12-31"
        out |= set(pd.bdate_range(a, b).difference(cal.schedule(a, b).index.normalize()))
    return out


# ---------------------------------------------------------------- calendar extension and horizon (A1 item 10)
def read_ext_lines(path=EXT_FILE):
    """The data lines of the extension file (header checked; blank lines skipped). A missing file has none."""
    path = Path(path)
    if not path.exists():
        return []
    lines = [ln.rstrip("\r") for ln in path.read_text(encoding="utf-8").split("\n")]
    if not lines or lines[0] != EXT_HEADER:
        raise ValueError(f"{path}: the header must be {EXT_HEADER!r}")
    return [ln for ln in lines[1:] if ln.strip()]


def _base_last_utc():
    ev = load_events()
    return {k: bars.model_to_utc(ev[k].max()) for k in EVENT_KINDS}


def parse_ext_line(line, base_last_utc=None):
    """(kind, UTC timestamp) of a well-formed extension line, or (None, reason)."""
    parts = line.split(",")
    if len(parts) != 3:
        return None, "not three fields event,ts_utc,source_url"
    kind, ts, src = (x.strip() for x in parts)
    if kind not in EXT_SOURCE:
        return None, f"unknown event {kind!r}"
    try:
        t = pd.Timestamp(ts)
    except (ValueError, TypeError):
        return None, f"bad ts_utc {ts!r}"
    if t.tzinfo is None:
        return None, "ts_utc needs an explicit UTC offset"
    t = t.tz_convert("UTC")
    if not src.startswith(EXT_SOURCE[kind]):
        return None, f"source is not the official {EXT_SOURCE[kind]} page"
    last = (base_last_utc or _base_last_utc())[kind]
    if t <= last:
        return None, "inside the frozen calendar range"
    return (kind, t), None


def ext_review(lines, seen, now_utc, run_id, head_sha):
    """Review the extension file against the append-only record of lines seen before.

    lines: read_ext_lines(); seen: rows of reports/system/calendar_ext.csv (dicts with EXT_SEEN_COLS).
    Returns (new seen rows, accepted {kind: [UTC timestamps]}, problems)."""
    now = pd.Timestamp(now_utc)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    base = _base_last_utc()
    known = {r["line"] for r in seen}
    new_rows, problems = [], []
    for ln in lines:
        if ln in known:
            continue
        known.add(ln)
        parsed, why = parse_ext_line(ln, base)
        if parsed and parsed[1] < now + EXT_LEAD:
            why = "less than 14 days after it was first seen"
        if why:
            problems.append(f"calendar extension line rejected ({why}): {ln}")
        new_rows.append({"line": ln, "first_seen_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "status": "rejected" if why else "accepted", "reason": why or "", "run_id": run_id,
                         "head_sha": head_sha})
    cur = set(lines)
    for r in seen:
        if r["status"] == "accepted" and r["line"] not in cur:
            problems.append(f"an accepted calendar extension line was changed or removed (it stays in use): "
                            f"{r['line']}")
    accepted = {k: [] for k in EVENT_KINDS}
    for r in list(seen) + new_rows:
        if r["status"] == "accepted":
            parsed, why = parse_ext_line(r["line"], base)
            if parsed is None:
                problems.append(f"an accepted calendar extension line no longer parses ({why}): {r['line']}")
            elif parsed[1] not in accepted[parsed[0]]:
                accepted[parsed[0]].append(parsed[1])
    return new_rows, accepted, problems


def calendar_horizon(events):
    """The last date the calendars cover: the earliest of the last NFP, CPI and FOMC model dates."""
    return min(pd.DatetimeIndex(events[k]).max().normalize() for k in EVENT_KINDS)


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
    ready = origin_utc < complete_utc                 # the whole origin hour is final, so price is its own open
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
    """Recompute the last `last_days` stored days from the raw files: a difference of F_H1, F_S or price beyond 1e-12
    relative, or a change of definedness, is non-determinism or code drift. Returns the differences (empty = OK)."""
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
        for col in ("F_H1", "F_S", "price"):
            a, b = float(r[col]) if pd.notna(r[col]) else np.nan, float(g.loc[k, col])
            if np.isfinite(a) != np.isfinite(b) or (np.isfinite(a) and abs(a - b) > REL_TOL * max(abs(a), abs(b))):
                out.append(f"{k} {col}: store {a!r} vs recomputed {b!r}")
    return out
