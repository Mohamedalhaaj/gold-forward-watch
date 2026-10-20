"""Lab v2 data: the input-only lookback, v1's committed raw days, the mid M1 and the seed bars.
SYSTEM_V2_PREREG.md §0, §2.2 and §2.5 item 3. FROZEN (lab v2): bar rules and the store rules v2 reads.

Sources, by UTC day (each day has exactly one source):
- 2026-01-01 .. 2026-08-31: the lab v2 lookback store, data/system/lab_v2/lookback/raw/YYYY/MM/DD/{BID,ASK}.bi5, with
  its own days file data/system/lab_v2/lookback/days.csv (input only, §0). UTC 2026-01-01 is in it because the seed
  input starts at 2026-01-02 00:00 model = 2026-01-01 22:00 UTC.
- 2026-09-01 on: v1's committed raw store data/system/raw with data/system/days.csv, read-only (§2.5 item 3). Lab v2
  never writes there and never fetches those days.
Together they are the input-only history 2026-01-02 .. START−1 of §0 and the forward days from START.

A (day, side) is read iff its days-file row is `ok` as of the run time (rows with fetched_utc <= now; the stores
write one row per (day, side)). Its file must have the row's sha256, else StoreMismatch (v2 halts). A v1 day
is read only if it is before complete_utc: v1's rule, the end (exclusive, UTC) of the longest run of UTC days from
2026-09-01 whose two sides are both final (ok or missing) as of the run time, so v2 sees exactly the M1 that v1's
forecasts see.

Arithmetic (§2.2, shared exactly by system and judge):
- decode: v1 bi5.decode, each price int32 / 1000.0 in IEEE double, timestamp = UTC day + sec;
- mid M1: pipeline/build_parquet.py line for line: per side concat, ts from ms (UTC), sort by ts, drop duplicate ts
  keeping the first; outer join of bid and ask on ts; mid_x = (bid_x + ask_x) / 2 in double for x in o, h, l, c.
  Flats (zero-volume minutes) are kept; a minute present on one side only has a NaN mid;
- model clock: harness._to_server = America/New_York wall clock + 7 h (the same function as volmap core.to_server);
- seed input: model time >= 2026-01-02 00:00 for every seed, never windowed; model weekdays only (Monday-Friday, as
  harness._slice does before aggregating); columns o, h, l, c = the mid;
- seed bars: harness._bars(input, TF) (resample label = closed = left; o = first, h = max, l = min, c = last,
  n = count of c, over the minutes present, NaN skipped; then dropna), then day = the bar start's model date
  (harness.load). No volume-validity filter.
"""
import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

import bi5
import v2paths

HARNESS_PATH = v2paths.VENDOR / "hunt" / "harness.py"
CANDIDATES = v2paths.VENDOR / "hunt" / "candidates"
LOOKBACK_FIRST = pd.Timestamp("2026-01-01")      # UTC days of the lookback store
LOOKBACK_LAST = pd.Timestamp("2026-08-31")
V1_FIRST = pd.Timestamp("2026-09-01")            # v1's raw store starts here
INPUT_START = pd.Timestamp("2026-01-02 00:00")   # model clock, every seed
DAYS_COLS = ["day", "side", "status", "bytes", "sha256", "records", "vol_minutes", "fetched_utc"]
SIDES = ("BID", "ASK")

_HARNESS = None


class StoreMismatch(RuntimeError):
    """A raw file the days file lists as ok is missing or differs from its recorded sha256."""


def harness():
    """The vendored, byte-identical hunt harness (loaded by file path, once)."""
    global _HARNESS
    if _HARNESS is None:
        spec = importlib.util.spec_from_file_location("v2_vendored_harness", HARNESS_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HARNESS = mod
    return _HARNESS


def to_utc(t):
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def raw_path(raw_dir, day, side):
    day = pd.Timestamp(day)
    return Path(raw_dir) / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}" / f"{side}.bi5"


def read_days(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=DAYS_COLS)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def final_status(days_df, now=None):
    """{(day, side): (status, sha256)} over the rows with fetched_utc <= now (None = all rows); as in v1
    fetch.final_status, a later row of the same (day, side) would win (the stores write one row per (day, side))."""
    out = {}
    for r in days_df.itertuples():
        if now is not None and to_utc(r.fetched_utc) > to_utc(now):
            continue
        out[(r.day, r.side)] = (r.status, r.sha256)
    return out


def v1_complete_utc(v1_data, now):
    """v1's complete-through rule (data/system/days.csv): end (exclusive, UTC) of the longest run of UTC days from
    2026-09-01 whose two sides are final as of `now`; a day counts only once it is complete (now >= day + 26 h)."""
    st = final_status(read_days(Path(v1_data) / "days.csv"), now)
    last = (to_utc(now).tz_localize(None) - pd.Timedelta(hours=26)).normalize()
    end = V1_FIRST
    if last >= V1_FIRST:
        for d in pd.date_range(V1_FIRST, last, freq="D"):
            key = d.strftime("%Y-%m-%d")
            if all((key, s) in st for s in SIDES):
                end = d + pd.Timedelta(days=1)
            else:
                break
    return end.tz_localize("UTC")


def _read_side(raw_dir, day, side, sha):
    p = raw_path(raw_dir, day, side)
    if not p.exists():
        raise StoreMismatch(f"{p}: listed as ok but missing")
    body = p.read_bytes()
    if hashlib.sha256(body).hexdigest() != sha:
        raise StoreMismatch(f"{p}: sha256 differs from its days-file row")
    return bi5.decode(body, day)


def source_days(lookback_dir, v1_data, now, complete_utc):
    """[(UTC day, side, raw_dir, sha256)] of every (day, side) lab v2 reads at `now`, in day then side order."""
    out = []
    lb = final_status(read_days(Path(lookback_dir) / "days.csv"), now)
    for (d, s), (status, sha) in lb.items():
        t = pd.Timestamp(d)
        if status == "ok" and LOOKBACK_FIRST <= t <= LOOKBACK_LAST:
            out.append((t, s, Path(lookback_dir) / "raw", sha))
    v1 = final_status(read_days(Path(v1_data) / "days.csv"), now)
    cut = to_utc(complete_utc).tz_localize(None)
    for (d, s), (status, sha) in v1.items():
        t = pd.Timestamp(d)
        if status == "ok" and t >= V1_FIRST and t < cut:
            out.append((t, s, Path(v1_data) / "raw", sha))
    return sorted(out, key=lambda x: (x[0], SIDES.index(x[1])))


def load_side(frames, side):
    """pipeline/build_parquet.load_side on in-memory dukascopy-node frames (side = "bid" or "ask")."""
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp"]).sort_values("ts")
    df = df.drop_duplicates(subset="ts", keep="first").set_index("ts")
    return df.rename(columns={"open": f"{side}_o", "high": f"{side}_h", "low": f"{side}_l", "close": f"{side}_c",
                              "volume": f"{side}_vol"})


def build_m1(bid_frames, ask_frames):
    """pipeline/build_parquet.main without the file I/O: UTC-indexed bid_*, ask_*, mid_*, spread_c."""
    empty = [bi5.decode(b"", "2026-01-01")]
    bid, ask = load_side(bid_frames or empty, "bid"), load_side(ask_frames or empty, "ask")
    m = bid.join(ask, how="outer")
    for p in "ohlc":
        m[f"mid_{p}"] = (m[f"bid_{p}"] + m[f"ask_{p}"]) / 2
    m["spread_c"] = m["ask_c"] - m["bid_c"]
    return m


def load_m1(lookback_dir, v1_data, now, complete_utc):
    """The UTC mid M1 of every (day, side) lab v2 reads at `now` (raises StoreMismatch on a bad raw file)."""
    frames = {"BID": [], "ASK": []}
    for day, side, raw_dir, sha in source_days(lookback_dir, v1_data, now, complete_utc):
        frames[side].append(_read_side(raw_dir, day, side, sha))
    if not frames["BID"] and not frames["ASK"]:
        return None
    return build_m1(frames["BID"], frames["ASK"])


def model_frame(m):
    """Model-clock M1 (o, h, l, c = the mid; bid_*, ask_*, volumes kept), sorted by model time."""
    f = m.copy()
    f.index = harness()._to_server(f.index)
    f = f.rename(columns={"mid_o": "o", "mid_h": "h", "mid_l": "l", "mid_c": "c"})
    return f.sort_index(kind="mergesort")


def seed_input(mf):
    """The seed input: model time >= 2026-01-02 00:00, model weekdays only, columns o, h, l, c (the mid)."""
    f = mf[(mf.index >= INPUT_START) & (mf.index.dayofweek < 5)]
    return f[["o", "h", "l", "c"]]


def seed_bars(m_in, tf):
    """harness._bars on the seed input, plus the model date `day` (exactly as harness.load builds them)."""
    b = harness()._bars(m_in, tf)
    b["day"] = b.index.normalize()
    return b


def minutes_of_day(mf, day):
    """The model day's M1 rows (for execution)."""
    day = pd.Timestamp(day).normalize()
    return mf[(mf.index >= day) & (mf.index < day + pd.Timedelta(days=1))]


def forecast_slots(store_path):
    """{(YYYY-MM-DD, slot): (F_H1, F_S)} of v1's write-once forecast store (data/system/forecasts.csv), read-only.
    An empty field is NaN."""
    p = Path(store_path)
    if not p.exists():
        return {}
    df = pd.read_csv(p, dtype={"day": str, "origin_model": str, "origin_utc": str, "computed_utc": str},
                     keep_default_na=False, na_values=[""], float_precision="round_trip")
    out = {}
    for r in df.itertuples():
        out[(r.day, int(r.slot))] = (float(r.F_H1) if pd.notna(r.F_H1) else np.nan,
                                     float(r.F_S) if pd.notna(r.F_S) else np.nan)
    return out
