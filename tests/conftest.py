"""Pytest fixtures shared across the suite.

Thin wrappers over `tests/factories.py` so a test can take `identity_with_work` /
`identity_without_work` as arguments, plus a `fixtures_dir` path. The plain builder
functions in `factories.py` are also importable directly — use whichever reads cleaner.

DB-backed sessions (for the RateCard / provenance tables) are created per-test with an
in-memory SQLite engine inside the test that needs them — kept out of here so the unit
tests that need no DB stay DB-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.identity import IdentityResult
from tests.factories import FIXTURES_DIR, make_identity


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def identity_with_work() -> IdentityResult:
    """A fully resolved identity (recording + work). Composition checks can run."""
    return make_identity(with_work=True)


@pytest.fixture
def identity_without_work() -> IdentityResult:
    """Recording resolved, work UNRESOLVED — composition checks must degrade to
    UNRESOLVED (never assert a gap)."""
    return make_identity(with_work=False)
