"""Top-level contracts: the request/response for the core audit loop.

services/audit.py consumes an AuditRequest and produces an AuditResponse by running
Stage 1 -> 2 -> 3. The Streamlit UI scaffolds against these against stubbed services as
soon as they're frozen — it doesn't wait for the real stages.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.estimate import EstimateResult, RoyaltyAssumptions
from app.schemas.gaps import GapReport
from app.schemas.identity import IdentityResult, TrackInput


class AuditRequest(BaseModel):
    track: TrackInput
    assumptions: RoyaltyAssumptions = RoyaltyAssumptions()


class AuditResponse(BaseModel):
    identity: IdentityResult
    gaps: GapReport
    estimate: EstimateResult
