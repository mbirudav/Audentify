"""Stage 2 tests (Phase 3). Registration-gap checks with provenance.

Placeholder until adapters land. Key contract to test: a COMPOSITION adapter must report
UNRESOLVED (not NOT_FOUND) when the work is missing — never assert a gap we can't check.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 3: implement base_adapter + one registry first.")


def test_composition_adapter_unresolved_without_work():
    ...


def test_gap_claim_stores_provenance():
    ...
