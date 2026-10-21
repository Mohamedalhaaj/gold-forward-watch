"""Unit tests of the judge's own implementations (SYSTEM_V2_PREREG.md §4 "Judge: unit tests")."""
import hashlib
import lzma
import math

import numpy as np
import pandas as pd
import pytest

from judge import (bars, checks, dukascopy, execution, l1, l3, lab_v1, lab_v2, publish, registry, status, vendored, verdict)
from judge.common import model_to_utc, rel_equal, utc_to_model


# ---------------------------------------------------------------- bi5 decode
def body(recs):
    a = np.array(recs, dtype=dukascopy.REC)
    return lzma.compress(a.tobytes(), format=lzma.FORMAT_ALONE)


def day_records(n=1440, price=4000000):
    return [(60 * i, price + i, price + i + 2, price + i - 3, price + i + 5, 1.5 if i % 7 else 0.0)
            for i in range(n)]


def test_decode_prices_are_int_over_1000_in_double():
    b = body(day_records())
    f = dukascopy.frame(b, "2026-11-03")
    assert len(f) == 1440
    assert f.o.iloc[0] == 4000000 / 1000.0 and f.c.iloc[0] == 4000002 / 1000.0
    assert f.l.iloc[1] == 3999998 / 1000.0 and f.h.iloc[1] == 4000006 / 1000.0
    assert f.ts.iloc[0] == pd.Timestamp("2026-11-03", tz="UTC")
    assert f.ts.iloc[1439] == pd.Timestamp("2026-11-03 23:59", tz="UTC")
    assert f.vol.iloc[1] == np.float32(1.5) and f.vol.iloc[0] == 0.0
    assert len(dukascopy.valid(b)) == 1440


def test_decode_rejects_bad_bodies():
    with pytest.raises(dukascopy.BadBody):
        dukascopy.valid(body(day_records(1439)))
    with pytest.raises(dukascopy.BadBody):
        dukascopy.records(b"not lzma at all")
    bad = day_records(3)
    bad[2] = (60, *bad[2][1:])         # not strictly increasing
    with pytest.raises(dukascopy.BadBody):
        dukascopy.records(body(bad))
    assert len(dukascopy.records(b"")) == 0
    raw = np.array(day_records(2), dtype=dukascopy.REC).tobytes()[:-3]
    with pytest.raises(dukascopy.BadBody):
        dukascopy.records(lzma.compress(raw, format=lzma.FORMAT_ALONE))


def test_arrays_equal_compares_every_field():
    a = dukascopy.records(body(day_records()))
    r = day_records()
    r[100] = (r[100][0], r[100][1], r[100][2], r[100][3], r[100][4], 2.5)
    assert dukascopy.arrays_equal(a, dukascopy.records(body(day_records())))
    assert not dukascopy.arrays_equal(a, dukascopy.records(body(r)))


# ---------------------------------------------------------------- mid M1 and bars
def _side_frame(day, minutes, base, vol=1.0):
    ts = pd.Timestamp(day, tz="UTC") + pd.to_timedelta(minutes, unit="m")
    n = len(minutes)
    return pd.DataFrame({"ts": ts, "o": base + np.arange(n) / 1000.0, "h": base + 1 + np.arange(n) / 1000.0,
                         "l": base - 1 + np.arange(n) / 1000.0, "c": base + 0.5 + np.arange(n) / 1000.0,
                         "vol": np.full(n, vol)})


def test_mid_is_bid_plus_ask_over_two_and_one_sided_minutes_are_nan():
    bid = _side_frame("2026-11-03", np.arange(0, 10), 4000.0)
    ask = _side_frame("2026-11-03", np.arange(1, 11), 4000.4)
    m = bars.mid_m1({"BID": [bid], "ASK": [ask]})
    assert len(m) == 11
    t1 = pd.Timestamp("2026-11-03 00:01", tz="UTC")
    assert m.loc[t1, "o"] == (m.loc[t1, "bid_o"] + m.loc[t1, "ask_o"]) / 2
    assert math.isnan(m.loc[pd.Timestamp("2026-11-03 00:00", tz="UTC"), "o"])
    assert math.isnan(m.loc[pd.Timestamp("2026-11-03 00:10", tz="UTC"), "c"])
    mf = bars.model_frame(m)
    assert mf.index[0] == pd.Timestamp("2026-11-03 02:00")   # 00:00 UTC = 19:00 EST of 11-02, + 7 h


def test_seed_bars_equal_the_harness_bars():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2026-03-02 00:00", periods=5000, freq="1min")
    c = 4000 + np.cumsum(rng.normal(0, 0.3, len(idx)))
    df = pd.DataFrame({"o": c, "h": c + 0.2, "l": c - 0.2, "c": c}, index=idx)
    df.iloc[100:130] = np.nan                       # a gap: the empty bins vanish
    df = df[df.index.dayofweek < 5]
    h = vendored.harness()
    for tf, m in (("M5", 5), ("M15", 15)):
        hb = h._bars(df, tf)
        hb["day"] = hb.index.normalize()
        jb = bars.seed_bars(df, m)
        assert hb.equals(jb.rename_axis(hb.index.name))


def test_lab_m15_validity_needs_12_minutes_with_volume_on_both_sides():
    day = pd.Timestamp("2026-11-03")
    idx = day + pd.Timedelta(hours=10) + pd.to_timedelta(np.arange(30), unit="m")
    mf = pd.DataFrame({"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "bid_vol": 1.0, "ask_vol": 1.0}, index=idx)
    mf.iloc[15:19, mf.columns.get_loc("ask_vol")] = 0.0     # 11 of the second bar's minutes keep volume
    b = bars.lab_m15(mf)
    assert bool(b.loc[day + pd.Timedelta(hours=10), "valid"])
    assert not bool(b.loc[day + pd.Timedelta(hours=10, minutes=15), "valid"])
    assert b.loc[day + pd.Timedelta(hours=11), "n"] == 0


# ---------------------------------------------------------------- clocks
def test_model_clock_round_trip_and_dst():
    assert model_to_utc(pd.Timestamp("2026-11-02 01:00")) == pd.Timestamp("2026-11-01 23:00", tz="UTC")
    assert model_to_utc(pd.Timestamp("2026-10-30 01:00")) == pd.Timestamp("2026-10-29 22:00", tz="UTC")
    t = pd.Timestamp("2026-11-10 06:00", tz="UTC")
    assert model_to_utc(utc_to_model(t)) == t


# ---------------------------------------------------------------- L1
def test_l1_truth_table():
    J = l1.judge
    for hu in (0.0, -1.0, float("nan"), float("inf"), 1e12):
        assert J(1, 0, 2, 5, 0, 0, 0, hu, 0.25, 1)[0] == "GREY"
    assert J(1, 0, 2, 5, 0, 0, 0, np.nextafter(1e12, 0), 0.25, 1)[0] == "GREEN"
    assert J(0, 0, 2, 5, 0, 0, 0, 6.0, 0.25, 1) == ("GREY", l1.R_UNDEF)
    assert J(1, 1, 2, 5, 0, 0, 0, 6.0, 0.25, 1) == ("GREY", l1.R_CLOSED)
    assert J(1, 0, 2, 5, 0, 1, 0, 6.0, 0.25, 1)[0] == "RED"            # CPI
    assert J(1, 0, 0, 0, 0, 0, 0, 6.0, 0.25, 1)[0] == "RED"            # week open
    assert J(1, 0, 1, 0, 0, 0, 0, 6.0, 0.25, 1) == ("YELLOW", l1.R_REOPEN)
    assert J(1, 0, 2, 5, 0, 0, 0, 0.25 / 0.06, 0.25, 1) == ("YELLOW", l1.R_COST)   # c = 0.06 exactly
    assert J(1, 0, 2, 5, 0, 0, 0, 0.25 / 0.12, 0.25, 1) == ("YELLOW", l1.R_COSTHIGH)
    assert J(1, 0, 4, 21, 0, 0, 0, 6.0, 0.25, 1) == ("YELLOW", l1.R_WEEKEND)
    assert J(1, 0, 2, 5, 0, 0, 0, 6.0, 0.25, 0) == ("YELLOW", l1.R_DRIFT)
    assert J(1, 0, 2, 5, 1, 0, 1, 6.0, 0.25, 1) == ("YELLOW", l1.R_NFP | l1.R_FOMC)
    assert J(1, 0, 2, 5, 0, 0, 0, 6.0, 0.25, 1) == ("GREEN", 0)


def test_l1_blocks_hysteresis():
    start = pd.Timestamp("2026-11-02")
    cu = pd.Timestamp("2027-12-01", tz="UTC")

    def block(k, hr):
        out = []
        days = pd.bdate_range(start + pd.Timedelta(days=91 * k), periods=65)
        n = 0
        for d in days:
            for h in range(23):
                hit = n < hr * 2 * 65 * 23
                out.append({"day": d, "origin": d + pd.Timedelta(hours=h + 1), "state": "GREEN", "entry": True,
                            "long": hit, "short": False})
                n += 1
        return out
    trs = block(0, 0.20) + block(1, 0.20) + block(2, 0.10) + block(3, 0.10)
    rows, g = l1.blocks(trs, start, cu, pd.DatetimeIndex([]))
    assert [r["green_ok_after"] for r in rows[:4]] == [1, 0, 0, 1]
    assert all(r["complete"] for r in rows[:4]) and rows[0]["expected"] == 23 * 65


# ---------------------------------------------------------------- L3
def test_l3_update_matches_a_hand_computation():
    obs = []
    rng = np.random.default_rng(1)
    for w in range(10):
        for i in range(5):
            d = pd.Timestamp("2027-01-04") + pd.Timedelta(days=7 * w + i)
            iso = d.isocalendar()
            obs.append({"day": d, "slot": 15, "r": 1.3 + rng.normal(0, 0.01), "bucket": "N_NY",
                        "week": iso[0] * 100 + iso[1]})
    for j in range(7):
        obs.append({"day": pd.Timestamp("2027-01-08") + pd.Timedelta(days=7 * j), "slot": 14, "r": 2.0 + j * 0.1,
                    "bucket": "CPI", "week": 0})
    rows = {r["bucket"]: r for r in l3.update(obs, pd.Timestamp("2027-04-01"), {}, 7.75)}
    ny = rows["N_NY"]
    r = np.array([o["r"] for o in obs if o["bucket"] == "N_NY"])
    wm = r.reshape(10, 5).mean(axis=1)
    se = np.std(wm, ddof=1) / math.sqrt(10)
    assert ny["n"] == 50 and ny["G"] == 10 and rel_equal(ny["se"], se, 1e-12)
    assert ny["active_after"] == 1 and rel_equal(ny["m"], 1 + (r.mean() - 1) * 10 / 18, 1e-12)
    many = [dict(o, week=o["week"] * 1000 + k) for k in range(30) for o in obs if o["bucket"] == "N_NY"]
    big = {x["bucket"]: x for x in l3.update(many, pd.Timestamp("2027-04-01"), {}, 7.75)}
    assert big["N_NY"]["G"] == 300 and big["N_NY"]["m"] == 1.25          # w near 1: clamped at 1.25
    cpi = rows["CPI"]
    x = np.array([2.0 + j * 0.1 for j in range(7)])
    assert rel_equal(cpi["se"], np.std(x, ddof=1) / math.sqrt(7), 1e-12) and cpi["eligible"] == 1
    assert rows["FOMC"]["n"] == 0 and rows["FOMC"]["m"] == 1.0 and rows["FOMC"]["eligible"] == 0
    # hysteresis: an active bucket stays active down to z*/2
    rows2 = {r["bucket"]: r for r in l3.update(obs, pd.Timestamp("2027-04-01"), {"N_NY": True}, 1e9)}
    assert rows2["N_NY"]["active_after"] == 0
    assert l3.bucket(0, 0, 0, 0, vendored.volmap()[0].session_of_hour) == "REOPEN"
    assert l3.bucket(14, 0, 1, 1, vendored.volmap()[0].session_of_hour) == "CPI"
    assert l3.bucket(9, 0, 0, 0, vendored.volmap()[0].session_of_hour) == "N_LONDON"


# ---------------------------------------------------------------- e-process and registry rules
def test_e_and_k_values():
    ys = [0.5, -1.0, 2.0]
    want = np.mean([np.prod([1 + lam * y for y in ys]) for lam in (0.025, 0.05, 0.1, 0.2, 0.4)])
    assert rel_equal(execution.e_value(ys), want, 1e-15)
    assert rel_equal(execution.e_path(ys)[-1], want, 1e-15)
    wk = np.mean([np.prod([1 - lam * y for y in ys]) for lam in (0.025, 0.05, 0.1, 0.2, 0.4)])
    assert rel_equal(execution.k_value(ys), wk, 1e-15)
    assert execution.e_value([]) == 1.0


def test_first_day_and_start_rules():
    s1 = registry.start_value(pd.Timestamp("2026-10-17T18:55:29Z"), "2026-11-02")
    assert s1 == pd.Timestamp("2026-11-02")
    s2 = registry.start_value(pd.Timestamp("2026-11-03T03:20:00Z"), s1)
    assert s2 == pd.Timestamp("2026-11-09")
    assert registry.first_day(pd.Timestamp("2026-10-17T18:55:29Z"), s1) == pd.Timestamp("2026-11-02")
    assert registry.first_day(pd.Timestamp("2026-11-10T05:00:00Z"), s1) == pd.Timestamp("2026-11-11")
    assert registry.first_day(pd.Timestamp("2026-11-09T21:00:00Z"), s1) == pd.Timestamp("2026-11-10")
    assert registry.first_day(pd.Timestamp("2026-11-09T22:00:01Z"), s1) == pd.Timestamp("2026-11-11")
    rec = {"promotable": True, "alpha_exact": "1/200", "gamma_exact": "3/10", "E_star_exact": "2000/3",
           "E_star": 666.6666666666666, "D_at_arrival": 0}
    assert registry.e_star_ok(rec, 2)
    assert not registry.e_star_ok(dict(rec, E_star=666.7), 2)
    assert registry.e_star_ok({"promotable": True, "alpha": 0.04, "gamma": 0.3, "E_star": 83.33333333333333}, 1)


def test_coin_side_is_the_sha_rule():
    for d in ("2026-11-02", "2026-11-03", "2026-12-25"):
        want = 1 if int(hashlib.sha256(f"L2-C1|{d}".encode()).hexdigest()[:8], 16) % 2 == 0 else -1
        assert lab_v1.coin_side(d) == want


# ---------------------------------------------------------------- execution edge cases
class DM:
    """A model day of minutes for execution tests: flat quotes unless set."""

    def __init__(self, bid=4000.0, ask=4000.4):
        self.has_row = np.ones(1440, dtype=bool)
        self.a = {}
        for side, p in (("bid", bid), ("ask", ask)):
            for f in "ohlc":
                self.a[f"{side}_{f}"] = np.full(1440, p)
        for f in "ohlc":
            self.a[f] = (self.a[f"bid_{f}"] + self.a[f"ask_{f}"]) / 2
        self.a["bid_vol"] = np.ones(1440)
        self.a["ask_vol"] = np.ones(1440)

    def __getitem__(self, k):
        return self.a[k]


def test_stop_at_x_and_gap_through_the_stop_fill_at_the_open():
    dm = DM()
    dm.a["bid_l"][605] = 3990.0                  # a long's stop at X = 3995 is reached inside minute 605
    px, m, reason, kind = execution.path(dm, 1, 3995.0, 601, 720)
    assert (px, m, reason, kind) == (3995.0, 605, "stop", "c")
    dm.a["bid_o"][603] = 3980.0                  # a gap through the stop: filled at the open
    dm.a["bid_l"][603] = 3979.0
    assert execution.path(dm, 1, 3995.0, 601, 720) == (3980.0, 603, "stop", "o")


def test_stop_wins_a_tie_with_the_time_exit_and_the_entry_minute_is_tested():
    dm = DM()
    dm.a["bid_l"][719] = 3990.0
    assert execution.path(dm, 1, 3995.0, 601, 720)[2] == "stop"
    dm2 = DM()
    dm2.a["ask_h"][601] = 4010.0                 # a short stopped in its entry minute
    assert execution.path(dm2, -1, 4005.0, 601, 720)[:3] == (4005.0, 601, "stop")
    assert execution.path(DM(), 1, 3995.0, 601, 720) == (4000.0, 719, "time", "c")


def test_fifteen_minutes_without_a_live_quote_settle_at_the_stop():
    dm = DM()
    dm.a["bid_vol"][610:625] = 0.0               # flats: quoted but not live
    px, m, reason, _ = execution.path(dm, 1, 3995.0, 601, 720)
    assert (px, m, reason) == (3995.0, 624, "gap")
    dm = DM()
    dm.a["bid_vol"][610:624] = 0.0               # 14 only
    assert execution.path(dm, 1, 3995.0, 601, 720)[2] == "time"


def test_entry_falls_back_to_the_last_finite_close_and_money():
    dm = DM()
    dm.a["ask_o"][601] = np.nan
    dm.a["ask_c"][600] = 4000.7
    assert execution.entry_price(dm, 1, 601) == (4000.7, 600, "c")
    m = execution.money(1, 4000.0, 4001.0, 2.0, 0.2, 0.2)
    assert m["net_usd"] == 1.0 - 0.10 and rel_equal(m["cost_usd"], 0.5, 1e-15)
    assert m["R"] == (1.0 - 0.10) / 2.0 and m["y"] == m["R"]
    assert execution.money(1, 4000.0, 3990.0, 2.0, 0, 0)["y"] == -2.0


def test_v2_disaster_stop_is_three_d():
    dm = DM()
    t = lab_v2.trade(dm, 1, 600, 120, 20.0)
    D = t["P_e"] * (1 - math.exp(-1.0540339626212611 * 20.0 / 1e4))
    assert t["D"] == D and t["X"] == t["P_e"] - 3 * D and t["reason"] == "time" and t["exit_model"] == "11:59"
    assert lab_v2.in_window(90, 120, False) and not lab_v2.in_window(89, 120, False)
    assert lab_v2.in_window(1245, 120, True) and not lab_v2.in_window(1250, 120, True)


# ---------------------------------------------------------------- append-only and snapshots
def test_prefix_rule():
    old = b"a,b\n1,2.5\n3,4\n"
    assert checks.prefix_problem(old, old + b"5,6\n") is None
    assert checks.prefix_problem(old, b"a,b\n1,2.5000000000000001\n3,4\n") is None
    assert "rewritten" in checks.prefix_problem(old, b"a,b\n1,2.6\n3,4\n")
    assert "removed" in checks.prefix_problem(old, b"a,b\n1,2.5\n")
    assert checks.prefix_problem(old, None) == "the file was deleted"
    assert checks.prefix_problem(old, b"a,c\n1,2.5\n3,4\n") == "the header changed"
    b0 = b"block,complete,hits\n1,0,5\n"
    b1 = b"block,complete,hits\n1,1,9\n"
    assert checks.blocks_problem(b0, b1) is None
    assert "changed" in checks.blocks_problem(b1, b"block,complete,hits\n1,0,9\n")


# ---------------------------------------------------------------- outputs
def test_reason_strings_follow_the_register():
    for code, r in verdict.REASONS.items():
        assert verdict.reason_valid(r), code
        assert not any(0x064B <= ord(c) <= 0x0652 for c in r) and "،" not in r
    assert verdict.REASONS["unverified"] == "تعذر التحقق" and len(verdict.REASONS["unverified"]) == 11
    assert verdict.REASONS["j5_mismatch"] == "إعادة الحساب لم تطابق قيد المراجعة"
    assert len(verdict.REASONS["j5_mismatch"]) == 34


def test_judge_csv_layout():
    raw = publish.judge_csv(pd.Timestamp("2026-11-03T13:10:00Z"), "a" * 40, "WARNING", "unverified", 7, 9)
    lines = raw.decode("utf-8").split("\n")
    assert lines[0] == "key,value" and lines[-1] == "" and lines[-2] == "end,8"
    assert [ln.split(",", 1)[0] for ln in lines[1:-2]] == ["version", "asof_utc", "head_sha", "verdict",
                                                            "reason_ar", "checks_ok", "checks_total"]
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    for ln in lines[1:-2]:
        assert ln.startswith("reason_ar,") or ln.isascii()


def test_status_parser_on_the_fixture(fixture_world):
    raw = (fixture_world / "reports/forward_site/system/VolMapSystem.csv").read_bytes()
    parsed, probs = status.parse(raw)
    assert probs == [] and dict(parsed["lines"])["lab_days"] == "25"
    _, probs = status.parse(raw.replace(b"end,29", b"end,28"))
    assert probs and "end" in probs[0]


def test_pin_problems_of_the_real_pins_file():
    assert checks.pin_problems() == []
    assert checks.V1_FREEZE == "6cd6d57ef62d8eb8710dd5151c7b5ddc2612d095"


class _FakeSeedRun:
    """Three M5 bars of a model day: one outside the window (00:00), two inside (10:00, 10:05)."""

    def __init__(self, online, full):
        day = pd.Timestamp("2026-11-10")
        self.B = pd.DataFrame(index=pd.DatetimeIndex([day, day + pd.Timedelta(hours=10),
                                                      day + pd.Timedelta(hours=10, minutes=5)]))
        self.tf = 5
        self.full = np.array(full)
        self._online = online

    def day_positions(self, day):
        return 0, 3

    def online(self, i):
        return self._online[i]


def test_the_causality_audit_fails_on_any_mismatch_window_or_not():
    """Amendment B2 item 4, R-V2-13: a difference outside the window also fails the audit; first_mismatch is the
    first differing bar of the day."""
    a, _ = lab_v2.audit_day(_FakeSeedRun([1, 0, 0], [0, 0, 0]), "2026-11-10", 120)
    assert (a["n_mismatch_window"], a["n_mismatch_outside"], a["first_mismatch"], a["result"]) == (0, 1, "00:00",
                                                                                                    "FAIL")
    a, _ = lab_v2.audit_day(_FakeSeedRun([1, 0, -1], [1, 0, 0]), "2026-11-10", 120)
    assert (a["n_mismatch_window"], a["n_mismatch_outside"], a["first_mismatch"], a["result"]) == (1, 0, "10:05",
                                                                                                    "FAIL")
    a, _ = lab_v2.audit_day(_FakeSeedRun([1, 0, -1], [1, 0, -1]), "2026-11-10", 120)
    assert (a["n_window"], a["n_signals"], a["first_mismatch"], a["result"]) == (2, 2, "", "ok")


def test_start_rule_problems():
    """v1 §0 / R-V1-38 and v2 §0 / R-V2-26 (review MF5)."""
    v1 = {"first_cloud_run_utc": "2026-10-17T18:55:29Z", "start": "2026-11-02"}
    assert checks.start_problems(v1, 1, None) == []
    assert checks.start_problems(dict(v1, start="2026-11-09"), 1, None)
    late = {"first_cloud_run_utc": "2026-11-03T03:20:00Z", "start": "2026-11-09", "v1_start": "2026-11-02"}
    assert checks.start_problems(late, 2, v1) == []
    assert checks.start_problems(dict(late, start="2026-11-16"), 2, v1)
    assert checks.start_problems(dict(late, v1_start="2026-11-09"), 2, v1)
    assert checks.start_problems(dict(late, first_cloud_run_utc="soon"), 2, v1)
    assert checks.start_problems(late, 2, None)                    # no v1 START to compare with
    # any first v2 run up to Saturday 2026-10-31 gives the v1 START (R-V2-26)
    assert checks.start_problems({"first_cloud_run_utc": "2026-10-31T23:00:00Z", "start": "2026-11-02",
                                  "v1_start": "2026-11-02"}, 2, v1) == []


def test_finding_keys_are_stable_and_clean():
    assert checks.finding_key("J3", "j3_ledger", "reports/system/lab/trades.csv", "937f11a32915") == \
        "J3|j3_ledger|reports/system/lab/trades.csv|937f11a32915"
    assert checks.finding_key("J8", "j8_rewritten", "a|b,c", None) == "J8|j8_rewritten|a/b/c|-"
    c = checks.Check("J3")
    c.violate("j3_raw", "x", "data/system/raw/2026/11/03/BID.bi5", "abc")
    c.violate("j3_raw", "x again", "data/system/raw/2026/11/03/BID.bi5", "abc")
    assert [k for k, _, _ in c.findings] == ["J3|j3_raw|data/system/raw/2026/11/03/BID.bi5|abc"]
    c.warn("unverified", "y")
    c.clear({"J3|j3_raw|data/system/raw/2026/11/03/BID.bi5|abc": "2026-12-06T00:00:00Z"})
    assert c.status == "warning" and c.reasons == ["unverified"]


def test_the_page_and_report_do_not_call_an_unverified_check_sound(tmp_path):
    """Review MF6: an ok check that verified nothing in this run is shown as «لم يُتحقق» (J6 without a complete week:
    «لا بيانات بعد»), in grey, and the summary counts it apart; VolMapJudge.csv and checks_ok are unchanged."""
    cs = [checks.Check(i) for i in ("J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9")]
    cs[0].idle = "unverified"
    cs[5].idle = "no_data"
    cs[8].idle = "unverified"
    cs[8].unverified.append("J9 2026-11-03: no key")
    now = pd.Timestamp("2026-11-04T13:10:00Z")
    publish.write_all(tmp_path, now, "a" * 40, "SOUND", "sound", 9, 9, cs, [], "x" * 64)
    page = (tmp_path / "reports/forward_site/judge/index.html").read_text()
    rep = (tmp_path / "reports/judge/REPORT.md").read_text()
    assert '<tr><td>J1</td><td>تطابق البيانات الخام مع تنزيل مستقل من المصدر</td><td class="s-unverified">لم يُتحقق' \
        in page
    assert '<td class="s-unverified">لا بيانات بعد</td></tr>' in page
    assert page.count('class="s-unverified"') == 3 and page.count('<td class="s-ok">سليم</td>') == 6
    assert "الفحوص السليمة 6 من 9، ولم يُتحقق من 3" in page and "الفحوص السليمة 6 من 9، ولم يُتحقق من 3" in rep
    assert "| J9 | مقارنة السعر بمصدر مستقل | لم يُتحقق |" in rep and "| J6 |" in rep and "لا بيانات بعد" in rep
    assert "checks ok 9 of 9; of these, nothing was verified in this run by: J1, J6, J9" in rep
    raw = (tmp_path / "reports/forward_site/judge/VolMapJudge.csv").read_text()
    assert "checks_ok,9\n" in raw and "verdict,SOUND\n" in raw
