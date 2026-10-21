"""The lab v2 job (SYSTEM_V2_PREREG.md §2.5). OPS: I/O orchestration only; every decision with lab semantics is made
in a FROZEN module (v2_data, v2_signals, v2_exec, v2_ledger, v2_registry and the v1 modules they import).

Isolation (§2.5): the workflow runs this as its own step, `uv run --frozen python -I
analysis/system/lab_v2/run_v2.py`, with continue-on-error, after v1's step and after v1's commit step, and commits only
data/system/lab_v2, reports/system/lab_v2 and reports/forward_site/system/lab_v2 in a separate commit. This script
writes nothing else: it reads v1's committed raw days (data/system/raw, days.csv), v1's forecast store
(data/system/forecasts.csv), v1's START.json and v1's coin-control trades, read-only. A v2 exception, a FROZEN_V2
mismatch, a raw-store mismatch, a registry problem, an inconsistent ledger, an audit failure or a tripwire difference
writes reports/system/lab_v2/HALT.md and halts lab v2 only (state PAUSED); v1's exit code, publish, deploy and commit
are never touched. HALT.md is a snapshot of the latest run: a later run that does not halt removes it, and every halt
is also appended to reports/system/lab_v2/halts.csv.

One run, in order: FROZEN_V2 and vendor check, registry check, OPS change log, lookback fetch (budget, cloud only),
raw-store checks, whether the lookback store is complete at the run time (v2_data.lookback_complete; while it is not,
S3 waits), registration (cloud: the registry files tracked at HEAD), the ledger consistency check, data and bars,
settlement with the causality audit (at most 10 days a run), the tripwire on the last settled day, states, START.json
(the first run that does not halt, cloud or synthetic), then publish (summary.json, STATUS.md, dashboard section) and
HALT.md.

Modes:
- cloud (default): only inside GitHub Actions, only on main and only when HEAD = origin/main (as v1).
- --dry: real data, read-only from the repo (or --raw-from, a checkout): no registration, no settlement, never a
  trade; it runs the signals and the online-vs-full causality audit on the latest input-only days (signals only) and
  writes dry_audit.json into a temporary folder (or --out).
- --dry --synthetic: the synthetic world (v1's synth.world from 2026-09-01 with v2_synth's deterministic edge edits,
  and v2_synth's lookback) and a sequence of
  simulated v1 + v2 runs; v2 starts at the 2026-11-03 run; placeholder registration (run id "dry", head
  "dry-placeholder", registered_utc = the simulated run time).

Exit code: 1 when lab v2 halted, 2 when an operation failed (lookback fetch) without a halt, else 0. The workflow step
has continue-on-error, so the code only marks the step.

Crashes (§2.5 item 2): this file imports only the standard library at top level; every other import (pandas, the v1
modules, the lab v2 modules) is guarded, and main() runs under try/except BaseException. A failed import, or any
exception or interrupt during a run, halts lab v2 only through the crash record of v2_crash.py (HALT.md, halts.csv,
summary.json marked PAUSED, the client's page re-rendered). In cloud mode main() finally writes its exit code to the
file named by the environment variable LAB2_EXIT_FILE (when set): the workflow treats the step as finished only when
that file holds the step's exit code, and otherwise (timeout, a killed process, a crash before main() could record
it) restores the lab v2 folders to HEAD and writes the same crash record itself (step "Lab v2 did not finish").
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXIT_HALT, EXIT_OPS = 1, 2
OPS_COLS = ["utc", "file", "sha256", "head_sha"]
OPS_FILES = ["analysis/system/lab_v2/run_v2.py", "analysis/system/lab_v2/v2_publish.py",
             "analysis/system/lab_v2/v2_page.py", "analysis/system/lab_v2/v2_crash.py",
             "analysis/system/lab_v2/v2_lookback.py", "analysis/system/lab_v2/v2_synth.py",
             "analysis/system/lab_v2/v2_frozen.py", ".github/workflows/system.yml", "analysis/system/publish.py",
             "reports/forward_site/system/index.html"]
DRY_AUDIT_DAYS = 5
SYNTH_V2_FROM = "2026-11-03 03:20"
SYNTH_LAST_DAY = "2026-12-04"
SYNTH_TIMES = ["2026-10-27 03:20", "2026-10-31 03:20", "2026-11-03 03:20", "2026-11-07 03:20", "2026-11-14 03:20",
               "2026-11-21 03:20", "2026-11-28 03:20", "2026-12-05 03:20"]

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
try:
    import v2_crash
except BaseException:  # noqa: BLE001 - main() falls back to a plain HALT.md
    v2_crash = None
IMPORT_ERROR = None
try:
    import v2paths  # noqa: E402,F401

    import pandas as pd  # noqa: E402

    import bars as v1bars  # noqa: E402
    import forecasts as v1fc  # noqa: E402
    import v2_data  # noqa: E402
    import v2_frozen  # noqa: E402
    import v2_ledger  # noqa: E402
    import v2_lookback  # noqa: E402
    import v2_publish  # noqa: E402
    import v2_registry  # noqa: E402
    import v2_signals  # noqa: E402
    from lab import registry as v1reg  # noqa: E402
except BaseException:  # noqa: BLE001 - recorded by main() as a lab v2 halt
    IMPORT_ERROR = traceback.format_exc(limit=3).strip().splitlines()[-1][:300]


class Paths:
    def __init__(self, base):
        base = Path(base)
        self.base = base
        self.v1data = base / "data" / "system"
        self.lb = self.v1data / "lab_v2" / "lookback"
        self.v1rep = base / "reports" / "system"
        self.v1lab = self.v1rep / "lab"
        self.rep = self.v1rep / "lab_v2"
        self.reg = self.rep / "registry"
        self.site = base / "reports" / "forward_site" / "system" / "lab_v2"


def git(*args):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def iso(t):
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def tracked_registry_ids():
    out = git("ls-tree", "-r", "--name-only", "HEAD", v2_registry.REG_REL + "/") or ""
    return {Path(p).stem for p in out.splitlines() if p.endswith(".json")}


def read_json(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def log_ops_changes(P, asof, head):
    """A row per OPS file whose sha256 changed since its last row (reports/system/lab_v2/ops_changes.csv)."""
    path = P.rep / "ops_changes.csv"
    last = {r["file"]: r["sha256"] for r in v2_ledger.read(path)}
    rows = []
    for f in OPS_FILES:
        p = ROOT / f
        if p.exists():
            h = v2_frozen.sha256(p)
            if last.get(f) != h:
                rows.append({"utc": asof, "file": f, "sha256": h, "head_sha": head})
    v2_ledger.append(path, OPS_COLS, rows)


def store_checks(P, now, complete):
    """Problems with the raw files lab v2 reads (lookback rows and v1 rows), empty = OK."""
    bad = v2_lookback.verify(P.lb)
    for day, side, raw_dir, sha in v2_data.source_days(P.lb, P.v1data, now, complete):
        if raw_dir == P.v1data / "raw":
            p = v2_data.raw_path(raw_dir, day, side)
            if not p.exists() or v2_frozen.sha256(p) != sha:
                bad.append(f"v1 raw {day.date()} {side}")
    return bad


def one_run(P, now, mode, run_id, head, fetch_on=True, log=print):
    """One lab v2 run (mode: cloud | synthetic). Returns (info, summary, halted)."""
    halt, ops = [], []
    asof = iso(now)
    halt += v2_frozen.check(ROOT) + v2_frozen.vendor_check()
    frozen_ok = not halt
    reg_bad = v2_registry.verify(P.reg, ROOT) if frozen_ok else []
    halt += reg_bad
    frozen_ok = frozen_ok and not reg_bad
    log_ops_changes(P, asof, head)
    if fetch_on and mode == "cloud" and not v2_lookback.complete(P.lb):
        try:
            log(f"lookback fetch: {v2_lookback.run(P.lb, now=now)}")
        except Exception:  # noqa: BLE001 - OPS: the next run continues
            ops.append("lookback fetch raised: " + traceback.format_exc(limit=1).strip().splitlines()[-1])
    complete = v2_data.v1_complete_utc(P.v1data, now)
    bad_store = store_checks(P, now, complete)
    if bad_store:
        halt.append(f"raw store differs from its days file: {', '.join(bad_store[:5])}")
    lb_done = v2_data.lookback_complete(P.lb, now)
    v1_start = (read_json(P.v1rep / "START.json") or {}).get("start")
    start = (read_json(P.rep / "START.json") or {}).get("start")
    recs = v2_registry.load(P.reg)
    ev_path = P.reg / "events.csv"
    events = v1reg.read_events(ev_path)
    if frozen_ok:
        tracked = tracked_registry_ids() if mode == "cloud" else {r["id"] for r in recs}
        v1reg.append_events(ev_path, v1reg.register_new(recs, events, asof, run_id, head, tracked))
        events = v1reg.read_events(ev_path)
    halt += v2_ledger.ledger_consistent(P.rep)
    sts = v1reg.states(recs, events, start)
    today = v1bars.to_model(pd.DatetimeIndex([now]))[0].normalize()
    b15, n_trades, settled_now = None, 0, []
    if not halt:
        mf = None
        m = v2_data.load_m1(P.lb, P.v1data, now, complete)
        if m is not None:
            mf = v2_data.model_frame(m)
        if mf is not None and len(mf):
            m_in = v2_data.seed_input(mf)
            bars_tf = {"M5": v2_data.seed_bars(m_in, "M5"), "M15": v2_data.seed_bars(m_in, "M15")}
            b15 = bars_tf["M15"]
            full = {r["id"]: v2_signals.full_values(v2_signals.load_seed(r["id"]), bars_tf[r["tf"]]) for r in recs}
            slots = v2_data.forecast_slots(P.v1data / "forecasts.csv")
            hol = set(pd.Timestamp(h) for h in v1fc.holidays(pd.Timestamp(now).year + 1))
            code8 = v2_frozen.code_sha8()

            def sig(sid, d, online=True):
                rec = next(r for r in recs if r["id"] == sid)
                return v2_signals.day_signals(sid, bars_tf[rec["tf"]], full[sid], d, online=online)

            def inputs(d):
                return v2_ledger.day_inputs(d, v2_data.minutes_of_day(mf, d), slots, hol)

            pend = v2_ledger.pending_days(P.rep, sts, complete, slots)
            n_trades, failures = v2_ledger.settle(P.rep, recs, sts, pend, sig, inputs, asof, code8, start,
                                                  synthetic=(mode == "synthetic"), lookback_complete=lb_done)
            if failures:
                v1reg.append_events(ev_path, v2_ledger.void_events(failures, events, asof, run_id, head))
                events = v1reg.read_events(ev_path)
                sts = v1reg.states(recs, events, start)
                halt.append("causality audit failed (online != full-data value): " + "; ".join(
                    f"{sid} {a['day']} at {a['first_mismatch']} ({a['n_mismatch_window']} window bars, "
                    f"{a['n_mismatch_outside']} outside)" for sid, a in failures)
                    + "; the seed is voided (RETIRED, reason bug)")
            else:
                settled_now = [d.strftime("%Y-%m-%d") for d in pend]
                days = v2_ledger.read(P.rep / "lab_days.csv")
                if days:
                    last = pd.Timestamp(days[-1]["day"])
                    fs = {r["id"]: sig(r["id"], last, online=False) for r in recs
                          if v2_ledger.active(r, sts[r["id"]], last)}
                    diffs = v2_ledger.tripwire(P.rep, recs, sts, inputs(last), fs, code8)
                    if diffs:
                        halt.append("lab v2 tripwire: " + "; ".join(diffs[:3]))
    lab_running = not halt
    if not lab_running:
        v1reg.append_events(ev_path, v2_ledger.halt_suspensions(recs, sts, events, asof, run_id, head))
    else:
        v2_ledger.update_states(P.rep, recs, sts, events, asof, True, run_id, head, today)
    events = v1reg.read_events(ev_path)
    sts = v1reg.states(recs, events, start)
    state = "RUNNING" if lab_running else "PAUSED"
    if lab_running and mode in ("cloud", "synthetic") and start is None and v1_start:
        v2_publish.write_json(P.rep / "START.json", v2_registry.start_record(now, run_id, head, v1_start))
        start = read_json(P.rep / "START.json")["start"]
    s = v2_publish.summary(P.rep, recs, sts, events, state, asof, start, P.v1lab, bars_m15=b15, halt=halt,
                           today=today, lookback_complete=lb_done)
    lbs = v2_data.final_status(v2_data.read_days(P.lb / "days.csv"))
    info = {"asof_utc": asof, "halt": halt, "ops": ops, "start": start, "v1_start": v1_start,
            "settled_now": settled_now, "trades_now": n_trades,
            "data": {"lookback_ok": sum(1 for v in lbs.values() if v[0] == "ok"),
                     "lookback_missing": sum(1 for v in lbs.values() if v[0] == "missing"),
                     "lookback_complete": lb_done,
                     "complete_utc": complete.strftime("%Y-%m-%d %H:%M")}}
    v2_publish.write_all(P.rep, P.site, info, s)
    if halt:
        write_halt(P, asof, run_id, head, halt)
    elif (P.rep / "HALT.md").exists():
        (P.rep / "HALT.md").unlink()
    return info, s, bool(halt)


def write_halt(P, asof, run_id, head, reasons):
    v2_crash.write_halt(P.base, asof, run_id, head, reasons)


def crash(P, now, run_id, head, exc_text):
    """A v2 exception: the crash record of v2_crash (HALT.md, halts.csv, the last summary marked PAUSED and the page
    re-rendered from it). Never raises."""
    record_crash(P.base, iso_utc(now), run_id, head, "lab v2 exception: " + exc_text)


def iso_utc(t):
    """`t` (a pandas or datetime timestamp, UTC) as YYYY-MM-DDTHH:MM:SSZ, with the standard library only."""
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def record_crash(base, asof, run_id, head, reason):
    """v2_crash.record, or a plain HALT.md when v2_crash itself cannot be imported. Never raises."""
    try:
        if v2_crash is not None:
            return v2_crash.record(base, asof, run_id, head, reason, log=lambda m: print(m, file=sys.stderr))
        rep = Path(base) / "reports" / "system" / "lab_v2"
        rep.mkdir(parents=True, exist_ok=True)
        (rep / "HALT.md").write_text("# HALT (lab v2 only; v1 is not affected)\n\n" + f"Run {asof}:\n\n- {reason}\n"
                                     + "- v2_crash.py could not be imported\n", encoding="utf-8")
        return ["HALT.md"]
    except BaseException:  # noqa: BLE001
        return []


def guarded_run(P, now, mode, run_id, head, fetch_on=True, log=print):
    """one_run, with any exception or interrupt turned into a v2-only halt. Returns (exit code, info or None)."""
    try:
        info, _, halted = one_run(P, now, mode, run_id, head, fetch_on=fetch_on, log=log)
    except BaseException:  # noqa: BLE001
        text = traceback.format_exc(limit=3).strip().splitlines()[-1][:300]
        log(traceback.format_exc())
        crash(P, now, run_id, head, text)
        return EXIT_HALT, None
    return (EXIT_HALT if halted else EXIT_OPS if info["ops"] else 0), info


# ---------------------------------------------------------------- dry run on real data: signals and audit only
def dry_audit(P, out_dir, now, n_days=DRY_AUDIT_DAYS, log=print):
    """Signals and the causality audit on the latest input-only days of the store at P (read-only); writes
    out_dir/dry_audit.json. Never settles, never trades."""
    complete = v2_data.v1_complete_utc(P.v1data, now)
    m = v2_data.load_m1(P.lb, P.v1data, now, complete)
    mf = v2_data.model_frame(m)
    m_in = v2_data.seed_input(mf)
    bars_tf = {"M5": v2_data.seed_bars(m_in, "M5"), "M15": v2_data.seed_bars(m_in, "M15")}
    days = sorted(set(bars_tf["M15"].day))
    days = [d for d in days if v1bars.model_to_utc(d + pd.Timedelta(hours=23, minutes=30)) <= complete][-n_days:]
    out = {"asof_utc": iso(now), "complete_utc": iso(complete), "days": [d.strftime("%Y-%m-%d") for d in days],
           "seeds": {}}
    for sid, _, tf, _ in v2_signals.SEEDS:
        mod = v2_signals.load_seed(sid)
        full = v2_signals.full_values(mod, bars_tf[tf])
        rows = [v2_ledger.audit_row(v2_signals.day_signals(sid, bars_tf[tf], full, d), tf, iso(now)) for d in days]
        out["seeds"][sid] = {"window_bars": sum(r["n_window"] for r in rows),
                             "mismatch_window": sum(r["n_mismatch_window"] for r in rows),
                             "mismatch_outside": sum(r["n_mismatch_outside"] for r in rows)}
        log(f"{sid}: {out['seeds'][sid]}")
    v2_publish.write_json(Path(out_dir) / "dry_audit.json", out)
    return out


# ---------------------------------------------------------------- synthetic world: v1 + v2 run sequence
def setup_synthetic(P):
    import synth
    P.v1lab.joinpath("registry").mkdir(parents=True, exist_ok=True)
    for f in ("S1.json", "S1R.json", "C1.json"):
        shutil.copyfile(ROOT / "reports/system/lab/registry" / f, P.v1lab / "registry" / f)
    shutil.copyfile(ROOT / "reports/system/L3_ZSTAR.json", P.v1rep / "L3_ZSTAR.json")
    P.reg.mkdir(parents=True, exist_ok=True)
    for f in ("S2.json", "S3.json", "S4.json", "S5.json"):
        shutil.copyfile(ROOT / v2_registry.REG_REL / f, P.reg / f)
    synth.world(P.v1data, first="2026-09-01", last=SYNTH_LAST_DAY)
    import v2_synth
    v2_synth.apply_edges(P.v1data)
    v2_synth.lookback_world(P.lb)


def synthetic_runs(P, times=None, crash_at=(), v2=True, log=print):
    """v1 then v2 at each simulated run time (v2 from 2026-11-03 03:20). crash_at: run times (or "all") at which v2
    is forced to raise (the isolation test); v2=False runs v1 alone. Returns the list of (time, v2 exit code)."""
    sys.path.insert(0, str(v2paths.SYSTEM))
    import run as v1run
    crash = None if crash_at == "all" else {pd.Timestamp(x, tz="UTC") for x in crash_at}
    out = []
    for t in [pd.Timestamp(x, tz="UTC") for x in (times or SYNTH_TIMES)]:
        info1, _ = v1run.one_run(v1run.Paths(P.base), t, "synthetic", "dry", "dry-placeholder", fetch_on=False,
                                 log=lambda *a: None)
        v1run.write_status(v1run.Paths(P.base), info1)
        if not v2 or t < pd.Timestamp(SYNTH_V2_FROM, tz="UTC"):
            continue
        if crash is None or t in crash:
            code = _forced_crash(P, t)
        else:
            code, info = guarded_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=log)
            if info:
                log(f"{t}: v2 settled {len(info['settled_now'])} days, {info['trades_now']} trades, "
                    f"halt {info['halt']}")
        out.append((t, code))
    return out


def _forced_crash(P, t):
    def boom(*a, **k):
        raise RuntimeError("forced crash (isolation test)")
    real = v2_data.load_m1
    v2_data.load_m1 = boom
    try:
        code, _ = guarded_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=lambda *a: None)
    finally:
        v2_data.load_m1 = real
    return code


def cloud_refusal(env=None):
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true":
        return "the lab v2 ledgers have one writer, the GitHub Actions job: run locally with --dry"
    if env.get("GITHUB_REF") != "refs/heads/main":
        return f"cloud mode runs only on main (GITHUB_REF = {env.get('GITHUB_REF')!r}); nothing was written"
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    if head and origin and head != origin:
        return f"HEAD {head[:8]} is not origin/main {origin[:8]}; nothing was written"
    return None


def report_exit(code):
    """Cloud mode: the exit code for the workflow (LAB2_EXIT_FILE), written last."""
    path = os.environ.get("LAB2_EXIT_FILE")
    if path:
        try:
            Path(path).write_text(f"{code}\n")
        except OSError:
            pass
    return code


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--raw-from")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    if a.synthetic and not a.dry:
        print("--synthetic needs --dry", file=sys.stderr)
        return 2
    if not a.dry:
        why = cloud_refusal()
        if why:
            print(why, file=sys.stderr)
            return 1
        head = git("rev-parse", "HEAD") or "unknown"
        run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
        from datetime import datetime, timezone
        wall = datetime.now(timezone.utc).replace(microsecond=0)
        if IMPORT_ERROR is not None:
            record_crash(ROOT, iso_utc(wall), run_id, head, "lab v2 could not import its modules: " + IMPORT_ERROR)
            print(json.dumps({"exit": EXIT_HALT, "halt": ["import failed: " + IMPORT_ERROR]}, ensure_ascii=False))
            return report_exit(EXIT_HALT)
        try:
            now = v2_data.to_utc(a.now) if a.now else pd.Timestamp.now(tz="UTC").floor("s")
            code, info = guarded_run(Paths(ROOT), now, "cloud", run_id, head, fetch_on=not a.no_fetch)
            print(json.dumps({"exit": code, "halt": info and info["halt"], "ops": info and info["ops"],
                              "start": info and info["start"]}, ensure_ascii=False))
        except BaseException:  # noqa: BLE001 - guarded_run never raises; this covers the code around it
            text = traceback.format_exc(limit=3).strip().splitlines()[-1][:300]
            record_crash(ROOT, iso_utc(wall), run_id, head, "lab v2 exception: " + text)
            code = EXIT_HALT
        return report_exit(code)
    if IMPORT_ERROR is not None:
        print("lab v2 could not import its modules: " + IMPORT_ERROR, file=sys.stderr)
        return EXIT_HALT
    now = v2_data.to_utc(a.now) if a.now else pd.Timestamp.now(tz="UTC").floor("s")
    base = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="lab_v2_dry_"))
    P = Paths(base)
    print(f"lab v2 dry output: {base}")
    if a.synthetic:
        setup_synthetic(P)
        res = synthetic_runs(P)
        return max(c for _, c in res) if res else 0
    dry_audit(Paths(a.raw_from or ROOT), base, now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
