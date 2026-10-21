"""The judge's vendored research files (SYSTEM_V2_PREREG.md §3.1): the frozen volmap model (research/volmap/core.py,
models.py, frozen/discovery_params.json), the hunt harness and the four v2 seed files, and the two official calendar
data files of research/system/calendars/ (IMPLEMENTATION_REGISTER R-V1-15), all byte-identical to xauusd-quant and
checked against judge/vendor/SHA256SUMS before use. Nothing else is vendored.
"""
import importlib.util
import json
import sys

from .common import VENDOR, sha256_file

SEED_FILES = {
    "S2": "hunt/candidates/levels__watched_level_break.py",
    "S3": "hunt/candidates/r3_ctaflow__cta_flip_flow_usmorning.py",
    "S4": "hunt/candidates/r2_orb__inplay_comex_orb60.py",
    "S5": "hunt/candidates/r2_exhaustion__databar_stretch_settle.py",
}
SEED_SPEC = {"S2": ("M5", 24), "S3": ("M15", 8), "S4": ("M5", 48), "S5": ("M15", 14)}   # R-V2-9


class VendorMismatch(Exception):
    pass


def sums():
    out = {}
    for line in (VENDOR / "SHA256SUMS").read_text().splitlines():
        if line.strip():
            h, p = line.split("  ", 1)
            out[p] = h
    return out


def check():
    """List of problems (empty when every vendored file matches SHA256SUMS and nothing is unlisted)."""
    probs = []
    want = sums()
    for p, h in want.items():
        f = VENDOR / p
        if not f.exists():
            probs.append(f"vendor/{p}: missing")
        elif sha256_file(f) != h:
            probs.append(f"vendor/{p}: sha256 differs from SHA256SUMS")
    for f in VENDOR.rglob("*"):
        if f.is_file() and f.name != "SHA256SUMS" and "__pycache__" not in f.parts:
            rel = f.relative_to(VENDOR).as_posix()
            if rel not in want:
                probs.append(f"vendor/{rel}: not in SHA256SUMS")
    return probs


def _require():
    probs = check()
    if probs:
        raise VendorMismatch("; ".join(probs))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cache = {}


def volmap():
    """(core, models, params) of the frozen volmap. models.py does `import core`, so the vendored core is registered
    under that name while models loads, and the previous binding (if any) is restored after."""
    if "volmap" in _cache:
        return _cache["volmap"]
    _require()
    core = _load("judge_vendor_core", VENDOR / "volmap/core.py")
    prev = sys.modules.get("core")
    sys.modules["core"] = core
    try:
        models = _load("judge_vendor_models", VENDOR / "volmap/models.py")
    finally:
        if prev is None:
            sys.modules.pop("core", None)
        else:
            sys.modules["core"] = prev
    params = json.loads((VENDOR / "volmap/frozen/discovery_params.json").read_text())["params"]
    _cache["volmap"] = (core, models, params)
    return _cache["volmap"]


def harness():
    if "harness" not in _cache:
        _require()
        _cache["harness"] = _load("judge_vendor_harness", VENDOR / "hunt/harness.py")
    return _cache["harness"]


def seed(sid):
    """The seed module, loaded the way the harness loads candidates (its own _import, spec_from_file_location)."""
    key = "seed_" + sid
    if key not in _cache:
        h = harness()
        mod = h._import(str(VENDOR / SEED_FILES[sid]))
        tf, hold = SEED_SPEC[sid]
        if mod.TF != tf or int(mod.HOLD) != hold:
            raise VendorMismatch(f"{sid}: TF/HOLD {mod.TF}/{mod.HOLD} differ from {tf}/{hold}")
        _cache[key] = mod
    return _cache[key]


def seed_sha(sid):
    return sums()[SEED_FILES[sid]]


def harness_sha():
    return sums()["hunt/harness.py"]
