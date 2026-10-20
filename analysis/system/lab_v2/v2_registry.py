"""Lab v2 registry: the four seed records, exact E*, verification and v2 START (SYSTEM_V2_PREREG.md §0, §2.1, §2.3;
v1 §3 items 5-7 and Amendment A1 item 5). FROZEN (lab v2).

- One file per seed, reports/system/lab_v2/registry/<id>.json (S2, S3, S4, S5), never edited after its commit
  (written by write_seed_files at the build; registry files are pinned in FROZEN_V2.sha256).
- α_v2 = 0.005 = 0.01·2^−(2−1) (A1 item 5); γ: S2 0.30, S3 0.30, S4 0.20, S5 0.20 (Σ = 1, no reserve); D_j = the v2
  promotions before seed j's arrival = 0 for S2-S5; α_j = α_v2·γ_j·(D_j + 1); E*_j = 1/α_j, stored exactly as a
  rational ("E_star_exact": "2000/3" for S2 and S3, "1000" for S4 and S5) and as the nearest double ("E_star").
  Promotion's P1 compares the double E with the exact rational (Python's exact float/Fraction comparison).
- registered_utc and first_day are v1 §3 item 5 (v1 lab.registry.register_new / first_day / states, unchanged): the
  UTC time at which a lab v2 run in GitHub Actions first finds the file at origin/main HEAD, logged as REGISTERED in
  the append-only reports/system/lab_v2/registry/events.csv; first_day = the first model weekday d with d 01:00 model
  >= registered_utc + 1 h and d >= the v2 START.
- v2 START (§0) = the later of the v1 START (reports/system/START.json) and the first Monday at least 2 calendar days
  after the first successful (non-halted) lab v2 cloud run, written once to reports/system/lab_v2/START.json.
- Titles follow v1's title rule (A1 item 3), checked by v1 lab.registry.title_ok.
"""
import datetime as dt
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pandas as pd

import v2_data
import v2_signals
from lab import registry as v1reg

LAB_VERSION = 2
ALPHA_V2 = Fraction(1, 200)
GAMMA = {"S2": Fraction(3, 10), "S3": Fraction(3, 10), "S4": Fraction(1, 5), "S5": Fraction(1, 5)}
TITLES = {"S2": "كسر المستويات المراقبة", "S3": "تدفق صناديق الاتجاه في الصباح",
          "S4": "كسر نطاق افتتاح كومكس", "S5": "الاندفاع بعد شمعة الخبر"}
HUNT = {  # research/hunt/referee_results.csv, existing results only (§0, §2.1); descriptive
    "S2": {"round": 1, "val_z": 1.775, "val_years": "3/4", "q": 0.215, "hunt_pass": False},
    "S3": {"round": 3, "val_z": 1.941, "val_years": "4/4", "q": 0.215, "hunt_pass": False},
    "S4": {"round": 2, "val_z": 0.913, "val_years": "3/4", "q": 0.61, "hunt_pass": False},
    "S5": {"round": 2, "val_z": 0.66, "val_years": "2/4", "q": 0.61, "hunt_pass": False},
}
SOURCE_COMMIT = "074e6b8716f18ce5dad89a10e40ed26bd8afeb0e"
COSTS = {"allowance_usd": 0.10, "stress_add_usd": 0.25}
STOP = {"kind": "disaster", "mult": 3, "unit": "S10 distance of the entry slot", "k_S": 1.0540339626212611}
START_RULE = ("later of the v1 START and the first Monday >= 2 days after the first successful lab v2 cloud run "
              "(SYSTEM_V2_PREREG.md §0)")
REG_REL = "reports/system/lab_v2/registry"


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def e_star_exact(gamma, D=0, alpha=ALPHA_V2):
    return 1 / (alpha * Fraction(gamma) * (D + 1))


def frac_str(f):
    f = Fraction(f)
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def seed_record(sid, arrival):
    t = v2_signals.seed_table()[sid]
    seed_path = v2_data.CANDIDATES / t["file"]
    mod = v2_signals.load_seed(sid)
    g = GAMMA[sid]
    es = e_star_exact(g)
    tf_min = v2_signals.TF_MIN[t["tf"]]
    rec = {
        "id": sid, "lab_version": LAB_VERSION, "tier": "SEED", "promotable": True, "arrival": arrival,
        "title_ar": TITLES[sid],
        "seed_name": mod.NAME,
        "seed_file": f"analysis/system/lab_v2/vendor/hunt/candidates/{t['file']}",
        "seed_sha256": sha256_file(seed_path),
        "harness_file": "analysis/system/lab_v2/vendor/hunt/harness.py",
        "harness_sha256": sha256_file(v2_data.HARNESS_PATH),
        "source": f"xauusd-quant research/hunt/candidates/{t['file']} at {SOURCE_COMMIT[:7]}, byte-identical",
        "tf": t["tf"], "tf_minutes": tf_min, "hold_bars": t["hold"], "hold_minutes": t["hold"] * tf_min,
        "input_start_model": "2026-01-02 00:00", "entry_delay_min": 1,
        "stop": dict(STOP), "cost": dict(COSTS),
        "gamma": float(g), "gamma_exact": frac_str(g), "alpha": float(ALPHA_V2), "alpha_exact": frac_str(ALPHA_V2),
        "D_at_arrival": 0, "alpha_j": float(ALPHA_V2 * g), "E_star": float(es), "E_star_exact": frac_str(es),
        "hunt": dict(HUNT[sid]),
    }
    if not v1reg.title_ok(rec["title_ar"]):
        raise ValueError(f"{sid}: title breaks the title rule")
    return rec


def seed_records():
    return [seed_record(s[0], i + 1) for i, s in enumerate(v2_signals.SEEDS)]


def write_seed_files(reg_dir):
    """Build-time only: write the four registry files (refuses to overwrite)."""
    for rec in seed_records():
        v1reg.write(reg_dir, rec)


def load(reg_dir):
    recs = [json.loads(p.read_text()) for p in sorted(Path(reg_dir).glob("*.json"))]
    return sorted(recs, key=lambda r: (r.get("arrival", 1_000_000), r["id"]))


def verify(reg_dir, root):
    """Problems with the registry files (empty = OK): each file equals its rebuilt record exactly (seed and harness
    sha256, TF, HOLD, γ, α, E* exact and double, title), γ sums to 1, ids are S2-S5."""
    bad = []
    recs = load(reg_dir)
    ids = [r["id"] for r in recs]
    if ids != [s[0] for s in v2_signals.SEEDS]:
        bad.append(f"registry ids {ids} are not S2, S3, S4, S5")
    gsum = Fraction(0)
    for r in recs:
        if r["id"] not in GAMMA:
            continue
        try:
            want = seed_record(r["id"], r.get("arrival"))
        except Exception as e:  # noqa: BLE001
            bad.append(f"{r['id']}: cannot rebuild the record ({e})")
            continue
        for k in sorted(set(want) | set(r)):
            if want.get(k) != r.get(k):
                bad.append(f"{r['id']}: field {k} differs from the rebuilt record")
        if Path(root, r["seed_file"]).exists() and sha256_file(Path(root, r["seed_file"])) != r["seed_sha256"]:
            bad.append(f"{r['id']}: seed file sha256 differs")
        if Fraction(r.get("E_star_exact", "0")) != e_star_exact(Fraction(r.get("gamma_exact", "1"))):
            bad.append(f"{r['id']}: E_star_exact does not follow from gamma")
        gsum += Fraction(r.get("gamma_exact", "0"))
    if recs and gsum != 1:
        bad.append(f"gamma sums to {gsum}, not 1")
    return bad


def start_v2(first_run_utc, v1_start):
    """The later of the v1 START and the first Monday at least 2 calendar days after the first successful run."""
    d = pd.Timestamp(first_run_utc).date() + dt.timedelta(days=2)
    monday = d + dt.timedelta(days=(7 - d.weekday()) % 7)
    return max(dt.date.fromisoformat(str(v1_start)[:10]), monday)


def start_record(first_run_utc, run_id, head_sha, v1_start):
    t = pd.Timestamp(first_run_utc)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return {"first_cloud_run_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "run_id": run_id, "head_sha": head_sha,
            "v1_start": str(v1_start)[:10], "start": str(start_v2(t, v1_start)), "rule": START_RULE}
