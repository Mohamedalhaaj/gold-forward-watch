"""J5 recomputation on the synthetic judge fixture (IMPLEMENTATION_REGISTER R-FX): every forecast, L1 block,
decision, trade, twin, e-value, state, the v2 summary and the published status file agree, and a single changed
number in a copy is found."""
import shutil
import sys

import pytest

from judge import recompute
from judge.common import parse_utc

NOW = parse_utc("2026-12-05T13:10:00Z")
PINS = {"lab-v1-freeze": "6cd6d57ef62d8eb8710dd5151c7b5ddc2612d095"}


@pytest.fixture(scope="module")
def full_run(root, fixture_world):
    ctx = recompute.Ctx(root, fixture_world, NOW, PINS)
    findings, info = recompute.run(ctx, v2_cover=None)
    return findings, info


def test_every_recomputed_number_agrees(full_run):
    findings, info = full_run
    assert findings == [], findings[:20]
    assert info["forecasts"]["compared"] == info["forecasts"]["store_rows"] == 1587
    assert info["l1"]["blocks"] == 1 and info["l1"]["green_ok"] == 1
    assert info["v1"]["days"] == 25 and info["v1"]["trades"] == 37
    assert info["v2"]["days"] == 20 and info["v2"]["trades"] == 21 and len(info["v2"]["checked_days"]) == 20
    assert info["status"]["lines"] == 28
    for name, m in list(sys.modules.items()):
        assert "/analysis/" not in (getattr(m, "__file__", None) or ""), name


@pytest.fixture()
def world_copy(tmp_path, fixture_world):
    dst = tmp_path / "w"
    shutil.copytree(fixture_world / "reports", dst / "reports")
    (dst / "data").symlink_to(fixture_world / "data")
    return dst


def _edit_csv(p, row_match, col, value):
    lines = p.read_text().splitlines()
    h = lines[0].split(",")
    i = h.index(col)
    for k, ln in enumerate(lines[1:], 1):
        if row_match(ln):
            parts = ln.split(",")
            parts[i] = value
            lines[k] = ",".join(parts)
            break
    p.write_text("\n".join(lines) + "\n")


def test_a_changed_v1_trade_is_found(root, world_copy):
    _edit_csv(world_copy / "reports/system/lab/trades.csv", lambda ln: ln.startswith("S1,2026-11-03"), "P_x",
              "4173.096")
    ctx = recompute.Ctx(root, world_copy, NOW, PINS)
    out = []
    recompute.check_v1_lab(ctx, out)
    assert any(f.subject == "v1 trades S1 2026-11-03" and "P_x" in f.detail for f in out), out


def test_a_changed_v2_decision_and_eproc_are_found(root, world_copy):
    _edit_csv(world_copy / "reports/system/lab_v2/decisions.csv", lambda ln: ln.startswith("S2,2026-11-09,12:05"),
              "signal", "1")
    _edit_csv(world_copy / "reports/system/lab_v2/eproc.csv", lambda ln: ln.startswith("S3,2,"), "E",
              "0.8807317817628584")
    ctx = recompute.Ctx(root, world_copy, NOW, PINS)
    out = []
    recompute.check_v2_lab(ctx, out, cover_days={"2026-11-09"})
    assert any(f.subject == "v2 decisions S2 2026-11-09" for f in out), out
    assert not any("eproc S3" in f.subject for f in out)       # 1e-16 relative: within 1e-9
    _edit_csv(world_copy / "reports/system/lab_v2/eproc.csv", lambda ln: ln.startswith("S3,2,"), "E", "0.9")
    out = []
    recompute.check_v2_lab(recompute.Ctx(root, world_copy, NOW, PINS), out, cover_days=set())
    assert any("eproc S3" in f.subject and "E " in f.detail for f in out), out


def test_a_changed_status_file_and_forecast_are_found(root, world_copy, tmp_path):
    p = world_copy / "reports/forward_site/system/VolMapSystem.csv"
    p.write_text(p.read_text().replace("lab_n_paper,1", "lab_n_paper,2").replace("lab2_days,15", "lab2_days,20"))
    ctx = recompute.Ctx(root, world_copy, NOW, PINS)
    out = []
    recompute.check_status_file(ctx, out, 1)
    assert any("lab_n_paper" in f.detail for f in out), out
    assert any("lab2_days '20' != '15'" in f.detail for f in out), out     # v1 published the PREVIOUS v2 summary
    # a forecast: the data folder is a symlink, so copy it for this edit
    (world_copy / "data").unlink()
    shutil.copytree(root / "tests/judge_fixtures/synthetic_world/data", world_copy / "data")
    fc = world_copy / "data/system/forecasts.csv"
    _edit_csv(fc, lambda ln: ln.startswith("2026-11-10,14,"), "F_S", "15.0")
    ctx = recompute.Ctx(root, world_copy, NOW, PINS)
    out = []
    recompute.check_forecasts(ctx, out)
    assert [f.subject for f in out] == ["forecasts 2026-11-10"], out
