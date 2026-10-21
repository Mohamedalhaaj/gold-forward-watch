"""The online-vs-full causality audit (§2.2, §4) on synthetic data and on the real input-only lookback days (signals
only: no trade and no outcome is computed on real data), plus the halt and the seed void when it fails."""
import json
import shutil
import types

import numpy as np
import pandas as pd
import pytest

import run_v2
import v2_data
import v2_ledger
import v2_signals

ROOT = run_v2.ROOT


def load_bars(P, now):
    cu = v2_data.v1_complete_utc(P.v1data, now)
    mf = v2_data.model_frame(v2_data.load_m1(P.lb, P.v1data, now, cu))
    m_in = v2_data.seed_input(mf)
    return {"M5": v2_data.seed_bars(m_in, "M5"), "M15": v2_data.seed_bars(m_in, "M15")}


def audit_days(bars_tf, days):
    out = {}
    for sid, _, tf, _ in v2_signals.SEEDS:
        full = v2_signals.full_values(v2_signals.load_seed(sid), bars_tf[tf])
        rows = [v2_ledger.audit_row(v2_signals.day_signals(sid, bars_tf[tf], full, d), tf, "t") for d in days]
        out[sid] = rows
    return out


def test_every_seed_is_causal_on_synthetic_days(world):
    bars_tf = load_bars(world, pd.Timestamp("2026-12-05 03:20", tz="UTC"))
    days = [pd.Timestamp(d) for d in ("2026-03-13", "2026-06-17", "2026-09-01", "2026-11-18", "2026-12-04")]
    res = audit_days(bars_tf, days)
    for sid, rows in res.items():
        assert all(r["result"] == "ok" and r["n_mismatch_outside"] == 0 for r in rows), (sid, rows)
        assert sum(r["n_window"] for r in rows) > 0
    assert sum(r["n_signals"] for rows in res.values() for r in rows) > 0


def lookahead_module():
    """A non-causal seed: the sign of the NEXT bar's move (reads the future)."""
    def signal(df):
        return np.sign(df.c.shift(-1) - df.c).fillna(0)
    return types.SimpleNamespace(NAME="peek", TF="M15", HOLD=8, signal=signal)


def test_a_lookahead_seed_fails_the_audit(world, monkeypatch):
    bars_tf = load_bars(world, pd.Timestamp("2026-12-05 03:20", tz="UTC"))
    monkeypatch.setitem(v2_signals._MODS, "S3", lookahead_module())
    b = bars_tf["M15"]
    full = v2_signals.full_values(v2_signals.load_seed("S3"), b)
    sg = v2_signals.day_signals("S3", b, full, "2026-11-18")
    row = v2_ledger.audit_row(sg, "M15", "t")
    assert row["result"] == "FAIL" and row["n_mismatch_window"] > 0 and row["first_mismatch"]
    assert all(v == 0 for v in sg.online)                 # online, the last bar has no next bar to peek at


@pytest.fixture(scope="module")
def short_world(tmp_path_factory):
    """A synthetic v1 + v2 sequence through 2026-11-07 (v2 registered, START 2026-11-09, nothing settled yet)."""
    base = tmp_path_factory.mktemp("short_world")
    P = run_v2.Paths(base)
    run_v2.setup_synthetic(P)
    run_v2.synthetic_runs(P, times=run_v2.SYNTH_TIMES[:4], log=lambda *a: None)
    return P


def copy_world(P, dst):
    shutil.copytree(P.base, dst)
    return run_v2.Paths(dst)


def test_an_audit_failure_halts_v2_and_voids_the_seed(short_world, tmp_path, monkeypatch):
    P = copy_world(short_world, tmp_path / "w")
    real = v2_signals.online_value

    def bad_online(mod, bars, i):                         # S5's online value differs at one window bar
        v = real(mod, bars, i)
        st = bars.index[i]
        if mod.NAME == "databar_stretch_settle" and st == pd.Timestamp("2026-11-10 12:00"):
            return 1 - v if v == 0 else -v
        return v
    monkeypatch.setattr(v2_signals, "online_value", bad_online)
    t = pd.Timestamp("2026-11-14 03:20", tz="UTC")
    code, info = run_v2.guarded_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=lambda *a: None)
    assert code == run_v2.EXIT_HALT and any("causality audit failed" in h for h in info["halt"])
    ev = pd.read_csv(P.reg / "events.csv")
    assert ((ev.id == "S5") & (ev.event == "RETIRED") & (ev.reason == "bug")).sum() == 1
    assert not (P.rep / "lab_days.csv").exists() and not (P.rep / "trades.csv").exists()
    audit = pd.read_csv(P.rep / "audit.csv")
    assert list(audit.result) == ["FAIL"] and list(audit.id) == ["S5"] and audit.first_mismatch[0] == "12:00"
    assert (P.rep / "HALT.md").exists()
    s = json.loads((P.rep / "summary.json").read_text())
    assert s["state"] == "PAUSED" and s["halted"]
    # the next run, without the defect: S5 stays void; the others settle; HALT.md is removed
    monkeypatch.setattr(v2_signals, "online_value", real)
    code, info = run_v2.guarded_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=lambda *a: None)
    assert code == 0 and info["settled_now"] and not (P.rep / "HALT.md").exists()
    assert "S5" not in set(pd.read_csv(P.rep / "decisions.csv").id) | set(
        pd.read_csv(P.rep / "audit.csv").query("result == 'ok'").id)
    s = json.loads((P.rep / "summary.json").read_text())
    assert s["state"] == "RUNNING" and {r["id"]: r["state"] for r in s["rules"]}["S5"] == "RETIRED"
    assert len(pd.read_csv(P.rep / "halts.csv")) == 1


def test_settlement_refuses_real_days_before_start(tmp_path):
    with pytest.raises(AssertionError):
        v2_ledger.settle(tmp_path, [], {}, [pd.Timestamp("2026-10-19")], None, None, "now", "x", "2026-11-09")
    with pytest.raises(AssertionError):
        v2_ledger.settle(tmp_path, [], {}, [pd.Timestamp("2026-11-10")], None, None, "now", "x", None)


REAL_DAYS = ["2026-01-14", "2026-02-11", "2026-03-11", "2026-04-15", "2026-05-13", "2026-06-17", "2026-07-15",
             "2026-08-12", "2026-09-16", "2026-10-14"]
V1_REAL_DAYS = ["2026-09-16", "2026-10-14"]          # in v1's committed raw store, always present


def real_lookback_view(tmp_path):
    """A read-only view of the real lookback store, whatever its state: a copy of its days rows (complete lines only,
    so a row being appended by a fetch in progress is ignored) and a link to its raw folder. Nothing is written in the
    real store."""
    src = ROOT / "data/system/lab_v2/lookback"
    dst = tmp_path / "lookback"
    dst.mkdir()
    text = (src / "days.csv").read_text() if (src / "days.csv").exists() else ""
    lines = [ln for ln in text.splitlines(keepends=True) if ln.endswith("\n") and ln.count(",") == 7]
    header = ",".join(v2_data.DAYS_COLS) + "\n"
    (dst / "days.csv").write_text(header + "".join(ln for ln in lines if ln != header))
    (dst / "raw").symlink_to(src / "raw", target_is_directory=True)
    return dst


def test_real_input_only_days_signals_are_causal(tmp_path):
    """Signals only, on input-only days (2026-01 .. 2026-10, all before START): online == full on every bar.
    No trade, no exit, no outcome is computed. It does not need a complete lookback store: it audits the days of
    REAL_DAYS that the store (or v1's store) holds when the test runs, at least the two v1 days."""
    P = types.SimpleNamespace(lb=real_lookback_view(tmp_path), v1data=ROOT / "data/system")
    now = pd.Timestamp.now(tz="UTC").floor("s")
    bars_tf = load_bars(P, now)
    have = set(bars_tf["M5"].day) & set(bars_tf["M15"].day)
    days = [pd.Timestamp(d) for d in REAL_DAYS if pd.Timestamp(d) in have]
    assert {pd.Timestamp(d) for d in V1_REAL_DAYS} <= set(days)
    assert max(days) < pd.Timestamp("2026-11-02")                      # input-only (before the earliest START)
    res = audit_days(bars_tf, days)
    for sid, rows in res.items():
        assert all(r["result"] == "ok" and r["n_mismatch_outside"] == 0 for r in rows), (sid, rows)
        assert all(r["n_bars"] > 0 for r in rows), sid
