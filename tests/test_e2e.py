"""End-to-end test of the core loop (Phase 4) through services/audit.run_audit — NO network.

The whole loop runs offline: an in-memory SQLite session (seeded via seed_rate_cards), a
manual TrackInput driving Stage 1, and fixture-backed Stage 2 adapters injected directly.
This pins the integration contract the orchestrator must hold:

  * identity carries BOTH copyrights (recording + work) — the manual-ISWC fallback populates
    the work side so composition checks have something to join on;
  * the registration map has >=1 REGISTERED registry end-to-end (MLC off the fixture, plus
    SoundExchange off the self-report toggle — the one registry that works fully offline);
  * a composition adapter with work=None degrades to UNRESOLVED (never NOT_FOUND): a separate
    run_audit WITHOUT an iswc proves the no-work path is flagged, not asserted as a gap;
  * the estimate is a real low<=high RANGE.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.domain import RegistrationStatus
from app.pipeline.stage2_gaps.base_adapter import RawResponse
from app.pipeline.stage2_gaps.mlc import MLCAdapter
from app.pipeline.stage2_gaps.soundexchange import SoundExchangeAdapter
from app.pipeline.stage3_estimate.calculator import RateCardEstimator
from app.rates.loader import seed_rate_cards
from app.schemas.audit import AuditRequest
from app.schemas.estimate import RoyaltyAssumptions
from app.schemas.identity import TrackInput
from app.services.audit import run_audit
from tests.factories import load_fixture

# The manual track that drives Stage 1 entirely offline. The ISRC matches the MLC fixture's
# query; the ISWC triggers the orchestrator's manual-work fallback so composition checks run.
_TITLE = "Test Track"
_ISRC = "US-S1Z-99-00001"
_ISWC = "T-123.456.789-0"


@pytest.fixture
def session() -> Session:
    """In-memory SQLite with the schema created and the RateCard table seeded. No network."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_rate_cards(s)
        s.flush()
        yield s
    engine.dispose()


def _assumptions() -> RoyaltyAssumptions:
    from app.domain import RoyaltyType

    return RoyaltyAssumptions(
        annual_volume={
            RoyaltyType.MECHANICAL: 1_000_000,
            RoyaltyType.PERFORMANCE: 1_000_000,
            RoyaltyType.DIGITAL_PERFORMANCE: 50_000,
        }
    )


def _mlc_raw() -> RawResponse:
    return RawResponse(
        body=load_fixture("mlc_work_search.json"),
        url="https://api.themlc.com/v1/works/search",
        params={"isrc": _ISRC},
        status_code=200,
    )


def test_e2e_full_loop_offline(session: Session):
    """The happy path: manual identity + work, fixture-backed checks, a seeded estimate."""
    request = AuditRequest(
        track=TrackInput(title=_TITLE, isrc=_ISRC, iswc=_ISWC),
        assumptions=_assumptions(),
    )

    # Fixture-backed Stage 2: MLC off the captured fixture (-> REGISTERED) and SoundExchange
    # off the self-report toggle (-> REGISTERED). Both offline; no network, no live adapters.
    checkers = [
        MLCAdapter(session=session, injected_raw=_mlc_raw()),
        SoundExchangeAdapter(self_reported_registered=True, session=session),
    ]

    response = run_audit(
        request,
        checkers=checkers,
        estimator=RateCardEstimator(session),
        session=session,  # injected -> run_audit must NOT close it
    )

    # --- Identity: BOTH copyrights resolved offline -----------------------------------
    assert response.identity.recording.title == _TITLE
    assert response.identity.recording.isrc == _ISRC
    assert response.identity.recording.source == "manual"
    assert response.identity.work is not None  # manual-ISWC fallback populated the work side
    assert response.identity.work.iswc == _ISWC
    assert response.identity.work.source == "manual"

    # --- Registration map: >=1 REGISTERED registry end-to-end -------------------------
    statuses = {r.registry: r.status for r in response.gaps.checks}
    registered = [
        r for r in response.gaps.checks if r.status is RegistrationStatus.REGISTERED
    ]
    assert len(registered) >= 1
    # Specifically: the MLC fixture is a HIGH match, and SoundExchange self-report = True.
    from app.domain import RegistryName

    assert statuses[RegistryName.MLC] is RegistrationStatus.REGISTERED
    assert statuses[RegistryName.SOUNDEXCHANGE] is RegistrationStatus.REGISTERED

    # --- Estimate: a real low <= high range -------------------------------------------
    assert response.estimate.total_low <= response.estimate.total_high
    assert response.estimate.line_items  # the seeded rates produced line items
    for li in response.estimate.line_items:
        assert li.low <= li.high

    # The injected session must still be usable (run_audit didn't close it).
    assert session.is_active


def test_e2e_backfills_user_iswc_when_resolver_returns_none(session: Session):
    """A resolver can return a work WITH writers but NO ISWC (common in MusicBrainz). When the
    user supplied an ISWC on the TrackInput, the orchestrator must backfill it onto the
    resolved work (without dropping the writers) so composition checks keep an identifier."""
    from app.schemas.identity import WorkResult
    from tests.factories import make_party

    class _ResolverNoISWC:
        source = "musicbrainz"

        def resolve_work(self, recording):
            return WorkResult(
                title=recording.title, iswc=None, writers=[make_party()], source="musicbrainz"
            )

    request = AuditRequest(
        track=TrackInput(title=_TITLE, isrc=_ISRC, iswc=_ISWC),
        assumptions=_assumptions(),
    )
    response = run_audit(
        request,
        work_resolver=_ResolverNoISWC(),
        checkers=[],  # no gap checks needed for this assertion
        estimator=RateCardEstimator(session),
        session=session,
    )

    assert response.identity.work is not None
    assert response.identity.work.iswc == _ISWC  # backfilled from the TrackInput
    assert response.identity.work.writers  # the resolver's writers were preserved


def test_e2e_no_work_yields_unresolved_composition_checks(session: Session):
    """Without an ISWC the work can't be resolved offline, so a composition adapter must
    degrade to UNRESOLVED (never NOT_FOUND) — we never assert a gap we couldn't check."""
    request = AuditRequest(
        track=TrackInput(title=_TITLE, isrc=_ISRC),  # NO iswc -> no manual-work fallback
        assumptions=_assumptions(),
    )

    # A composition-side adapter; with identity.work None the base check() returns UNRESOLVED.
    checkers = [MLCAdapter(session=session, injected_raw=_mlc_raw())]

    response = run_audit(
        request,
        checkers=checkers,
        estimator=RateCardEstimator(session),
        session=session,
    )

    from app.domain import RegistryName

    assert response.identity.work is None
    (mlc,) = response.gaps.checks
    assert mlc.status is RegistrationStatus.UNRESOLVED
    assert mlc.status is not RegistrationStatus.NOT_FOUND
    # GapReport.unresolved surfaces it so the UI flags "couldn't check", not "no gap".
    assert RegistryName.MLC in response.gaps.unresolved
