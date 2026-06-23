"""ASCAP adapter (Phase 3, [P]). Composition side — performance royalties.

Needs WORK identity (title + writer + ISWC) from Stage 1's work_resolver — can be coded in
parallel but can't be end-to-end tested until work_resolver produces real work identity.
"""

from __future__ import annotations

from app.domain import CopyrightSide, RegistryName
from app.pipeline.stage2_gaps.base_adapter import RegistryAdapter
from app.schemas.identity import IdentityResult


class ASCAPAdapter(RegistryAdapter):
    registry = RegistryName.ASCAP
    keys_on = CopyrightSide.COMPOSITION

    def _query(self, identity: IdentityResult):
        raise NotImplementedError("Phase 3: query ASCAP by title + writer (+ ISWC).")
