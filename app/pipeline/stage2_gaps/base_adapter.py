"""Registry adapter base (Phase 3). The shared concrete base over the GapChecker contract.

RegistryAdapter holds the common plumbing — guard the required copyright side, fetch the raw
response, cache it for provenance, parse it to candidate strings, fuzzy-match with
confidence, and build a provenance-complete RegistrationResult. Concrete adapters implement
only `_query` (get the raw response) and `_parse` (raw -> candidate match strings).

NO live scraping in this build. `_query` is fixture-backed in tests (constructor-inject the
raw response, or a subclass returns one); a live path may exist but MUST sit behind the
http client's `allow_live_network` gate. "public" data is NOT the same as "permitted to
scrape" — registry ToS may forbid automated access (see CLAUDE.md).

Each subclass MUST set `registry` and `keys_on`. A COMPOSITION adapter (keys_on=COMPOSITION)
given `identity.work is None` returns status UNRESOLVED (never NOT_FOUND) — we never assert
a gap we can't actually check, because a false positive is the worst outcome.
"""

from __future__ import annotations

import datetime as dt
from abc import abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from app.cache import store
from app.domain import (
    ConfidenceBand,
    CopyrightSide,
    RegistrationStatus,
    RegistryName,
)
from app.pipeline.interfaces import GapChecker
from app.pipeline.stage2_gaps.matching import band_for_score, score_match
from app.schemas.gaps import RegistrationResult
from app.schemas.identity import IdentityResult


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


@dataclass
class RawResponse:
    """The transport-agnostic raw response a `_query` returns.

    `body` is what gets persisted (as evidence) AND parsed. The rest is provenance metadata.
    In tests this is built from a fixture; in a live path it'd be built from an httpx
    Response. Keeping it a plain carrier means `_parse` never touches transport.
    """

    body: str | None
    url: str | None = None
    params: dict | None = None
    status_code: int | None = None


@dataclass
class Candidate:
    """One candidate row parsed out of a registry response.

    `match_value` is what we fuzzy-match the identity's query value against (usually the
    title; could be a writer name). `identifier` is the registry-side id we record as
    `matched_identifier` (an ISWC/work code/etc.) when this candidate wins.
    """

    match_value: str
    identifier: str | None = None
    extra: dict = field(default_factory=dict)


class RegistryAdapter(GapChecker):
    registry: RegistryName
    keys_on: CopyrightSide

    def __init__(
        self,
        session=None,
        *,
        injected_raw: RawResponse | None = None,
    ) -> None:
        # Constructor injection for persistence: with a session we persist the raw response
        # for provenance; without one we still return a valid result (just no raw_response_id).
        self._session = session
        # Fixture-backed raw response for tests; subclasses' `_query` may also use it.
        self._injected_raw = injected_raw

    # --- The shared flow ----------------------------------------------------------------

    def check(self, identity: IdentityResult) -> RegistrationResult:
        checked_at = _utcnow()

        # (a) Degrade gracefully: a composition-side check with no work identity is
        # UNRESOLVED — NOT NOT_FOUND. ISRC does not join the composition side, so we simply
        # cannot check, and must not imply a gap.
        if self.keys_on is CopyrightSide.COMPOSITION and identity.work is None:
            return RegistrationResult(
                registry=self.registry,
                side=self.keys_on,
                status=RegistrationStatus.UNRESOLVED,
                checked_at=checked_at,
                notes="no work identity to check (composition side needs ISWC/writers)",
            )

        # (b) Fetch the raw response (fixture-backed in tests / live behind the flag).
        raw = self._query(identity)

        # (c) Persist provenance when a session is present; capture the row id.
        raw_response_id = None
        if self._session is not None and raw is not None:
            row = store.save_raw_response(
                self._session,
                self.registry,
                request_url=raw.url,
                request_params=raw.params,
                status_code=raw.status_code,
                response_body=raw.body,
            )
            raw_response_id = row.id

        # (d) Parse the raw response into candidate match strings.
        candidates = self._parse(raw) if raw is not None else []

        # (e) Fuzzy-match the identity's query value against each candidate; take the best.
        query_value = self._query_value(identity)
        best = self._best_match(query_value, candidates)

        # (f) Map the best match to a status + provenance-complete result.
        if best is None:
            return RegistrationResult(
                registry=self.registry,
                side=self.keys_on,
                status=RegistrationStatus.NOT_FOUND,
                checked_at=checked_at,
                raw_response_id=raw_response_id,
                notes="checked; no candidate matched",
            )

        score, candidate = best
        band = band_for_score(score)
        status = (
            RegistrationStatus.REGISTERED
            if band is ConfidenceBand.HIGH
            else RegistrationStatus.AMBIGUOUS
        )
        return RegistrationResult(
            registry=self.registry,
            side=self.keys_on,
            status=status,
            confidence_band=band,
            confidence_score=Decimal(str(round(score, 4))),
            matched_identifier=candidate.identifier,
            checked_at=checked_at,
            raw_response_id=raw_response_id,
            notes=None
            if status is RegistrationStatus.REGISTERED
            else "match below HIGH confidence — flag for human review",
        )

    # --- Helpers a subclass may override -------------------------------------------------

    def _query_value(self, identity: IdentityResult) -> str:
        """The string we fuzzy-match against candidates. Default: the work title (composition
        side) falling back to the recording title. Override for writer/identifier matching."""
        if identity.work is not None:
            return identity.work.title
        return identity.recording.title

    @staticmethod
    def _best_match(
        query_value: str, candidates: list[Candidate]
    ) -> tuple[float, Candidate] | None:
        """Highest-scoring candidate (score, candidate), or None when there are none."""
        if not candidates:
            return None
        scored = [(score_match(query_value, c.match_value), c) for c in candidates]
        return max(scored, key=lambda sc: sc[0])

    # --- Subclass contract ---------------------------------------------------------------

    @abstractmethod
    def _query(self, identity: IdentityResult) -> RawResponse | None:
        """Adapter-specific: return the registry's raw response (fixture-backed in tests;
        live behind allow_live_network). May return the constructor-injected fixture."""

    @abstractmethod
    def _parse(self, raw: RawResponse) -> list[Candidate]:
        """Adapter-specific: parse the raw response body into candidate match rows."""
