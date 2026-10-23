import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def base(tmp_path_factory):
    """The full synthetic world (canary and live), built once per session (it takes most of the suite's time)."""
    from world import World
    return World(str(tmp_path_factory.mktemp("world") / "w")).build()


@pytest.fixture
def w(base, tmp_path):
    """A copy of the built world, for a post-hoc tamper."""
    return base.clone(str(tmp_path / "copy"))
