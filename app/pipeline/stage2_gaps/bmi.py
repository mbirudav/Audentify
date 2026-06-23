"""BMI adapter (Phase 3, [P]). Composition side — performance royalties.

Like ASCAP: needs WORK identity from work_resolver. Independent of the other adapters by
design (the adapter pattern's payoff).
"""

from __future__ import annotations

from app.domain import CopyrightSide, RegistryName
from app.pipeline.stage2_gaps.base_adapter import RegistryAdapter
from app.schemas.identity import IdentityResult


class BMIAdapter(RegistryAdapter):
    registry = RegistryName.BMI
    keys_on = CopyrightSide.COMPOSITION

    def _query(self, identity: IdentityResult):
        raise NotImplementedError("Phase 3: query BMI by title + writer (+ ISWC).")
