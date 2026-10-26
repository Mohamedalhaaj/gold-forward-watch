"""§16.18 A9 (2026-10-26): the model day's market data from Twelve Data (R-AN-87), as the judge sees them.
Written from the register text (R-AN-17..R-AN-19, R-AN-23, R-AN-66..R-AN-68, R-AN-84, R-AN-87 as amended by A9)
without reading the analyst code: the judge's own R-AN-87 rules (`jlib/td.py`), A4's rebuild of
`analyst-context/2`, the Dukascopy cross-check (A11 `td_mismatch`, `td_unchecked`), the probe rules of
`net.twelvedata` and `net.dukascopy`, and A12 `ga_tag`'s one extra tag.
"""
import copy
import datetime as dt

import pytest

from jlib import td
from jlib.common import UTC, VIOLATION, WARNING, fmt_utc
from jlib.judge import probe_fails
from jlib.sources import FakeHourFetcher, HourSource
from world import GA, T, World

H = dt.timedelta(hours=1)


def keys(res, check=None, severity=None, code=None):
    return [f.key for f in res.findings.items if (not check or f.check == check) and
            (not severity or f.severity == severity) and (not code or f.code == code)]


def has(res, check, code, severity):
    return bool(keys(res, check, severity, code))


# ---------------------------------------------------------------- R-AN-87: URLs, reasons, provenance (unit)

def test_urls_are_the_register_text_exactly():
    a = dt.datetime(2026, 11, 30, 5, tzinfo=UTC)
    b = dt.datetime(2026, 11, 30, 9, tzinfo=UTC)
    assert td.hourly_url("XAUUSD", a, b) == (
        "https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1h&start_date=2026-11-30T05:00:00"
        "&end_date=2026-11-30T09:00:00&timezone=UTC&order=asc&outputsize=5000&dp=5")
    assert td.hourly_url("USDJPY", a, b).startswith(
        "https://api.twelvedata.com/time_series?symbol=USD/JPY&interval=1h&start_date=")
    assert td.FRESH_URL == ("https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1min&outputsize=1"
                            "&timezone=UTC&dp=5")
    assert td.REQ_ORDER == ("XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF", "fresh")
    assert td.SOURCES == {
        "history": "dukascopy_store", "today": "twelvedata_1h",
        "note": "bars_h1 entries with src td, p_ref when p_ref_src is td, and fx come from Twelve Data hourly bars in "
                "UTC; bars_h1 entries with src store are Dukascopy mid; bars_d1 are built from bars_h1; Twelve Data "
                "and Dukascopy levels can differ slightly; settlement uses Dukascopy."}


@pytest.mark.parametrize("http,code,tries,reason", [
    (200, 401, 1, "key"), (401, 401, 1, "key"), (403, 403, 1, "plan"), (200, 429, 1, "credits"),
    (429, 429, 2, "credits"), (0, 0, 2, "server"), (503, 503, 2, "server"), (200, 500, 1, "server"),
    (200, 200, 1, "invalid"), (404, 404, 1, "other"), (200, 400, 1, "other"), (500, 200, 1, "other"),
    (0, 0, 0, "budget")])
def test_reason_table(http, code, tries, reason):
    assert td.expected_reason(http, code, tries) == reason


def _ok(req, url, bars, n=None, fetched="2026-11-30T07:22:09Z"):
    return {"src": "td", "req": req, "url": url, "http": 200, "td_code": 200, "status": "ok", "reason": None,
            "bytes": 5000, "sha256": "a" * 64, "values_n": len(bars) if n is None else n, "bars": bars,
            "fetched_utc": fetched, "tries": 1}


def _bar(t, o=4000.1, h=4003.0, low=3998.5, c=4001.2):
    return {"t_utc": t, "o": o, "h": h, "l": low, "c": c}


ASOF = T("2026-11-30T07:22:00Z")
HOURS = {"2026-11-30T05:00:00Z", "2026-11-30T06:00:00Z"}
URL = td.hourly_url("XAUUSD", T("2026-11-30T05:00:00Z"), T("2026-11-30T07:00:00Z"))


def problems(f, req="XAUUSD", url=URL, hours=HOURS):
    return td.provenance_problems(f, req, url, hours, ASOF)


def test_a_conforming_provenance_has_no_problem():
    assert problems(_ok("XAUUSD", URL, [_bar("2026-11-30T05:00:00Z"), _bar("2026-11-30T06:00:00Z")], n=3)) == []
    fresh = _ok("fresh", td.FRESH_URL, [_bar("2026-11-30T07:20:00Z")], n=1)
    assert td.provenance_problems(fresh, "fresh", td.FRESH_URL, None, ASOF) == []
    err = {"src": "td", "req": "XAUUSD", "url": URL, "http": 200, "td_code": 429, "status": "error",
           "reason": "credits", "bytes": 120, "sha256": "b" * 64, "values_n": 0, "bars": [],
           "fetched_utc": "2026-11-30T07:22:01Z", "tries": 1}
    assert problems(err) == []
    budget = dict(err, http=0, td_code=0, reason="budget", bytes=0, sha256="", fetched_utc=None, tries=0)
    assert problems(budget) == []


@pytest.mark.parametrize("change,why", [
    ({"url": URL + "&apikey=x"}, "url"),
    ({"req": "fresh"}, "req"),
    ({"src": "tick"}, "src"),
    ({"reason": "key"}, "reason"),
    ({"td_code": 401}, "ok_fields"),
    ({"bytes": 262145}, "ok_fields"),
    ({"tries": 3}, "tries"),
    ({"fetched_utc": "2026-11-30T07:21:59Z"}, "fetched_utc"),
    ({"values_n": 1}, "bars.values_n"),
])
def test_provenance_problems(change, why):
    f = _ok("XAUUSD", URL, [_bar("2026-11-30T05:00:00Z"), _bar("2026-11-30T06:00:00Z")])
    f.update(change)
    assert why in problems(f)


@pytest.mark.parametrize("bars,why", [
    ([_bar("2026-11-30T07:00:00Z")], "bars.hours"),                         # past h_new: not a listed hour
    ([_bar("2026-11-30T06:00:00Z"), _bar("2026-11-30T05:00:00Z")], "bars.order"),
    ([_bar("2026-11-30T05:00:00Z"), _bar("2026-11-30T05:00:00Z")], "bars.order"),
    ([_bar("2026-11-30T05:00:00Z", low=4000.5)], "bars.values"),            # l > min(o, c)
    ([_bar("2026-11-30T05:00:00Z", h=4001.0)], "bars.values"),              # h < max(o, c)
    ([_bar("2026-11-30T05:00:00Z", o=0.0, low=0.0)], "bars.values"),
    ([dict(_bar("2026-11-30T05:00:00Z"), n=3)], "bars.keys"),
    ([_bar("2026-11-30 05:00:00")], "bars.keys"),
])
def test_bar_rules(bars, why):
    assert why in problems(_ok("XAUUSD", URL, bars))


def test_an_error_keeps_no_bars_and_budget_needs_no_try():
    f = _ok("XAUUSD", URL, [_bar("2026-11-30T05:00:00Z")])
    f.update(status="error", reason="invalid")
    assert "bars" in problems(f) and "values_n" in problems(f)
    g = dict(f, bars=[], values_n=0, reason="budget", tries=1)
    assert "reason" in problems(g)


def test_fresh_keeps_its_newest_element_only():
    f = _ok("fresh", td.FRESH_URL, [_bar("2026-11-30T07:19:00Z"), _bar("2026-11-30T07:20:00Z")], n=2)
    assert "bars.fresh" in td.provenance_problems(f, "fresh", td.FRESH_URL, None, ASOF)
    g = _ok("fresh", td.FRESH_URL, [_bar("2026-11-30T07:20:30Z")], n=1)
    assert "bars.keys" in td.provenance_problems(g, "fresh", td.FRESH_URL, None, ASOF)
    e = _ok("fresh", td.FRESH_URL, [], n=1)
    assert "bars.fresh" in td.provenance_problems(e, "fresh", td.FRESH_URL, None, ASOF)


def test_canary_probe_outcome_from_the_context():
    x = _ok("XAUUSD", URL, [])
    fr = _ok("fresh", td.FRESH_URL, [])
    assert td.probe_outcome([x, fr]) == 200
    assert td.probe_outcome([dict(x, status="error", reason="credits", td_code=429, values_n=0), fr]) == 429
    assert td.probe_outcome([dict(x, status="error", reason="invalid", values_n=0)]) == -1
    assert td.probe_outcome([dict(x, status="error", reason="server", http=0, td_code=0)]) == 0
    eur = dict(_ok("EURUSD", "u", []), status="error", reason="key", td_code=401)
    assert td.probe_outcome([eur, fr]) == 200                  # no XAUUSD request: the `fresh` request
    assert td.probe_outcome([eur]) == -2
    assert td.probe_outcome([]) == -2


# ---------------------------------------------------------------- R-AN-84 as amended by A9 (unit)

@pytest.mark.parametrize("o,canary_fail,probe_fail", [
    (200, False, False), (0, False, True), (-2, False, True), (429, False, True), (503, False, True),
    (-1, True, True), (401, True, True), (403, True, True), (404, True, True), ("none", False, True)])
def test_net_twelvedata_pass_rules(o, canary_fail, probe_fail):
    base = {"net.twelvedata": o, "net.dukascopy": 0}
    assert ("net.twelvedata" in probe_fails(base, canary=True)) is canary_fail
    assert ("net.twelvedata" in probe_fails(base, canary=False)) is probe_fail


def test_net_dukascopy_is_expected_refused_from_A9_on():
    assert "net.dukascopy" in probe_fails({"net.twelvedata": 200, "net.dukascopy": 200}, canary=False)
    assert "net.dukascopy" in probe_fails({"net.twelvedata": 200, "net.dukascopy": 200}, canary=True)
    assert probe_fails({"net.twelvedata": 200, "net.dukascopy": 0}, canary=False) == []
    assert probe_fails({"net.twelvedata": 200, "net.dukascopy": 503}, canary=True) == []
    # a record without `net.twelvedata` was written by the pre-A9 code: net.dukascopy 200 was its pass (J-D44)
    assert probe_fails({"net.dukascopy": 200}, canary=False) == []


# ---------------------------------------------------------------- the judge's hour cache retries (unit)

def test_hour_source_refresh_retries_a_file_that_was_not_present(tmp_path):
    url_h = dt.datetime(2026, 11, 30, 5, tzinfo=UTC)
    from jlib import ticks
    from world import World as _W
    body, _n = _W.tick_file(None, "XAUUSD", url_h)
    files = {}
    hs = HourSource(FakeHourFetcher(files), str(tmp_path / "hours.csv"), "2026-11-30T08:00:00Z")
    assert hs.get("XAUUSD", url_h)["status"] == "empty"
    hs.flush()
    files[ticks.hour_url("XAUUSD", url_h)] = (200, body)
    hs2 = HourSource(FakeHourFetcher(files), str(tmp_path / "hours.csv"), "2026-12-01T08:00:00Z")
    assert hs2.get("XAUUSD", url_h)["status"] == "empty"                 # the cache answers
    assert hs2.get("XAUUSD", url_h, refresh=True)["status"] == "present"
    hs2.flush()
    hs3 = HourSource(FakeHourFetcher({}, down=True), str(tmp_path / "hours.csv"), "2026-12-02T08:00:00Z")
    assert hs3.get("XAUUSD", url_h, refresh=True)["status"] == "present"  # the later row wins; no fetch
    assert hs3.fetched == 0


def test_weekdays_since():
    d = dt.date(2026, 11, 30)                                           # a Monday
    assert td.weekdays_since(d, dt.date(2026, 12, 3)) == 3
    assert td.weekdays_since(d, dt.date(2026, 12, 4)) == 4
    assert td.weekdays_since(dt.date(2026, 11, 27), dt.date(2026, 12, 2)) == 3   # Fri -> Wed


# ---------------------------------------------------------------- the world (analyst-context/2)

SMALL = dict(canary_days=(), live_from="2026-11-30", live_to="2026-12-04", now="2026-12-07T23:00:00Z")


def small(tmp_path, hooks, **kw):
    return World(str(tmp_path / "small"), hooks=hooks, **dict(SMALL, **kw)).build()


def test_world_contexts_are_analyst_context_2(base):
    import json
    from jlib.gitrepo import GitRepo
    g = GitRepo(base.repo.path)
    try:
        b = g.show(g.head(), "analyst/calls/2026-11-30_W1.json")
    finally:
        g.close()
    ctx = json.loads(b)["context"]
    assert ctx["schema"] == "analyst-context/2" and ctx["sources"] == td.SOURCES
    assert [f["req"] for f in ctx["files"]] == list(td.REQ_ORDER)
    assert all(b_["src"] == "td" and b_["n"] is None for b_ in ctx["bars_h1"] if b_["t_utc"] >= "2026-11-30")
    assert ctx["p_ref"]["p_ref_src"] == "td" and isinstance(ctx["fresh"]["lag_s"], int)


def test_small_v2_world_is_sound(tmp_path):
    res = small(tmp_path, {}).judge()
    assert keys(res) == []
    assert res.summary["td_compared"] > 0 and res.summary.get("td_outside", 0) == 0


def test_A4_context_schema_1_is_not_accepted(tmp_path):
    def hook(world, win, ctx):
        if win.call_id == "2026-11-30_W2":
            ctx["schema"] = "analyst-context/1"
    res = small(tmp_path, {"context": hook}).judge()
    assert has(res, "A4", "context_schema", VIOLATION)


def _tamper_files(call_id, fn):
    def hook(world, win, files):
        if win.call_id == call_id:
            fn(world, win, files)
    return {"files": hook}


@pytest.mark.parametrize("fn", [
    lambda w, win, f: f[0].update(url=f[0]["url"] + "&apikey=demo"),
    lambda w, win, f: f[1].update(status="error", reason="credits", http=200, td_code=401, values_n=0, bars=[]),
    lambda w, win, f: f.insert(1, copy.deepcopy(f[1])),
    lambda w, win, f: f.pop(6),
    lambda w, win, f: f[0]["bars"].append(dict(f[0]["bars"][-1], t_utc=fmt_utc(T(f[0]["bars"][-1]["t_utc"]) + H))),
    lambda w, win, f: f[0]["bars"][-1].update(l=f[0]["bars"][-1]["h"] + 1),
])
def test_A4_recorded_requests_must_follow_R_AN_87(tmp_path, fn):
    res = small(tmp_path, _tamper_files("2026-11-30_W2", fn)).judge()
    assert has(res, "A4", "context_differs", VIOLATION)


def test_A4_bar_value_shown_differently_from_its_provenance(tmp_path):
    def hook(world, win, ctx):
        if win.call_id == "2026-11-30_W1":
            ctx["bars_h1"][-1]["c"] += 0.01
    res = small(tmp_path, {"context": hook}).judge()
    assert has(res, "A4", "context_differs", VIOLATION)


def _xau_fails(reason, http, code, extra_after=False):
    def fn(world, win, files):
        x = files[0]
        x.update(status="error", reason=reason, http=http, td_code=code, values_n=0, bars=[], bytes=90)
        if not extra_after:
            del files[1:]
    return fn


def test_xau_credits_failure_stops_the_context_no_call_data_td_credits(tmp_path):
    def probe(world, win, rec):
        if win.call_id == "2026-11-30_W2":
            rec["outcomes"]["net.twelvedata"] = 429
            rec["pass"]["net.twelvedata"] = None
            rec["verdict"] = "incomplete"
    hooks = dict(_tamper_files("2026-11-30_W2", _xau_fails("credits", 200, 429)), probe=probe)
    w = small(tmp_path, hooks, canary_days=("2026-11-30",), live_from="2026-12-01")
    res = w.judge()
    assert not keys(res, "A4") and not keys(res, "A5") and not keys(res, "A12", VIOLATION)
    assert w.call_status("canary", "2026-11-30_W2") == ("no_call:data", "td_credits")


def test_A4_a_request_after_the_xau_failure(tmp_path):
    hooks = _tamper_files("2026-11-30_W2", _xau_fails("key", 401, 401, extra_after=True))
    res = small(tmp_path, hooks).judge()
    assert has(res, "A4", "context_differs", VIOLATION)


def test_A12_canary_probe_twelvedata_must_be_the_contexts_first_request(tmp_path):
    def probe(world, win, rec):
        if win.call_id == "2026-11-30_W1":
            rec["outcomes"]["net.twelvedata"] = 0          # an outage would be null, but the context got 200
            rec["pass"]["net.twelvedata"] = None
    res = small(tmp_path, {"probe": probe}, canary_days=("2026-11-30",), live_from="2026-12-01").judge()
    assert keys(res, "A12", VIOLATION, "probe_failed") == [
        "A12|probe_failed|analyst/canary/calls/2026-11-30_W1.json|" + res_commit(res, "2026-11-30_W1")]


def res_commit(res, call_id):
    for f in res.findings.items:
        if f.code == "probe_failed" and call_id in f.path:
            return f.commit
    return "?"


# ---------------------------------------------------------------- A11: the Dukascopy cross-check

def _shift_dukascopy(world, sym, hour, factor):
    """Rewrite the judge's double of one Dukascopy hour file with every price times `factor`."""
    import lzma
    import struct
    from jlib import ticks
    from world import lzma_alone
    url = ticks.hour_url(sym, hour)
    http, body = world.hour_files[url]
    raw = lzma.decompress(body, format=lzma.FORMAT_ALONE)
    out = b""
    for ms, ask, bid, av, bv in struct.iter_unpack(">IIIff", raw):
        out += struct.pack(">IIIff", ms, round(ask * factor), round(bid * factor), av, bv)
    world.hour_files[url] = (200, lzma_alone(out))


def _first_xau_hour(world, call_id):
    ctx = world.context_of(call_id)
    return T(ctx["files"][0]["bars"][-1]["t_utc"])


def test_A11_td_mismatch_outside_1e_3(tmp_path):
    w = small(tmp_path, {})
    h = _first_xau_hour(w, "2026-11-30_W2")
    _shift_dukascopy(w, "XAUUSD", h, 1.0012)
    res = w.judge()
    ks = keys(res, "A11", WARNING, "td_mismatch")
    assert ks and all(k.startswith("A11|td_mismatch|analyst/calls/2026-11-30_W2.json|") for k in ks)
    f = [x for x in res.findings.items if x.code == "td_mismatch"][0]
    assert "XAUUSD" in f.detail and "rel" in f.detail
    assert not keys(res, severity=VIOLATION)
    assert res.summary["td_outside"] >= 1


def test_A11_within_1e_3_is_no_finding(tmp_path):
    w = small(tmp_path, {})
    h = _first_xau_hour(w, "2026-11-30_W2")
    _shift_dukascopy(w, "XAUUSD", h, 1.0006)
    res = w.judge()
    assert keys(res) == []


def test_A11_fx_p0_mismatch(tmp_path):
    w = small(tmp_path, {})
    ctx = w.context_of("2026-11-30_W1")
    t0 = T(ctx["fx"]["pairs"][1]["t0_hour_utc"])
    _shift_dukascopy(w, "USDJPY", t0, 0.997)
    res = w.judge()
    f = [x for x in res.findings.items if x.code == "td_mismatch"]
    # t0 is the model day's start, so both windows of the day compare that hour's p0
    assert sorted(x.path for x in f) == ["analyst/calls/2026-11-30_W1.json", "analyst/calls/2026-11-30_W2.json"]
    assert all("outside 1e-3: USDJPY 2026-11-29T22:00:00Z p0" in x.detail for x in f)


def test_A11_td_unchecked_after_3_weekdays_pending_before(tmp_path):
    w = small(tmp_path, {})
    down = HourSource(FakeHourFetcher({}, down=True), None, w.now)
    res = w.judge(hours=down)
    assert has(res, "A11", "td_unchecked", WARNING) and not keys(res, severity=VIOLATION)
    early = HourSource(FakeHourFetcher({}, down=True), None, "2026-12-02T23:00:00Z")
    res2 = w.judge(hours=early, now="2026-12-02T23:00:00Z")
    assert not keys(res2, "A11", code="td_unchecked") and res2.summary["td_pending"] > 0


class _Hours:
    """{(sym, hour_utc): row}: the judge's HourSource as the cross-check sees it."""

    def __init__(self, rows):
        self.rows = rows
        self.refreshed = []

    def get(self, sym, hour, refresh=False):
        if refresh:
            self.refreshed.append((sym, fmt_utc(hour)))
        return self.rows.get((sym, fmt_utc(hour)))


def _present(first, last, sym="XAUUSD"):
    pts = 1000 if sym in ("XAUUSD", "USDJPY") else 100000
    a, b = round(first * pts), round(last * pts)
    return {"status": "present", "first_ask": a, "first_bid": a, "last_ask": b, "last_bid": b}


def test_cross_check_rules():
    from jlib.context import td_cross_check
    x = _ok("XAUUSD", URL, [_bar("2026-11-30T05:00:00Z", o=4000.0, h=4010, low=3990, c=4004.0),
                             _bar("2026-11-30T06:00:00Z", o=4004.0, h=4010, low=3990, c=4008.0)])
    e = _ok("EURUSD", "u", [_bar("2026-11-29T22:00:00Z", o=1.08, h=1.09, low=1.07, c=1.081),
                             _bar("2026-11-30T06:00:00Z", o=1.082, h=1.09, low=1.07, c=1.083)])
    j = _ok("USDJPY", "u", [_bar("2026-11-30T06:00:00Z", o=150.0, h=151, low=149, c=150.5)])   # no t0 bar
    rows = {("XAUUSD", "2026-11-30T05:00:00Z"): _present(4000.0, 4004.0 * 1.002),
            ("XAUUSD", "2026-11-30T06:00:00Z"): {"status": "empty"},
            ("EURUSD", "2026-11-29T22:00:00Z"): _present(1.0801, 1.0, "EURUSD"),
            ("EURUSD", "2026-11-30T06:00:00Z"): _present(1.0, 1.0831, "EURUSD")}
    hs = _Hours(rows)
    r = td_cross_check("2026-11-30_W1", [x, e, j], hs, lambda h: False, dt.date(2026, 12, 1))
    assert [(c[0], c[1]) for c in r.compared] == [("XAUUSD", "2026-11-30T05:00:00Z"),
                                                  ("XAUUSD", "2026-11-30T05:00:00Z"),
                                                  ("EURUSD", "2026-11-29T22:00:00Z"),
                                                  ("EURUSD", "2026-11-30T06:00:00Z")]
    assert [c[2] for c in r.outside] == ["c"]                   # 4004 vs 4012: 2e-3; the rest within 1e-3
    assert r.pending == 2 and r.unchecked == []                 # the 06Z XAU file: tried again at each run
    assert ("XAUUSD", "2026-11-30T06:00:00Z") in hs.refreshed
    late = td_cross_check("2026-11-30_W1", [x, e, j], _Hours(rows), lambda h: False, dt.date(2026, 12, 4))
    assert late.pending == 0 and [u[:3] for u in late.unchecked] == [("XAUUSD", "2026-11-30T06:00:00Z", "o"),
                                                                       ("XAUUSD", "2026-11-30T06:00:00Z", "c")]
    opt = td_cross_check("2026-11-30_W1", [x, e, j], _Hours(rows), lambda h: h.hour == 6, dt.date(2026, 12, 4))
    assert opt.unchecked == [] and opt.pending == 0             # an optional hour whose file is empty: skipped
    gone = dict(rows)
    gone[("XAUUSD", "2026-11-30T06:00:00Z")] = None
    opt2 = td_cross_check("2026-11-30_W1", [x], _Hours(gone), lambda h: h.hour == 6, dt.date(2026, 12, 4))
    assert len(opt2.unchecked) == 2                             # not fetched at all: unchecked even when optional
    bad = dict(x, status="error", reason="invalid", bars=[], values_n=0)
    assert td_cross_check("2026-11-30_W1", [bad], _Hours(rows), lambda h: False, dt.date(2026, 12, 4)).compared == []


# ---------------------------------------------------------------- A12 ga_tag: the Dukascopy version's tag

def test_A12_ga_tag_allows_the_dukascopy_tag_at_its_commit_only(w):
    good = "79b9247901f15ee40d14d0f33cc8001f89bf31ce"
    tagobj = "1" * 40
    base_ls = list(w.api["ls_remote"][GA])
    w.api["ls_remote"][GA] = base_ls + [[tagobj, "refs/tags/analyst-dukascopy-v0.6"],
                                        [good, "refs/tags/analyst-dukascopy-v0.6^{}"]]
    assert keys(w.judge(), "A12") == []
    w.api["ls_remote"][GA] = base_ls + [[good, "refs/tags/analyst-dukascopy-v0.6"]]           # lightweight
    assert keys(w.judge(), "A12") == []
    head = w.repo.head()
    w.api["ls_remote"][GA] = base_ls + [[head, "refs/tags/analyst-dukascopy-v0.6"]]           # main's head: not it
    assert keys(w.judge(), "A12") == [f"A12|ga_tag|refs/tags/analyst-dukascopy-v0.6|{head}"]
    w.api["ls_remote"][GA] = base_ls + [[good, "refs/tags/analyst-dukascopy-v0.7"]]
    assert keys(w.judge(), "A12") == [f"A12|ga_tag|refs/tags/analyst-dukascopy-v0.7|{good}"]
