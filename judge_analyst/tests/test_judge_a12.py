"""§16.18 A12 (2026-10-26): `analyst-context/3` and `analyst-plan/2`, as the judge sees them. Written from the
register text (R-AN-14, R-AN-16, R-AN-17, R-AN-19, R-AN-23, R-AN-26, R-AN-28, R-AN-67 A4/A5, R-AN-68, R-AN-87 and
the new R-AN-88, as amended by A12; decisions A12-D6..D9) without reading the analyst code: the schema paired with
repo_head_sha through the pinned A12 build commit, the `AUDJPY` request in R-AN-87's order, `risk` and `levels`
rebuilt within R-AN-68, the 25-weekday `bars_d1`, the AUDJPY Dukascopy cross-check (A11 `td_mismatch`,
`td_unchecked`), and `stay_out_reason` (A5).
"""
import copy
import datetime as dt
import statistics

import pytest

from jlib import derive, levels, td, ticks
from jlib.clock import model_to_utc, weekday_before
from jlib.common import VIOLATION, WARNING, fmt_utc
from jlib.sources import FakeHourFetcher, HourSource
from world import PLAN_BUY, PLAN_SELL, PLAN_STAY, T, World

V2, V3 = "analyst-context/2", "analyst-context/3"


def keys(res, check=None, severity=None, code=None, path=None):
    return [f.key for f in res.findings.items if (not check or f.check == check) and
            (not severity or f.severity == severity) and (not code or f.code == code) and
            (not path or f.path == path)]


def call_path(cid):
    return f"analyst/calls/{cid}.json"


# ---------------------------------------------------------------- R-AN-87 / R-AN-16: the AUDJPY request (unit)

def test_audjpy_request_url_order_and_points():
    a = dt.datetime(2026, 11, 29, 22, tzinfo=dt.timezone.utc)
    b = dt.datetime(2026, 11, 30, 7, tzinfo=dt.timezone.utc)
    assert td.SYMBOLS["AUDJPY"] == "AUD/JPY"
    assert td.hourly_url("AUDJPY", a, b) == (
        "https://api.twelvedata.com/time_series?symbol=AUD/JPY&interval=1h&start_date=2026-11-29T22:00:00"
        "&end_date=2026-11-30T07:00:00&timezone=UTC&order=asc&outputsize=5000&dp=5")
    assert td.REQ_ORDER == ("XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF", "fresh")    # /2 unchanged
    assert td.REQ_ORDER_V3 == ("XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF", "AUDJPY", "fresh")
    assert ticks.POINTS["AUDJPY"] == 1000
    assert ticks.tick_mid(97_001, 96_999, "AUDJPY") == 97.0
    assert ticks.hour_url("AUDJPY", b) == "https://datafeed.dukascopy.com/datafeed/AUDJPY/2026/10/30/07h_ticks.bi5"
    assert "AUDJPY" not in ticks.FX_PAIRS                       # it does not enter proxy_pct (R-AN-19)


# ---------------------------------------------------------------- R-AN-26 / A12-D2: analyst-plan/2 (unit)

STAY2 = dict(PLAN_STAY, stay_out_reason="no_setup")


@pytest.mark.parametrize("reason", ["event_risk", "no_setup", "conflicting_signals", "mid_range"])
def test_plan_v3_stay_out_reasons(reason):
    assert derive.plan_errors(dict(PLAN_STAY, stay_out_reason=reason), v3=True) == []


def test_plan_v3_rules():
    assert "keys" in derive.plan_errors(PLAN_STAY, v3=True)                           # missing
    assert derive.plan_errors(dict(PLAN_STAY, stay_out_reason="bored"), v3=True) == ["stay_out_reason"]
    assert derive.plan_errors(dict(PLAN_STAY, stay_out_reason=1), v3=True) == ["stay_out_reason"]
    assert derive.plan_errors(dict(PLAN_STAY, stay_out_reason=None), v3=True) == ["stay_out_reason"]
    assert "keys" in derive.plan_errors(dict(PLAN_BUY, stay_out_reason="no_setup"), v3=True)   # on a trade
    assert derive.plan_errors(PLAN_BUY, v3=True) == [] and derive.plan_errors(PLAN_SELL, v3=True) == []
    # an analyst-context/2 call keeps the old key set
    assert derive.plan_errors(PLAN_STAY) == [] and derive.plan_errors(PLAN_STAY, v3=False) == []
    assert "keys" in derive.plan_errors(STAY2)


# ---------------------------------------------------------------- R-AN-88: levels (unit, hand-computed)

D = dt.date(2026, 12, 2)                    # a Wednesday; server = UTC + 2 in December


def mbar(day, hour, o, h, low, c):
    """An hourly bar at model `hour` of model `day` (t_utc from the model clock)."""
    t = model_to_utc(dt.datetime(day.year, day.month, day.day, hour))
    return {"t_utc": fmt_utc(t), "o": o, "h": h, "l": low, "c": c}


def scenario_one():
    mon, tue = dt.date(2026, 11, 30), dt.date(2026, 12, 1)
    B = [mbar(mon, 1, 3970.0, 3975.0, 3965.0, 3972.0),
         mbar(tue, 1, 4000.0, 4008.0, 3990.0, 4001.0), mbar(tue, 2, 4001.0, 4009.0, 3992.0, 4003.0),
         mbar(tue, 5, 4003.0, 4050.0, 3950.0, 4004.0),                    # after k_end: not in the hist
         mbar(D, 1, 4000.0, 4002.0, 3996.0, 4001.0), mbar(D, 2, 4001.0, 4006.0, 3999.0, 4004.0),
         mbar(D, 3, 4004.0, 4005.0, 3995.0, 4000.0), mbar(D, 10, 4000.0, 4100.0, 3900.0, 4000.0)]
    d1 = [{"day": "2026-12-01", "o": 3990.0, "h": 4010.0, "l": 3980.0, "c": 4005.0, "n_hours": 23}]
    return B, d1


def test_levels_prev_day_week_open_asia():
    B, d1 = scenario_one()
    u = levels.compute(4000.0, 20.0, B, d1, D)
    assert levels.rounded(u) == {
        "prev_day": {"day": "2026-12-01", "h": 4010.0, "l": 3980.0, "c": 4005.0, "dist_h": 0.5, "dist_l": -1.0,
                     "dist_c": 0.25},
        "week_open": {"t_utc": "2026-11-29T23:00:00Z", "o": 3970.0, "dist": -1.5},
        "asia": {"from_utc": "2026-12-01T23:00:00Z", "to_utc": "2026-12-02T02:00:00Z", "n_hours": 3,
                 "complete": False, "h": 4006.0, "l": 3995.0, "dist_h": 0.3, "dist_l": -0.25, "width_ratio": None,
                 "hist": [{"day": "2026-12-01", "h": 4009.0, "l": 3990.0}]},
        "ret_1d": None, "ret_5d": None, "ret_20d": None, "vol_ratio": None}
    assert list(levels.rounded(u)) == ["prev_day", "week_open", "asia", "ret_1d", "ret_5d", "ret_20d", "vol_ratio"]
    assert levels.compute(4000.0, 20.0, [], [], D) == {k: None for k in levels.LEVEL_KEYS}


def scenario_two(n_d1=25, n_hist=12):
    days = [weekday_before(D, k) for k in range(25, 0, -1)]
    d1 = []
    for i, dd in enumerate(days):
        c = 4000.0 + i
        r = 10.0 if i < 20 else 20.0
        d1.append({"day": dd.isoformat(), "o": c, "h": c + r / 2, "l": c - r / 2, "c": c, "n_hours": 1})
    d1 = d1[-n_d1:]
    B = []
    for e in d1[-20:][:n_hist]:
        dd = dt.date.fromisoformat(e["day"])
        B.append(mbar(dd, 1, 4000.0, 4002.0, 3998.0, 4000.0))
        B.append(mbar(dd, 2, 4000.0, 4100.0, 3900.0, 4000.0))           # model hour 2 > k_end = 1
    B.append(mbar(D, 1, 4000.0, 4005.0, 3995.0, 4000.0))
    return B, d1


def test_levels_returns_vol_and_width():
    B, d1 = scenario_two()
    u = levels.compute(4010.0, 25.0, B, d1, D)
    r = levels.rounded(u)
    assert r["ret_1d"] == round(100 * (4024.0 / 4023.0 - 1), 3)
    assert r["ret_5d"] == round(100 * (4024.0 / 4019.0 - 1), 3)
    assert r["ret_20d"] == round(100 * (4024.0 / 4004.0 - 1), 3)
    assert r["vol_ratio"] == 1.6                                        # 20 / mean(15 x 10, 5 x 20)
    assert len(r["asia"]["hist"]) == 12 and r["asia"]["width_ratio"] == 2.5     # 10 / median 4
    assert r["asia"]["n_hours"] == 1 and r["asia"]["to_utc"] == "2026-12-02T00:00:00Z"
    assert u["asia"]["width_ratio"] == 10.0 / statistics.median([4.0] * 12)
    r20 = levels.rounded(levels.compute(4010.0, 25.0, B, d1[-20:], D))
    assert r20["ret_20d"] is None and r20["ret_5d"] is not None and r20["vol_ratio"] is not None
    r19 = levels.rounded(levels.compute(4010.0, 25.0, B, d1[-19:], D))
    assert r19["vol_ratio"] is None
    B9, d19 = scenario_two(n_hist=9)
    assert levels.rounded(levels.compute(4010.0, 25.0, B9, d19, D))["asia"]["width_ratio"] is None
    # the recorded hist, when given, is what width_ratio uses (the judge recomputes from the record)
    hist = [{"day": "x", "h": 4002.0, "l": 3997.0}] * 10
    assert levels.compute(4010.0, 25.0, B, d1, D, hist=hist)["asia"]["width_ratio"] == 2.0


def test_levels_tolerance_and_nulls():
    B, d1 = scenario_one()
    u = levels.compute(4000.0, 20.0, B, d1, D)
    hist = u["asia"]["hist"]
    r = levels.rounded(u)
    assert levels.compare(r, u, hist) == []
    assert levels.compare(None, None, None) == []
    assert levels.compare({}, None, None) == ["levels"]
    assert levels.compare(None, u, hist) == ["levels"]

    def tweak(fn):
        x = copy.deepcopy(r)
        fn(x)
        return levels.compare(x, u, hist)
    assert tweak(lambda x: x["prev_day"].update(dist_h=0.5 + 0.0049)) == []           # 0.5·10^-2 + 1e-9
    assert tweak(lambda x: x["prev_day"].update(dist_h=0.5 + 0.0051)) == ["levels.prev_day.dist_h"]
    assert tweak(lambda x: x["prev_day"].update(dist_h=None)) == ["levels.prev_day.dist_h"]
    assert tweak(lambda x: x["asia"].update(width_ratio=1.0)) == ["levels.asia.width_ratio"]   # null in the judge's
    assert tweak(lambda x: x["prev_day"].update(h=4010.001)) == ["levels.prev_day.h"]           # prices exact
    assert tweak(lambda x: x["week_open"].update(t_utc="2026-11-30T00:00:00Z")) == ["levels.week_open.t_utc"]
    assert tweak(lambda x: x["asia"].update(complete=True)) == ["levels.asia.complete"]
    assert tweak(lambda x: x["asia"]["hist"][0].update(l=3990.5)) == ["levels.asia.hist"]
    assert tweak(lambda x: x.pop("vol_ratio")) == ["levels.keys"]
    assert tweak(lambda x: x["prev_day"].pop("dist_c")) == ["levels.prev_day.keys"]
    assert tweak(lambda x: x.update(week_open=None)) == ["levels.week_open"]
    assert tweak(lambda x: x["prev_day"].update(dist_l=True)) == ["levels.prev_day.dist_l"]
    B2, d12 = scenario_two()
    u2 = levels.compute(4010.0, 25.0, B2, d12, D)
    r2 = levels.rounded(u2)
    x = copy.deepcopy(r2)
    x["ret_5d"] = r2["ret_5d"] + 0.0004                                  # 0.5·10^-3 + 1e-9
    assert levels.compare(x, u2, u2["asia"]["hist"]) == []
    x["ret_5d"] = u2["ret_5d"] + 0.0006
    assert levels.compare(x, u2, u2["asia"]["hist"]) == ["levels.ret_5d"]


# ---------------------------------------------------------------- the world: analyst-context/3 from the A12 commit

A12_WORLD = dict(canary_days=(), live_from="2026-11-30", live_to="2026-12-08", now="2026-12-09T23:00:00Z",
                 store_first="2026-10-19", a12_from="2026-12-01")
PLANS = {"2026-11-30_W1": ("call", PLAN_STAY), "2026-11-30_W2": ("call", PLAN_BUY),
         "2026-12-01_W1": ("call", PLAN_STAY), "2026-12-01_W2": ("call", PLAN_SELL),
         "2026-12-02_W1": ("call", PLAN_BUY), "2026-12-02_W2": ("call", PLAN_STAY),
         "2026-12-03_W1": ("data_absent",), "2026-12-03_W2": ("call", PLAN_BUY),
         "2026-12-04_W1": ("call", PLAN_SELL), "2026-12-04_W2": ("call", PLAN_STAY)}


def a12_world(root, hooks=None):
    return World(root, plans=dict(PLANS), hooks=hooks or {}, **A12_WORLD).build()


@pytest.fixture(scope="module")
def a12(tmp_path_factory):
    return a12_world(str(tmp_path_factory.mktemp("a12") / "w"))


def test_a12_world_contexts(a12):
    for cid in ("2026-11-30_W1", "2026-11-30_W2"):
        ctx = a12.context_of(cid)
        assert ctx["schema"] == V2 and "risk" not in ctx and "levels" not in ctx
        assert [f["req"] for f in ctx["files"]] == list(td.REQ_ORDER) and len(ctx["bars_d1"]) == 10
        assert "stay_out_reason" not in (a12.calls[("live", cid)]["plan"] or {})
    ctx = a12.context_of("2026-12-02_W2")
    assert ctx["schema"] == V3 and ctx["status"] == "ok"
    assert [f["req"] for f in ctx["files"]] == list(td.REQ_ORDER_V3)
    assert ctx["files"][6]["url"].startswith("https://api.twelvedata.com/time_series?symbol=AUD/JPY&interval=1h")
    ks = list(ctx)
    assert ks.index("risk") == ks.index("fx") + 1 and ks.index("levels") == ks.index("d_ref") + 1
    assert set(ctx["risk"]) == {"pair", "p0", "p1", "pct", "t0_hour_utc", "t1_hour_utc"}
    assert ctx["risk"]["pair"] == "AUDJPY" and ctx["risk"]["t0_hour_utc"] == ctx["fx"]["pairs"][0]["t0_hour_utc"]
    assert ctx["risk"]["pct"] == 100 * (ctx["risk"]["p1"] / ctx["risk"]["p0"] - 1)
    assert list(ctx["levels"]) == list(levels.LEVEL_KEYS)
    assert all(ctx["levels"][k] is not None for k in levels.LEVEL_KEYS)
    assert len(ctx["bars_d1"]) == 25 and ctx["bars_d1"][-1]["day"] == "2026-12-01"
    assert min(b["t_utc"] for b in ctx["bars_h1"]) > ctx["store"]["start_hist_utc"]   # bars_h1: still from start_hist
    assert ctx["bars_d1"][0]["day"] < ctx["store"]["start_hist_utc"][:10]       # history from start_lv
    assert a12.calls[("live", "2026-12-02_W2")]["plan"]["stay_out_reason"] == "no_setup"
    gone = a12.context_of("2026-12-03_W1")                     # hour_absent: the context stops after XAUUSD
    assert gone["status"] == "no_call:data" and [f["req"] for f in gone["files"]] == ["XAUUSD"]
    assert gone["levels"] is None and gone["risk"] is None


def test_a12_world_is_sound(a12):
    res = a12.judge()
    assert keys(res) == []
    assert res.summary["td_compared"] > 0 and res.summary.get("td_outside", 0) == 0
    assert res.summary["contexts_rebuilt"] == len(a12.calls) == 14


def test_A4_unpinned_judge_rejects_context_3(a12):
    res = a12.judge(a12_commit=None)
    ks = keys(res, "A4", VIOLATION, "context_schema")
    v3 = sorted(cid for (m, cid) in a12.calls if a12.context_of(cid)["schema"] == V3)
    assert sorted(k.split("|")[2] for k in ks) == [call_path(c) for c in v3]
    assert not keys(res, "A4", code="context_schema", path=call_path("2026-11-30_W1"))


def test_A4_pin_at_an_earlier_commit_requires_3_for_all(a12):
    from jlib.gitrepo import GitRepo
    g = GitRepo(a12.repo.path)
    try:
        first = g.run("rev-list", "--max-parents=0", "HEAD").split()[0]
    finally:
        g.close()
    res = a12.judge(a12_commit=first)
    assert sorted(k.split("|")[2] for k in keys(res, "A4", VIOLATION, "context_schema")) == \
        [call_path("2026-11-30_W1"), call_path("2026-11-30_W2")]


def _shift(world, sym, hour, factor):
    from test_judge_a9 import _shift_dukascopy
    _shift_dukascopy(world, sym, hour, factor)


def test_A11_audjpy_cross_check(a12):
    w = copy.copy(a12)
    w.hour_files = dict(a12.hour_files)
    risk = a12.context_of("2026-12-02_W2")["risk"]
    _shift(w, "AUDJPY", T(risk["t1_hour_utc"]), 1.002)
    res = w.judge()
    ks = keys(res, "A11", WARNING, "td_mismatch")
    assert [k.split("|")[2] for k in ks] == [call_path("2026-12-02_W2")]
    f = [x for x in res.findings.items if x.code == "td_mismatch"][0]
    assert f.detail.startswith("outside 1e-3: AUDJPY ") and " p1 " in f.detail
    assert not keys(res, severity=VIOLATION)
    w2 = copy.copy(a12)
    w2.hour_files = dict(a12.hour_files)
    _shift(w2, "AUDJPY", T(risk["t0_hour_utc"]), 1.0006)                # within 1e-3
    assert keys(w2.judge()) == []


def test_A11_audjpy_unchecked_without_its_file(a12):
    risk = a12.context_of("2026-12-02_W1")["risk"]
    files = dict(a12.hour_files)
    files[ticks.hour_url("AUDJPY", T(risk["t0_hour_utc"]))] = (404, b"")
    res = a12.judge(hours=HourSource(FakeHourFetcher(files), None, a12.now))
    ks = keys(res, "A11", WARNING, "td_unchecked")
    assert sorted(k.split("|")[2] for k in ks) == [call_path("2026-12-02_W1"), call_path("2026-12-02_W2")]
    assert all("AUDJPY" in f.detail and "p0" in f.detail for f in res.findings.items if f.code == "td_unchecked")


# ---------------------------------------------------------------- the world: planted A12 defects (one build)

def _ctx_hook(world, win, ctx):
    cid = win.call_id
    if cid == "2026-11-30_W2":
        ctx["schema"] = V3                                              # before the A12 commit
    elif cid == "2026-12-01_W2":
        ctx["schema"] = V2                                              # after it
    elif cid == "2026-12-02_W1":
        ctx["levels"]["prev_day"]["dist_h"] += 0.011
    elif cid == "2026-12-03_W2":
        ctx["risk"]["p1"] *= 1.000001
    elif cid == "2026-12-04_W1":
        ctx["levels"]["asia"]["hist"][0]["h"] += 0.01
    elif cid == "2026-12-03_W1":
        ctx["levels"] = {}                                             # levels on a no_call context
    elif cid == "2026-12-07_W2":
        ctx["levels"]["vol_ratio"] = None
    elif cid == "2026-12-08_W2":
        ctx["bars_d1"] = ctx["bars_d1"][-10:]                           # the /2 history length


def _files_hook(world, win, files):
    cid = win.call_id
    i = next((k for k, f in enumerate(files) if f["req"] == "AUDJPY"), None)
    if cid == "2026-12-07_W1":                                          # a failed AUDJPY: risk null, no finding
        files[i].update(status="error", reason="server", http=503, td_code=503, values_n=0, bars=[], tries=2,
                        bytes=40)
    elif cid == "2026-12-08_W1":
        files.pop(i)
    elif cid == "2026-12-04_W2":
        files[i]["url"] = files[i]["url"].replace("symbol=AUD/JPY", "symbol=AUDJPY")


def _call_hook(world, win, call):
    cid = win.call_id
    if cid == "2026-12-01_W1":
        del call["plan"]["stay_out_reason"]
    elif cid == "2026-12-02_W2":
        call["plan"]["stay_out_reason"] = "bored"
    elif cid == "2026-12-02_W1":
        call["plan"]["stay_out_reason"] = "no_setup"                    # on a trade
    elif cid == "2026-11-30_W1":
        call["plan"]["stay_out_reason"] = "no_setup"                    # a /2 call keeps the old key set


@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    w = a12_world(str(tmp_path_factory.mktemp("a12p") / "w"),
                  hooks={"context": _ctx_hook, "files": _files_hook, "call": _call_hook})
    return w, w.judge()


@pytest.mark.parametrize("cid,code", [
    ("2026-11-30_W2", "context_schema"), ("2026-12-01_W2", "context_schema"),
    ("2026-12-02_W1", "context_differs"), ("2026-12-03_W2", "context_differs"),
    ("2026-12-04_W1", "context_differs"), ("2026-12-03_W1", "context_differs"),
    ("2026-12-07_W2", "context_differs"), ("2026-12-08_W1", "context_differs"),
    ("2026-12-04_W2", "context_differs"), ("2026-12-08_W2", "context_differs")])
def test_A4_planted(planted, cid, code):
    _w, res = planted
    assert keys(res, "A4", VIOLATION, code, path=call_path(cid)), (cid, code, keys(res, "A4"))


@pytest.mark.parametrize("cid,detail", [
    ("2026-12-01_W1", "keys"), ("2026-12-02_W2", "stay_out_reason"), ("2026-12-02_W1", "keys"),
    ("2026-11-30_W1", "keys")])
def test_A5_planted_stay_out_reason(planted, cid, detail):
    _w, res = planted
    f = [x for x in res.findings.items if x.check == "A5" and x.code == "plan_invalid" and x.path == call_path(cid)]
    assert f and detail in f[0].detail and f[0].severity == VIOLATION


def test_planted_details_and_clean_windows(planted):
    w, res = planted
    det = {f.path: f.detail for f in res.findings.items if f.code == "context_differs"}
    assert "levels.prev_day.dist_h" in det[call_path("2026-12-02_W1")]
    assert "risk" in det[call_path("2026-12-03_W2")]
    assert "levels.asia.hist" in det[call_path("2026-12-04_W1")]
    assert "levels" in det[call_path("2026-12-03_W1")]
    assert "levels.vol_ratio" in det[call_path("2026-12-07_W2")]
    assert "files.sequence" in det[call_path("2026-12-08_W1")]
    assert "files[6].url" in det[call_path("2026-12-04_W2")]
    assert "bars_d1.days" in det[call_path("2026-12-08_W2")]
    assert w.context_of("2026-12-07_W1")["risk"] is None and w.context_of("2026-12-07_W1")["status"] == "ok"
    assert not keys(res, "A4", path=call_path("2026-12-07_W1"))
    assert not keys(res, "A5", path=call_path("2026-12-04_W2"))        # a valid stay_out_reason
