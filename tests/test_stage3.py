"""Stage 3 tests (Phase 2). Per-royalty-type estimate as a range.

Key contracts under test: per-royalty-type (not one flat formula), output is a RANGE, the
rate comes from the versioned RateCard table (reproducible at its effective version, never
hardcoded), the seed loader is idempotent, and gaps drive the leak framing.

All DB work is an in-memory SQLite engine created per test — no live DB, no network.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, RateCard
from app.domain import (
    ConfidenceBand,
    CopyrightSide,
    RegistrationStatus,
    RegistryName,
    RoyaltyType,
)
from app.pipeline.stage3_estimate.calculator import RateCardEstimator
from app.rates.loader import seed_rate_cards
from app.schemas.estimate import RoyaltyAssumptions
from app.schemas.gaps import RegistrationResult
from tests.factories import make_identity


@pytest.fixture
def session() -> Session:
    """A fresh in-memory SQLite DB with the schema created. No live DB needed."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _add_rate(
    session: Session,
    *,
    royalty_type: RoyaltyType,
    registry: RegistryName | None,
    version: str,
    rate: str,
    unit: str = "per_stream",
    effective_date: dt.date = dt.date(2024, 1, 1),
) -> None:
    session.add(
        RateCard(
            royalty_type=royalty_type,
            registry=registry,
            version=version,
            effective_date=effective_date,
            rate=Decimal(rate),
            unit=unit,
            currency="USD",
        )
    )
    session.flush()


def _gap(
    registry: RegistryName, status: RegistrationStatus, side: CopyrightSide
) -> RegistrationResult:
    return RegistrationResult(
        registry=registry,
        side=side,
        status=status,
        confidence_band=ConfidenceBand.HIGH,
    )


def test_estimate_is_a_range_per_royalty_type(session: Session):
    """One line item per royalty type that has volume, and each is a real range (low <= high
    and not a degenerate point)."""
    _add_rate(
        session, royalty_type=RoyaltyType.MECHANICAL, registry=RegistryName.MLC,
        version="v1", rate="0.0005",
    )
    _add_rate(
        session, royalty_type=RoyaltyType.PERFORMANCE, registry=RegistryName.ASCAP,
        version="v1", rate="0.0003",
    )
    _add_rate(
        session, royalty_type=RoyaltyType.DIGITAL_PERFORMANCE,
        registry=RegistryName.SOUNDEXCHANGE, version="v1", rate="0.0010", unit="per_play",
    )

    assumptions = RoyaltyAssumptions(
        annual_volume={
            RoyaltyType.MECHANICAL: 1_000_000,
            RoyaltyType.PERFORMANCE: 1_000_000,
            RoyaltyType.DIGITAL_PERFORMANCE: 50_000,
        }
    )
    est = RateCardEstimator(session)
    result = est.estimate(make_identity(), assumptions, gaps=[])

    # Exactly one line item per royalty type that had volume.
    assert {li.royalty_type for li in result.line_items} == set(assumptions.annual_volume)
    assert len(result.line_items) == 3

    for li in result.line_items:
        assert li.low <= li.high
        # A real band, not a point: high strictly exceeds low for a non-zero estimate.
        assert li.high > li.low
        # Assumptions are exposed for the UI.
        assert "rate" in li.assumptions
        assert "band" in li.assumptions
        assert "annual_volume" in li.assumptions

    # PERFORMANCE carries the pooled/survey approximation note.
    perf = next(li for li in result.line_items if li.royalty_type == RoyaltyType.PERFORMANCE)
    assert "approximation_note" in perf.assumptions


def test_estimate_band_formula_is_symmetric():
    """Sanity-check the exact range math against the documented formula."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_rate(
            session, royalty_type=RoyaltyType.MECHANICAL, registry=RegistryName.MLC,
            version="v1", rate="0.0005",
        )
        assumptions = RoyaltyAssumptions(
            annual_volume={RoyaltyType.MECHANICAL: 1_000_000}
        )
        est = RateCardEstimator(session, band=Decimal("0.30"))
        result = est.estimate(make_identity(), assumptions, gaps=[])

        (li,) = result.line_items
        point = Decimal("1000000") * Decimal("0.0005")  # = 500
        assert li.low == point * Decimal("0.70")
        assert li.high == point * Decimal("1.30")


def test_performance_rate_blends_across_pros(session: Session):
    """PERFORMANCE spans multiple PROs (ASCAP + BMI). The estimate must blend their rates
    (mean), not arbitrarily pick whichever row was inserted last."""
    _add_rate(
        session, royalty_type=RoyaltyType.PERFORMANCE, registry=RegistryName.ASCAP,
        version="v1", rate="0.0002",
    )
    _add_rate(
        session, royalty_type=RoyaltyType.PERFORMANCE, registry=RegistryName.BMI,
        version="v1", rate="0.0004",
    )
    est = RateCardEstimator(session)
    result = est.estimate(
        make_identity(),
        RoyaltyAssumptions(annual_volume={RoyaltyType.PERFORMANCE: 1_000_000}),
        gaps=[],
    )
    (li,) = result.line_items
    # Mean of 0.0002 and 0.0004 is 0.0003 -> point = 1,000,000 * 0.0003 = 300.
    assert Decimal(li.assumptions["rate"]) == Decimal("0.0003")
    assert li.low == Decimal("300") * Decimal("0.70")
    assert li.high == Decimal("300") * Decimal("1.30")
    # Transparent about the blend.
    assert li.assumptions["rate_blended_across"] == "ascap, bmi"


def test_estimate_uses_versioned_rate(session: Session):
    """Two rate versions for the same royalty type. Pinning the version changes the figure
    AND stamps the line item with that version — proving the rate is read from the versioned
    table, not a literal."""
    _add_rate(
        session, royalty_type=RoyaltyType.MECHANICAL, registry=RegistryName.MLC,
        version="2023", rate="0.0004", effective_date=dt.date(2023, 1, 1),
    )
    _add_rate(
        session, royalty_type=RoyaltyType.MECHANICAL, registry=RegistryName.MLC,
        version="2024", rate="0.0006", effective_date=dt.date(2024, 1, 1),
    )

    est = RateCardEstimator(session)

    pinned_2023 = est.estimate(
        make_identity(),
        RoyaltyAssumptions(
            annual_volume={RoyaltyType.MECHANICAL: 1_000_000}, rate_version="2023"
        ),
        gaps=[],
    )
    pinned_2024 = est.estimate(
        make_identity(),
        RoyaltyAssumptions(
            annual_volume={RoyaltyType.MECHANICAL: 1_000_000}, rate_version="2024"
        ),
        gaps=[],
    )

    (li_2023,) = pinned_2023.line_items
    (li_2024,) = pinned_2024.line_items

    assert li_2023.rate_version == "2023"
    assert li_2024.rate_version == "2024"
    assert li_2023.rate_effective_date == "2023-01-01"
    assert li_2024.rate_effective_date == "2024-01-01"
    # Different versioned rate -> different figure.
    assert li_2023.high != li_2024.high
    assert li_2024.high > li_2023.high  # 0.0006 > 0.0004


def test_estimate_unpinned_uses_latest_effective(session: Session):
    """With no pin, the latest effective_date (<= today) wins."""
    _add_rate(
        session, royalty_type=RoyaltyType.MECHANICAL, registry=RegistryName.MLC,
        version="old", rate="0.0004", effective_date=dt.date(2023, 1, 1),
    )
    _add_rate(
        session, royalty_type=RoyaltyType.MECHANICAL, registry=RegistryName.MLC,
        version="new", rate="0.0006", effective_date=dt.date(2024, 1, 1),
    )
    est = RateCardEstimator(session)
    result = est.estimate(
        make_identity(),
        RoyaltyAssumptions(annual_volume={RoyaltyType.MECHANICAL: 1_000_000}),
        gaps=[],
    )
    (li,) = result.line_items
    assert li.rate_version == "new"


def test_not_found_gap_drives_leak_total_registered_does_not(session: Session):
    """A NOT_FOUND gap makes its royalty type a candidate leak (counts to the total); a
    REGISTERED gap does not."""
    _add_rate(
        session, royalty_type=RoyaltyType.MECHANICAL, registry=RegistryName.MLC,
        version="v1", rate="0.0005",
    )
    _add_rate(
        session, royalty_type=RoyaltyType.PERFORMANCE, registry=RegistryName.ASCAP,
        version="v1", rate="0.0003",
    )

    assumptions = RoyaltyAssumptions(
        annual_volume={
            RoyaltyType.MECHANICAL: 1_000_000,
            RoyaltyType.PERFORMANCE: 1_000_000,
        }
    )
    gaps = [
        # Mechanical (MLC) not found -> candidate leak.
        _gap(RegistryName.MLC, RegistrationStatus.NOT_FOUND, CopyrightSide.COMPOSITION),
        # Performance (ASCAP) registered -> NOT a leak.
        _gap(RegistryName.ASCAP, RegistrationStatus.REGISTERED, CopyrightSide.COMPOSITION),
    ]
    est = RateCardEstimator(session)
    result = est.estimate(make_identity(), assumptions, gaps=gaps)

    mech = next(li for li in result.line_items if li.royalty_type == RoyaltyType.MECHANICAL)
    perf = next(li for li in result.line_items if li.royalty_type == RoyaltyType.PERFORMANCE)

    assert mech.assumptions["counts_toward_total"] == "True"
    assert perf.assumptions["counts_toward_total"] == "False"

    # The total reflects ONLY the mechanical (leaking) line item.
    assert result.total_low == mech.low
    assert result.total_high == mech.high


def test_unresolved_gap_does_not_assert_leak(session: Session):
    """UNRESOLVED means we couldn't check — never assert a leak (excluded from total)."""
    _add_rate(
        session, royalty_type=RoyaltyType.PERFORMANCE, registry=RegistryName.ASCAP,
        version="v1", rate="0.0003",
    )
    assumptions = RoyaltyAssumptions(
        annual_volume={RoyaltyType.PERFORMANCE: 1_000_000}
    )
    gaps = [
        _gap(RegistryName.ASCAP, RegistrationStatus.UNRESOLVED, CopyrightSide.COMPOSITION)
    ]
    est = RateCardEstimator(session)
    result = est.estimate(make_identity(), assumptions, gaps=gaps)

    (li,) = result.line_items
    assert li.assumptions["counts_toward_total"] == "False"
    assert result.total_low == Decimal("0")
    assert result.total_high == Decimal("0")


def test_empty_gaps_estimates_all_and_notes_unchecked(session: Session):
    """No gaps supplied: estimate every type with volume, flag registration as unchecked,
    and treat the total as potential exposure."""
    _add_rate(
        session, royalty_type=RoyaltyType.MECHANICAL, registry=RegistryName.MLC,
        version="v1", rate="0.0005",
    )
    assumptions = RoyaltyAssumptions(
        annual_volume={RoyaltyType.MECHANICAL: 1_000_000}
    )
    est = RateCardEstimator(session)
    result = est.estimate(make_identity(), assumptions, gaps=[])

    (li,) = result.line_items
    assert li.assumptions["registration_checked"] == "False"
    assert result.total_high > 0  # potential exposure surfaced


def test_seed_rate_cards_is_idempotent(session: Session):
    """Running the seeder twice yields the same row count (upsert, no duplicates)."""
    first = seed_rate_cards(session)
    rows_after_first = session.query(RateCard).count()

    second = seed_rate_cards(session)
    rows_after_second = session.query(RateCard).count()

    assert first == second
    assert rows_after_first == rows_after_second
    assert rows_after_first == first  # every seeded row landed exactly once


def test_seeded_rates_are_usable_by_estimator(session: Session):
    """End-to-end: seed from YAML, then the estimator reads those exact rows from the table."""
    seed_rate_cards(session)
    assumptions = RoyaltyAssumptions(
        annual_volume={
            RoyaltyType.MECHANICAL: 1_000_000,
            RoyaltyType.PERFORMANCE: 1_000_000,
            RoyaltyType.DIGITAL_PERFORMANCE: 50_000,
        }
    )
    est = RateCardEstimator(session)
    result = est.estimate(make_identity(), assumptions, gaps=[])
    assert len(result.line_items) == 3
    for li in result.line_items:
        assert li.rate_version == "2024-placeholder"
