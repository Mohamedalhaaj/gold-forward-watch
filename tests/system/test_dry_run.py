"""End to end (§9): the synthetic lab dry run, determinism and write-once ledgers, no lab outcome in a real-data dry
run, the FROZEN manifest, the vendored copies, and the untouched watch files."""
import filecmp
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import frozen_hashes
import publish
import run
import synth

WATCH = ["analysis/forward_doubletop_tracker.py", "analysis/forward_wick_tracker.py",
         ".github/workflows/forward-watch.yml", "reports/FORWARD_DOUBLETOP_PREREG.md",
         "reports/FORWARD_DOUBLETOP_CAUSAL_PREREG.md", "reports/FORWARD_WICK_PREREG.md"]
TRACKER_SHA = {"analysis/forward_doubletop_tracker.py":
               "fb3db8659b1a525c55aeb2622a3bda732cbc5c198abe456593cc93e01ab8b834",
               "analysis/forward_wick_tracker.py": "d1dc9d233cd95c929da192c07beefc66a3c2f9c529cad084e9eb4f4ad65b94b1"}
LEDGERS = ["data/system/forecasts.csv", "reports/system/l3_updates.csv", "reports/system/lab/decisions.csv",
           "reports/system/lab/trades.csv", "reports/system/lab/eproc.csv", "reports/system/lab/twins.csv",
           "reports/system/lab/lab_days.csv", "reports/system/lab/registry/events.csv"]


def watch_snapshot():
    root = pytest.ROOT
    files = [root / p for p in WATCH]
    for d in ("reports/forward_doubletop", "reports/forward_wick", "data/forward_doubletop", "data/forward_wick",
              "reports/forward_deploy"):
        files += sorted(p for p in (root / d).rglob("*") if p.is_file())
    files += sorted(p for p in (root / "reports/forward_site").rglob("*") if p.is_file() and "system" not in p.parts)
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    before = watch_snapshot()
    out = tmp_path_factory.mktemp("synthetic_a")
    assert run.main(["--dry", "--synthetic", "--out", str(out)]) == 0
    return out, before


def test_synthetic_lab_dry_run(synthetic):
    out, _ = synthetic
    start = json.loads((out / "reports/system/START.json").read_text())
    assert start["start"] == "2026-11-02"
    ev = pd.read_csv(out / "reports/system/lab/registry/events.csv")
    assert list(ev[ev.event == "REGISTERED"].id) == ["S1", "S1R", "C1"]
    assert set(ev.head_sha) == {"dry-placeholder"}
    days = pd.read_csv(out / "reports/system/lab/lab_days.csv")
    assert days.day.min() == "2026-11-02" and len(days) > 60
    dec = pd.read_csv(out / "reports/system/lab/decisions.csv")
    assert len(dec) == 3 * len(days)                                    # one row per rule per lab day
    assert not dec.duplicated(["id", "day"]).any()
    tr = pd.read_csv(out / "reports/system/lab/trades.csv")
    assert (tr.day >= "2026-11-02").all() and set(tr.status) == {"final"}
    assert len(tr) == (dec.outcome == "trigger").sum()                 # every trigger is settled
    s1 = tr[tr.id == "S1"]
    assert set(pd.to_datetime(s1.day).dt.dayofweek) <= {0, 1, 2, 3}     # Mon-Thu
    assert (s1.entry_model == "23:01").all() and (tr[tr.id == "S1R"].entry_model == "23:00").all()
    ep = pd.read_csv(out / "reports/system/lab/eproc.csv")
    assert len(ep) == len(tr)
    props = sorted(p.stem for p in (out / "reports/system/lab/proposer").glob("*.json"))
    assert props[0] == "2026-12-26" and all((pd.Timestamp(b) - pd.Timestamp(a)).days == 28
                                           for a, b in zip(props, props[1:]))
    kv = publish.parse_system_csv((out / "reports/forward_site/system/VolMapSystem.csv").read_text())
    assert kv is not None and kv["lab_state"] == "RUNNING" and int(kv["lab_days"]) == len(days)
    assert kv["l3_asof"] == "2027-02-01"
    lab = json.loads((out / "reports/forward_site/system/lab.json").read_text())        # strict JSON, no NaN
    assert {r["id"] for r in lab["rules"]} >= {"S1", "S1R", "C1"}
    assert "HALT.md" not in {p.name for p in (out / "reports/system").iterdir()}


def test_rerun_is_deterministic_and_write_once(synthetic, tmp_path):
    out, _ = synthetic
    out_b = tmp_path / "synthetic_b"
    assert run.main(["--dry", "--synthetic", "--out", str(out_b)]) == 0
    for f in LEDGERS + ["reports/forward_site/system/VolMapSystem.csv"]:
        assert filecmp.cmp(out / f, out_b / f, shallow=False), f
    # one more run at the last time: no ledger row changes
    snap = {f: (out_b / f).read_bytes() for f in LEDGERS}
    P = run.Paths(out_b)
    run.one_run(P, pd.Timestamp("2027-02-27 03:20", tz="UTC"), "synthetic", "dry", "dry-placeholder",
                fetch_on=False)
    for f in LEDGERS:
        assert (out_b / f).read_bytes() == snap[f], f


def test_a_dry_run_on_market_data_never_computes_lab_outcomes(tmp_path):
    """mode "dry" (real data) runs fetch -> forecasts -> L3 -> publish only; no lab ledger is written."""
    P = run.Paths(tmp_path)
    synth.world(P.data, first="2026-09-01", last="2026-11-20")
    P.reg.mkdir(parents=True)
    for f in run.SEED_FILES:
        (P.reg / f).write_bytes((pytest.ROOT / "reports/system/lab/registry" / f).read_bytes())
    info, halted = run.one_run(P, pd.Timestamp("2026-11-21 03:20", tz="UTC"), "dry", "dry", "dry", fetch_on=False)
    assert not halted
    for f in ("lab_days.csv", "decisions.csv", "trades.csv", "eproc.csv", "twins.csv"):
        assert not (P.lab / f).exists()
    assert not (P.reg / "events.csv").exists()
    assert (P.data / "forecasts.csv").exists() and (P.site / "VolMapSystem.csv").exists()


def test_watch_files_untouched(synthetic):
    _, before = synthetic
    assert watch_snapshot() == before
    for p, sha in TRACKER_SHA.items():
        assert hashlib.sha256((pytest.ROOT / p).read_bytes()).hexdigest() == sha


def test_frozen_manifest_and_vendored_copies():
    assert frozen_hashes.check() == []
    assert frozen_hashes.vendor_check() == []
    listed = [ln.split(maxsplit=1)[1] for ln in frozen_hashes.MANIFEST.read_text().splitlines()]
    assert listed == frozen_hashes.FROZEN_FILES


def test_a_frozen_mismatch_halts_the_lab(tmp_path, monkeypatch):
    monkeypatch.setattr(run.frozen_hashes, "check", lambda root=None: ["analysis/system/lab/grammar.py: differs"])
    P = run.Paths(tmp_path)
    synth.world(P.data, first="2026-09-01", last="2026-09-20")
    P.reg.mkdir(parents=True)
    info, halted = run.one_run(P, pd.Timestamp("2026-09-21 03:20", tz="UTC"), "synthetic", "dry", "dry",
                               fetch_on=False)
    assert halted and info["lab"]["state"] == "PAUSED"
    assert (P.rep / "HALT.md").exists()
    kv = publish.parse_system_csv((P.site / "VolMapSystem.csv").read_text())
    assert kv["lab_state"] == "PAUSED"
