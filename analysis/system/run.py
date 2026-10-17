"""The system job (SYSTEM_V1_PREREG.md §7, Amendment A1 items 9-11). OPS: I/O orchestration only.

Every decision with lab or calibration semantics is made in a FROZEN module (A1 item 9): registration and states
(lab/registry.py), settlement, suspensions and the tripwire (lab/ledger.py), α-spending, γ_k, D_j and E*_k
(lab/eproc.py, lab/proposer.py), the proposer's schedule and training days (lab/proposer.py), the L3 monthly chain and
its hysteresis state (l3.py), the store and the calendars (forecasts.py). This file reads and writes files, calls
them in order and reports.

One run, in order: FROZEN check, fetch, store check, calendars, forecasts (write-once) and their tripwire, L3 (monthly
update and green suppression), lab (registration, settlement, e-processes, promotion/demotion, proposer on its
Saturday), publish, then deploy with wrangler (same site and secret as forward-watch), then STATUS.md. The workflow
commits the ledgers after.

Modes:
- cloud (default): only inside GitHub Actions and only on main (GITHUB_REF = refs/heads/main, and HEAD = origin/main
  when that ref resolves; A1 item 11); anything else exits non-zero before writing. Writes the repo's data/system,
  reports/system and reports/forward_site/system. REGISTERED rows come from the registry files found at HEAD; the
  first non-halted run writes reports/system/START.json.
- --dry: everything goes to a temporary folder (or --out), no git, no deploy. On real data the lab is NOT run: no lab
  outcome is computed on real data before the freeze (§0, §9). --raw-from seeds the temp store from a data folder.
- --dry --synthetic: a synthetic random-walk world (synth.py) and a sequence of simulated runs (the first on a
  Tuesday, then every Saturday 03:20 UTC), with placeholder registration: the end-to-end lab dry run of §9.

Exit code: 1 when the run halted (FROZEN mismatch, raw-store mismatch, registry or tripwire difference: the lab is
PAUSED); 2 when it did not halt but an operation failed (A1 item 11: the fetch raised, the deploy failed, the complete
data lag more than 2 trading days, the calendars end within 60 days, or a calendar extension line was rejected or
lost): the lab is not halted. Either way GitHub emails the owner; the commit step still runs.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import syspath  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import bars  # noqa: E402
import fetch  # noqa: E402
import forecasts  # noqa: E402
import frozen_hashes  # noqa: E402
import l3  # noqa: E402
import publish  # noqa: E402
from lab import ledger, proposer, registry  # noqa: E402

ROOT = syspath.ROOT
WRANGLER = ["npx", "--yes", "wrangler@4.151.1", "deploy", "--config", "reports/forward_deploy/wrangler.jsonc"]
SEED_FILES = ("S1.json", "S1R.json", "C1.json")
LAG_MAX_TRADING_DAYS = 2
CALENDAR_WARN_DAYS = 60
EXIT_HALT, EXIT_OPS = 1, 2


class Paths:
    def __init__(self, base):
        base = Path(base)
        self.base = base
        self.data = base / "data" / "system"
        self.rep = base / "reports" / "system"
        self.lab = self.rep / "lab"
        self.reg = self.lab / "registry"
        self.site = base / "reports" / "forward_site" / "system"


def git(*args):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def tracked_registry_ids():
    out = git("ls-tree", "-r", "--name-only", "HEAD", "reports/system/lab/registry/") or ""
    return {Path(p).stem for p in out.splitlines() if p.endswith(".json")}


def read_start(P):
    p = P.rep / "START.json"
    return json.loads(p.read_text())["start"] if p.exists() else None


def write_start(P, now, run_id, head):
    p = P.rep / "START.json"
    if not p.exists():
        publish.write_json(p, registry.start_record(now, run_id, head))


OPS_FILES = ["analysis/system/run.py", "analysis/system/fetch.py", "analysis/system/publish.py",
             "analysis/system/synth.py", "analysis/system/l3_sim.py", "analysis/system/frozen_hashes.py",
             ".github/workflows/system.yml", "reports/forward_site/system/index.html",
             "analysis/system/calendars_ext/events.csv"]


def log_ops_changes(P, asof, head):
    """§3 item 6: OPS fixes are allowed and logged. A row per OPS file whose sha256 changed since the last row."""
    path = P.rep / "ops_changes.csv"
    last = {}
    if path.exists():
        for r in pd.read_csv(path, dtype=str).itertuples():
            last[r.file] = r.sha256
    rows = []
    for f in OPS_FILES:
        p = ROOT / f
        if not p.exists():
            continue
        h = frozen_hashes.sha256(p)
        if last.get(f) != h:
            rows.append({"utc": asof, "file": f, "sha256": h, "head_sha": head})
    if rows:
        exists = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=["utc", "file", "sha256", "head_sha"]).to_csv(
            path, mode="a", header=not exists, index=False, lineterminator="\n")


def write_csv(path, cols, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False, lineterminator="\n")


def append_csv(path, cols, rows):
    if rows:
        exists = Path(path).exists()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=cols).to_csv(path, mode="a", header=not exists, index=False,
                                                lineterminator="\n")


def calendars(P, now, asof, run_id, head, ops):
    """Frozen calendars plus the accepted extension lines (forecasts.ext_review); horizon warning (A1 item 10)."""
    seen_path = P.rep / "calendar_ext.csv"
    seen = (pd.read_csv(seen_path, dtype=str, keep_default_na=False).to_dict("records")
            if seen_path.exists() else [])
    try:
        lines = forecasts.read_ext_lines(forecasts.EXT_FILE)
    except ValueError as e:
        ops.append(f"calendar extension file unreadable, ignored: {e}")
        lines = [r["line"] for r in seen]
    new_seen, accepted, problems = forecasts.ext_review(lines, seen, now, run_id, head)
    append_csv(seen_path, forecasts.EXT_SEEN_COLS, new_seen)
    ops += problems
    events = forecasts.load_events(ext=accepted)
    horizon = forecasts.calendar_horizon(events)
    today = pd.Timestamp(now).tz_convert("UTC").tz_localize(None).normalize()
    if today >= horizon - pd.Timedelta(days=CALENDAR_WARN_DAYS):
        ops.append(f"the event calendars end on {horizon.date()}: add the next official NFP/CPI/FOMC dates to "
                   f"analysis/system/calendars_ext/events.csv (at least 14 days ahead)")
    rows = seen + new_seen
    info = {"horizon": str(horizon.date()), "ext_accepted": sum(1 for r in rows if r["status"] == "accepted"),
            "ext_rejected": sum(1 for r in rows if r["status"] == "rejected")}
    return events, forecasts.holidays(today.year + 1), forecasts.full_closures(today.year + 1), info


def one_run(P, now, mode, run_id, head, fetch_on=True, log=print):
    """One run of the job up to publishing (mode: cloud | dry | synthetic). Returns (info, halted).

    info["ops"] lists the operational failures (A1 item 11); STATUS.md is written by write_status, after the deploy."""
    halt, ops = [], []
    asof = fetch.iso(now)
    halt += frozen_hashes.check(ROOT) + frozen_hashes.vendor_check(ROOT)
    frozen_ok = not halt
    log_ops_changes(P, asof, head)

    # 1 fetch (OPS: a failure fails the run but never stops it; the next run backfills)
    if fetch_on:
        try:
            s = fetch.run(P.data, now=now)
            log(f"fetch: {s}")
        except Exception:  # noqa: BLE001
            ops.append("fetch raised: " + traceback.format_exc(limit=1).strip().splitlines()[-1])
    bad_raw = fetch.verify_store(P.data)
    if bad_raw:
        halt.append(f"raw store differs from days.csv: {', '.join(bad_raw[:5])}")
    complete = fetch.complete_through_utc(P.data, now)
    lag = fetch.lag_trading_days(P.data, now)
    if lag > LAG_MAX_TRADING_DAYS:
        ops.append(f"complete data lag {lag} trading days (through {complete:%Y-%m-%d %H:%M} UTC)")

    # 2 calendars and forecasts
    events, hol, closures, cal_info = calendars(P, now, asof, run_id, head, ops)
    store = forecasts.read_store(P.data / "forecasts.csv")
    grid, mf, n_new = None, None, 0
    if frozen_ok and not bad_raw:
        days = fetch.ok_days(P.data, now, before=complete)
        m = bars.load_store(P.data / "raw", days) if days else None
        if m is not None:
            mf = bars.model_frame(m)
            grid = forecasts.compute(bars.volmap_input(mf), events, hol)
            tw = forecasts.tripwire(store, grid)
            if tw:
                halt.append("forecast tripwire: " + "; ".join(tw[:3]))
            else:
                rows = forecasts.new_rows(grid, store, complete, asof)
                forecasts.append_store(P.data / "forecasts.csv", rows)
                n_new = len(rows)
                store = forecasts.read_store(P.data / "forecasts.csv")
    start = read_start(P)
    if start is None and mode != "cloud":
        start = str(registry.start_from_first_run(now))      # dry placeholder; synthetic writes START.json below
        if mode == "synthetic":
            write_start(P, now, run_id, head)
    today_model = bars.to_model(pd.DatetimeIndex([now]))[0].normalize()

    # 3 L3 and the green suppression
    zstar = l3.load_zstar(P.rep / "L3_ZSTAR.json")
    upd_path = P.rep / "l3_updates.csv"
    updates = pd.read_csv(upd_path, dtype={"month": str}) if upd_path.exists() else pd.DataFrame(
        columns=l3.UPDATE_COLS)
    n_obs, trials, blocks, green_ok = 0, pd.DataFrame(), [], 1
    if grid is not None and not halt:
        obs = l3.observations(store, grid, start, complete)
        n_obs = len(obs)
        new_upd = [r | {"computed_utc": asof} for r in l3.monthly_updates(obs, updates, today_model, complete, zstar)]
        append_csv(upd_path, l3.UPDATE_COLS, new_upd)
        if new_upd:
            updates = pd.read_csv(upd_path, dtype={"month": str})
        trials = l3.hour_trials(mf, store, start, complete)
        blocks, green_ok = l3.green_blocks(trials, start, complete, closures)
        write_csv(P.rep / "l1_blocks.csv", l3.BLOCK_COLS, blocks)
    mult, l3_month = l3.current_multipliers(updates)
    l1 = {"green_ok": green_ok, "asof": str(pd.Timestamp(now).date()),
          "blocks": [{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in b.items()}
                     for b in blocks], "states": publish.state_table(trials)}
    publish.write_json(P.rep / "l1_flags.json", {"l1_green_ok": green_ok, "l1_asof": l1["asof"], "blocks": l1["blocks"]})
    l3_info = {"asof": f"{l3_month}-01" if l3_month else None, "mult": mult, "zstar": zstar, "n_obs": n_obs}

    # 4 lab
    lab_running = not halt
    recs = registry.load(P.reg)
    reg_bad = registry.verify(P.reg)
    if reg_bad:
        halt += reg_bad
        lab_running = False
    ev_path = P.reg / "events.csv"
    events_l = registry.read_events(ev_path)
    run_lab = mode in ("cloud", "synthetic")
    if run_lab and frozen_ok:
        tracked = tracked_registry_ids() if mode == "cloud" else {r["id"] for r in recs}
        registry.append_events(ev_path, registry.register_new(recs, events_l, asof, run_id, head, tracked))
        events_l = registry.read_events(ev_path)
    sts = registry.states(recs, events_l, start)
    proposer_report = None
    if run_lab and not lab_running:
        registry.append_events(ev_path, ledger.halt_suspensions(recs, sts, events_l, asof, run_id, head))
        events_l = registry.read_events(ev_path)
        sts = registry.states(recs, events_l, start)
    if run_lab and lab_running and mf is not None:
        lbars = bars.lab_bars(mf)
        hol_set = {pd.Timestamp(h) for h in hol}
        evd = forecasts.event_days(events)
        code8 = frozen_hashes.code_sha8()

        def inputs(d):
            return ledger.day_inputs(d, mf, lbars, store, hol_set, evd)

        pend = ledger.pending_days(P.lab, sts, complete)
        ledger.settle_days(P.lab, recs, sts, [inputs(d) for d in pend], asof, code8, start,
                           synthetic=(mode == "synthetic"))
        settled = [r["day"] for r in ledger.read(P.lab / "lab_days.csv")]
        if settled:
            diffs = ledger.tripwire(P.lab, recs, sts, inputs(pd.Timestamp(settled[-1])), code8)
            if diffs:
                halt.append("lab tripwire: " + "; ".join(diffs[:3]))
                lab_running = False
        ledger.update_states(P.lab, recs, sts, events_l, asof, lab_running, run_id, head, today_model)
        events_l = registry.read_events(ev_path)
        sts = registry.states(recs, events_l, start)
        # proposer (on its Saturday): schedule, training days, k, γ_k, D and E*_k all come from proposer.py
        done = sorted(p.stem for p in (P.lab / "proposer").glob("*.json"))
        pl = proposer.plan(pd.Timestamp(now).date(), settled, sts, done, lab_running)
        if pl:
            rep = proposer.execute([inputs(d) for d in pl["train_days"]], pl, recs, sts)
            new = proposer.new_records(rep, recs, events_l)
            for rec in new:
                registry.write(P.reg, rec)
            rep["registered_ids"] = [rec["id"] for rec in new]
            publish.write_json(P.lab / "proposer" / f"{pl['date']}.json", rep)
            proposer_report = rep
            recs = registry.load(P.reg)
            sts = registry.states(recs, events_l, start)

    # 5 publish
    lab_info = publish.lab_summary(P.lab, recs, sts, events_l, "RUNNING" if lab_running else "PAUSED")
    if proposer_report is None:
        done = sorted((P.lab / "proposer").glob("*.json"))
        if done:
            proposer_report = json.loads(done[-1].read_text())
    if proposer_report:
        lab_info["proposer"] = {k: proposer_report[k] for k in ("run_date", "n_scored", "q95", "chosen",
                                                                 "n_rules")}
        lab_info["proposer"]["n_train"] = len(proposer_report["train_days"])
    publish.write_system_csv(P.site / "VolMapSystem.csv", publish.system_csv(asof, l1, l3_info, lab_info))
    st_store = forecasts.read_store(P.data / "forecasts.csv")
    info = {"asof_utc": asof, "halt": halt, "ops": ops, "start": start, "l1": l1, "l3": l3_info, "lab": lab_info,
            "calendar": cal_info,
            "data": {"ok_days": len(fetch.ok_days(P.data, now)), "missing": fetch.missing(P.data),
                     "complete_through_utc": complete.strftime("%Y-%m-%d %H:%M"), "lag_trading_days": lag,
                     "revisions": len(fetch.read_csv(P.data / "revisions.csv", fetch.REVISION_COLS)),
                     "store_rows": len(st_store), "store_defined": int(pd.notna(st_store.F_H1).sum()),
                     "store_new": n_new}}
    publish.write_json(P.site / "lab.json", publish.site_json(info))
    if halt:
        (P.rep / "HALT.md").write_text("# HALT\n\n" + "\n".join(f"- {h}" for h in halt) + "\n")
    return info, bool(halt)


def write_status(P, info):
    """reports/system/STATUS.md, after the deploy, so that it lists every operational failure of the run."""
    P.rep.mkdir(parents=True, exist_ok=True)
    (P.rep / "STATUS.md").write_text(publish.status_md(info))


def exit_code(info, halted):
    return EXIT_HALT if halted else (EXIT_OPS if info["ops"] else 0)


def deploy(log=print):
    try:
        r = subprocess.run(WRANGLER, cwd=ROOT, capture_output=True, text=True)
    except OSError as e:
        log(f"deploy could not start: {e}")
        return False
    log(r.stdout[-2000:] + r.stderr[-2000:])
    return r.returncode == 0


def synthetic_runs(P, log=print):
    """The end-to-end lab dry run on a synthetic world: Tuesday 2026-10-27, then every Saturday 03:20 UTC."""
    import synth
    synth.world(P.data)
    times = [pd.Timestamp("2026-10-27 03:20", tz="UTC")] + list(
        pd.date_range("2026-10-31 03:20", "2027-02-27 03:20", freq="7D", tz="UTC"))
    halted, ops = False, []
    for t in times:
        info, h = one_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=log)
        write_status(P, info)
        halted = halted or h
        ops += info["ops"]
        log(f"{t}: lab days {info['lab']['days']}, paper {info['lab']['n_paper']}, live {info['lab']['n_live']}, "
            f"store {info['data']['store_rows']}, halt {info['halt']}, ops {info['ops']}")
    info["ops"] = ops
    return info, halted


def cloud_run(P, now, run_id, head, fetch_on=True, deploy_fn=deploy):
    """The cloud run: one_run, START.json (first non-halted run), the deploy, then STATUS.md with every failure."""
    info, halted = one_run(P, now, "cloud", run_id, head, fetch_on=fetch_on)
    if not halted:
        write_start(P, now, run_id, head)
    if deploy_fn is not None and not deploy_fn():
        info["ops"].append("deploy failed (wrangler)")
    write_status(P, info)
    return info, halted


def cloud_refusal(env=None):
    """Why cloud mode must not run here (None = it may): GitHub Actions, on main only (A1 item 11)."""
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true":
        return "the ledgers have one writer, the GitHub Actions job: run locally with --dry"
    if env.get("GITHUB_REF") != "refs/heads/main":
        return f"cloud mode runs only on main (GITHUB_REF = {env.get('GITHUB_REF')!r}); nothing was written"
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    if head and origin and head != origin:
        return f"HEAD {head[:8]} is not origin/main {origin[:8]}; nothing was written"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--raw-from")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--no-deploy", action="store_true")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    now = fetch.to_utc(a.now) if a.now else fetch.utcnow()
    if a.synthetic and not a.dry:
        print("--synthetic needs --dry", file=sys.stderr)
        return 2
    if not a.dry:
        why = cloud_refusal()
        if why:
            print(why, file=sys.stderr)
            return 1
    if a.dry:
        base = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="system_dry_"))
        P = Paths(base)
        P.reg.mkdir(parents=True, exist_ok=True)
        for f in SEED_FILES:
            shutil.copyfile(ROOT / "reports/system/lab/registry" / f, P.reg / f)
        shutil.copyfile(ROOT / "reports/system/L3_ZSTAR.json", P.rep / "L3_ZSTAR.json")
        if a.raw_from and not (P.data / "days.csv").exists():
            src = Path(a.raw_from)
            shutil.copytree(src / "raw", P.data / "raw", dirs_exist_ok=True)
            shutil.copyfile(src / "days.csv", P.data / "days.csv")
        print(f"dry run output: {base}")
        if a.synthetic:
            info, halted = synthetic_runs(P)
        else:
            info, halted = one_run(P, now, "dry", "dry", "dry", fetch_on=not a.no_fetch)
            write_status(P, info)
    else:
        info, halted = cloud_run(Paths(ROOT), now, os.environ.get("GITHUB_RUN_ID", "unknown"),
                                 git("rev-parse", "HEAD") or "unknown", fetch_on=not a.no_fetch,
                                 deploy_fn=None if a.no_deploy else deploy)
    print(json.dumps({"halt": info["halt"], "ops": info["ops"], "start": info["start"], "lab_days": info["lab"]["days"],
                      "data": info["data"], "l1_green_ok": info["l1"]["green_ok"]}, indent=1, ensure_ascii=False))
    return exit_code(info, halted)


if __name__ == "__main__":
    sys.exit(main())
