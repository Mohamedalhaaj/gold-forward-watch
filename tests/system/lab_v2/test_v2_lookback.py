"""The lab v2 lookback store (§0, §2.5 item 3): range, write-once files and rows, failures and `missing`, orphans,
the request budget, and the store check."""
import hashlib

import numpy as np
import pandas as pd

import bi5
import v2_data
import v2_lookback
import v2_synth


def body(tag=0):
    sec = np.arange(1440) * 60
    p = np.full(1440, 4100000 + tag)
    return v2_synth.encode(sec, p, p, p, p, np.ones(1440, dtype=np.float32))


class Feed:
    def __init__(self, fail=(), short=()):
        self.fail, self.short, self.calls = set(fail), set(short), []

    def __call__(self, url):
        self.calls.append(url)
        if url in self.fail:
            return 503, b""
        if url in self.short:
            return 200, body()[:-200]
        return 200, body()


NOW = pd.Timestamp("2026-10-21 08:00", tz="UTC")


def test_range_is_utc_2026_01_01_to_08_31():
    d = v2_lookback.days()
    assert d[0] == pd.Timestamp("2026-01-01") and d[-1] == pd.Timestamp("2026-08-31") and len(d) == 243


def test_budget_write_once_and_rows(tmp_path):
    feed = Feed()
    s = v2_lookback.run(tmp_path, now=NOW, max_requests=5, get=feed, sleep=lambda x: None)
    assert s["requests"] == 5 and s["fetched"] == 5 and s["pending"] == 2 * 243 - 5
    rows = pd.read_csv(tmp_path / "days.csv", dtype=str)
    assert list(rows.columns) == v2_data.DAYS_COLS
    assert list(zip(rows.day, rows.side))[:3] == [("2026-01-01", "BID"), ("2026-01-01", "ASK"), ("2026-01-02", "BID")]
    p = v2_data.raw_path(tmp_path / "raw", "2026-01-01", "BID")
    assert hashlib.sha256(p.read_bytes()).hexdigest() == rows.sha256[0] and set(rows.fetched_utc) == {
        "2026-10-21T08:00:00Z"}
    assert feed.calls[0] == bi5.url("2026-01-01", "BID")
    v2_lookback.run(tmp_path, now=NOW, max_requests=3, get=feed, sleep=lambda x: None)
    assert len(pd.read_csv(tmp_path / "days.csv")) == 8 and len(feed.calls) == 8      # never refetched
    assert v2_lookback.verify(tmp_path) == []
    p.write_bytes(body(1))
    assert v2_lookback.verify(tmp_path) == ["lookback 2026-01-01 BID"]


def test_failures_become_missing_after_three_days(tmp_path):
    bad = bi5.url("2026-01-01", "BID")
    short = bi5.url("2026-01-01", "ASK")
    feed = Feed(fail=[bad], short=[short])
    v2_lookback.run(tmp_path, now=NOW, max_requests=2, get=feed, sleep=lambda x: None)
    att = pd.read_csv(tmp_path / "attempts.csv", dtype=str)
    assert att.result[0] == "http 503" and att.result[1].startswith("bad body") and len(att) == 2
    assert not (tmp_path / "days.csv").exists()
    v2_lookback.run(tmp_path, now=NOW + pd.Timedelta(days=2), max_requests=2, get=feed, sleep=lambda x: None)
    assert not (tmp_path / "days.csv").exists()
    v2_lookback.run(tmp_path, now=NOW + pd.Timedelta(days=3), max_requests=2, get=feed, sleep=lambda x: None)
    rows = pd.read_csv(tmp_path / "days.csv", dtype=str, keep_default_na=False)
    assert list(rows.status) == ["missing", "missing"] and set(rows.sha256) == {""}


def test_an_orphan_file_is_adopted_with_its_own_bytes(tmp_path):
    p = v2_data.raw_path(tmp_path / "raw", "2026-01-01", "BID")
    p.parent.mkdir(parents=True)
    p.write_bytes(body(7))
    v2_lookback.run(tmp_path, now=NOW, max_requests=1, get=Feed(), sleep=lambda x: None)
    rows = pd.read_csv(tmp_path / "days.csv", dtype=str)
    assert rows.sha256[0] == hashlib.sha256(body(7)).hexdigest() and p.read_bytes() == body(7)
    assert "adopted an orphan" in pd.read_csv(tmp_path / "attempts.csv").result[0]


def test_complete():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assert not v2_lookback.complete(d)
