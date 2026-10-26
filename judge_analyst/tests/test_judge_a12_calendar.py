"""Register §16.18 A12-D17..D21 (R-AN-10, R-AN-20, R-AN-23, R-AN-67 A4): the live macro calendar
`analyst/calendars/macro_2026_2027.csv`, the twelve-kind `events` block of `analyst-context/3` rebuilt from that file
at each call's repo_head_sha, its data-refresh rule (`A4|macro_calendar`) and the `/3` sources note. Built blind,
from the register text only."""
from __future__ import annotations

import datetime as dt
import hashlib

import pytest

from jlib import clock, td
from jlib.clock import KINDS_V3, MACRO_BUILD_SHA256, MACRO_PATH, Events, macro_problems
from jlib.common import VIOLATION
from jlib.context import rebuild_context
from jlib.gitrepo import GitRepo
from test_judge_a12 import A12_WORLD, PLANS, V2, V3, call_path, keys
from world import T, World

BUILD = clock.macro_build_bytes()
OPS_HEAD = b"utc,file,sha256,head_sha,note\n"
NEW8 = ("ppi", "jolts", "gdp", "pce", "retail", "ism_mfg", "ism_svc", "claims", "ecb")
JOLTS_ROW = ("2026-12-08,JOLTS,10:00,America/New_York,2026-12-08 15:00:00+00:00,"
             "https://www.bls.gov/schedule/news_release/jolts.htm")
ISM_ROW = ("2027-01-05,ISM_MFG,10:00,America/New_York,2027-01-05 15:00:00+00:00,"
           "https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/")
CLAIMS_1203 = next(ln for ln in BUILD.decode().split("\n") if ln.startswith("2026-12-03,CLAIMS,"))
NOTE_V3 = ("bars_h1 entries with src td, p_ref when p_ref_src is td, and fx come from Twelve Data hourly bars in UTC; "
           "bars_h1 entries with src store are Dukascopy mid; bars_d1 cover the 25 weekdays before the model day and "
           "are built from hourly bars made as bars_h1's are, but bars_h1 lists only the last 10 of those days, so the "
           "older bars_d1 days come from Dukascopy store hours not shown in bars_h1; Twelve Data and Dukascopy levels "
           "can differ slightly; settlement uses Dukascopy.")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def lines_of(b):
    return b.decode().split("\n")


def with_row(b, row):
    """b with `row` added where D17's order (ts_utc, event) puts it."""
    ls = lines_of(b)
    data = [x for x in ls[1:] if x] + [row]
    data.sort(key=lambda x: (x.split(",")[4], x.split(",")[1]))
    return ("\n".join([ls[0]] + data) + "\n").encode()


def replace_line(b, old, new):
    ls = lines_of(b)
    return "\n".join(new if x == old else x for x in ls).encode()


def log_row(b, note="refresh"):
    return f"2026-12-01T12:00:00Z,{MACRO_PATH},{sha(b)},{'a' * 40},{note}\n".encode()


def ev3(b=BUILD):
    return Events.judge_copies().with_macro(b)


def probs(b, ops=OPS_HEAD):
    return macro_problems(b, ops)


def has(ps, code):
    return any(p == code or p.startswith(code + " ") for p in ps)


# ---------------------------------------------------------------- D17: the build file (the judge's own byte copy)

def test_build_copy_is_the_registers_file():
    assert sha(BUILD) == MACRO_BUILD_SHA256 == "68a4c46c76087870b4cd7d6560418457d39daf67994188b6c600740e6c44fbb0"
    ls = lines_of(BUILD)
    assert ls[0] == "date,event,time_local,tz,ts_utc,source" and ls[-1] == ""
    assert len([x for x in ls[1:] if x]) == 136
    assert probs(BUILD) == []


# ---------------------------------------------------------------- D18: the events block

def test_events_v3_register_example_2026_10_29():
    b = ev3().context_block(dt.date(2026, 10, 29))
    assert set(b) == {"today", "next", "today_times_utc", "next_times_utc", "next_day"}
    assert tuple(b["today"]) == KINDS_V3 == ("nfp", "cpi", "fomc") + NEW8
    assert {k for k, v in b["today"].items() if v == 1} == {"claims", "gdp", "pce", "ecb"}
    assert all(v == 0 for k, v in b["today"].items() if k not in ("claims", "gdp", "pce", "ecb"))
    assert b["today_times_utc"] == [{"kind": "claims", "utc": "2026-10-29T12:30:00Z"},
                                    {"kind": "gdp", "utc": "2026-10-29T12:30:00Z"},
                                    {"kind": "pce", "utc": "2026-10-29T12:30:00Z"},
                                    {"kind": "ecb", "utc": "2026-10-29T13:15:00Z"}]
    assert b["next_day"] == "2026-10-30" and tuple(b["next"]) == KINDS_V3


def test_events_v3_next_day_and_sort_by_utc_then_kind():
    b = ev3().context_block(dt.date(2026, 11, 30))
    assert b["today_times_utc"] == [] and all(v in (0, None) for v in b["today"].values())
    assert b["next_day"] == "2026-12-01"
    assert b["next_times_utc"] == [{"kind": "ism_mfg", "utc": "2026-12-01T15:00:00Z"},
                                   {"kind": "jolts", "utc": "2026-12-01T15:00:00Z"}]
    f = ev3().context_block(dt.date(2026, 12, 4))                      # Friday: next is Monday
    assert f["next_day"] == "2026-12-07"
    assert f["today_times_utc"] == [{"kind": "nfp", "utc": "2026-12-04T13:30:00Z"}]


def test_events_v3_nulls_after_each_kinds_last_event():
    e = ev3()
    f = e.flags(dt.date(2026, 12, 1))
    assert f["jolts"] == 1 and f["ism_mfg"] == 1 and f["ism_svc"] == 0
    f = e.flags(dt.date(2026, 12, 2))
    assert f["jolts"] is None and f["ism_mfg"] is None and f["ism_svc"] == 0 and f["claims"] == 0
    f = e.flags(dt.date(2026, 12, 3))
    assert f["ism_svc"] == 1 and f["claims"] == 1
    assert e.flags(dt.date(2026, 12, 4))["ism_svc"] is None
    f = e.flags(dt.date(2027, 12, 22))
    assert f["gdp"] == 1 and f["pce"] == 1 and f["ppi"] is None and f["ecb"] is None and f["claims"] == 0
    f = e.flags(dt.date(2027, 12, 30))
    assert f["claims"] == 1 and f["gdp"] is None and f["nfp"] is None
    assert all(v is None for v in e.flags(dt.date(2027, 12, 31)).values())
    # a refresh moves a kind's horizon (R-AN-10: null after the last event in the file read)
    r = ev3(with_row(BUILD, ISM_ROW))
    assert r.flags(dt.date(2026, 12, 2))["ism_mfg"] == 0 and r.flags(dt.date(2027, 1, 5))["ism_mfg"] == 1
    assert r.flags(dt.date(2027, 1, 6))["ism_mfg"] is None


def test_events_v3_repeated_row_listed_once_and_v2_unchanged():
    first = lines_of(BUILD)[1]
    dup = BUILD + (first + "\n").encode()
    b = ev3(dup).context_block(dt.date(2026, 10, 29))
    assert [x["kind"] for x in b["today_times_utc"]] == ["claims", "gdp", "pce", "ecb"]
    v2 = Events.judge_copies().context_block(dt.date(2026, 12, 3))
    assert set(v2["today"]) == {"nfp", "cpi", "fomc"} and all(isinstance(t, str) for t in v2["next_times_utc"])
    assert v2["next_times_utc"] == ["2026-12-04T13:30:00Z"]


@pytest.mark.parametrize("bad", [
    None, b"\xff\xfe", BUILD.replace(b",source\n", b",src\n", 1),
    with_row(BUILD, ISM_ROW.replace("ISM_MFG", "PMI")),
    with_row(BUILD, ISM_ROW.replace("2027-01-05 15:00:00+00:00", "2027-01-05T15:00:00Z")),
    with_row(BUILD, "2027-01-05,ISM_MFG,10:00,America/New_York,2027-01-05 15:00:00+00:00")])
def test_events_v3_unbuildable_file_raises(bad):
    with pytest.raises(ValueError):
        ev3(bad)


# ---------------------------------------------------------------- D19: the refresh rule (A4 macro_calendar)

def test_refresh_logged_is_clean_and_unlogged_is_sha256():
    new = with_row(BUILD, ISM_ROW)
    assert probs(new, OPS_HEAD + log_row(new)) == []
    assert probs(new) == ["sha256"]
    other = OPS_HEAD + log_row(new).replace(MACRO_PATH.encode(), b"analyst/tables/holidays.csv")
    assert probs(new, other) == ["sha256"]
    assert probs(new, b"\xff") == ["sha256"]                           # an unreadable log logs nothing
    assert probs(new, None) == ["sha256"]


@pytest.mark.parametrize("make,code", [
    (lambda: replace_line(BUILD, CLAIMS_1203, CLAIMS_1203.replace("https://", "http://")), "build_rows"),
    (lambda: replace_line(BUILD, CLAIMS_1203, "\x00"), "build_rows"),
    (lambda: "\n".join(x for x in lines_of(BUILD) if x != CLAIMS_1203).encode(), "build_rows"),
    (lambda: BUILD.replace(b",source\n", b",src\n", 1), "header"),
    (lambda: with_row(BUILD, ISM_ROW.replace("2027-01-05", "2027-01-02")), "weekday"),
    (lambda: with_row(BUILD, ISM_ROW.replace("15:00:00+00:00", "14:00:00+00:00")), "ts_utc"),
    (lambda: with_row(BUILD, ISM_ROW.replace("ISM_MFG", "PMI")), "event"),
    (lambda: with_row(BUILD, ISM_ROW.replace("ISM_MFG", "ism_mfg")), "event"),
    (lambda: with_row(BUILD, ISM_ROW.replace("America/New_York", "EST")), "tz"),
    (lambda: with_row(BUILD, ISM_ROW.replace(",10:00,", ",10:00:00,")), "time_local"),
    (lambda: with_row(BUILD, ISM_ROW.replace(",10:00,", ",9:30,").replace("15:00:00", "14:30:00")), "time_local"),
    (lambda: with_row(BUILD, ISM_ROW.split(",https")[0] + ","), "source"),
    (lambda: with_row(BUILD, ISM_ROW.replace("2027-01-05,", "2027-1-05,", 1)), "date"),
    (lambda: with_row(BUILD, ISM_ROW + ",extra"), "fields"),
    (lambda: BUILD + (ISM_ROW + "\n").encode(), "order"),
    (lambda: with_row(with_row(BUILD, ISM_ROW), ISM_ROW.replace(",10:00,", ",14:00,").replace("15:00:00", "19:00:00")),
     "duplicate"),
])
def test_refresh_rule_breaks(make, code):
    b = make()
    ps = probs(b, OPS_HEAD + log_row(b))                               # logged, so only the rule itself breaks
    assert has(ps, code), (code, ps)
    assert not has(ps, "sha256")


def test_missing_and_unreadable_files():
    assert probs(None) == ["missing"]
    assert probs(b"\xff\xfe") == ["unreadable"]


# ---------------------------------------------------------------- the world: refreshes on gold-analyst main

def _commit(world, day, files, msg):
    world.owner_commit(files, T(f"{day.isoformat()}T03:30:00Z"), msg)


F1 = with_row(BUILD, JOLTS_ROW)
F2 = with_row(F1, ISM_ROW)
F4 = replace_line(F2, CLAIMS_1203, CLAIMS_1203.replace("claims_arch.asp", "claims.asp"))
OPS1 = OPS_HEAD + log_row(F1, "JOLTS 2026-12-08")
OPS3 = OPS1 + log_row(F2, "ISM_MFG 2027-01-05")
OPS4 = OPS3 + log_row(F4, "an edited build row")


def _day_hook(world, day):
    if day == dt.date(2026, 12, 2):                                    # a logged refresh: clean
        _commit(world, day, {MACRO_PATH: F1, "analyst/ops_changes.csv": OPS1}, "calendar refresh 1")
    elif day == dt.date(2026, 12, 4):                                  # a refresh not logged: macro_calendar
        _commit(world, day, {MACRO_PATH: F2}, "calendar refresh 2 (unlogged)")
    elif day == dt.date(2026, 12, 7):                                  # its sha logged later: clean again
        _commit(world, day, {"analyst/ops_changes.csv": OPS3}, "ops log for refresh 2")
    elif day == dt.date(2026, 12, 8):                                  # a build row edited, logged: macro_calendar
        _commit(world, day, {MACRO_PATH: F4, "analyst/ops_changes.csv": OPS4}, "calendar edit")


def _ctx_hook(world, win, ctx):
    if win.call_id == "2026-12-07_W2":                                 # events from the build file, not the file at R
        ctx["events"] = ev3().context_block(win.day)


@pytest.fixture(scope="module")
def refreshed(tmp_path_factory):
    w = World(str(tmp_path_factory.mktemp("a12cal") / "w"), plans=dict(PLANS),
              hooks={"day": _day_hook, "context": _ctx_hook}, **A12_WORLD).build()
    return w, w.judge()


def test_world_contexts_events_and_note(refreshed):
    w, _res = refreshed
    c2 = w.context_of("2026-11-30_W1")
    assert c2["schema"] == V2 and set(c2["events"]["today"]) == {"nfp", "cpi", "fomc"}
    assert c2["sources"] == td.SOURCES and "bars_d1 are built from bars_h1" in c2["sources"]["note"]
    c3 = w.context_of("2026-12-01_W1")                                 # at the build commit, before any refresh
    assert c3["schema"] == V3 and c3["sources"] == {"history": "dukascopy_store", "today": "twelvedata_1h",
                                                    "note": NOTE_V3}
    assert td.SOURCES_V3["note"] == NOTE_V3
    assert tuple(c3["events"]["today"]) == KINDS_V3
    assert c3["events"]["today"]["jolts"] == 1 and c3["events"]["next"]["jolts"] is None
    assert c3["events"]["today_times_utc"] == [{"kind": "ism_mfg", "utc": "2026-12-01T15:00:00Z"},
                                               {"kind": "jolts", "utc": "2026-12-01T15:00:00Z"}]
    c4 = w.context_of("2026-12-02_W1")                                 # after refresh 1, read at its repo_head_sha
    assert c4["events"]["today"]["jolts"] == 0 and c4["events"]["today"]["ism_mfg"] is None
    c5 = w.context_of("2026-12-08_W1")
    assert {"kind": "jolts", "utc": "2026-12-08T15:00:00Z"} in c5["events"]["today_times_utc"]
    assert c5["events"]["today"]["jolts"] == 1


def test_world_macro_calendar_findings(refreshed):
    w, res = refreshed
    mc = [f for f in res.findings.items if f.code == "macro_calendar"]
    assert mc and all(f.check == "A4" and f.severity == VIOLATION and f.path == MACRO_PATH for f in mc)
    heads = {cid: c["repo_head_sha"] for cid, c in w.contexts.items()}
    bad = {heads[c] for c in ("2026-12-04_W1", "2026-12-04_W2", "2026-12-08_W1", "2026-12-08_W2")}
    assert {f.commit for f in mc} == bad
    det = {f.commit: f.detail for f in mc}
    assert all("sha256" in det[heads[c]] for c in ("2026-12-04_W1", "2026-12-04_W2"))
    assert all("build_rows" in det[heads[c]] and "sha256" not in det[heads[c]]
               for c in ("2026-12-08_W1", "2026-12-08_W2"))
    assert f"A4|macro_calendar|{MACRO_PATH}|{heads['2026-12-04_W1']}" in [f.key for f in mc]


def test_world_rebuilds_events_at_repo_head_sha(refreshed):
    _w, res = refreshed
    f = [x for x in res.findings.items if x.code == "context_differs"]
    assert [x.path for x in f] == [call_path("2026-12-07_W2")] and "events" in f[0].detail
    others = [k for k in keys(res) if "|macro_calendar|" not in k and "|context_differs|" not in k]
    assert others == []
    assert res.summary["contexts_rebuilt"] == len(_w.calls) == 14


def test_rebuild_without_the_file_is_unreproducible(refreshed):
    w, _res = refreshed

    class NoMacro:
        def __init__(self, g):
            self.g = g

        def __getattr__(self, n):
            return getattr(self.g, n)

        def show(self, c, p):
            return None if p == MACRO_PATH else self.g.show(c, p)

    g = GitRepo(w.repo.path)
    try:
        ctx = w.context_of("2026-12-02_W1")
        rb = rebuild_context(ctx, "2026-12-02_W1", "live", NoMacro(g), None, w.holidays, w.events, schema=V3)
        assert rb.error == "macro_calendar"
        ok = rebuild_context(ctx, "2026-12-02_W1", "live", g, None, w.holidays, w.events, schema=V3)
        assert ok.error is None and ok.expected["events"] == ctx["events"]
    finally:
        g.close()
