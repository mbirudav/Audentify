"""Data-model tests. The splits-sum-to-100 rule is the highest-value check at Phase 0 —
Postgres can't enforce a cross-row sum cleanly, so the app must, and a wrong split silently
corrupts every downstream estimate.

These run WITHOUT a database (they exercise the pure validation helpers). DB-level
constraint tests (the Split XOR check, enum types) come with a test-DB fixture later.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.models import (
    Base,
    RawRegistryResponse,
    RateCard,
    RegistrationCheck,
    assert_splits_sum_to_100,
    splits_sum_to_100,
)


def test_models_import_and_register():
    # All tables register on the shared metadata (catches a missing __tablename__, etc.).
    tables = set(Base.metadata.tables)
    assert {
        "parties",
        "works",
        "recordings",
        "splits",
        "registration_checks",
        "raw_registry_responses",
        "rate_cards",
    } <= tables
    # Sanity: the Phase 2/3 tables exist as classes too.
    assert RegistrationCheck.__tablename__ == "registration_checks"
    assert RawRegistryResponse.__tablename__ == "raw_registry_responses"
    assert RateCard.__tablename__ == "rate_cards"


def test_splits_sum_exact_100():
    assert splits_sum_to_100([Decimal("50"), Decimal("50")])
    assert splits_sum_to_100([Decimal("100")])


def test_splits_sum_rounding_within_tolerance():
    # Three-way split rounds to 100.00 within the ±0.01 tolerance.
    assert splits_sum_to_100([Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])


def test_splits_sum_rejects_under_and_over():
    assert not splits_sum_to_100([Decimal("50"), Decimal("49")])
    assert not splits_sum_to_100([Decimal("60"), Decimal("60")])


def test_empty_splits_is_invalid():
    # "No splits" is not a fully-owned parent.
    assert not splits_sum_to_100([])


def test_assert_raises_on_bad_sum():
    with pytest.raises(ValueError):
        assert_splits_sum_to_100([Decimal("50"), Decimal("40")])


def test_assert_passes_on_good_sum():
    assert_splits_sum_to_100([Decimal("25"), Decimal("25"), Decimal("50")])  # no raise


def test_splits_accept_floats_too():
    assert splits_sum_to_100([33.33, 33.33, 33.34])
