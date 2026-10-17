"""BLOCKING (SYSTEM_V1_PREREG.md §1): the vendored volmap path reproduces the client terminal's logged forecasts.

Fixtures (tests/system/fixtures/hycm_v113, gzipped copies of the files VolMapBand.ex5 v1.13 wrote with LogCsv = true
on the client's HYCM terminal; SOURCE_SHA256SUMS holds the hashes of the uncompressed originals):
- VolMap_XAUUSD_m1.csv / _h1.csv: ts_srv (server-clock epoch seconds), o, h, l, c
- VolMap_XAUUSD_events.csv: server_time, kind
- VolMap_XAUUSD_clock.csv: the server clock the indicator used (FIXED, 0 s = UTC)
- VolMap_XAUUSD_out.csv: its forecasts; origins on the model clock (New York + 7), the times compare_terminal_log.py
  checks.

The server clock is UTC, so a logged time maps to the model clock exactly as a Dukascopy UTC time does (bars.to_model,
the vendored core.to_server). PASS: every logged origin is a row of the vendored models.build/predict output, with
F_H1 and F_S defined where the terminal's status is 0, each within 1e-9 relative.
"""
import gzip
import hashlib

import numpy as np
import pandas as pd
import pytest

import bars
import forecasts

FIX = pytest.FIXTURES / "hycm_v113"


def _read(name):
    with gzip.open(FIX / f"VolMap_XAUUSD_{name}.csv.gz", "rt") as f:
        return pd.read_csv(f, float_precision="round_trip")


def _epoch_index(sec):
    return pd.DatetimeIndex(pd.to_datetime(np.asarray(sec, dtype="int64"), unit="s", utc=True))


def _hycm_inputs():
    clock = _read("clock").iloc[0]
    assert (str(clock.rule), int(clock.std_s)) == ("FIXED", 0), "the log's server clock must be UTC"
    raw = _read("m1")
    m1 = pd.DataFrame(raw[["o", "h", "l", "c"]].values, columns=["o", "h", "l", "c"],
                      index=bars.to_model(_epoch_index(raw.ts_srv)))
    ev = _read("events")
    t = pd.to_datetime(ev.server_time, format="%Y.%m.%d %H:%M:%S", utc=True)
    events = {k: bars.to_model(pd.DatetimeIndex(t[ev.kind == k])).sort_values() for k in ("NFP", "CPI", "FOMC")}
    return m1, events


def test_fixture_hashes_match_the_source_files():
    sums = dict(line.split()[::-1] for line in (FIX / "SOURCE_SHA256SUMS").read_text().splitlines())
    for name, digest in sums.items():
        with gzip.open(FIX / f"{name}.gz", "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == digest, name


def test_calendar_events_match_the_logged_events():
    """The shared calendars give the same NFP/CPI/FOMC times as the terminal logged, over the log's span."""
    m1, logged = _hycm_inputs()
    cal = forecasts.load_events()
    lo, hi = m1.index.min().normalize(), m1.index.max().normalize() + pd.Timedelta(days=1)
    for k in ("NFP", "CPI", "FOMC"):
        c = cal[k][(cal[k] >= lo) & (cal[k] < hi)]
        assert list(c) == list(logged[k]), k


def test_vendored_path_reproduces_terminal_forecasts():
    m1, events = _hycm_inputs()
    grid = forecasts.compute(m1, events, forecasts.holidays())
    origin = ((pd.DatetimeIndex(grid.origin) - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")).astype("int64")
    g = grid.set_index(pd.Index(origin, name="origin"))
    out = _read("out")
    assert len(out) >= 24
    bad = []
    for _, r in out.iterrows():
        o = int(r.origin)
        assert o in g.index, f"logged origin {pd.to_datetime(o, unit='s')} is not a row of the vendored grid"
        p = g.loc[o]
        if int(r.status) != 0:
            assert not np.isfinite(p.F_H1), f"{o}: terminal undefined, vendored defined"
            continue
        for col in ("F_H1", "F_S"):
            ref = float(r[col])
            rel = abs(p[col] - ref) / abs(ref)
            if not (rel < 1e-9):
                bad.append(f"{pd.to_datetime(o, unit='s')} {col}: vendored {p[col]!r} terminal {ref!r} rel {rel:.3e}")
    assert not bad, "\n".join(bad)


def test_the_same_with_the_calendar_events():
    """Run with the calendars (the cloud's event source) instead of the logged list: identical forecasts."""
    m1, events = _hycm_inputs()
    hol = forecasts.holidays()
    a = forecasts.compute(m1, events, hol)
    b = forecasts.compute(m1, forecasts.load_events(), hol)
    np.testing.assert_array_equal(a.F_H1.values, b.F_H1.values)
    np.testing.assert_array_equal(a.F_S.values, b.F_S.values)
