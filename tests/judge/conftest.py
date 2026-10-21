"""Shared paths for the judge's tests. Nothing here reads analysis/system/** source code."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/judge_fixtures/synthetic_world"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def root():
    return ROOT


@pytest.fixture(scope="session")
def fixture_world():
    return FIXTURE
