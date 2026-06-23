"""AcoustID client wrapper (Phase 1).

Used by fingerprint.py: a Chromaprint fingerprint -> AcoustID -> MusicBrainz recording IDs.
Needs ACOUSTID_API_KEY. The `fpcalc` (Chromaprint) binary is a system dep handled in
fingerprint.py, not here. No pipeline logic here.

Live network is gated behind `settings.allow_live_network`: when False (default, and always
in tests) `lookup` raises rather than calling the AcoustID web service. Tests inject a fake
client returning a captured fixture dict.
"""

from __future__ import annotations

from app.config import get_settings


class AcoustIDClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or get_settings().acoustid_api_key

    def lookup(self, fingerprint: str, duration: int) -> dict:
        """Look up a Chromaprint fingerprint (+ duration in seconds) against AcoustID.

        Returns the raw AcoustID response dict: `{"status": "ok", "results": [{"id", "score",
        "recordings": [{"id", "title", "artists": [...]}, ...]}]}`. We request `recordings`
        metadata so the fingerprint identifier can read title/artist/MBID without a separate
        AcoustID call.
        """
        if not get_settings().allow_live_network:
            raise RuntimeError("live network disabled; set allow_live_network=True")
        import acoustid

        # acoustid.lookup returns the parsed JSON dict (the same shape as the web service).
        return acoustid.lookup(
            self._api_key, fingerprint, duration, meta=["recordings"]
        )
