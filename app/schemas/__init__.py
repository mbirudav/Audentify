"""Pydantic request/response contracts. FROZEN EARLY — the moment these exist, the stages
stop depending on one another and the UI can scaffold against stubs.

Re-exported here so callers can `from app.schemas import IdentityResult` without caring
which module a model lives in.
"""

from app.schemas.audit import AuditRequest, AuditResponse
from app.schemas.estimate import EstimateResult, RoyaltyAssumptions, RoyaltyLineItem
from app.schemas.gaps import GapReport, RegistrationResult
from app.schemas.identity import (
    IdentityResult,
    PartyRef,
    RecordingResult,
    TrackInput,
    WorkResult,
)

__all__ = [
    "AuditRequest",
    "AuditResponse",
    "EstimateResult",
    "RoyaltyAssumptions",
    "RoyaltyLineItem",
    "GapReport",
    "RegistrationResult",
    "IdentityResult",
    "PartyRef",
    "RecordingResult",
    "TrackInput",
    "WorkResult",
]
