"""The lab v2 crash record (SYSTEM_V2_PREREG.md §2.5 item 2). OPS, Python standard library only.

A lab v2 run that cannot finish normally halts lab v2 only, and leaves the same record whatever stopped it:
- reports/system/lab_v2/HALT.md (rewritten) and a row of reports/system/lab_v2/halts.csv (`utc,run_id,head_sha,reason`);
- reports/system/lab_v2/summary.json: the last good summary with state PAUSED, halted true, halt_reasons [reason]
  and halt_utc (asof_utc stays the time of that last good run). Nothing is written when there is no valid summary
  yet, so v1's publisher then leaves the lab2_* keys out, as before the first lab v2 run;
- the client's page reports/forward_site/system/lab_v2/{index.html, lab_v2.json} re-rendered from that PAUSED summary
  (v2_page), so it shows «المختبر الثاني متوقف مؤقتًا».

Who calls it:
- run_v2.py, for an exception inside the run and for a failed import of any module it needs (it imports only the
  standard library at top level and guards every other import);
- the workflow (.github/workflows/system.yml, step "Lab v2 did not finish"), when the lab v2 step did not report its
  own end: the 10-minute timeout, a killed process (out of memory), a crash before run_v2.py could record it, or a
  failed `uv run`. That step first restores the three lab v2 folders to HEAD, then runs
  `python -I analysis/system/lab_v2/v2_crash.py --reason "<reason>"`.

Each write is attempted on its own; the function never raises.
"""
import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HALT_COLS = ["utc", "run_id", "head_sha", "reason"]
STATES = ("RUNNING", "PAUSED")


def rep_dir(base):
    return Path(base) / "reports" / "system" / "lab_v2"


def site_dir(base):
    return Path(base) / "reports" / "forward_site" / "system" / "lab_v2"


def write_halt(base, asof, run_id, head, reasons):
    """HALT.md (a snapshot of the latest run) and one halts.csv row per reason."""
    rep = rep_dir(base)
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "HALT.md").write_text("# HALT (lab v2 only; v1 is not affected)\n\n" + f"Run {asof}:\n\n"
                                 + "\n".join(f"- {h}" for h in reasons) + "\n", encoding="utf-8")
    path = rep / "halts.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HALT_COLS, lineterminator="\n")
        if new:
            w.writeheader()
        for h in reasons:
            w.writerow({"utc": asof, "run_id": run_id, "head_sha": head, "reason": h})


def paused(old, asof, reason):
    """The summary after a crashed run: the last good summary with state PAUSED (None if there is no valid one)."""
    if not isinstance(old, dict) or old.get("state") not in STATES or not isinstance(old.get("rules"), list):
        return None
    out = dict(old)
    out.update({"state": "PAUSED", "halted": True, "halt_reasons": [reason], "halt_utc": asof})
    return out


def _json(path, obj):
    def clean(x):
        if isinstance(x, float):
            return x if math.isfinite(x) else None
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        if isinstance(x, list):
            return [clean(v) for v in x]
        return x
    path = Path(path)
    path.write_text(json.dumps(clean(obj), ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")


def record(base, asof, run_id, head, reason, log=None):
    """The crash record (see the module doc). Returns the list of the parts written."""
    done = []
    reason = " ".join(str(reason).split())[:500]
    try:
        write_halt(base, asof, run_id, head, [reason])
        done.append("HALT.md")
    except Exception as e:  # noqa: BLE001 - never raises
        if log:
            log(f"crash record: HALT.md not written ({type(e).__name__})")
    new = None
    try:
        p = rep_dir(base) / "summary.json"
        old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        new = paused(old, asof, reason)
        if new is not None:
            _json(p, new)
            done.append("summary.json")
    except Exception as e:  # noqa: BLE001
        new = None
        if log:
            log(f"crash record: summary.json not marked PAUSED ({type(e).__name__})")
    if new is not None:
        try:
            if str(HERE) not in sys.path:
                sys.path.insert(0, str(HERE))
            import v2_page
            v2_page.write_site(site_dir(base), new)
            done.append("page")
        except Exception as e:  # noqa: BLE001
            if log:
                log(f"crash record: page not re-rendered ({type(e).__name__})")
    return done


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the lab v2 crash record (HALT.md, halts.csv, PAUSED summary, page).")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--base", default=str(ROOT))
    ap.add_argument("--now")
    ap.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "unknown"))
    ap.add_argument("--head", default=os.environ.get("GITHUB_SHA", "unknown"))
    a = ap.parse_args(argv)
    done = record(a.base, a.now or now_iso(), a.run_id, a.head, a.reason, log=print)
    print("lab v2 crash record: " + (", ".join(done) or "nothing written"))
    return 0 if "HALT.md" in done else 1


if __name__ == "__main__":
    sys.exit(main())
