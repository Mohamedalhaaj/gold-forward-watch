"""Independence (SYSTEM_V2_PREREG.md §3.1): judge/ imports nothing from analysis/ and executes no system code; it
vendors only the frozen research model and the hunt seeds plus harness, all sha-checked."""
import ast
import sys
from pathlib import Path

from judge import vendored

ROOT = Path(__file__).resolve().parents[2]
JUDGE = ROOT / "judge"
# the only analysis/ paths the judge may name: data files and manifests it reads or hashes, never executes
ALLOWED_ANALYSIS_STRINGS = {
    "analysis/system/FROZEN.sha256",
    "analysis/system/lab_v2/FROZEN_V2.sha256",
    "analysis/system/vendor/calendars",
}
VENDOR_EXPECTED = {
    "volmap/core.py", "volmap/models.py", "volmap/frozen/discovery_params.json", "hunt/harness.py",
    "hunt/candidates/levels__watched_level_break.py", "hunt/candidates/r3_ctaflow__cta_flip_flow_usmorning.py",
    "hunt/candidates/r2_orb__inplay_comex_orb60.py", "hunt/candidates/r2_exhaustion__databar_stretch_settle.py",
    "calendars/bls_2026_2027.csv", "calendars/fomc_2026_2027.csv",          # R-V1-15 (lab review MF5)
}


def own_sources():
    return [p for p in JUDGE.rglob("*.py") if "vendor" not in p.relative_to(JUDGE).parts]


def test_no_import_of_system_code():
    for p in own_sources():
        tree = ast.parse(p.read_text(), str(p))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert not a.name.split(".")[0] in ("analysis", "run_v2", "v2_data", "lab"), (p, a.name)
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("analysis"), (p, mod)
                if node.level == 0:
                    assert mod.split(".")[0] not in ("analysis",), (p, mod)
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                assert name not in ("exec", "eval", "run_path", "run_module", "import_module"), (p, name)


def test_analysis_paths_are_only_data_files():
    for p in own_sources():
        for node in ast.walk(ast.parse(p.read_text(), str(p))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "analysis" in node.value:
                v = node.value
                if any(ch.isspace() for ch in v):
                    continue            # prose (docstrings, messages), not a path
                assert v in ALLOWED_ANALYSIS_STRINGS, (p, v)


def test_modules_are_loaded_only_from_the_vendor_folder():
    for p in own_sources():
        src = p.read_text()
        if "spec_from_file_location" in src:
            assert p.name == "vendored.py", p
    assert "subprocess" not in (JUDGE / "recompute.py").read_text()
    for p in own_sources():
        src = p.read_text()
        if "subprocess" in src:
            assert p.name == "gitio.py", p      # git only


def test_vendored_files_are_exactly_the_allowed_set_and_match_their_sums():
    assert set(vendored.sums()) == VENDOR_EXPECTED
    assert vendored.check() == []
    # the same sha256 values as the lab v2 registry records state (R-V2-2) and the volmap discovery params (L2 §3.3)
    sums = vendored.sums()
    assert sums["hunt/harness.py"].startswith("f9208d01")
    assert sums["hunt/candidates/levels__watched_level_break.py"].startswith("b068c6d8")
    assert sums["hunt/candidates/r3_ctaflow__cta_flip_flow_usmorning.py"].startswith("5a17b57d")
    assert sums["hunt/candidates/r2_orb__inplay_comex_orb60.py"].startswith("99e5426f")
    assert sums["hunt/candidates/r2_exhaustion__databar_stretch_settle.py"].startswith("b0854354")
    assert sums["volmap/frozen/discovery_params.json"].startswith("1182acf5")
    # the calendars: the register's sha256 values (R-V1-15)
    assert sums["calendars/bls_2026_2027.csv"] == "7e829d6c5acd861c276552d4086a2c639cbec03fc66242b859cd9d4fabdef45d"
    assert sums["calendars/fomc_2026_2027.csv"] == "dd709aee9821d0e1b4a1e9e0a8939422e92bb9520961090e31e96f4d30dc10f5"


def test_runtime_loads_no_module_from_analysis():
    vendored.volmap()
    for sid in ("S2", "S3", "S4", "S5"):
        vendored.seed(sid)
    for name, m in list(sys.modules.items()):
        f = getattr(m, "__file__", None) or ""
        assert "/analysis/" not in f.replace("\\", "/"), (name, f)


def test_frozen_judge_manifest_is_current_and_the_v1_pin_is_the_prereg_value():
    import json
    from judge import checks, manifests
    cur = manifests.parse((JUDGE / "FROZEN_JUDGE.sha256").read_text())
    live = manifests.parse(checks.judge_manifest_text(ROOT))
    assert cur == live, "run `uv run --frozen python -I judge/run.py --write-manifest` after changing judge code"
    assert ".github/workflows/judge.yml" in cur and "judge/run.py" in cur and "judge/vendor/hunt/harness.py" in cur
    pins = json.loads((JUDGE / "FROZEN_PINS.json").read_text())
    assert pins["lab-v1-freeze"] == "6cd6d57ef62d8eb8710dd5151c7b5ddc2612d095"     # SYSTEM_V2_PREREG.md §3.1
    assert set(pins) >= {"lab-v1-freeze", "lab-v2-freeze", "judge-v1-freeze"}
