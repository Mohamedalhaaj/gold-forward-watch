"""Shared setup for the system tests: the system modules and the vendored volmap on sys.path."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "system"))
import syspath  # noqa: E402,F401

pytest.FIXTURES = Path(__file__).resolve().parent / "fixtures"
pytest.ROOT = ROOT


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long Monte Carlo checks (run by default; deselect with -m 'not slow')")
