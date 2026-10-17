"""bi5 decoding (committed fixture day) and the mid M1 builder against pipeline/build_parquet.py (§1, §9)."""
import hashlib
import lzma
import runpy
import shutil

import numpy as np
import pandas as pd
import pytest

import bars
import bi5
import synth

DUKA = pytest.FIXTURES / "duka"
VENDOR = pytest.ROOT / "analysis" / "system" / "vendor"


def fixture_frames():
    bid = bi5.decode((DUKA / "2026-10-16_BID.bi5").read_bytes(), "2026-10-16")
    ask = bi5.decode((DUKA / "2026-10-16_ASK.bi5").read_bytes(), "2026-10-16")
    return bid, ask


def test_url_uses_a_zero_based_month():
    assert bi5.url("2026-10-16", "BID") == \
        "https://datafeed.dukascopy.com/datafeed/XAUUSD/2026/09/16/BID_candles_min_1.bi5"
    assert bi5.url("2027-01-04", "ASK").endswith("/2027/00/04/ASK_candles_min_1.bi5")


def test_decode_fixture_day():
    """2026-10-16 as checked in the spec (§1): 1,440 rows, 1,260 with volume, prices / 1000, UTC from 00:00."""
    bid, ask = fixture_frames()
    assert len(bid) == len(ask) == 1440
    assert int((bid.volume > 0).sum()) == 1260
    t0 = pd.Timestamp("2026-10-16", tz="UTC")
    assert pd.to_datetime(bid.timestamp.iloc[0], unit="ms", utc=True) == t0
    assert pd.to_datetime(bid.timestamp.iloc[-1], unit="ms", utc=True) == t0 + pd.Timedelta(minutes=1439)
    raw = lzma.decompress((DUKA / "2026-10-16_BID.bi5").read_bytes(), format=lzma.FORMAT_ALONE)
    sec, o, c, lo, hi, v = __import__("struct").unpack_from(">5if", raw, 0)
    assert (sec, bid.open[0], bid.close[0], bid.low[0], bid.high[0]) == (0, o / 1000, c / 1000, lo / 1000, hi / 1000)
    assert (bid.low <= bid.open).all() and (bid.low <= bid.close).all() and (bid.high >= bid.open).all()
    assert (ask.close - bid.close).median() > 0


def test_encode_decode_round_trip():
    sec = np.arange(5) * 60
    p = np.array([4100000, 4100123, 4099999, 4101000, 4100500])
    body = synth.encode(sec, p, p + 7, p - 3, p + 9, np.array([0, 1.5, 0, 2, 3], dtype=np.float32))
    df = bi5.decode(body, "2026-11-02")
    assert list(df.open) == list(p / 1000) and list(df.close) == list((p + 7) / 1000)
    assert list(df.volume) == [0, 1.5, 0, 2, 3]


def test_decode_rejects_bad_bodies():
    with pytest.raises(Exception):
        bi5.decode(b"not lzma", "2026-10-16")
    bad = lzma.compress(b"\x00" * 25, format=lzma.FORMAT_ALONE)
    with pytest.raises(ValueError):
        bi5.decode(bad, "2026-10-16")
    assert len(bi5.decode(b"", "2026-10-16")) == 0


def _csv(df, path):
    """A dukascopy-node CSV (-v -fl -f csv): timestamp in ms, open, high, low, close, volume, shortest reprs."""
    with open(path, "w") as f:
        f.write("timestamp,open,high,low,close,volume\n")
        for r in df.itertuples():
            f.write(f"{int(r.timestamp)},{r.open!r},{r.high!r},{r.low!r},{r.close!r},{r.volume!r}\n")


def test_mid_builder_is_build_parquet(tmp_path):
    """Run the vendored, byte-identical pipeline/build_parquet.py on CSVs of the same records: identical frame."""
    src = VENDOR / "pipeline" / "build_parquet.py"
    sums = dict(line.split()[::-1] for line in (VENDOR / "SHA256SUMS").read_text().splitlines())
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sums["pipeline/build_parquet.py"]
    bid, ask = fixture_frames()
    bid2 = synth_day("2026-10-15", 1, shift=0.0)
    ask2 = synth_day("2026-10-15", 1, shift=0.4)
    ask2 = ask2.drop(index=[10, 11, 500])             # minutes present on one side only stay, with a NaN mid
    bid = bid.drop(index=[700])
    (tmp_path / "pipeline").mkdir()
    shutil.copyfile(src, tmp_path / "pipeline" / "build_parquet.py")
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    _csv(pd.concat([bid2, bid]), raw / "xauusd-m1-bid-2026.csv")
    _csv(pd.concat([ask2, ask]), raw / "xauusd-m1-ask-2026.csv")
    runpy.run_path(str(tmp_path / "pipeline" / "build_parquet.py"), run_name="__main__")
    ref = pd.read_parquet(tmp_path / "data" / "parquet" / "m1.parquet")
    ours = bars.build_m1([bid, bid2], [ask2, ask])     # order of the day files does not matter
    vols = ["bid_vol", "ask_vol"]
    pd.testing.assert_frame_equal(ours.drop(columns=vols), ref.drop(columns=vols), check_exact=True)
    # volumes do not enter the mid; pandas' default CSV float parser is not correctly rounded for 17-digit values
    pd.testing.assert_frame_equal(ours[vols], ref[vols], check_exact=False, rtol=1e-15)
    assert ours.mid_c.isna().sum() == 4


def synth_day(day, seed, shift):
    rng = np.random.default_rng(seed)
    t0 = int(pd.Timestamp(day).value // 10**6)
    p = 4150 + np.cumsum(rng.standard_normal(1440)) * 0.2
    q = np.round((p + shift) * 1000) / 1000
    return pd.DataFrame({"timestamp": t0 + np.arange(1440) * 60000, "open": q, "high": q + 0.1, "low": q - 0.1,
                         "close": q, "volume": rng.uniform(size=1440)})


def test_volmap_input_is_guard_load_m1():
    """The frame handed to models.build: model clock (core.to_server), mid columns renamed o/h/l/c, sorted."""
    bid, ask = fixture_frames()
    m = bars.build_m1([bid], [ask])
    v = bars.volmap_input(bars.model_frame(m))
    assert list(v.columns) == ["o", "h", "l", "c"]
    assert v.index[0] == pd.Timestamp("2026-10-16 03:00")          # 00:00 UTC = 20:00 EDT = 03:00 model
    np.testing.assert_array_equal(v.o.values, m.mid_o.values)


def test_no_bar_before_the_forward_window():
    early = synth_day("2026-08-31", 1, 0.0)
    with pytest.raises(AssertionError):
        bars.build_m1([early], [early])


def test_lab_bars_need_12_minutes_with_volume():
    bid, ask = fixture_frames()
    mf = bars.model_frame(bars.build_m1([bid], [ask]))
    lb = bars.lab_bars(mf)
    assert (lb.valid == (lb.nvol >= 12)).all()
    vol = bars.has_volume(mf)
    b = lb[lb.n == 15].iloc[0]
    sl = (mf.index >= b.start) & (mf.index < b.start + pd.Timedelta(minutes=15))
    assert b.nvol == int(vol[sl].sum())
    assert b.o == mf.o[sl].iloc[0] and b.c == mf.c[sl].iloc[-1]
    assert b.h == mf.h[sl].max() and b.l == mf.l[sl].min()
    assert lb.start.dt.strftime("%H:%M").min() == "01:30" and lb.start.dt.strftime("%H:%M").max() == "23:15"
