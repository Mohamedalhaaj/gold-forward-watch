"""Publisher format and `end` count (§5), the fetch store rules (§1), the registry and START/first_day (§0, §3)."""
import hashlib
import json

import pandas as pd
import pytest

import fetch
import forecasts
import publish
import synth
import system_common as sc
from lab import registry

L1 = {"green_ok": 1, "asof": "2026-11-03"}
L3 = {"asof": None, "mult": {b: (1.0, 0) for b in sc.BUCKETS}}
LAB = {"state": "RUNNING", "days": 0, "n_paper": 1, "n_live": 0, "best_progress": 0.0, "live": []}


# ---------------------------------------------------------------- VolMapSystem.csv
def test_system_csv_exact_format():
    lines = publish.system_csv("2026-11-03T03:20:05Z", L1, L3, LAB)
    keys = [ln.split(",")[0] for ln in lines]
    assert lines[:5] == ["key,value", "version,1", "asof_utc,2026-11-03T03:20:05Z", "l1_green_ok,1",
                         "l1_asof,2026-11-03"]
    assert keys[5] == "l3_asof" and lines[5] == "l3_asof,-"
    assert [k for k in keys if k.startswith("l3_m_")] == [f"l3_m_{b}" for b in sc.BUCKETS]
    assert [k for k in keys if k.startswith("l3_n_")] == [f"l3_n_{b}" for b in sc.BUCKETS]
    assert "l3_m_N_NY,1.0000" in lines
    assert keys[-6:-1] == ["lab_state", "lab_days", "lab_n_paper", "lab_n_live", "lab_best_progress"]
    assert lines[-1] == f"end,{len(lines) - 1}"
    assert all(ln.isascii() and ln.count(",") == 1 for ln in lines)


def test_live_rules_and_hex_title():
    live = [{"title_ar": "عكس حركة ما قبل إغلاق نيويورك", "n_post": 7}]
    lines = publish.system_csv("2027-05-01T03:20:00Z", L1, L3, LAB | {"n_live": 1, "live": live})
    kv = publish.parse_system_csv("\n".join(lines) + "\n")
    assert kv is not None and kv["lab_live_1_npost"] == "7"
    assert publish.unhex_utf16(kv["lab_live_1_title_ar"]) == live[0]["title_ar"]
    assert kv["lab_live_1_title_ar"].startswith("0639")                        # U+0639 ARABIC LETTER AIN


def test_reader_rejects_a_file_without_a_valid_end():
    lines = publish.system_csv("2026-11-03T03:20:00Z", L1, L3, LAB)
    text = "\n".join(lines) + "\n"
    assert publish.parse_system_csv(text) is not None
    assert publish.parse_system_csv("\n".join(lines[:-1]) + "\n") is None          # truncated
    assert publish.parse_system_csv("\n".join(lines[:-1] + ["end,3"]) + "\n") is None
    assert publish.parse_system_csv(text.replace("key,value", "k,v")) is None


def test_written_file_is_ascii_with_lf(tmp_path):
    p = tmp_path / "VolMapSystem.csv"
    publish.write_system_csv(p, publish.system_csv("2026-11-03T03:20:00Z", L1, L3, LAB))
    b = p.read_bytes()
    assert b.isascii() and b"\r" not in b and b.endswith(b"\n")


# ---------------------------------------------------------------- fetch store
class FakeFeed:
    def __init__(self, bodies, fail=()):
        self.bodies, self.fail, self.calls = bodies, set(fail), []

    def __call__(self, url):
        self.calls.append(url)
        if url in self.fail:
            return 0, b""
        return (200, self.bodies[url]) if url in self.bodies else (404, b"")


def bodies_for(days, tag=0):
    out = {}
    for d in days:
        for side in ("BID", "ASK"):
            import numpy as np
            sec = np.arange(1440) * 60
            p = np.full(1440, 4100000 + tag)
            out[__import__("bi5").url(d, side)] = synth.encode(sec, p, p, p, p, np.ones(1440, dtype=np.float32))
    return out


def test_only_complete_days_are_fetched(tmp_path):
    feed = FakeFeed(bodies_for(pd.date_range("2026-09-01", "2026-09-03")))
    fetch.run(tmp_path, now="2026-09-03T01:59:00Z", get=feed, sleep=lambda s: None)
    assert fetch.ok_days(tmp_path) == ["2026-09-01"]                  # 09-02 is complete only after 09-03 02:00
    fetch.run(tmp_path, now="2026-09-03T02:00:00Z", get=feed, sleep=lambda s: None)
    assert fetch.ok_days(tmp_path) == ["2026-09-01", "2026-09-02"]
    assert (tmp_path / "raw/2026/09/02/BID.bi5").exists() and (tmp_path / "raw/2026/09/02/ASK.bi5").exists()
    rows = pd.read_csv(tmp_path / "days.csv", dtype=str)
    p = tmp_path / "raw/2026/09/01/ASK.bi5"
    assert rows[(rows.day == "2026-09-01") & (rows.side == "ASK")].sha256.iloc[0] == hashlib.sha256(
        p.read_bytes()).hexdigest()
    assert fetch.complete_through_utc(tmp_path, "2026-09-03T02:00:00Z") == pd.Timestamp("2026-09-03", tz="UTC")
    assert fetch.verify_store(tmp_path) == []


def test_missing_after_three_days_and_never_refetched(tmp_path):
    b = bodies_for(pd.date_range("2026-09-01", "2026-09-06"))
    bad = __import__("bi5").url("2026-09-02", "ASK")
    feed = FakeFeed(b, fail={bad})
    fetch.run(tmp_path, now="2026-09-04T03:00:00Z", get=feed, sleep=lambda s: None, recheck=False)
    assert fetch.complete_through_utc(tmp_path, "2026-09-04T03:00:00Z") == pd.Timestamp("2026-09-02", tz="UTC")
    fetch.run(tmp_path, now="2026-09-07T02:59:00Z", get=feed, sleep=lambda s: None, recheck=False)
    assert fetch.missing(tmp_path) == []                         # 3 days after the first failed attempt: not yet
    fetch.run(tmp_path, now="2026-09-07T03:00:00Z", get=feed, sleep=lambda s: None, recheck=False)
    assert fetch.missing(tmp_path) == ["2026-09-02 ASK"]
    assert fetch.complete_through_utc(tmp_path, "2026-09-07T03:00:00Z") == pd.Timestamp("2026-09-07", tz="UTC")
    n = len(feed.calls)
    fetch.run(tmp_path, now="2026-09-08T03:00:00Z", get=feed, sleep=lambda s: None, recheck=False)
    assert bad not in feed.calls[n:]


def test_a_backfilled_old_day_gets_three_days_of_retries(tmp_path):
    """An old day that fails on its first attempt is not missing at once: 3 days from that first attempt."""
    b = bodies_for(pd.date_range("2026-09-01", "2026-09-02"))
    bad = __import__("bi5").url("2026-09-01", "BID")
    feed = FakeFeed(b, fail={bad})
    fetch.run(tmp_path, now="2026-10-17T07:00:00Z", get=feed, sleep=lambda s: None, recheck=False)
    assert fetch.missing(tmp_path) == []
    fetch.run(tmp_path, now="2026-10-20T06:59:00Z", get=feed, sleep=lambda s: None, recheck=False)
    assert fetch.missing(tmp_path) == []
    fetch.run(tmp_path, now="2026-10-20T07:00:00Z", get=feed, sleep=lambda s: None, recheck=False)
    miss = fetch.missing(tmp_path)
    assert "2026-09-01 BID" in miss and "2026-09-01 ASK" not in miss and "2026-09-02 BID" not in miss


def test_revisions_are_logged_and_never_used(tmp_path):
    days = pd.date_range("2026-09-01", "2026-09-01")
    fetch.run(tmp_path, now="2026-09-02T03:00:00Z", get=FakeFeed(bodies_for(days)), sleep=lambda s: None)
    before = (tmp_path / "raw/2026/09/01/BID.bi5").read_bytes()
    fetch.run(tmp_path, now="2026-09-03T03:00:00Z", get=FakeFeed(bodies_for(days, tag=5)), sleep=lambda s: None)
    rev = pd.read_csv(tmp_path / "revisions.csv", dtype=str)
    assert len(rev) == 2 and set(rev.side) == {"BID", "ASK"}
    assert (tmp_path / "raw/2026/09/01/BID.bi5").read_bytes() == before
    chk = pd.read_csv(tmp_path / "rechecks.csv", dtype=str)
    assert set(chk.same) == {"0"}
    fetch.run(tmp_path, now="2026-09-04T03:00:00Z", get=FakeFeed(bodies_for(days, tag=9)), sleep=lambda s: None)
    assert len(pd.read_csv(tmp_path / "revisions.csv")) == 2                  # each file is re-checked once


def test_store_verification_catches_an_edited_raw_file(tmp_path):
    fetch.run(tmp_path, now="2026-09-02T03:00:00Z", get=FakeFeed(bodies_for(["2026-09-01"])),
              sleep=lambda s: None)
    (tmp_path / "raw/2026/09/01/BID.bi5").write_bytes(b"x")
    assert fetch.verify_store(tmp_path) == ["2026-09-01 BID"]


# ---------------------------------------------------------------- forecast store (write once)
def test_forecast_store_is_write_once(tmp_path):
    grid = pd.DataFrame({"day": pd.to_datetime(["2026-11-03"] * 2), "wd": 1, "slot": [0, 1],
                         "origin": pd.to_datetime(["2026-11-03 01:00", "2026-11-03 02:00"]),
                         "F_H1": [10.5, float("nan")], "F_S": [20.25, 30.0], "price": [4000.0, 4001.0],
                         "y_bp": [1.0, 2.0], "nfp": 0, "cpi": 0, "fomc": 0, "hol": 0, "y3_bp": 0.0})
    store = forecasts.read_store(tmp_path / "f.csv")
    complete = pd.Timestamp("2026-11-02 23:30", tz="UTC")                     # 01:00 model = 23:00 UTC (EST)
    rows = forecasts.new_rows(grid, store, complete, "now")
    assert [r["slot"] for r in rows] == [0]
    forecasts.append_store(tmp_path / "f.csv", rows)
    store = forecasts.read_store(tmp_path / "f.csv")
    rows2 = forecasts.new_rows(grid, store, pd.Timestamp("2026-11-03 06:00", tz="UTC"), "later")
    assert [r["slot"] for r in rows2] == [1] and rows2[0]["F_H1"] == ""
    assert forecasts.tripwire(store, grid) == []
    assert forecasts.tripwire(store, grid.assign(F_H1=[10.5000001, float("nan")]))


# ---------------------------------------------------------------- registry, START, first_day
def test_start_rule():
    assert registry.start_from_first_run("2026-10-20T03:20:00Z") == pd.Timestamp("2026-11-02").date()
    assert registry.start_from_first_run("2026-10-31T03:20:00Z") == pd.Timestamp("2026-11-02").date()
    assert registry.start_from_first_run("2026-11-01T09:20:00Z") == pd.Timestamp("2026-11-09").date()
    assert registry.start_from_first_run("2026-11-03T03:20:00Z") == pd.Timestamp("2026-11-09").date()
    assert registry.start_from_first_run("2026-11-07T03:20:00Z") == pd.Timestamp("2026-11-09").date()


def test_first_day_rule():
    # 01:00 model on Tuesday 2026-11-10 is 23:00 UTC on Monday (EST): registered 21:59 UTC -> +1 h = 22:59 -> Tuesday
    assert registry.first_day("2026-11-09T21:59:00Z", "2026-11-02") == "2026-11-10"
    assert registry.first_day("2026-11-09T22:01:00Z", "2026-11-02") == "2026-11-11"
    assert registry.first_day("2026-11-06T23:00:00Z", "2026-11-02") == "2026-11-09"           # Friday night
    assert registry.first_day("2026-10-27T03:20:00Z", "2026-11-02") == "2026-11-02"           # never before START
    assert registry.first_day("2026-10-27T03:20:00Z", None) is None


def test_registry_files_verify_and_registration(tmp_path):
    for r in registry.seed_records():
        registry.write(tmp_path, r)
    with pytest.raises(FileExistsError):
        registry.write(tmp_path, registry.seed_records()[0])
    assert registry.verify(tmp_path) == []
    recs = registry.load(tmp_path)
    assert [r["id"] for r in recs] == ["S1", "S1R", "C1"]
    ev = registry.register_new(recs, [], "2026-10-27T03:20:00Z", "123", "abc", tracked={"S1", "C1"})
    assert [e["id"] for e in ev] == ["S1", "C1"]
    st = registry.states(recs, ev, "2026-11-02")
    assert st["S1"]["state"] == "PAPER" and st["C1"]["state"] == "REF" and st["S1R"]["state"] == "PENDING"
    assert st["S1"]["first_day"] == "2026-11-02"
    d = json.loads((tmp_path / "S1.json").read_text())
    d["spec"]["when"][0][4] = "0.40"
    (tmp_path / "S1.json").write_text(json.dumps(d))
    assert registry.verify(tmp_path) == ["S1: spec_sha256 mismatch"]


def test_seed_registry_matches_the_spec():
    recs = {r["id"]: r for r in registry.load(pytest.ROOT / "reports/system/lab/registry")}
    s1 = recs["S1"]
    assert s1["promotable"] and s1["gamma"] == 0.30 and s1["E_star"] == pytest.approx(83.333, abs=1e-3)
    assert s1["spec"]["days"] == 15 and s1["entry_delay_min"] == 1 and s1["cost"]["allowance_usd"] == 0.10
    assert recs["S1R"]["entry_delay_min"] == 0 and recs["S1R"]["gamma"] == 0 and not recs["S1R"]["promotable"]
    assert recs["S1R"]["spec_sha256"] == s1["spec_sha256"]
    assert recs["C1"]["spec"]["side"] == ["COIN"] and recs["C1"]["spec"]["T"] == "1500"
    assert recs["C1"]["spec"]["hold"] == 8 and not recs["C1"]["promotable"]
    assert registry.verify(pytest.ROOT / "reports/system/lab/registry") == []
