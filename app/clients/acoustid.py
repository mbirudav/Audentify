"""AcoustID client wrapper (Phase 1).

Used by fingerprint.py: a Chromaprint fingerprint -> AcoustID -> MusicBrainz recording IDs.
Needs ACOUSTID_API_KEY. The `fpcalc` (Chromaprint) binary is a system dep handled in
fingerprint.py, not here. No pipeline logic here.
"""

from __future__ import annotations

from app.config import get_settings


class AcoustIDClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or get_settings().acoustid_api_key

    def lookup(self, fingerprint: str, duration: int) -> dict:
        raise NotImplementedError("Phase 1: AcoustID lookup by fingerprint + duration.")
