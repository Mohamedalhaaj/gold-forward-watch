"""The synthetic end-to-end dry run (§4): v1 + v2 on the synthetic world, byte-identical across two runs and equal to
the committed judge fixture (tests/judge_fixtures/synthetic_world), with the registration, START, ledger and publish
contracts checked on its output."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import publish
import run_v2
import v2_ledger
import v2_lookback

FIXTURE = Path(__file__).resolve().parents[2] / "judge_fixtures" / "synthetic_world"
FIXTURE_DOCS = {"README.md", "MANIFEST.sha256"}


def tree(base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(base).rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def dry(tmp_path_factory):
    out = tmp_path_factory.mktemp("dry_a")
    assert run_v2.main(["--dry", "--synthetic", "--out", str(out)]) == 0
    return out


def test_two_runs_are_byte_identical(dry, tmp_path):
    out_b = tmp_path / "dry_b"
    assert run_v2.main(["--dry", "--synthetic", "--out", str(out_b)]) == 0
    a, b = tree(dry), tree(out_b)
    assert a == b and len(a) > 700


def test_the_committed_judge_fixture_is_this_run(dry):
    got = {k: v for k, v in tree(FIXTURE).items() if k not in FIXTURE_DOCS}
    assert got == tree(dry)
    man = dict(line.split("  ", 1)[::-1] for line in (FIXTURE / "MANIFEST.sha256").read_text().splitlines())
    assert man == got


def test_registration_start_and_first_day(dry):
    P = run_v2.Paths(dry)
    s1 = json.loads((dry / "reports/system/START.json").read_text())
    s2 = json.loads((P.rep / "START.json").read_text())
    assert s1["start"] == "2026-11-02" and s2["v1_start"] == "2026-11-02"
    assert s2["first_cloud_run_utc"] == "2026-11-03T03:20:00Z" and s2["start"] == "2026-11-09"
    ev = pd.read_csv(P.reg / "events.csv")
    reg = ev[ev.event == "REGISTERED"]
    assert list(reg.id) == ["S2", "S3", "S4", "S5"] and set(reg.utc) == {"2026-11-03T03:20:00Z"}
    assert set(reg.run_id) == {"dry"} and set(reg.head_sha) == {"dry-placeholder"}
    s = json.loads((P.rep / "summary.json").read_text())
    assert {r["first_day"] for r in s["rules"]} == {"2026-11-09"}


def test_ledgers(dry):
    P = run_v2.Paths(dry)
    days = pd.read_csv(P.rep / "lab_days.csv")
    assert days.day.min() == "2026-11-09" and days.day.max() == "2026-12-04" and len(days) == 20
    dec = pd.read_csv(P.rep / "decisions.csv")
    tr = pd.read_csv(P.rep / "trades.csv")
    assert (dec.day >= "2026-11-09").all() and set(dec.outcome) <= set(v2_ledger.OUTCOMES)
    assert len(tr) == (dec.outcome == "trade").sum() and set(tr.status) == {"final"}
    assert (dec[dec.day.isin(["2026-11-26", "2026-11-27"])].outcome == "abstain_day").all()   # NYSE holidays
    ep = pd.read_csv(P.rep / "eproc.csv")
    tw = pd.read_csv(P.rep / "twins.csv")
    assert len(ep) == len(tr) == len(tw)
    for sid, g in ep.groupby("id"):
        assert list(g.trade_no) == list(range(1, len(g) + 1))
    au = pd.read_csv(P.rep / "audit.csv")
    assert len(au) == 4 * len(days) and set(au.result) == {"ok"} and au.n_mismatch_window.sum() == 0
    assert (pd.to_datetime(tr.day + " " + tr.entry_model) - pd.to_datetime(tr.day + " " + tr["T"])).eq(
        pd.Timedelta(minutes=1)).all()
    assert v2_ledger.ledger_consistent(P.rep) == []
    assert not (P.rep / "HALT.md").exists()


def test_publish(dry):
    P = run_v2.Paths(dry)
    s = json.loads((P.rep / "summary.json").read_text())
    assert s["state"] == "RUNNING" and s["days"] == 20 and s["n_paper"] == 4
    assert {r["id"]: r.get("warmup") for r in s["rules"]}["S3"] is True
    kv = publish.parse_system_csv((dry / "reports/forward_site/system/VolMapSystem.csv").read_text())
    assert kv["lab2_state"] == "RUNNING" and kv["lab2_n_paper"] == "4" and kv["lab2_days"] == "15"   # previous run's
    html = (P.site / "index.html").read_text()
    assert "المختبر، الإصدار الثاني" in html and "في مرحلة الإحماء حتى تكتمل بياناتها" in html
    assert json.loads((P.site / "lab_v2.json").read_text())["c1"]["n"] > 0
    assert v2_lookback.complete(P.lb)
