"""Shared constants and helpers of the independent judge (xauusd-quant research/system/SYSTEM_V2_PREREG.md §3).

Written from the preregs and research/system/IMPLEMENTATION_REGISTER.md only; nothing here comes from the system's
code. Clocks (R-C1), time formats (R-C4), numbers (R-C6) and CSV rules (R-C7) follow the register.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

JUDGE_DIR = Path(__file__).resolve().parent
VENDOR = JUDGE_DIR / "vendor"

STORE_FIRST_DAY = pd.Timestamp("2026-09-01")      # v1 raw store starts (v1 §0)
LOOKBACK_FIRST = pd.Timestamp("2026-01-01")       # lab v2 lookback store, UTC days (R-V2-40)
LOOKBACK_LAST = pd.Timestamp("2026-08-31")
V2_INPUT_START = pd.Timestamp("2026-01-02 00:00")  # model clock (§2.2, R-V2-7)
V1_START_FLOOR = pd.Timestamp("2026-11-02")

K10_H = 1.049036930300697        # H10 multiplier (L2 §3.3)
K10_S = 1.0540339626212611       # S10 multiplier
ALLOWANCE = 0.10                 # $ round trip (v1 §3 item 2)
STRESS_ADD = 0.25
BUCKETS = ("CPI", "FOMC", "NFP", "REOPEN", "N_ASIA", "N_LONDON", "N_NY")
LAMBDAS = (0.025, 0.05, 0.1, 0.2, 0.4)   # L2 §9.1

SHIFT = pd.Timedelta(hours=7)


# ---------------------------------------------------------------- clocks (R-C1)
def to_model(idx):
    """UTC DatetimeIndex (tz-aware) -> model clock (America/New_York wall + 7 h), tz-naive."""
    return idx.tz_convert("America/New_York").tz_localize(None) + SHIFT


def model_to_utc(ts):
    """Model-clock time (tz-naive Timestamp) -> UTC Timestamp."""
    t = pd.Timestamp(ts) - SHIFT
    return t.tz_localize("America/New_York", ambiguous="raise", nonexistent="raise").tz_convert("UTC")


def utc_to_model(ts):
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("America/New_York").tz_localize(None) + SHIFT


# ---------------------------------------------------------------- time formats (R-C4)
def parse_utc(s):
    """'YYYY-MM-DDTHH:MM:SSZ' (or the forecast store's 'YYYY-MM-DDTHH:MMZ') -> UTC Timestamp; '' -> None."""
    if s is None or s == "":
        return None
    return pd.Timestamp(s.replace("Z", "+00:00")).tz_convert("UTC")


def iso_s(ts):
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_m(ts):
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%MZ")


def day_str(ts):
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def hhmm(minutes):
    m = int(minutes)
    return f"{m // 60:02d}:{m % 60:02d}"


def parse_hhmm(s):
    """'HH:MM' or 'HHMM' -> minutes of the day."""
    s = s.replace(":", "")
    return int(s[:2]) * 60 + int(s[2:])


def now_utc():
    return pd.Timestamp.now(tz="UTC").floor("s")


# ---------------------------------------------------------------- numbers (R-C6)
def num(s):
    """Ledger number -> float; the empty string is NaN."""
    if s is None or s == "":
        return float("nan")
    return float(s)


def rnum(x):
    """repr(float) of a finite number, '' otherwise (R-C6)."""
    x = float(x)
    return repr(x) if math.isfinite(x) else ""


def rel_equal(a, b, tol):
    """|a - b| <= tol * max(|a|, |b|); NaN equals NaN only (definedness must agree)."""
    a, b = float(a), float(b)
    fa, fb = math.isfinite(a), math.isfinite(b)
    if not fa or not fb:
        return (math.isnan(a) and math.isnan(b)) or (a == b)
    return abs(a - b) <= tol * max(abs(a), abs(b))


def is_numeric_text(s):
    if s == "":
        return False
    try:
        float(s)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------- files
def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


def read_csv_text(text):
    """CSV text -> (header, rows as lists of strings). R-C7: one header line, then rows."""
    if text is None or text == "":
        return [], []
    rd = list(csv.reader(io.StringIO(text)))
    if not rd:
        return [], []
    return rd[0], rd[1:]


def read_csv(p):
    p = Path(p)
    if not p.exists():
        return [], []
    return read_csv_text(p.read_text(encoding="utf-8"))


def read_dicts(p):
    h, rows = read_csv(p)
    return [dict(zip(h, r)) for r in rows]


def write_csv_append(p, header, rows):
    """Append rows to an append-only CSV (header written when the file is created). LF, csv module default."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists() or p.stat().st_size == 0
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if new:
        w.writerow(header)
    for r in rows:
        w.writerow(r)
    with open(p, "a", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())


def write_text_atomic(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(p)


def load_json(p):
    p = Path(p)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------- calendars
def weekdays_between(a, b):
    """Weekdays in (a, b] for dates a, b (np.busday_count(a + 1 day, b + 1 day)); holidays not removed."""
    a = pd.Timestamp(a).normalize() + pd.Timedelta(days=1)
    b = pd.Timestamp(b).normalize() + pd.Timedelta(days=1)
    return int(np.busday_count(a.date(), b.date()))


def nyse_days(models, years, early=True):
    """Union over calendar years of models.nyse_holidays (full closures and early closes; R-V1-16). With
    early=False only the full closures (L3 block counts)."""
    out = pd.DatetimeIndex([])
    for y in years:
        if early:
            out = out.union(models.nyse_holidays(f"{y}-01-01", f"{y}-12-31"))
        else:
            import pandas_market_calendars as mcal
            cal = mcal.get_calendar("NYSE")
            a, b = f"{y}-01-01", f"{y}-12-31"
            sched = cal.schedule(a, b)
            out = out.union(pd.bdate_range(a, b).difference(sched.index.normalize()))
    return out.normalize()
