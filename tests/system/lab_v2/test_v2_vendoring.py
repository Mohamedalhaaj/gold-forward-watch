"""Vendoring (§2.1, §4): the hunt harness and the four seeds are byte-identical copies of xauusd-quant at the pinned
commit, checked by sha256; the registry files are exactly the rebuilt records; the FROZEN_V2 manifest covers every
frozen file and v1's manifest is untouched."""
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

import frozen_hashes
import v2_data
import v2_frozen
import v2_registry
import v2_signals

ROOT = Path(__file__).resolve().parents[3]
VENDOR = ROOT / "analysis/system/lab_v2/vendor"
XQ = Path(os.environ.get("XAUUSD_QUANT", Path.home() / "Documents/xauusd-quant"))
PINNED = {  # sha256 at xauusd-quant 074e6b8 (research/hunt/...)
    "hunt/harness.py": "f9208d01ae9fafd8c907d72fa26170bd48490c110c6b7a102ef9f71765ebb4fc",
    "hunt/candidates/levels__watched_level_break.py":
        "b068c6d87ade2eda20e715d1ba5e4f75f0cf97042053ff22a3bbdf15a9465e7f",
    "hunt/candidates/r3_ctaflow__cta_flip_flow_usmorning.py":
        "5a17b57dd2a34d62a276fff87a66426e4727dbd9dae5d3e715c9548f33812800",
    "hunt/candidates/r2_orb__inplay_comex_orb60.py":
        "99e5426f9a520ee9cb41b18b914c1671f4fc5fe75b517097901f159508361c1c",
    "hunt/candidates/r2_exhaustion__databar_stretch_settle.py":
        "b0854354566bd18d0fa035fc66222bf632a2b7b68ca8ab485af22c15bc4fcf1a",
}
V1_MANIFEST_SHA = "8f2095c4f0680857d6aa93e5cca5d2b0dcd7bfcec883b1c22da942792b41afe8"   # at lab-v1-freeze 6cd6d57


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_vendored_files_match_the_pins_and_sha256sums():
    sums = dict(line.split()[::-1] for line in (VENDOR / "SHA256SUMS").read_text().splitlines())
    assert sums == PINNED
    for rel, digest in PINNED.items():
        assert sha(VENDOR / rel) == digest, rel
    assert v2_frozen.vendor_check() == []


@pytest.mark.skipif(not (XQ / ".git").exists(), reason="xauusd-quant checkout not available")
def test_vendored_files_are_byte_identical_to_xauusd_quant_at_the_pinned_commit():
    for rel, digest in PINNED.items():
        src = "research/hunt/" + rel.split("hunt/", 1)[1]
        body = subprocess.run(["git", "-C", str(XQ), "show", f"{v2_registry.SOURCE_COMMIT}:{src}"],
                              capture_output=True, check=True).stdout
        assert hashlib.sha256(body).hexdigest() == digest, src
        assert body == (VENDOR / rel).read_bytes()


def test_seeds_have_the_prereg_tf_and_hold():
    want = {"S2": ("M5", 24), "S3": ("M15", 8), "S4": ("M5", 48), "S5": ("M15", 14)}
    for sid, (tf, hold) in want.items():
        mod = v2_signals.load_seed(sid)
        assert (mod.TF, mod.HOLD) == (tf, hold)
    assert v2_data.harness()._bars.__code__.co_filename == str(v2_data.HARNESS_PATH)


def test_registry_files_are_the_rebuilt_records():
    reg = ROOT / v2_registry.REG_REL
    assert v2_registry.verify(reg, ROOT) == []
    recs = v2_registry.load(reg)
    assert [r["id"] for r in recs] == ["S2", "S3", "S4", "S5"]
    for r in recs:
        assert r["seed_sha256"] == PINNED["hunt/candidates/" + Path(r["seed_file"]).name]
        assert r["harness_sha256"] == PINNED["hunt/harness.py"]


def test_a_tampered_registry_file_fails_verification(tmp_path):
    import json
    import shutil
    reg = tmp_path / "registry"
    shutil.copytree(ROOT / v2_registry.REG_REL, reg, ignore=shutil.ignore_patterns("events.csv"))
    rec = json.loads((reg / "S4.json").read_text())
    rec["gamma_exact"] = "3/10"
    (reg / "S4.json").write_text(json.dumps(rec))
    bad = v2_registry.verify(reg, ROOT)
    assert any("S4" in b for b in bad) and any("gamma sums" in b for b in bad)


def test_frozen_v2_manifest_covers_the_frozen_files_and_v1_is_untouched():
    assert v2_frozen.check() == []
    listed = [ln.split(maxsplit=1)[1] for ln in v2_frozen.MANIFEST.read_text().splitlines()]
    assert listed == v2_frozen.FROZEN_V2_FILES
    for f in ("v2_data.py", "v2_signals.py", "v2_exec.py", "v2_ledger.py", "v2_registry.py", "v2paths.py"):
        assert f"analysis/system/lab_v2/{f}" in listed
    for f in ("run_v2.py", "v2_publish.py", "v2_lookback.py", "v2_synth.py", "v2_frozen.py"):
        assert f"analysis/system/lab_v2/{f}" not in listed           # OPS
    assert frozen_hashes.check() == [] and frozen_hashes.vendor_check() == []
    assert sha(frozen_hashes.MANIFEST) == V1_MANIFEST_SHA              # v1's manifest is never edited (§2.5 item 1)


def test_a_frozen_v2_mismatch_is_reported(tmp_path):
    import shutil
    for f in v2_frozen.FROZEN_V2_FILES:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / f, tmp_path / f)
    shutil.copyfile(v2_frozen.MANIFEST, tmp_path / "manifest")
    assert v2_frozen.check(tmp_path, tmp_path / "manifest") == []
    p = tmp_path / "analysis/system/lab_v2/v2_exec.py"
    p.write_text(p.read_text() + "\n# edited\n")
    assert v2_frozen.check(tmp_path, tmp_path / "manifest") == [
        "analysis/system/lab_v2/v2_exec.py: sha256 differs from FROZEN_V2.sha256"]
