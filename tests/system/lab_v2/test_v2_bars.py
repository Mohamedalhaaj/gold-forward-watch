"""Bar arithmetic (§2.2, §4): decode, the mid M1 (build_parquet), the model clock, the fixed input start, model
weekends dropped, and the seed bars against the hunt harness's own `_bars` and against a plain re-implementation."""
import lzma
import struct

import numpy as np
import pandas as pd
import pytest

import bars as v1bars
import bi5
import core
import v2_data

DUKA = pytest.FIXTURES / "duka"


def fixture_frames():
    bid = bi5.decode((DUKA / "2026-10-16_BID.bi5").read_bytes(), "2026-10-16")
    ask = bi5.decode((DUKA / "2026-10-16_ASK.bi5").read_bytes(), "2026-10-16")
    return bid, ask


def test_decode_is_int32_over_1000_in_double():
    raw = lzma.decompress((DUKA / "2026-10-16_ASK.bi5").read_bytes(), format=lzma.FORMAT_ALONE)
    ask = fixture_frames()[1]
    for i in (0, 700, 1439):
        sec, o, c, lo, hi, v = struct.unpack_from(">5if", raw, 24 * i)
        assert ask.open[i] == o / 1000.0 and ask.close[i] == c / 1000.0
        assert ask.low[i] == lo / 1000.0 and ask.high[i] == hi / 1000.0 and ask.volume[i] == np.float32(v)
        assert ask.timestamp[i] == int(pd.Timestamp("2026-10-16").value // 10**6) + sec * 1000


def test_mid_builder_equals_v1_and_build_parquet_logic():
    """v2's builder is v1 bars.build_m1 (itself proved equal to the vendored build_parquet.py by v1's tests) without
    v1's 2026-09-01 guard: identical frames on the fixture day, with one-sided minutes and a duplicate."""
    bid, ask = fixture_frames()
    ask = ask.drop(index=[10, 11, 500])
    bid = pd.concat([bid, bid.iloc[[5]].assign(close=1.0)], ignore_index=True)   # duplicate ts: keep the first
    a = v2_data.build_m1([bid], [ask])
    b = v1bars.build_m1([bid], [ask])
    pd.testing.assert_frame_equal(a, b)
    assert a.mid_c.isna().sum() == 3 and (a.mid_o == (a.bid_o + a.ask_o) / 2).sum() == 1437
    assert len(a) == 1440 and a.index.is_unique


def test_model_clock_is_core_to_server():
    idx = pd.date_range("2026-01-01 20:00", "2026-11-03 06:00", freq="37min", tz="UTC")
    assert (v2_data.harness()._to_server(idx) == core.to_server(idx)).all()
    t = v2_data.harness()._to_server(pd.DatetimeIndex([pd.Timestamp("2026-01-01 22:00", tz="UTC")]))[0]
    assert t == v2_data.INPUT_START                                        # EST: model = UTC + 2 h
    t = v2_data.harness()._to_server(pd.DatetimeIndex([pd.Timestamp("2026-08-31 21:00", tz="UTC")]))[0]
    assert t == pd.Timestamp("2026-09-01 00:00")                           # EDT: model = UTC + 3 h


def plain_bars(m, tf_min):
    """A plain re-implementation: bins [k·tf, (k+1)·tf) on the model clock, first/max/min/last over the minutes
    whose mid is finite, a bin with no finite o, h, l or c dropped."""
    rows = {}
    for t, r in m.iterrows():
        k = t.floor(f"{tf_min}min")
        rows.setdefault(k, []).append(r)
    out = []
    for k in sorted(rows):
        rs = rows[k]
        o = [r.o for r in rs if np.isfinite(r.o)]
        h = [r.h for r in rs if np.isfinite(r.h)]
        lo = [r.l for r in rs if np.isfinite(r.l)]
        c = [r.c for r in rs if np.isfinite(r.c)]
        if o and h and lo and c:
            out.append((k, o[0], max(h), min(lo), c[-1], len(c)))
    df = pd.DataFrame(out, columns=["t", "o", "h", "l", "c", "n"]).set_index("t")
    df.index.name = None
    return df


@pytest.mark.parametrize("tf,tf_min", [("M5", 5), ("M15", 15)])
def test_seed_bars_equal_the_harness_aggregation_and_a_plain_one(world, tf, tf_min):
    now = pd.Timestamp("2026-09-12 03:20", tz="UTC")
    cu = v2_data.v1_complete_utc(world.v1data, now)
    m = v2_data.load_m1(world.lb, world.v1data, now, cu)
    mf = v2_data.model_frame(m)
    m_in = v2_data.seed_input(mf)
    assert m_in.index.min() == v2_data.INPUT_START and (m_in.index.dayofweek < 5).all()
    b = v2_data.seed_bars(m_in, tf)
    # the harness's own aggregation, as harness.load applies it after _slice (weekdays only)
    h = v2_data.harness()._bars(mf[(mf.index >= v2_data.INPUT_START) & (mf.index.dayofweek < 5)][["o", "h", "l", "c"]],
                                tf)
    pd.testing.assert_frame_equal(b.drop(columns="day"), h)
    assert (b.day == b.index.normalize()).all()
    # a plain loop on three windows: the input start, the lookback/v1 boundary (UTC 2026-09-01) and a Friday close
    for a, z in (("2026-01-02 00:00", "2026-01-02 03:00"), ("2026-08-31 22:00", "2026-09-01 04:00"),
                 ("2026-09-04 22:00", "2026-09-05 00:00")):
        sub = m_in[(m_in.index >= a) & (m_in.index < z)]
        want = plain_bars(sub, tf_min)
        got = b[(b.index >= a) & (b.index < z)][["o", "h", "l", "c", "n"]]
        pd.testing.assert_frame_equal(got, want, check_dtype=False, check_freq=False, check_names=False)


def test_one_sided_minutes_and_empty_bins(tmp_path):
    """A bar over minutes with NaN mids takes first/max/min/last over the finite ones; a bin with none is dropped."""
    t = pd.date_range("2026-03-02 10:00", periods=15, freq="min")
    m = pd.DataFrame({"o": np.arange(15.0), "h": np.arange(15.0) + 1, "l": np.arange(15.0) - 1, "c": np.arange(15.0)},
                     index=t)
    m.iloc[0] = np.nan
    m.iloc[4] = np.nan
    m.iloc[5:10] = np.nan
    b = v2_data.seed_bars(m, "M5")
    assert list(b.index) == [t[0], t[10]]
    assert (b.o.iloc[0], b.h.iloc[0], b.l.iloc[0], b.c.iloc[0], b.n.iloc[0]) == (1.0, 4.0, 0.0, 3.0, 3)


def test_the_lookback_and_v1_sources_never_overlap(world):
    now = pd.Timestamp("2026-11-21 03:20", tz="UTC")
    cu = v2_data.v1_complete_utc(world.v1data, now)
    src = v2_data.source_days(world.lb, world.v1data, now, cu)
    lb = [d for d, _, r, _ in src if r == world.lb / "raw"]
    v1 = [d for d, _, r, _ in src if r == world.v1data / "raw"]
    assert max(lb) == pd.Timestamp("2026-08-31") and min(lb) == pd.Timestamp("2026-01-01")
    assert min(v1) == pd.Timestamp("2026-09-01") and max(v1) < cu.tz_localize(None)
    assert len(src) == len({(d, s) for d, s, _, _ in src})


def test_a_changed_raw_file_is_a_store_mismatch(world, tmp_path):
    import shutil
    lb = tmp_path / "lookback"
    shutil.copytree(world.lb, lb)
    p = v2_data.raw_path(lb / "raw", "2026-03-03", "ASK")
    p.write_bytes(p.read_bytes()[:-1] + b"\x00")
    now = pd.Timestamp("2026-09-12 03:20", tz="UTC")
    with pytest.raises(v2_data.StoreMismatch):
        v2_data.load_m1(lb, world.v1data, now, v2_data.v1_complete_utc(world.v1data, now))


def test_v1_complete_rule_matches_v1(world):
    import fetch
    for t in ("2026-09-02 01:59", "2026-09-02 02:00", "2026-10-05 03:20", "2026-12-05 03:20"):
        now = pd.Timestamp(t, tz="UTC")
        assert v2_data.v1_complete_utc(world.v1data, now) == fetch.complete_through_utc(world.v1data, now)
