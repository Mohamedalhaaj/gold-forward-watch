"""The system job (SYSTEM_V1_PREREG.md §7). OPS: orchestration.

One run, in order: FROZEN check, fetch, store check, forecasts (write-once) and their tripwire, L3 (monthly update and
green suppression), lab (registration, settlement, e-processes, promotion/demotion, proposer on its Saturday),
publish, then deploy with wrangler (same site and secret as forward-watch). The workflow commits the ledgers after.

Modes:
- cloud (default; only inside GitHub Actions): writes the repo's data/system, reports/system and
  reports/forward_site/system. REGISTERED rows come from the registry files found at HEAD; the first successful run
  writes reports/system/START.json.
- --dry: everything goes to a temporary folder (or --out), no git, no deploy. On real data the lab is NOT run: no lab
  outcome is computed on real data before the freeze (§0, §9). --raw-from seeds the temp store from a data folder.
- --dry --synthetic: a synthetic random-walk world (synth.py) and a sequence of simulated runs (the first on a
  Tuesday, then every Saturday 03:20 UTC), with placeholder registration: the end-to-end lab dry run of §9.

Exit code 1 when the run halted (FROZEN mismatch, raw-store mismatch, registry or tripwire difference), so GitHub
emails the owner; the commit step still runs.
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
import system_common as sc  # noqa: E402
from lab import eproc, ledger, proposer, registry  # noqa: E402

ROOT = syspath.ROOT
WRANGLER = ["npx", "--yes", "wrangler@4.151.1", "deploy", "--config", "reports/forward_deploy/wrangler.jsonc"]
SEED_FILES = ("S1.json", "S1R.json", "C1.json")


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
    if p.exists():
        return
    start = registry.start_from_first_run(now)
    publish.write_json(p, {"first_cloud_run_utc": fetch.iso(now), "run_id": run_id, "head_sha": head,
                           "start": str(start), "rule": "later of 2026-11-02 and the first Monday >= 2 days after "
                                                        "the first successful cloud run (SYSTEM_V1_PREREG.md §0)"})


OPS_FILES = ["analysis/system/run.py", "analysis/system/fetch.py", "analysis/system/publish.py",
             "analysis/system/synth.py", "analysis/system/l3_sim.py", "analysis/system/frozen_hashes.py",
             ".github/workflows/system.yml", "reports/forward_site/system/index.html"]


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


def one_run(P, now, mode, run_id, head, fetch_on=True, log=print):
    """One run of the job. mode: cloud | dry | synthetic. Returns (info dict, halted bool)."""
    halt, ops = [], []
    asof = fetch.iso(now)
    halt += frozen_hashes.check(ROOT) + frozen_hashes.vendor_check(ROOT)
    frozen_ok = not halt
    log_ops_changes(P, asof, head)

    # 1 fetch (OPS: a failure never stops the run; the next run backfills)
    if fetch_on:
        try:
            s = fetch.run(P.data, now=now)
            log(f"fetch: {s}")
        except Exception:  # noqa: BLE001
            ops.append("fetch failed: " + traceback.format_exc(limit=1).strip().splitlines()[-1])
    bad_raw = fetch.verify_store(P.data)
    if bad_raw:
        halt.append(f"raw store differs from days.csv: {', '.join(bad_raw[:5])}")
    complete = fetch.complete_through_utc(P.data, now)

    # 2 forecasts
    store = forecasts.read_store(P.data / "forecasts.csv")
    grid, mf, n_new = None, None, 0
    events = forecasts.load_events()
    hol = forecasts.holidays()
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
        new_upd = []
        for month in l3.due_months(today_model, set(updates.month)):
            if bars.model_to_utc(pd.Timestamp(month + "-01")) > complete:
                break                                        # data before the cut not final yet: next run
            prev = updates[updates.month == updates.month.max()] if len(updates) else updates
            before = {r.bucket: bool(r.active_after) for r in prev.itertuples()}
            rows = l3.update(obs, month, before, zstar)
            for r in rows:
                r["computed_utc"] = asof
            new_upd += rows
            updates = pd.concat([updates, pd.DataFrame(rows)], ignore_index=True)
        if new_upd:
            exists = upd_path.exists()
            pd.DataFrame(new_upd, columns=l3.UPDATE_COLS).to_csv(upd_path, mode="a", header=not exists,
                                                                index=False, lineterminator="\n")
        trials = l3.hour_trials(mf, store, start, complete)
        blocks, green_ok = l3.green_blocks(trials, start, complete, forecasts.full_closures())
        write_csv(P.rep / "l1_blocks.csv", l3.BLOCK_COLS, blocks)
    mult, l3_month = l3.current_multipliers(updates)
    l1 = {"green_ok": green_ok, "asof": str(pd.Timestamp(now).date()),
          "blocks": [{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in b.items()}
                     for b in blocks]}
    if len(trials):
        st = []
        for s_, g in trials[trials.entry == 1].groupby("state"):
            hr = (g.hit_long.sum() + g.hit_short.sum()) / (2 * len(g))
            st.append({"state": ["GREY", "GREEN", "YELLOW", "RED"][int(s_)], "n": len(g), "hit_rate": f"{hr:.3f}"})
        l1["states"] = st
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
        new_ev = registry.register_new(recs, events_l, asof, run_id, head, tracked)
        registry.append_events(ev_path, new_ev)
        events_l = registry.read_events(ev_path)
    sts = registry.states(recs, events_l, start)
    proposer_report = None
    if run_lab and not lab_running:
        # L2 §12.9: a halt pauses the lab and suspends every LIVE rule (it resumes when the lab runs again)
        rows = [{"utc": asof, "id": r["id"], "event": "SUSPENDED", "reason": "S-a: lab paused", "n": "", "E": "",
                 "K": "", "D_total": registry.promotions_count(events_l), "run_id": run_id, "head_sha": head}
                for r in recs if sts[r["id"]]["state"] == "LIVE"]
        registry.append_events(ev_path, rows)
        events_l = registry.read_events(ev_path)
        sts = registry.states(recs, events_l, start)
    if run_lab and lab_running and mf is not None:
        lbars = bars.lab_bars(mf)
        hol_set = {pd.Timestamp(h) for h in hol}
        evd = forecasts.event_days(events)
        code8 = frozen_hashes.code_sha8()
        pend = ledger.pending_days(P.lab, sts, complete)
        dis = [ledger.day_inputs(d, mf, lbars, store, hol_set, evd) for d in pend]
        ledger.settle_days(P.lab, recs, sts, dis, asof, code8, start, synthetic=(mode == "synthetic"))
        settled = ledger.read(P.lab / "lab_days.csv")
        if settled:
            last = pd.Timestamp(settled[-1]["day"])
            diffs = ledger.tripwire(P.lab, recs, sts, ledger.day_inputs(last, mf, lbars, store, hol_set, evd), code8)
            if diffs:
                halt.append("lab tripwire: " + "; ".join(diffs[:3]))
                lab_running = False
        ledger.update_states(P.lab, recs, sts, events_l, asof, lab_running, run_id, head, today_model)
        events_l = registry.read_events(ev_path)
        sts = registry.states(recs, events_l, start)
        # proposer (on its Saturday)
        done = sorted(p.stem for p in (P.lab / "proposer").glob("*.json"))
        first = ledger.lab_first_day(sts)
        n_settled = sum(1 for r in settled if first and r["day"] >= first)
        pdate = proposer.due(pd.Timestamp(now).date(), n_settled, done) if lab_running else None
        if pdate and first:
            tdays = [r["day"] for r in settled if r["day"] >= first and r["day"] < pdate][-proposer.TRAIN_DAYS:]
            tin = [ledger.day_inputs(d, mf, lbars, store, hol_set, evd) for d in tdays]
            active = sum(1 for r in recs if r["tier"] == "PROPOSER" and sts[r["id"]]["state"] in
                         ("PENDING", "PAPER", "LIVE", "SUSPENDED"))
            rep = proposer.run(tin, pdate, first, [r["question"] for r in recs], active)
            D_now = registry.promotions_count(events_l)
            k0 = sum(1 for r in recs if r["tier"] == "PROPOSER")
            for i, spec in enumerate(rep["chosen_specs"]):
                k = k0 + i + 1
                rec = registry.record(f"P{k:03d}", spec, tier="PROPOSER", promotable=True,
                                      gamma=eproc.gamma_proposal(k), D=D_now, title_ar=proposer.title_for(spec),
                                      source=f"proposer {pdate}: t {rep['chosen_t'][i]:.3f} >= q95 {rep['q95']:.3f}",
                                      extra={"arrival": 100 + k, "proposal_k": k, "proposed_date": pdate})
                registry.write(P.reg, rec)
            rep["registered_ids"] = [f"P{k0 + i + 1:03d}" for i in range(len(rep["chosen_specs"]))]
            publish.write_json(P.lab / "proposer" / f"{pdate}.json", rep)
            proposer_report = rep
            recs = registry.load(P.reg)
            sts = registry.states(recs, events_l, start)

    # 5 publish
    lab_info = lab_summary(P, recs, sts, events_l, "RUNNING" if lab_running else "PAUSED", start)
    if proposer_report is None:
        done = sorted((P.lab / "proposer").glob("*.json"))
        if done:
            proposer_report = json.loads(done[-1].read_text())
    if proposer_report:
        lab_info["proposer"] = {k: proposer_report[k] for k in ("run_date", "n_scored", "q95", "chosen",
                                                                 "n_rules")}
        lab_info["proposer"]["n_train"] = len(proposer_report["train_days"])
    lines = publish.system_csv(asof, l1, l3_info, lab_info)
    publish.write_system_csv(P.site / "VolMapSystem.csv", lines)
    st_store = forecasts.read_store(P.data / "forecasts.csv")
    info = {"asof_utc": asof, "halt": halt, "ops": ops, "start": start, "l1": l1, "l3": l3_info, "lab": lab_info,
            "data": {"ok_days": len(fetch.ok_days(P.data, now)), "missing": fetch.missing(P.data),
                     "complete_through_utc": complete.strftime("%Y-%m-%d %H:%M"),
                     "revisions": len(fetch.read_csv(P.data / "revisions.csv", fetch.REVISION_COLS)),
                     "store_rows": len(st_store), "store_defined": int(pd.notna(st_store.F_H1).sum()),
                     "store_new": n_new}}
    publish.write_json(P.site / "lab.json", site_json(info))
    (P.rep / "STATUS.md").write_text(publish.status_md(info))
    if halt:
        (P.rep / "HALT.md").write_text("# HALT\n\n" + "\n".join(f"- {h}" for h in halt) + "\n")
    return info, bool(halt)


def lab_summary(P, recs, sts, events_l, state, start):
    twins = ledger.read(P.lab / "twins.csv")
    days = ledger.read(P.lab / "lab_days.csv")
    first = ledger.lab_first_day(sts)
    rules, best, ever_promoted = [], 0.0, any(e["event"] == "PROMOTED" for e in events_l)
    interp = ever_promoted
    for r in recs:
        s = sts[r["id"]]
        stt = ledger.rule_stats(P.lab, r, s, twins)
        E, Es = stt["E"], (r["E_star"] if r["E_star"] is not None else float("inf"))
        prog = None
        if r["promotable"] and np.isfinite(Es):
            prog = float(min(max(np.log(max(E, 1e-300)) / np.log(Es), 0.0), 1.0))
            if s["state"] == "PAPER":
                best = max(best, E / Es)
        interp = interp or eproc.interpreter_needed(E, Es, stt["n"], r["promotable"] and s["state"] == "PAPER",
                                                    False)
        # §3 item 11: a promoted rule's record is its post-promotion record only
        if s["state"] in ("LIVE", "SUSPENDED"):
            n_shown, net_shown = len(stt["post"]), float(sum(t["net_usd"] for t in stt["post"]))
        else:
            n_shown, net_shown = stt["n"], stt["sum_net"]
        rules.append({"id": r["id"], "title_ar": r["title_ar"], "tier": r["tier"], "promotable": r["promotable"],
                      "state": s["state"], "state_ar": publish.STATE_AR[s["state"]], "first_day": s["first_day"],
                      "registered_utc": s["registered_utc"], "n": n_shown, "net_sum": net_shown,
                      "net_avg": net_shown / n_shown if n_shown else None, "E": E,
                      "record": "post-promotion" if s["state"] in ("LIVE", "SUSPENDED") else "since first_day",
                      "E_star": Es if np.isfinite(Es) else None, "progress": prog, "n_post": len(stt["post"]),
                      "spec": r["spec"]})
    live = [x for x in rules if x["state"] == "LIVE"]
    return {"state": state, "days": sum(1 for d in days if first and d["day"] >= first),
            "n_paper": sum(1 for x in rules if x["promotable"] and x["state"] == "PAPER"), "n_live": len(live),
            "best_progress": best, "live": live, "rules": rules, "interpreter_needed": bool(interp),
            "first_day": first}


def site_json(info):
    """lab.json for the card page: no NaN, Arabic texts as they are."""
    def clean(x):
        if isinstance(x, float):
            return None if not np.isfinite(x) else round(x, 6)
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.floating,)):
            return clean(float(x))
        return x
    lab = info["lab"]
    return clean({"generated_utc": info["asof_utc"], "lab_state": lab["state"], "halted": bool(info["halt"]),
                  "start": info["start"], "lab_days": lab["days"], "n_paper": lab["n_paper"], "n_live": lab["n_live"],
                  "interpreter_needed": lab["interpreter_needed"], "rules": [
                      {k: v for k, v in r.items() if k != "spec"} | {"T": r["spec"]["T"], "hold": r["spec"]["hold"]}
                      for r in lab["rules"]],
                  "proposer": lab.get("proposer"), "l1_green_ok": info["l1"]["green_ok"],
                  "l3": {"asof": info["l3"]["asof"], "zstar": info["l3"]["zstar"],
                         "mult": {b: {"m": m, "n": n} for b, (m, n) in info["l3"]["mult"].items()}},
                  "data": info["data"]})


def deploy(log=print):
    r = subprocess.run(WRANGLER, cwd=ROOT, capture_output=True, text=True)
    log(r.stdout[-2000:] + r.stderr[-2000:])
    return r.returncode == 0


def synthetic_runs(P, log=print):
    """The end-to-end lab dry run on a synthetic world: Tuesday 2026-10-27, then every Saturday 03:20 UTC."""
    import synth
    synth.world(P.data)
    times = [pd.Timestamp("2026-10-27 03:20", tz="UTC")] + list(
        pd.date_range("2026-10-31 03:20", "2027-02-27 03:20", freq="7D", tz="UTC"))
    halted = False
    for t in times:
        info, h = one_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=log)
        halted = halted or h
        log(f"{t}: lab days {info['lab']['days']}, paper {info['lab']['n_paper']}, live {info['lab']['n_live']}, "
            f"store {info['data']['store_rows']}, halt {info['halt']}")
    return info, halted


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
        sys.exit("--synthetic needs --dry")
    if not a.dry and os.environ.get("GITHUB_ACTIONS") != "true":
        sys.exit("the ledgers have one writer, the GitHub Actions job: run locally with --dry")
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
    else:
        P = Paths(ROOT)
        run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
        head = git("rev-parse", "HEAD") or "unknown"
        info, halted = one_run(P, now, "cloud", run_id, head, fetch_on=not a.no_fetch)
        if not a.no_deploy and not deploy():
            info["ops"].append("deploy failed")
        if not halted:
            write_start(P, now, run_id, head)
    print(json.dumps({"halt": info["halt"], "ops": info["ops"], "start": info["start"], "lab_days": info["lab"]["days"],
                      "data": info["data"], "l1_green_ok": info["l1"]["green_ok"]}, indent=1, ensure_ascii=False))
    return 1 if halted else 0


if __name__ == "__main__":
    sys.exit(main())
