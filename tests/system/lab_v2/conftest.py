"""Shared setup for the lab v2 tests (SYSTEM_V2_PREREG.md §4): the v2 modules on sys.path, and one synthetic world
(v1's synth.world from 2026-09-01 plus v2_synth's lookback) shared by the tests that only read it."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "analysis" / "system" / "lab_v2"))
import v2paths  # noqa: E402,F401

FIXTURE = ROOT / "tests" / "judge_fixtures" / "synthetic_world"


@pytest.fixture(scope="session")
def world(tmp_path_factory):
    """A synthetic raw world (no runs): data/system (v1, 2026-09-01 .. 2026-12-04) and the v2 lookback."""
    import run_v2
    base = tmp_path_factory.mktemp("v2_world")
    P = run_v2.Paths(base)
    run_v2.setup_synthetic(P)
    return P
