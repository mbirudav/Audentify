"""MLC adapter (Phase 3, [P]). Composition side — mechanical royalties.

The MLC is composition-side but keeps ISRC->work links, so ISRC MAY work as a search input
(verify against the live site). Build this one end-to-end first.
"""

from __future__ import annotations

from app.domain import CopyrightSide, RegistryName
from app.pipeline.stage2_gaps.base_adapter import RegistryAdapter
from app.schemas.identity import IdentityResult


class MLCAdapter(RegistryAdapter):
    registry = RegistryName.MLC
    keys_on = CopyrightSide.COMPOSITION

    def _query(self, identity: IdentityResult):
        raise NotImplementedError("Phase 3: query the MLC (try ISRC search input).")
