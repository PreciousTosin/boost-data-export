"""Shared pytest fixtures."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

# The sample dataset supplied with the brief lives in examples/ so the demo
# script can use it too. It's loaded by path because examples/ is not a package.
SAMPLE_DATA_PATH = Path(__file__).resolve().parents[1] / "examples" / "data.py"


@pytest.fixture(scope="session")
def sample_data() -> list[dict[str, Any]]:
    """The ~1,000-row dataset from the brief.

    Session-scoped (loaded once) for speed. Tests must treat it as read-only:
    mutating it would leak state into other tests.
    """
    spec = importlib.util.spec_from_file_location("sample_data", SAMPLE_DATA_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data: list[dict[str, Any]] = module.data
    return data


class FakeClock:
    """A controllable clock for TTL tests: time only moves when we say so."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
