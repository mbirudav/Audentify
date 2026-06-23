"""SoundExchange adapter (Phase 3). MASTER side — digital performance (non-interactive).

There is NO public SoundExchange lookup, so this does not scrape. It degrades to a manual
self-report toggle: the artist tells us whether they're registered, and we record that with
provenance (source = self-report) instead of asserting from a query.

Mapping (keys on ISRC, the master key):
  * self_reported_registered is None  -> UNRESOLVED  (we don't know — never imply a gap)
  * self_reported_registered is True  -> REGISTERED
  * self_reported_registered is False -> NOT_FOUND   (artist says not registered)
"""

from __future__ import annotations

import datetime as dt

from app.domain import CopyrightSide, RegistrationStatus, RegistryName
from app.pipeline.stage2_gaps.base_adapter import (
    Candidate,
    RawResponse,
    RegistryAdapter,
)
from app.schemas.gaps import RegistrationResult
from app.schemas.identity import IdentityResult


class SoundExchangeAdapter(RegistryAdapter):
    registry = RegistryName.SOUNDEXCHANGE
    keys_on = CopyrightSide.MASTER

    def __init__(
        self,
        *,
        self_reported_registered: bool | None = None,
        session=None,
    ) -> None:
        super().__init__(session=session)
        self._self_reported_registered = self_reported_registered

    def check(self, identity: IdentityResult) -> RegistrationResult:
        checked_at = dt.datetime.now(dt.UTC)
        isrc = identity.recording.isrc

        if self._self_reported_registered is None:
            status = RegistrationStatus.UNRESOLVED
            notes = "no self-report provided (no public SoundExchange lookup exists)"
            matched = None
        elif self._self_reported_registered:
            status = RegistrationStatus.REGISTERED
            notes = "source: self-report (artist states registered with SoundExchange)"
            matched = isrc
        else:
            status = RegistrationStatus.NOT_FOUND
            notes = "source: self-report (artist states NOT registered with SoundExchange)"
            matched = isrc

        return RegistrationResult(
            registry=self.registry,
            side=self.keys_on,
            status=status,
            matched_identifier=matched,
            checked_at=checked_at,
            notes=notes,
        )

    # No public lookup — these never run (check() is fully overridden), but the base
    # declares them abstract, so provide concrete guards.
    def _query(self, identity: IdentityResult) -> RawResponse | None:
        raise NotImplementedError(
            "SoundExchange has no public lookup — use the self-report toggle."
        )

    def _parse(self, raw: RawResponse) -> list[Candidate]:
        raise NotImplementedError(
            "SoundExchange has no public lookup — use the self-report toggle."
        )
