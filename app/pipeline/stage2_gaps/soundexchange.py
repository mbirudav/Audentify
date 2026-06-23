"""SoundExchange adapter (Phase 3, [P]). MASTER side — digital performance (non-interactive).

No public lookup exists, so this degrades to a manual self-report toggle rather than a
scrape: the artist tells us whether they're registered, and we record that with provenance
(source = self-report) instead of asserting from a query.
"""

from __future__ import annotations

from app.domain import CopyrightSide, RegistryName
from app.pipeline.stage2_gaps.base_adapter import RegistryAdapter
from app.schemas.identity import IdentityResult


class SoundExchangeAdapter(RegistryAdapter):
    registry = RegistryName.SOUNDEXCHANGE
    keys_on = CopyrightSide.MASTER

    def _query(self, identity: IdentityResult):
        raise NotImplementedError(
            "Phase 3: no public lookup — wire the manual self-report toggle instead."
        )
