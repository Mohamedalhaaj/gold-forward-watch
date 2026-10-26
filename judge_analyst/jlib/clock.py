"""Clocks, windows, holidays and event calendars for the analyst judge.

Spec: R-C1 (model clock = New York + 7 h), R-C3 (slot), R-AN-4 (ids), R-AN-8 (windows), R-AN-9 (holidays, embedded
here from the register so the judge does not trust the analyst's table), R-AN-10 (event calendars, the judge's own
byte copies, sha256-pinned; since §16.18 A12-D17..D19 also the live macro calendar, read at each call's
repo_head_sha), R-AN-11 (expected windows).
"""
from __future__ import annotations

import copy
import csv
import datetime as dt
import io
import os
import re
from zoneinfo import ZoneInfo

from .common import UTC, fmt_server, fmt_utc, sha256_bytes

LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")
MODEL_SHIFT = dt.timedelta(hours=7)

WINDOW_DEF = {
    # window: (zone, entry (h, m), forced exit (h, m), exchange)
    "W1": (LONDON, (8, 0), (12, 0), "LSE"),
    "W2": (NEW_YORK, (9, 30), (13, 30), "NYSE"),
}

# ---------------------------------------------------------------- model clock (R-C1)


def to_server(t: dt.datetime) -> dt.datetime:
    """UTC (aware) → model clock (naive): New York wall clock + 7 h."""
    return t.astimezone(NEW_YORK).replace(tzinfo=None) + MODEL_SHIFT


def model_to_utc(m: dt.datetime) -> dt.datetime:
    """Model clock (naive) → UTC (aware). Ambiguous or non-existent New York times raise (R-C1)."""
    x = m - MODEL_SHIFT
    a = x.replace(tzinfo=NEW_YORK, fold=0)
    b = x.replace(tzinfo=NEW_YORK, fold=1)
    if a.utcoffset() != b.utcoffset():
        raise ValueError(f"ambiguous or non-existent New York time {x}")
    return a.astimezone(UTC)


def slot_of(t_utc: dt.datetime) -> int:
    """R-C3: H1 slot = model hour − 1."""
    return to_server(t_utc).hour - 1


# ---------------------------------------------------------------- weekdays


def is_weekday(d: dt.date) -> bool:
    return d.weekday() < 5


def busday_count(a: dt.date, b: dt.date) -> int:
    """numpy.busday_count(a, b) with the default Mon-Fri week and no holidays."""
    if a == b:
        return 0
    sign = 1
    if b < a:
        a, b, sign = b, a, -1
    n = 0
    d = a
    while d < b:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return sign * n


def weekday_before(d: dt.date, k: int) -> dt.date:
    """The k-th weekday before d (k >= 1)."""
    x = d
    n = 0
    while n < k:
        x -= dt.timedelta(days=1)
        if x.weekday() < 5:
            n += 1
    return x


def next_weekday(d: dt.date) -> dt.date:
    x = d + dt.timedelta(days=1)
    while x.weekday() >= 5:
        x += dt.timedelta(days=1)
    return x


def iso_week(d: dt.date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def add_months_12(d: dt.date) -> dt.date:
    """(d + pandas.DateOffset(months=12)).date(): same month and day next year, Feb 29 → Feb 28."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


# ---------------------------------------------------------------- windows (R-AN-4, R-AN-8)


class Window:
    __slots__ = ("day", "w", "entry", "exit", "deadline", "span_lo", "call_id", "exchange", "entry_server",
                 "exit_server", "slot")

    def __init__(self, day: dt.date, w: str):
        if w not in WINDOW_DEF:
            raise ValueError(w)
        zone, (eh, em), (xh, xm), exch = WINDOW_DEF[w]
        self.day = day
        self.w = w
        self.entry = dt.datetime(day.year, day.month, day.day, eh, em, tzinfo=zone).astimezone(UTC)
        self.exit = dt.datetime(day.year, day.month, day.day, xh, xm, tzinfo=zone).astimezone(UTC)
        self.deadline = self.entry - dt.timedelta(minutes=15)
        self.span_lo = self.entry - dt.timedelta(minutes=45)
        self.call_id = f"{day.isoformat()}_{w}"
        self.exchange = exch
        self.entry_server = fmt_server(to_server(self.entry))
        self.exit_server = fmt_server(to_server(self.exit))
        self.slot = slot_of(self.entry)

    @property
    def order(self):
        return (self.day, self.w)

    def start_hi(self, t_run_min: int) -> dt.datetime:
        return self.deadline - dt.timedelta(minutes=t_run_min)

    def times(self) -> dict:
        return {"entry_utc": fmt_utc(self.entry), "exit_utc": fmt_utc(self.exit), "deadline_utc": fmt_utc(self.deadline)}

    def __repr__(self):
        return f"Window({self.call_id})"


def parse_call_id(call_id: str):
    try:
        day_s, w = call_id.split("_")
        d = dt.date.fromisoformat(day_s)
    except Exception:
        return None
    if w not in WINDOW_DEF or not is_weekday(d) or d.isoformat() != day_s:
        return None
    return d, w


def window_of(call_id: str):
    p = parse_call_id(call_id)
    return None if p is None else Window(*p)


def windows_between(d0: dt.date, d1: dt.date):
    """Every W1 and W2 of the weekdays in [d0, d1], in window order."""
    out = []
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            out.append(Window(d, "W1"))
            out.append(Window(d, "W2"))
        d += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------- holidays (R-AN-9)

HOLIDAY_HORIZON = dt.date(2027, 12, 31)
_NYSE_FULL = ["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
              "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"]
_NYSE_EARLY = ["2026-11-27", "2026-12-24", "2027-11-26"]            # close 18:00 UTC
_LSE_FULL = ["2026-12-25", "2026-12-28", "2027-01-01", "2027-03-26", "2027-03-29", "2027-05-03", "2027-05-31",
             "2027-08-30", "2027-12-27", "2027-12-28"]
_LSE_EARLY = ["2026-12-24", "2026-12-31", "2027-12-24", "2027-12-31"]  # close 12:30 UTC


def register_holiday_rows():
    """The rows R-AN-9 lists (generated 2026-10-23), as (date, exchange, kind, close_utc) tuples, sorted."""
    rows = []
    for d in _NYSE_FULL:
        rows.append((d, "NYSE", "full", ""))
    for d in _NYSE_EARLY:
        rows.append((d, "NYSE", "early", f"{d}T18:00:00Z"))
    for d in _LSE_FULL:
        rows.append((d, "LSE", "full", ""))
    for d in _LSE_EARLY:
        rows.append((d, "LSE", "early", f"{d}T12:30:00Z"))
    return sorted(rows)


class Holidays:
    """The judge's holiday view: the register's rows up to the horizon, plus rows the analyst table appends after it
    (an OPS append, R-AN-9). `table_rows` are the analyst table's rows as read (for the comparison finding)."""

    def __init__(self, table_bytes: bytes | None):
        self.rows = {}
        for d, ex, kind, close in register_holiday_rows():
            self.rows[(d, ex)] = (kind, close)
        self.table_rows = []
        self.horizon = HOLIDAY_HORIZON
        self.table_error = None
        if table_bytes is not None:
            try:
                rd = csv.reader(io.StringIO(table_bytes.decode("utf-8")))
                header = next(rd)
                if header != ["date", "exchange", "kind", "close_utc"]:
                    raise ValueError("header")
                for r in rd:
                    if not r:
                        continue
                    self.table_rows.append(tuple(r))
            except Exception as e:  # noqa: BLE001
                self.table_error = f"unreadable table ({type(e).__name__})"
        for r in self.table_rows:
            if len(r) == 4:
                try:
                    d = dt.date.fromisoformat(r[0])
                except ValueError:
                    continue
                if d > HOLIDAY_HORIZON:
                    self.rows[(r[0], r[1])] = (r[2], r[3])
                    if d > self.horizon:
                        self.horizon = d

    def mismatch_up_to_horizon(self):
        """Rows <= the register's horizon that differ from the register (both directions)."""
        reg = set(register_holiday_rows())
        tab = {r for r in self.table_rows if len(r) == 4 and r[0] <= HOLIDAY_HORIZON.isoformat()}
        return sorted(reg - tab), sorted(tab - reg)

    def is_holiday(self, day: dt.date, exchange: str) -> bool:
        return (day.isoformat(), exchange) in self.rows

    def is_nyse_full(self, day: dt.date) -> bool:
        r = self.rows.get((day.isoformat(), "NYSE"))
        return r is not None and r[0] == "full"

    def covers(self, day: dt.date) -> bool:
        return day <= self.horizon

    def window_holiday(self, win: Window) -> bool:
        return self.is_holiday(win.day, win.exchange)


# ---------------------------------------------------------------- event calendars (R-AN-10, R-V1-15)

BLS_SHA256 = "7e829d6c5acd861c276552d4086a2c639cbec03fc66242b859cd9d4fabdef45d"
FOMC_SHA256 = "dd709aee9821d0e1b4a1e9e0a8939422e92bb9520961090e31e96f4d30dc10f5"
CAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calendars")

# §16.18 A12-D17..D19 (R-AN-10, R-AN-20): the live macro calendar. Data, refreshed only by appending, read at each
# call's repo_head_sha; the build's file is the judge's own byte copy, pinned to the register's sha256 (J-D52).
MACRO_PATH = "analyst/calendars/macro_2026_2027.csv"
MACRO_BUILD_FILE = "macro_2026_2027_build.csv"
MACRO_BUILD_SHA256 = "68a4c46c76087870b4cd7d6560418457d39daf67994188b6c600740e6c44fbb0"
MACRO_HEADER = ["date", "event", "time_local", "tz", "ts_utc", "source"]
MACRO_EVENTS = ("PPI", "JOLTS", "GDP", "PCE", "RETAIL", "ISM_MFG", "ISM_SVC", "CLAIMS", "ECB")
MACRO_TZ = ("America/New_York", "Europe/Berlin")
OPS_PATH = "analyst/ops_changes.csv"
KINDS_V2 = ("nfp", "cpi", "fomc")
KINDS_V3 = KINDS_V2 + tuple(e.lower() for e in MACRO_EVENTS)      # R-AN-20's order for analyst-context/3
_TS_FORM = "%Y-%m-%d %H:%M:%S+00:00"
_HHMM = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def macro_build_bytes() -> bytes:
    """The A12 build's macro calendar: the judge's own copy, checked against the register's sha256 (A12-D17)."""
    with open(os.path.join(CAL_DIR, MACRO_BUILD_FILE), "rb") as f:
        b = f.read()
    if sha256_bytes(b) != MACRO_BUILD_SHA256:
        raise ValueError("macro calendar copy differs from A12-D17's sha256")
    return b


def _macro_table(b) -> list:
    """The file's data rows (lists of fields); raises ValueError when it is missing, not UTF-8, or its header is not
    D17's."""
    if b is None:
        raise ValueError("missing")
    rd = csv.reader(io.StringIO(b.decode("utf-8"), newline=""))
    if next(rd, None) != MACRO_HEADER:
        raise ValueError("header")
    return [r for r in rd if r]


def macro_events(b) -> list:
    """(kind, ts) of every row, the kind being `event` lower-cased and ts `ts_utc` (R-AN-10 as amended by A12-D17).
    Raises ValueError when the rows cannot be read that way: no file, not UTF-8, another header, a row of another
    width, an event that is not one of the nine, or a `ts_utc` not of D17's form."""
    out = []
    for r in _macro_table(b):
        if len(r) != len(MACRO_HEADER) or r[1] not in MACRO_EVENTS:
            raise ValueError("row")
        out.append((r[1].lower(), dt.datetime.strptime(r[4], _TS_FORM).replace(tzinfo=UTC)))
    return out


def _ops_shas(ops_bytes) -> set:
    """The `sha256` values logged for the macro calendar in analyst/ops_changes.csv (A12-D19); none if unreadable."""
    try:
        rows = csv.DictReader(io.StringIO(ops_bytes.decode("utf-8"), newline=""))
        return {r.get("sha256") for r in rows if r.get("file") == MACRO_PATH}
    except Exception:  # noqa: BLE001
        return set()


def macro_problems(b, ops_bytes, build: bytes | None = None) -> list:
    """A12-D19's rules for the macro calendar read at a commit, with that commit's ops log: [] when they hold, else
    short codes (A4 `macro_calendar`, R-AN-67). `missing`, `unreadable` (not UTF-8 or not CSV) and `header` stop the
    check; else `build_rows <n>` (build lines absent byte for byte), the first row breaking each of D17's format
    rules (`fields`, `date`, `weekday`, `event`, `time_local`, `tz`, `ts_utc`, `source`, `order` for (ts_utc, event),
    `duplicate` for (date, event)), and `sha256` (neither the build's nor one logged for this path)."""
    if b is None:
        return ["missing"]
    build = macro_build_bytes() if build is None else build
    try:
        rows = _macro_table(b)
    except ValueError as e:
        return ["header" if str(e) == "header" else "unreadable"]
    except Exception:  # noqa: BLE001
        return ["unreadable"]
    out = []
    have = set(b.split(b"\n"))
    missing = [ln for ln in build.split(b"\n")[1:] if ln and ln not in have]
    if missing:
        out.append(f"build_rows {len(missing)}")
    first = {}
    seen = set()
    prev = None
    for i, r in enumerate(rows, start=2):                     # the file's line number
        def bad(code):
            first.setdefault(code, i)
        if len(r) != len(MACRO_HEADER):
            bad("fields")
            continue
        d_s, ev, tl, tz, ts, src = r
        day = None
        try:
            day = dt.date.fromisoformat(d_s)
            if day.isoformat() != d_s:
                raise ValueError(d_s)
        except ValueError:
            bad("date")
            day = None
        if day is not None and day.weekday() >= 5:
            bad("weekday")
        if ev not in MACRO_EVENTS:
            bad("event")
        hhmm = _HHMM.match(tl)
        if not hhmm:
            bad("time_local")
        if tz not in MACRO_TZ:
            bad("tz")
        if day is not None and hhmm and tz in MACRO_TZ:
            loc = dt.datetime(day.year, day.month, day.day, int(tl[:2]), int(tl[3:]), tzinfo=ZoneInfo(tz))
            if loc.astimezone(UTC).strftime(_TS_FORM) != ts:
                bad("ts_utc")
        if not src.strip():
            bad("source")
        k = (ts, ev)
        if prev is not None and k < prev:
            bad("order")
        prev = k
        if (d_s, ev) in seen:
            bad("duplicate")
        seen.add((d_s, ev))
    for code in ("fields", "date", "weekday", "event", "time_local", "tz", "ts_utc", "source", "order", "duplicate"):
        if code in first:
            out.append(f"{code} row {first[code]}")
    sh = sha256_bytes(b)
    if sh != sha256_bytes(build) and sh not in _ops_shas(ops_bytes or b""):
        out.append("sha256")
    return out


class Events:
    def __init__(self, bls_bytes: bytes, fomc_bytes: bytes):
        if sha256_bytes(bls_bytes) != BLS_SHA256 or sha256_bytes(fomc_bytes) != FOMC_SHA256:
            raise ValueError("event calendar sha256 differs from R-V1-15")
        self.v3 = False
        self.by_kind = {"nfp": [], "cpi": [], "fomc": []}
        for r in csv.DictReader(io.StringIO(bls_bytes.decode("utf-8"))):
            ts = dt.datetime.fromisoformat(r["ts_utc"]).astimezone(UTC)
            kind = {"NFP": "nfp", "CPI": "cpi"}.get(r["event"])
            if kind:
                self.by_kind[kind].append(ts)
        for r in csv.DictReader(io.StringIO(fomc_bytes.decode("utf-8"))):
            ts = dt.datetime.strptime(r["utc_timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            self.by_kind["fomc"].append(ts)
        self._finish()
        self._macro_cache = {}

    def _finish(self):
        for k in self.by_kind:
            self.by_kind[k] = sorted(set(self.by_kind[k]))
        self.last_model_day = {k: (max(to_server(t).date() for t in v) if v else None)
                               for k, v in self.by_kind.items()}

    @classmethod
    def judge_copies(cls):
        with open(os.path.join(CAL_DIR, "bls_2026_2027.csv"), "rb") as f:
            b = f.read()
        with open(os.path.join(CAL_DIR, "fomc_2026_2027.csv"), "rb") as f:
            fo = f.read()
        return cls(b, fo)

    def with_macro(self, macro_bytes) -> "Events":
        """The `analyst-context/3` events (A12-D18): these frozen kinds plus the nine of the macro calendar
        `macro_bytes` (read at the call's repo_head_sha). Raises ValueError when the file cannot be read as rows
        (macro_events)."""
        key = sha256_bytes(macro_bytes) if macro_bytes is not None else None
        if key is not None and key in self._macro_cache:
            return self._macro_cache[key]
        rows = macro_events(macro_bytes)
        ev = copy.copy(self)
        ev.v3 = True
        ev._macro_cache = {}
        ev.by_kind = {k: list(self.by_kind[k]) for k in KINDS_V2}
        for k in KINDS_V3[3:]:
            ev.by_kind[k] = []
        for kind, ts in rows:
            ev.by_kind[kind].append(ts)
        ev._finish()
        self._macro_cache[key] = ev
        return ev

    def flags(self, model_day: dt.date):
        out = {}
        for k, ts in self.by_kind.items():
            last = self.last_model_day[k]
            if last is None or model_day > last:
                out[k] = None
            else:
                out[k] = 1 if any(to_server(t).date() == model_day for t in ts) else 0
        return out

    def times(self, model_day: dt.date):
        if self.v3:
            # A12-D18: one {"kind", "utc"} per distinct (kind, time) of the model date, by utc and then kind
            pairs = {(fmt_utc(t), k) for k, v in self.by_kind.items() for t in v if to_server(t).date() == model_day}
            return [{"kind": k, "utc": u} for u, k in sorted(pairs)]
        ts = sorted({t for v in self.by_kind.values() for t in v if to_server(t).date() == model_day})
        return [fmt_utc(t) for t in ts]

    def context_block(self, d: dt.date) -> dict:
        nd = next_weekday(d)
        return {"today": self.flags(d), "next": self.flags(nd), "today_times_utc": self.times(d),
                "next_times_utc": self.times(nd), "next_day": nd.isoformat()}
