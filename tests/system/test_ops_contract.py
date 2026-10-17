"""The status-file contract with the indicator (A1 item 3), operations (A1 item 11: failures exit non-zero, cloud mode
on main only) and the calendars (A1 item 10: extension file, horizon warning, per-year NYSE closures)."""
import hashlib

import pandas as pd
import pytest

import forecasts
import models
import publish
import run
import synth
import system_common as sc
from lab import proposer, registry

L1 = {"green_ok": 1, "asof": "2027-05-01"}
L3 = {"asof": None, "mult": {b: (1.0, 0) for b in sc.BUCKETS}}
LAB = {"state": "RUNNING", "days": 120, "n_paper": 1, "n_live": 0, "best_progress": 0.25, "live": []}


# ---------------------------------------------------------------- the indicator's reader, ported (VolMapBand.mq5)
def indicator_clean_title(v):
    """CleanTitle of VolMapBand.mq5 (xauusd-quant 6b5dc99, A1 item 3): 1..31 characters, each an Arabic letter
    (U+0621..U+064A without the tatweel U+0640), a digit (0-9 or U+0660..U+0669) or a space; the first an Arabic
    letter, the last not a space; else "" (the rule is shown without a title)."""
    def letter(c):
        return 0x0621 <= ord(c) <= 0x064A and ord(c) != 0x0640

    def digit(c):
        return "0" <= c <= "9" or 0x0660 <= ord(c) <= 0x0669
    if not 1 <= len(v) <= 31:
        return ""
    if not all(letter(c) or digit(c) or c == " " for c in v):
        return ""
    return v if letter(v[0]) and v[-1] != " " else ""


def indicator_read(data):
    """ParseSystem: the bytes as UTF-8 (CharArrayToString CP_UTF8), lines split on LF with CR removed, a BOM dropped,
    trailing empty lines dropped, the header and the end count checked, then key,value per line."""
    text = data.decode("utf-8")
    lines = [ln.replace("\r", "") for ln in text.split("\n")]
    if lines and lines[0].startswith("﻿"):
        lines[0] = lines[0][1:]
    while lines and lines[-1] == "":
        lines.pop()
    tail = lines[-1][4:] if lines else ""
    if not (len(lines) >= 2 and lines[0] == "key,value" and lines[-1].startswith("end,") and tail.isdigit()
            and int(tail) == len(lines) - 1):
        return None
    out = {"titles": {}}
    for ln in lines[1:-1]:
        c = ln.find(",")
        if c <= 0:
            return None
        key, v = ln[:c], ln[c + 1:]
        if key.startswith("lab_live_") and key.endswith("_title_ar"):
            out["titles"][int(key[9:-9])] = indicator_clean_title(v)
        else:
            out[key] = v
    return out


def test_every_possible_live_title_survives_publish_and_the_indicator_reader(tmp_path):
    """Cross-repo contract (review item CONTRACT-TITLE-ENCODING): the writer's file, read the indicator's way, gives
    back each title unchanged, for every title the proposer can produce and for the seeds."""
    titles = sorted({proposer.title_for(s) for s in proposer.space()}) + [r["title_ar"] for r in
                                                                          registry.seed_records()]
    for k in range(0, len(titles), 9):
        chunk = titles[k:k + 9]
        live = [{"id": f"P{i}", "title_ar": t, "n_post": i} for i, t in enumerate(chunk)]
        path = tmp_path / "VolMapSystem.csv"
        publish.write_system_csv(path, publish.system_csv("2027-05-01T03:20:00Z", L1, L3,
                                                          LAB | {"n_live": len(live), "live": live}))
        data = path.read_bytes()
        got = indicator_read(data)
        assert got is not None
        assert [got["titles"][i + 1] for i in range(len(chunk))] == chunk
        assert got["lab_n_paper"] == "1" and got["lab_days"] == "120"
        assert publish.parse_system_csv(data)["lab_live_1_title_ar"] == chunk[0]


MQ5 = pytest.ROOT.parent / "xauusd-quant" / "mt5" / "VolMapBand.mq5"


@pytest.mark.skipif(not MQ5.exists(), reason="the xauusd-quant checkout is not next to this repo")
def test_the_port_matches_the_indicator_source():
    """The port above against the indicator's source: the length limit, the letter and digit ranges, CP_UTF8."""
    import re
    src = MQ5.read_text(encoding="utf-8", errors="replace")
    assert re.search(r"#define\s+VM_TITLE_MAX\s+31\b", src)
    assert "return (c >= 0x0621 && c <= 0x064A && c != 0x0640);" in src
    assert "return ((c >= '0' && c <= '9') || (c >= 0x0660 && c <= 0x0669));" in src
    assert "CharArrayToString(raw, 0, (int)nr, CP_UTF8)" in src


def test_the_reader_port_drops_what_the_old_encoding_sent():
    """The v1 build wrote hex UTF-16 ("0639..."): the indicator would have shown no title."""
    assert indicator_clean_title("0639064300633") == ""
    assert indicator_clean_title("عكس حركة إغلاق نيويورك قبل 23") == "عكس حركة إغلاق نيويورك قبل 23"


# ---------------------------------------------------------------- operations (A1 item 11)
def world(P, last):
    synth.world(P.data, first="2026-09-01", last=last)
    P.reg.mkdir(parents=True, exist_ok=True)
    for f in run.SEED_FILES:
        (P.reg / f).write_bytes((pytest.ROOT / "reports/system/lab/registry" / f).read_bytes())


def test_cloud_mode_runs_only_on_main(monkeypatch):
    assert run.cloud_refusal({}) is not None
    assert "main" in run.cloud_refusal({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/system-v1"})
    monkeypatch.setattr(run, "git", lambda *a: "abc")
    assert run.cloud_refusal({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"}) is None
    monkeypatch.setattr(run, "git", lambda *a: "abc" if a[-1] == "HEAD" else "def")
    assert "origin/main" in run.cloud_refusal({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"})


def test_main_refuses_another_branch_before_writing_anything(monkeypatch):
    def snap():
        out = {}
        for d in ("data/system", "reports/system", "reports/forward_site/system"):
            for p in sorted((pytest.ROOT / d).rglob("*")):
                if p.is_file():
                    out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out
    before = snap()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    assert run.main(["--no-fetch", "--no-deploy"]) != 0
    assert snap() == before


def test_a_fetch_exception_fails_the_run_without_halting_the_lab(tmp_path, monkeypatch):
    P = run.Paths(tmp_path)
    world(P, "2026-11-20")
    def boom(*a, **k):
        raise RuntimeError("feed down")
    monkeypatch.setattr(run.fetch, "run", boom)
    info, halted = run.one_run(P, pd.Timestamp("2026-11-21 03:20", tz="UTC"), "dry", "dry", "dry", fetch_on=True)
    assert not halted and info["lab"]["state"] == "RUNNING"
    assert any("fetch raised" in o for o in info["ops"]) and run.exit_code(info, halted) == run.EXIT_OPS


def test_a_failed_deploy_fails_the_run_and_is_in_status(tmp_path):
    P = run.Paths(tmp_path)
    world(P, "2026-10-26")
    info, halted = run.cloud_run(P, pd.Timestamp("2026-10-27 03:20", tz="UTC"), "7", "h7", fetch_on=False,
                                 deploy_fn=lambda: False)
    assert not halted and "deploy failed (wrangler)" in info["ops"] and run.exit_code(info, halted) == 2
    assert "deploy failed (wrangler)" in (P.rep / "STATUS.md").read_text()
    assert (P.rep / "START.json").exists()
    ok, h2 = run.cloud_run(run.Paths(tmp_path / "b"), pd.Timestamp("2026-10-27 03:20", tz="UTC"), "7", "h7",
                           fetch_on=False, deploy_fn=lambda: True)
    assert ok["ops"] == [] or all("deploy" not in o for o in ok["ops"])


def test_lagging_data_fail_the_run(tmp_path):
    P = run.Paths(tmp_path)
    world(P, "2026-11-13")                                    # data end Friday 11-13; the run is on Thursday 11-19
    info, halted = run.one_run(P, pd.Timestamp("2026-11-19 03:20", tz="UTC"), "dry", "dry", "dry", fetch_on=False)
    assert not halted and info["data"]["lag_trading_days"] == 3
    assert any("lag 3 trading days" in o for o in info["ops"]) and run.exit_code(info, halted) == 2
    info, halted = run.one_run(P, pd.Timestamp("2026-11-18 03:20", tz="UTC"), "dry", "dry", "dry", fetch_on=False)
    assert info["data"]["lag_trading_days"] == 2 and not any("lag" in o for o in info["ops"])


# ---------------------------------------------------------------- calendars (A1 item 10)
BLS = "https://www.bls.gov/schedule/news_release/empsit.htm"
FED = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


def test_holidays_per_year_equal_the_frozen_range():
    assert forecasts.holidays(2027).equals(models.nyse_holidays("2015-01-01", "2027-12-31"))
    h28 = forecasts.holidays(2028)
    assert h28[h28 <= "2027-12-31"].equals(forecasts.holidays(2027)) and (h28 > "2027-12-31").sum() >= 9
    import pandas_market_calendars as mcal
    a, b = "2015-01-01", "2027-12-31"
    old = set(pd.bdate_range(a, b).difference(mcal.get_calendar("NYSE").schedule(a, b).index.normalize()))
    assert forecasts.full_closures(2027) == old
    assert pd.Timestamp("2028-12-25") in forecasts.full_closures(2028)


def test_extension_review():
    now = pd.Timestamp("2027-12-20 03:20", tz="UTC")
    good = [f"NFP,2028-01-07 13:30:00+00:00,{BLS}", f"FOMC,2028-01-26T19:00:00Z,{FED}"]
    bad = [f"NFP,2028-01-02 13:30:00+00:00,{BLS}",            # less than 14 days after it was first seen
           f"CPI,2028-01-12 13:30:00+00:00,https://example.com/cpi",   # not the official page
           f"CPI,2027-11-10 13:30:00+00:00,{BLS}",            # inside the frozen range
           f"CPI,2028-01-12 13:30:00,{BLS}",                  # no offset
           f"GDP,2028-01-12 13:30:00+00:00,{BLS}"]
    new, acc, problems = forecasts.ext_review(good + bad, [], now, "1", "h")
    assert [r["status"] for r in new] == ["accepted"] * 2 + ["rejected"] * 5 and len(problems) == 5
    assert "14 days" in new[2]["reason"] and "official" in new[3]["reason"] and "frozen" in new[4]["reason"]
    assert acc["NFP"] == [pd.Timestamp("2028-01-07 13:30", tz="UTC")] and len(acc["FOMC"]) == 1
    # the next run: nothing new, no problem; dropping a rejected line is fine
    new2, acc2, p2 = forecasts.ext_review(good, new, now + pd.Timedelta(days=1), "2", "h")
    assert new2 == [] and p2 == [] and acc2 == acc
    # an accepted line that is changed: the old one stays in use, the change is reported (and reviewed as new)
    edited = [good[0].replace("13:30", "14:30"), good[1]]
    new3, acc3, p3 = forecasts.ext_review(edited, new, now + pd.Timedelta(days=2), "3", "h")
    assert any("changed or removed" in x for x in p3)
    assert pd.Timestamp("2028-01-07 13:30", tz="UTC") in acc3["NFP"]
    ev = forecasts.load_events(ext=acc)
    assert pd.Timestamp("2028-01-07 15:30") in ev["NFP"]          # model clock = New York + 7 (EST: UTC + 2)
    assert len(ev["CPI"]) == len(forecasts.load_events()["CPI"])


def test_calendar_horizon_warning(tmp_path, monkeypatch):
    assert forecasts.calendar_horizon(forecasts.load_events()) == pd.Timestamp("2027-12-03")
    P = run.Paths(tmp_path)
    ext = tmp_path / "events.csv"
    ext.write_text(forecasts.EXT_HEADER + "\n")
    monkeypatch.setattr(forecasts, "EXT_FILE", ext)
    ops = []
    run.calendars(P, pd.Timestamp("2027-10-03 03:20", tz="UTC"), "x", "1", "h", ops)
    assert ops == []
    run.calendars(P, pd.Timestamp("2027-10-04 03:20", tz="UTC"), "x", "1", "h", ops)
    assert len(ops) == 1 and "2027-12-03" in ops[0]
    # extending every kind moves the horizon; the record of seen lines is append-only
    ext.write_text(forecasts.EXT_HEADER + "\n" + "\n".join([
        f"NFP,2028-01-07 13:30:00+00:00,{BLS}", f"CPI,2028-01-12 13:30:00+00:00,{BLS}",
        f"FOMC,2028-01-26 19:00:00+00:00,{FED}"]) + "\n")
    ops = []
    ev, hol, clo, cal = run.calendars(P, pd.Timestamp("2027-10-04 03:20", tz="UTC"), "x", "2", "h", ops)
    assert ops == [] and cal["horizon"] == "2028-01-07" and cal["ext_accepted"] == 3
    seen = pd.read_csv(P.rep / "calendar_ext.csv", dtype=str)
    assert list(seen.status) == ["accepted"] * 3 and set(seen.first_seen_utc) == {"2027-10-04T03:20:00Z"}


def test_the_extension_file_is_ops_not_frozen():
    listed = [ln.split(maxsplit=1)[1] for ln in (pytest.ROOT / "analysis/system/FROZEN.sha256").read_text().splitlines()]
    assert "analysis/system/calendars_ext/events.csv" not in listed
    assert "analysis/system/calendars_ext/events.csv" in run.OPS_FILES
    assert forecasts.read_ext_lines(forecasts.EXT_FILE) == [] or all(
        forecasts.parse_ext_line(ln)[0] for ln in forecasts.read_ext_lines(forecasts.EXT_FILE))
