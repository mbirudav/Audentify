"""Pipeline ABCs — the contracts that make stages swappable and parallel-buildable.

FROZEN EARLY alongside schemas/. The four roles map to the build plan:

    Identifier    raw input  -> RecordingResult         (master side, ISRC)
    WorkResolver  recording  -> WorkResult | None        (composition side, ISWC + writers)
    GapChecker    identity   -> RegistrationResult        (one registry; declares its side)
    Estimator     identity + assumptions + gaps -> EstimateResult

Every concrete implementation lives behind one of these so a broken scraper or a swapped
API never ripples into another stage. GapChecker declares `registry` and `keys_on` so the
orchestrator can route an identity to the right checks and skip composition-side checks
when the work is unresolved.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain import CopyrightSide, RegistryName
from app.schemas.estimate import EstimateResult, RoyaltyAssumptions
from app.schemas.gaps import RegistrationResult
from app.schemas.identity import IdentityResult, RecordingResult, TrackInput, WorkResult


class Identifier(ABC):
    """Resolve raw track input -> the RECORDING (master side, ISRC). Does NOT resolve the
    work — that's a deliberate second step (see WorkResolver)."""

    source: str

    @abstractmethod
    def identify(self, track: TrackInput) -> RecordingResult:
        """Return the canonical recording. Raise if the track can't be identified."""


class WorkResolver(ABC):
    """Resolve a recording -> its WORK (ISWC + writer IPIs). This is what makes the
    composition-side gap checks (ASCAP/BMI/MLC) possible at all. Returns None when the work
    can't be resolved — callers must degrade gracefully, never assert 'no gap'."""

    source: str

    @abstractmethod
    def resolve_work(self, recording: RecordingResult) -> WorkResult | None:
        ...


class GapChecker(ABC):
    """Check one identity against ONE registry and return a provenance-bearing result.

    Subclasses set `registry` and `keys_on`. `keys_on` tells the orchestrator which
    copyright side this checker needs: a COMPOSITION checker requires identity.work, and
    must report UNRESOLVED (not NOT_FOUND) when it's missing."""

    registry: RegistryName
    keys_on: CopyrightSide

    @abstractmethod
    def check(self, identity: IdentityResult) -> RegistrationResult:
        ...


class Estimator(ABC):
    """Estimate the annual leak as a per-royalty-type RANGE. Reads rates from the versioned
    RateCard table; volume comes from assumptions. Never one flat formula, never false
    precision."""

    @abstractmethod
    def estimate(
        self,
        identity: IdentityResult,
        assumptions: RoyaltyAssumptions,
        gaps: list[RegistrationResult],
    ) -> EstimateResult:
        ...
