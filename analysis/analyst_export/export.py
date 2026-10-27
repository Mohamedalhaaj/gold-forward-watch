"""The analyst input mirror (xauusd-quant IMPLEMENTATION_REGISTER.md R-AN-12; ANALYST_V1_PREREG.md R1 Isolation (a)).

Copies into a checkout of Mohamedalhaaj/gold-analyst ONLY the inputs the analyst may see:
1. `mirror/system/days.csv` = a byte copy of `data/system/days.csv`. The mirror's existing bytes must be a prefix of it.
2. For every `ok` row with day >= 2026-09-01: `data/system/raw/YYYY/MM/DD/<SIDE>.bi5` -> the same path under
   `mirror/system/raw/` if absent there. The source file and an existing mirror file must have the row's sha256.
3. `mirror/system/forecasts_slots.csv` = the header line of `data/system/forecasts.csv` plus, in source order, the
   exact source lines whose `slot` is 9, 10 or 15 (the only slots D_ref uses). The existing content must be a byte
   prefix of it.
3b. (§16.18 A14-D10) `mirror/system/forecasts.csv` = a byte copy of `data/system/forecasts.csv` (every slot). The
   mirror's existing content must be a byte prefix of it. Its sha256 is the row's `forecasts_sha256`.
4. One row appended to `mirror/exports.csv`:
   `utc,source_sha,days_sha256,forecasts_sha256,slots_sha256,raw_files,new_raw_files,run_id`.
Everything is checked before anything is written; a failed check stops the job (ops failure) and writes nothing.
No system file is read beyond these, and nothing in gold-forward-watch is changed.

Usage: python -I analysis/analyst_export/export.py --source GFW_DIR --dest GOLD_ANALYST_DIR [--run-id ID]
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import subprocess
import sys
from pathlib import Path

FIRST_DAY = "2026-09-01"
SLOTS = {"9", "10", "15"}
EXPORT_COLS = ["utc", "source_sha", "days_sha256", "forecasts_sha256", "slots_sha256", "raw_files", "new_raw_files",
               "run_id"]


class ExportError(Exception):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def raw_rel(day, side):
    y, m, d = day.split("-")
    return f"{y}/{m}/{d}/{side}.bi5"


def slot_lines(text):
    lines = text.split("\n")
    if not lines or not lines[0].startswith("day,slot,"):
        raise ExportError("forecasts.csv header")
    out = [lines[0]]
    for line in lines[1:]:
        if not line:
            continue
        row = next(csv.reader([line]))
        if row[1] in SLOTS:
            out.append(line)
    return "\n".join(out) + "\n"


def plan(src, dst):
    """Everything to write, after every check: (writes {rel: bytes}, summary)."""
    src, dst = Path(src), Path(dst)
    days_b = (src / "data/system/days.csv").read_bytes()
    fc_b = (src / "data/system/forecasts.csv").read_bytes()
    writes = {}
    old = dst / "mirror/system/days.csv"
    if old.exists() and not days_b.startswith(old.read_bytes()):
        raise ExportError("mirror days.csv is not a prefix of the source")
    writes["mirror/system/days.csv"] = days_b
    n_raw = n_new = 0
    for r in csv.DictReader(io.StringIO(days_b.decode("utf-8"))):
        if r["status"] != "ok" or r["day"] < FIRST_DAY:
            continue
        rel = raw_rel(r["day"], r["side"])
        s = src / "data/system/raw" / rel
        if not s.exists() or sha(s.read_bytes()) != r["sha256"]:
            raise ExportError(f"source raw file differs from its row: {rel}")
        d = dst / "mirror/system/raw" / rel
        n_raw += 1
        if d.exists():
            if sha(d.read_bytes()) != r["sha256"]:
                raise ExportError(f"mirror raw file differs from its row: {rel}")
            continue
        writes[f"mirror/system/raw/{rel}"] = s.read_bytes()
        n_new += 1
    slots_b = slot_lines(fc_b.decode("utf-8")).encode("utf-8")
    old_s = dst / "mirror/system/forecasts_slots.csv"
    if old_s.exists() and not slots_b.startswith(old_s.read_bytes()):
        raise ExportError("mirror forecasts_slots.csv is not a prefix of the new content")
    writes["mirror/system/forecasts_slots.csv"] = slots_b
    old_f = dst / "mirror/system/forecasts.csv"                     # step 3b (A14-D10)
    if old_f.exists() and not fc_b.startswith(old_f.read_bytes()):
        raise ExportError("mirror forecasts.csv is not a prefix of the source")
    writes["mirror/system/forecasts.csv"] = fc_b
    return writes, {"days_sha256": sha(days_b), "forecasts_sha256": sha(fc_b), "slots_sha256": sha(slots_b),
                    "raw_files": n_raw, "new_raw_files": n_new}


def export(src, dst, source_sha, run_id, now):
    writes, summ = plan(src, dst)
    dst = Path(dst)
    for rel, b in writes.items():
        p = dst / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.read_bytes() != b:
            p.write_bytes(b)
    if sha((dst / "mirror/system/forecasts.csv").read_bytes()) != summ["forecasts_sha256"]:
        raise ExportError("mirror forecasts.csv differs from the row's forecasts_sha256")   # read back, no row
    ex = dst / "mirror/exports.csv"
    new = not ex.exists()
    with open(ex, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_COLS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow({"utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source_sha": source_sha, **summ,
                    "run_id": run_id})
    return summ


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--run-id", default="")
    a = ap.parse_args(argv)
    head = subprocess.run(["git", "-C", a.source, "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    try:
        s = export(a.source, a.dest, head, a.run_id, now)
    except ExportError as e:
        print(f"ops failure: {e}")
        return 2
    print(f"mirror source {head[:12]} raw {s['raw_files']} new {s['new_raw_files']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
