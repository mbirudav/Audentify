"""Fuzzy-matching tests (Phase 3). The highest-value UNIT test in the codebase: confidence
thresholds and false-positive avoidance. TDD this with synthetic data before any scraper
exists — telling someone they leak money when they don't is the worst failure mode.

Placeholder until matching.py is implemented in Phase 3.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 3: implement matching.py first (TDD here).")


def test_exact_title_is_high_confidence():
    ...


def test_near_miss_is_flagged_not_asserted():
    ...
