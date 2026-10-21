"""analysis/system/lab_v2/FROZEN_V2.sha256 (SYSTEM_V2_PREREG.md §2.5 item 1). OPS tool; the manifest it writes is the
lab v2 freeze. v1's analysis/system/FROZEN.sha256 is never edited.

FROZEN (lab v2), by sha256: the v2 bar rules, signal and audit, accounting, ledger and state machine, registry and
START rule, the vendored hunt harness and seeds with their SHA256SUMS, the four registry files, and the FROZEN v1
modules lab v2 imports (pinned here too, so a change to any of them halts v2 as well as v1). Everything else in
analysis/system/lab_v2 (run_v2.py, v2_publish.py, v2_page.py, v2_crash.py, v2_lookback.py, v2_synth.py, this file) is
OPS: fixes are allowed and logged in reports/system/lab_v2/ops_changes.csv.

A lab v2 run checks every line of the manifest and the vendored SHA256SUMS; any mismatch halts v2 only
(reports/system/lab_v2/HALT.md).

Usage: uv run --frozen python -I analysis/system/lab_v2/v2_frozen.py [--write | --check]
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "analysis" / "system" / "lab_v2" / "FROZEN_V2.sha256"
VENDOR = ROOT / "analysis" / "system" / "lab_v2" / "vendor"
FROZEN_V2_FILES = [
    # lab v2: bar rules, signal and audit, accounting, ledger and states, registry and START
    "analysis/system/lab_v2/v2paths.py",
    "analysis/system/lab_v2/v2_data.py",
    "analysis/system/lab_v2/v2_signals.py",
    "analysis/system/lab_v2/v2_exec.py",
    "analysis/system/lab_v2/v2_ledger.py",
    "analysis/system/lab_v2/v2_registry.py",
    # vendored hunt harness and seeds (byte-identical, xauusd-quant 074e6b8)
    "analysis/system/lab_v2/vendor/SHA256SUMS",
    "analysis/system/lab_v2/vendor/hunt/harness.py",
    "analysis/system/lab_v2/vendor/hunt/candidates/levels__watched_level_break.py",
    "analysis/system/lab_v2/vendor/hunt/candidates/r3_ctaflow__cta_flip_flow_usmorning.py",
    "analysis/system/lab_v2/vendor/hunt/candidates/r2_orb__inplay_comex_orb60.py",
    "analysis/system/lab_v2/vendor/hunt/candidates/r2_exhaustion__databar_stretch_settle.py",
    # seed registry
    "reports/system/lab_v2/registry/S2.json",
    "reports/system/lab_v2/registry/S3.json",
    "reports/system/lab_v2/registry/S4.json",
    "reports/system/lab_v2/registry/S5.json",
    # FROZEN v1 modules lab v2 imports (read-only)
    "analysis/system/bi5.py",
    "analysis/system/bars.py",
    "analysis/system/forecasts.py",
    "analysis/system/vendor/volmap/core.py",
    "analysis/system/vendor/volmap/models.py",
    "analysis/system/lab/__init__.py",
    "analysis/system/lab/grammar.py",
    "analysis/system/lab/execution.py",
    "analysis/system/lab/eproc.py",
    "analysis/system/lab/registry.py",
]


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(root=ROOT, manifest=MANIFEST):
    lines = [f"{sha256(Path(root) / f)}  {f}" for f in FROZEN_V2_FILES]
    Path(manifest).write_text("\n".join(lines) + "\n")
    return lines


def check(root=ROOT, manifest=MANIFEST):
    """Problems (empty = every file in the manifest matches)."""
    manifest = Path(manifest)
    if not manifest.exists():
        return [f"{manifest.name} is missing"]
    bad = []
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, path = line.split(maxsplit=1)
        p = Path(root) / path
        if not p.exists():
            bad.append(f"{path}: missing")
        elif sha256(p) != digest:
            bad.append(f"{path}: sha256 differs from FROZEN_V2.sha256")
    return bad


def vendor_check(vendor=VENDOR):
    """vendor/SHA256SUMS against the vendored hunt files."""
    bad = []
    for line in (Path(vendor) / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        p = Path(vendor) / path
        if not p.exists() or sha256(p) != digest:
            bad.append(f"lab_v2/vendor/{path}: sha256 differs from SHA256SUMS")
    return bad


def code_sha8(manifest=MANIFEST):
    m = Path(manifest)
    return sha256(m)[:8] if m.exists() else "nofrozen"


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        for line in write():
            print(line)
        return 0
    bad = check() + vendor_check()
    print("\n".join(bad) if bad else "FROZEN_V2.sha256: every file matches")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
