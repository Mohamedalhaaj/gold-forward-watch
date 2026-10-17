"""analysis/system/FROZEN.sha256 (SYSTEM_V1_PREREG.md §3 item 6). OPS tool; the manifest it writes is the freeze.

FROZEN, by sha256: grammar, accounting, bar rules, e-process, registry, proposer, calendars, vendored volmap, L3
estimator (with its z*), L1 twin and the seed registry. Everything else (fetch transport, orchestration, publish,
dashboard, workflow) is OPS and may be fixed after the freeze, with the fix logged.

A run checks every line of the manifest; any mismatch halts it (lab PAUSED, reports/system/HALT.md).
The paths are read from the manifest itself, so this file's list matters only when the manifest is (re)written,
which happens once, at the freeze (tag lab-v1-freeze).

Usage: uv run --frozen python -I analysis/system/frozen_hashes.py [--write | --check]
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "analysis" / "system" / "FROZEN.sha256"
FROZEN_FILES = [
    # bar rules and clocks
    "analysis/system/bi5.py",
    "analysis/system/bars.py",
    "analysis/system/syspath.py",
    # vendored volmap, its adapter and the calendars
    "analysis/system/forecasts.py",
    "analysis/system/vendor/SHA256SUMS",
    "analysis/system/vendor/volmap/core.py",
    "analysis/system/vendor/volmap/models.py",
    "analysis/system/vendor/volmap/discovery_params.json",
    "analysis/system/vendor/calendars/bls_2026_2027.csv",
    "analysis/system/vendor/calendars/fomc_2026_2027.csv",
    # L1 twin
    "analysis/system/vendor/system_common.py",
    # L3 estimator and its z*
    "analysis/system/l3.py",
    "reports/system/L3_ZSTAR.json",
    # lab: grammar, accounting, e-process, registry, proposer
    "analysis/system/lab/__init__.py",
    "analysis/system/lab/grammar.py",
    "analysis/system/lab/execution.py",
    "analysis/system/lab/ledger.py",
    "analysis/system/lab/eproc.py",
    "analysis/system/lab/registry.py",
    "analysis/system/lab/proposer.py",
    # seed registry
    "reports/system/lab/registry/S1.json",
    "reports/system/lab/registry/S1R.json",
    "reports/system/lab/registry/C1.json",
]


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(root=ROOT, manifest=MANIFEST):
    lines = [f"{sha256(Path(root) / f)}  {f}" for f in FROZEN_FILES]
    Path(manifest).write_text("\n".join(lines) + "\n")
    return lines


def check(root=ROOT, manifest=MANIFEST):
    """List of problems (empty = every frozen file matches the manifest)."""
    manifest = Path(manifest)
    if not manifest.exists():
        return [f"{manifest} is missing"]
    bad = []
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, path = line.split(maxsplit=1)
        p = Path(root) / path
        if not p.exists():
            bad.append(f"{path}: missing")
        elif sha256(p) != digest:
            bad.append(f"{path}: sha256 differs from FROZEN.sha256")
    return bad


def vendor_check(root=ROOT):
    """vendor/SHA256SUMS against the vendored files (byte-identical copies of xauusd-quant)."""
    vd = Path(root) / "analysis" / "system" / "vendor"
    bad = []
    for line in (vd / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        if sha256(vd / path) != digest:
            bad.append(f"vendor/{path}: sha256 differs from SHA256SUMS")
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
    print("\n".join(bad) if bad else "FROZEN.sha256: every file matches")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
