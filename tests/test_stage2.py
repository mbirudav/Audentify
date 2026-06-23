"""Stage 2 tests (Phase 3). Registration-gap checks with provenance — NO network.

Every adapter is fed a fixture-backed raw response (constructor-injected RawResponse), so
nothing here touches the network. The provenance test uses an in-memory SQLite session.

Key contracts pinned:
  * a COMPOSITION adapter with no work identity -> UNRESOLVED (never NOT_FOUND);
  * every result carries provenance, and with a session a raw_response_id points at a
    persisted RawRegistryResponse row;
  * a HIGH match -> REGISTERED; no candidate -> NOT_FOUND; a near-miss -> AMBIGUOUS;
  * SoundExchange's self-report toggle maps None/True/False -> UNRESOLVED/REGISTERED/NOT_FOUND.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, RawRegistryResponse
from app.domain import (
    ConfidenceBand,
    CopyrightSide,
    RegistrationStatus,
    RegistryName,
)
from app.pipeline.stage2_gaps.ascap import ASCAPAdapter
from app.pipeline.stage2_gaps.base_adapter import RawResponse
from app.pipeline.stage2_gaps.bmi import BMIAdapter
from app.pipeline.stage2_gaps.mlc import MLCAdapter
from app.pipeline.stage2_gaps.soundexchange import SoundExchangeAdapter
from tests.factories import load_fixture, make_identity


@pytest.fixture
def db_session():
    """An in-memory SQLite session with the schema created. No network, no Postgres."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _mlc_raw() -> RawResponse:
    return RawResponse(
        body=load_fixture("mlc_work_search.json"),
        url="https://api.themlc.com/v1/works/search",
        params={"isrc": "US-S1Z-99-00001"},
        status_code=200,
    )


# --- Degrade gracefully: composition side with no work --------------------------------


@pytest.mark.parametrize("adapter_cls", [MLCAdapter, ASCAPAdapter, BMIAdapter])
def test_composition_adapter_unresolved_without_work(adapter_cls, identity_without_work):
    # A composition-side adapter cannot check without a work identity. It MUST report
    # UNRESOLVED — never NOT_FOUND (asserting a gap we can't actually check is the worst
    # outcome). ISRC does not join the composition side.
    adapter = adapter_cls()
    result = adapter.check(identity_without_work)

    assert result.status is RegistrationStatus.UNRESOLVED
    assert result.status is not RegistrationStatus.NOT_FOUND
    assert result.registry is adapter_cls.registry
    assert result.side is CopyrightSide.COMPOSITION
    assert result.checked_at is not None


# --- Provenance on every claim --------------------------------------------------------


def test_gap_claim_stores_provenance(db_session, identity_with_work):
    adapter = MLCAdapter(session=db_session, injected_raw=_mlc_raw())
    result = adapter.check(identity_with_work)

    # Provenance fields present on the result.
    assert result.registry is RegistryName.MLC
    assert result.side is CopyrightSide.COMPOSITION
    assert result.status is not None
    assert result.checked_at is not None
    assert result.raw_response_id is not None

    # The id points at a persisted RawRegistryResponse row with a content hash (evidence).
    row = db_session.get(RawRegistryResponse, result.raw_response_id)
    assert row is not None
    assert row.registry is RegistryName.MLC
    assert row.response_body  # the raw body is captured
    assert row.content_hash and len(row.content_hash) == 64  # sha256 hex digest


def test_no_session_skips_persistence_but_still_valid(identity_with_work):
    # Without a session we still return a valid, checked result — just no raw_response_id.
    adapter = MLCAdapter(injected_raw=_mlc_raw())
    result = adapter.check(identity_with_work)
    assert result.raw_response_id is None
    assert result.checked_at is not None
    assert result.status is RegistrationStatus.REGISTERED


# --- Found / not-found / ambiguous mapping --------------------------------------------


def test_found_match_is_registered_high(identity_with_work):
    # The fixture's first work is exactly "Test Track" -> HIGH -> REGISTERED.
    adapter = MLCAdapter(injected_raw=_mlc_raw())
    result = adapter.check(identity_with_work)

    assert result.status is RegistrationStatus.REGISTERED
    assert result.confidence_band is ConfidenceBand.HIGH
    assert result.confidence_score is not None and result.confidence_score >= 0.9
    assert result.matched_identifier == "T-123.456.789-0"


def test_no_candidate_is_not_found(identity_with_work):
    # An empty result set -> checked, nothing matched -> NOT_FOUND (a candidate leak).
    empty_raw = RawResponse(body='{"results": []}', status_code=200)
    adapter = MLCAdapter(injected_raw=empty_raw)
    result = adapter.check(identity_with_work)

    assert result.status is RegistrationStatus.NOT_FOUND
    assert result.matched_identifier is None


def test_near_miss_is_ambiguous_not_a_gap():
    # The registry only has a near-miss title; the work we're checking is "Midnight City".
    # A near-miss must come back AMBIGUOUS (flag a human) — NOT REGISTERED, NOT NOT_FOUND.
    identity = make_identity(work=_work_titled("Midnight City"))
    near_miss_raw = RawResponse(
        body='{"results": [{"workTitle": "Midnight City Lights", "iswc": "T-000.000.000-0"}]}',
        status_code=200,
    )
    adapter = MLCAdapter(injected_raw=near_miss_raw)
    result = adapter.check(identity)

    assert result.status is RegistrationStatus.AMBIGUOUS
    assert result.status is not RegistrationStatus.REGISTERED
    assert result.status is not RegistrationStatus.NOT_FOUND
    assert result.confidence_band is not ConfidenceBand.HIGH


# --- ASCAP (HTML) and BMI (JSON) parse their own fixtures -----------------------------


def test_ascap_parses_html_fixture(identity_with_work):
    raw = RawResponse(body=load_fixture("ascap_repertory_search.html"), status_code=200)
    result = ASCAPAdapter(injected_raw=raw).check(identity_with_work)
    assert result.status is RegistrationStatus.REGISTERED
    assert result.matched_identifier == "T-123.456.789-0"


def test_bmi_parses_json_fixture(identity_with_work):
    raw = RawResponse(body=load_fixture("bmi_repertoire_search.json"), status_code=200)
    result = BMIAdapter(injected_raw=raw).check(identity_with_work)
    assert result.status is RegistrationStatus.REGISTERED
    assert result.matched_identifier == "T-123.456.789-0"


# --- SoundExchange self-report toggle -------------------------------------------------


@pytest.mark.parametrize(
    ("self_reported", "expected"),
    [
        (None, RegistrationStatus.UNRESOLVED),
        (True, RegistrationStatus.REGISTERED),
        (False, RegistrationStatus.NOT_FOUND),
    ],
)
def test_soundexchange_self_report_mapping(self_reported, expected, identity_with_work):
    adapter = SoundExchangeAdapter(self_reported_registered=self_reported)
    result = adapter.check(identity_with_work)

    assert result.status is expected
    assert result.side is CopyrightSide.MASTER
    assert result.checked_at is not None
    if expected is not RegistrationStatus.UNRESOLVED:
        # provenance: the claim is sourced from the self-report, keyed on the ISRC.
        assert "self-report" in (result.notes or "")
        assert result.matched_identifier == identity_with_work.recording.isrc


# --- helpers --------------------------------------------------------------------------


def _work_titled(title: str):
    from tests.factories import make_work

    return make_work(title=title)
