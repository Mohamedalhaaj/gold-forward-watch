"""The analyst input mirror (xauusd-quant IMPLEMENTATION_REGISTER.md R-AN-12)."""
import datetime as dt
import hashlib
import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("analyst_export", ROOT / "analysis/analyst_export/export.py")
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)
NOW = dt.datetime(2026, 10, 23, 5, 10, tzinfo=dt.timezone.utc)


def source(tmp, days=("2026-10-20", "2026-10-21"), fc_rows=None):
    src = tmp / "gfw"
    lines = ["day,side,status,bytes,sha256,records,vol_minutes,fetched_utc"]
    for d in days:
        for side in ("BID", "ASK"):
            body = f"{d}{side}".encode() * 10
            p = src / "data/system/raw" / ex.raw_rel(d, side)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
            lines.append(f"{d},{side},ok,{len(body)},{hashlib.sha256(body).hexdigest()},1440,1380,2026-10-22T08:00:00Z")
    lines.append("2026-08-31,BID,ok,1,x,1440,1380,2026-10-17T00:00:00Z")          # before 2026-09-01: never copied
    lines.append("2026-10-19,ASK,missing,,,,,2026-10-23T00:00:00Z")
    (src / "data/system").mkdir(parents=True, exist_ok=True)
    (src / "data/system/days.csv").write_text("\n".join(lines) + "\n")
    rows = fc_rows or [f"2026-10-21,{s},2026-10-21 {s + 1:02d}:00,2026-10-21T00:00Z,1.0,2.0,4000.0,,0,0,0,0,"
                       f"2026-10-22T08:40:00Z" for s in range(23)]
    (src / "data/system/forecasts.csv").write_text(
        "day,slot,origin_model,origin_utc,F_H1,F_S,price,y_bp,nfp,cpi,fomc,hol,computed_utc\n" + "\n".join(rows) + "\n")
    return src


def test_first_export_and_idempotent_second(tmp_path):
    src, dst = source(tmp_path), tmp_path / "ga"
    dst.mkdir()
    s = ex.export(src, dst, "a" * 40, "7", NOW)
    assert s["raw_files"] == 4 and s["new_raw_files"] == 4
    assert (dst / "mirror/system/days.csv").read_bytes() == (src / "data/system/days.csv").read_bytes()
    slots = (dst / "mirror/system/forecasts_slots.csv").read_text().splitlines()
    assert slots[0].startswith("day,slot,") and [l.split(",")[1] for l in slots[1:]] == ["9", "10", "15"]
    for l in slots[1:]:
        assert l in (src / "data/system/forecasts.csv").read_text()           # exact source lines
    assert not (dst / "mirror/system/raw/2026/08/31").exists()
    s2 = ex.export(src, dst, "b" * 40, "8", NOW)
    assert s2["new_raw_files"] == 0
    rows = (dst / "mirror/exports.csv").read_text().splitlines()
    assert rows[0] == ",".join(ex.EXPORT_COLS) and len(rows) == 3 and rows[2].split(",")[1] == "b" * 40


def test_prefix_and_sha_checks_write_nothing(tmp_path):
    src, dst = source(tmp_path), tmp_path / "ga"
    dst.mkdir()
    ex.export(src, dst, "a" * 40, "1", NOW)
    before = {p: p.read_bytes() for p in dst.rglob("*") if p.is_file()}
    (dst / "mirror/system/days.csv").write_bytes(b"different\n")
    with pytest.raises(ex.ExportError):
        ex.export(src, dst, "a" * 40, "2", NOW)
    (dst / "mirror/system/days.csv").write_bytes(before[dst / "mirror/system/days.csv"])
    raw = dst / "mirror/system/raw" / ex.raw_rel("2026-10-20", "BID")
    raw.write_bytes(b"tampered")
    with pytest.raises(ex.ExportError):
        ex.export(src, dst, "a" * 40, "3", NOW)
    raw.write_bytes(before[raw])
    (src / "data/system/raw" / ex.raw_rel("2026-10-21", "ASK")).write_bytes(b"changed at the source")
    with pytest.raises(ex.ExportError):
        ex.export(src, dst, "a" * 40, "4", NOW)
    after = {p: p.read_bytes() for p in dst.rglob("*") if p.is_file()}
    assert after == before


def test_slots_must_stay_a_prefix(tmp_path):
    src, dst = source(tmp_path), tmp_path / "ga"
    dst.mkdir()
    ex.export(src, dst, "a" * 40, "1", NOW)
    fc = src / "data/system/forecasts.csv"
    fc.write_text(fc.read_text().replace("2026-10-21,9,", "2026-10-21,9,X", 1))
    with pytest.raises(ex.ExportError):
        ex.export(src, dst, "a" * 40, "2", NOW)


def test_the_workflow_pushes_mirror_only_with_a_named_deploy_key():
    wf = (ROOT / ".github/workflows/analyst-export.yml").read_text()
    assert "${{ secrets.ANALYST_MIRROR_DEPLOY_KEY }}" in wf
    assert "grep -v '^mirror/'" in wf and "pull_request" not in wf
    assert "permissions:\n  contents: read" in wf


# §16.18 A14-D10 (R-AN-12 step 3b): the whole forecast store, byte copy, prefix rule.
def test_step_3b_copies_the_whole_forecast_store(tmp_path):
    src, dst = source(tmp_path), tmp_path / "ga"
    dst.mkdir()
    s = ex.export(src, dst, "a" * 40, "1", NOW)
    fc_src = (src / "data/system/forecasts.csv").read_bytes()
    fc_dst = (dst / "mirror/system/forecasts.csv").read_bytes()
    assert fc_dst == fc_src                                                     # every slot, byte copy
    assert hashlib.sha256(fc_dst).hexdigest() == s["forecasts_sha256"]
    row = dict(zip(ex.EXPORT_COLS, (dst / "mirror/exports.csv").read_text().splitlines()[1].split(",")))
    assert row["forecasts_sha256"] == hashlib.sha256(fc_dst).hexdigest()
    assert (dst / "mirror/system/forecasts_slots.csv").exists()                 # step 3 unchanged
    fc = src / "data/system/forecasts.csv"                                      # the store grows by appending
    fc.write_bytes(fc_src + b"2026-10-22,0,2026-10-22 01:00,2026-10-22T00:00Z,1.0,2.0,4000.0,,0,0,0,0,"
                            b"2026-10-23T08:40:00Z\n")
    s2 = ex.export(src, dst, "b" * 40, "2", NOW)
    assert (dst / "mirror/system/forecasts.csv").read_bytes() == fc.read_bytes()
    assert s2["forecasts_sha256"] == hashlib.sha256(fc.read_bytes()).hexdigest()


def test_step_3b_starts_on_a_mirror_that_has_only_the_slots_file(tmp_path):
    src, dst = source(tmp_path), tmp_path / "ga"
    dst.mkdir()
    ex.export(src, dst, "a" * 40, "1", NOW)
    (dst / "mirror/system/forecasts.csv").unlink()                              # gold-analyst main before A14
    ex.export(src, dst, "a" * 40, "2", NOW)
    assert (dst / "mirror/system/forecasts.csv").read_bytes() == (src / "data/system/forecasts.csv").read_bytes()


def test_step_3b_prefix_rule_stops_and_writes_nothing(tmp_path):
    src, dst = source(tmp_path), tmp_path / "ga"
    dst.mkdir()
    ex.export(src, dst, "a" * 40, "1", NOW)
    before = {p: p.read_bytes() for p in dst.rglob("*") if p.is_file()}
    fc = src / "data/system/forecasts.csv"                                      # a slot outside 9, 10, 15 rewritten:
    fc.write_text(fc.read_text().replace("2026-10-21,3,", "2026-10-21,3,X", 1))  # the slots file still a prefix
    with pytest.raises(ex.ExportError, match="forecasts.csv"):
        ex.export(src, dst, "a" * 40, "2", NOW)
    after = {p: p.read_bytes() for p in dst.rglob("*") if p.is_file()}
    assert after == before
    with pytest.raises(ex.ExportError):
        ex.plan(src, dst)
