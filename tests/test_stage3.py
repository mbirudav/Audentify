"""Stage 3 tests (Phase 2). Per-royalty-type estimate as a range.

Placeholder until calculator.py lands. Key contracts to test: per-royalty-type (not one
flat formula), output is a range, and the rate comes from the versioned RateCard table
(reproducible at its effective version) — never hardcoded.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 2: implement calculator.py first.")


def test_estimate_is_a_range_per_royalty_type():
    ...


def test_estimate_uses_versioned_rate():
    ...
