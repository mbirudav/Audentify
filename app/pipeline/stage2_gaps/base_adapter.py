"""Registry adapter base (Phase 3, build FIRST, then one registry end-to-end).

RegistryAdapter is the shared concrete base over the GapChecker contract: it will hold the
common plumbing (fetch via clients/http, cache the raw response for provenance, build a
RegistrationResult with confidence). Concrete adapters implement only the query + parse.

Each subclass MUST set `registry` and `keys_on`. A COMPOSITION adapter must return status
UNRESOLVED (not NOT_FOUND) when identity.work is missing — never assert a gap we can't check.
"""

from __future__ import annotations

from abc import abstractmethod

from app.domain import CopyrightSide, RegistryName
from app.pipeline.interfaces import GapChecker
from app.schemas.gaps import RegistrationResult
from app.schemas.identity import IdentityResult


class RegistryAdapter(GapChecker):
    registry: RegistryName
    keys_on: CopyrightSide

    def check(self, identity: IdentityResult) -> RegistrationResult:
        # Shared flow lands in Phase 3: guard the required copyright side, fetch (cached),
        # parse, fuzzy-match with confidence, persist provenance, return a result.
        raise NotImplementedError("Phase 3: implement the shared check() flow.")

    @abstractmethod
    def _query(self, identity: IdentityResult):
        """Adapter-specific: hit the registry and return its raw response."""
