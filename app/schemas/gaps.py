"""Stage 2 contracts: where the artist is / isn't registered, with provenance.

Every RegistrationResult is self-describing evidence: which registry, which copyright side,
the status, a confidence band+score, what (if anything) matched, when it was checked, and a
pointer to the cached raw response. The UI renders these directly as the "registration map".
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain import ConfidenceBand, CopyrightSide, RegistrationStatus, RegistryName


class RegistrationResult(BaseModel):
    registry: RegistryName
    side: CopyrightSide
    status: RegistrationStatus
    confidence_band: ConfidenceBand | None = None
    confidence_score: Decimal | None = Field(default=None, ge=0, le=1)
    matched_identifier: str | None = None
    checked_at: dt.datetime | None = None
    notes: str | None = None
    raw_response_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class GapReport(BaseModel):
    """The full registration map for one identity. `unresolved` lists registries we could
    not check (e.g. no work identity) so the UI flags them instead of implying no gap."""

    checks: list[RegistrationResult] = Field(default_factory=list)
    unresolved: list[RegistryName] = Field(default_factory=list)

    @property
    def candidate_leaks(self) -> list[RegistrationResult]:
        return [c for c in self.checks if c.status == RegistrationStatus.NOT_FOUND]
