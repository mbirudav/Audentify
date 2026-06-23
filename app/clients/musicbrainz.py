"""MusicBrainz client wrapper (Phase 1).

Used by work_resolver: recording (ISRC) -> work-relations -> ISWC + writers. MusicBrainz
requires a custom User-Agent and ~1 req/sec rate limiting (enforced here, not in the
stage). No pipeline logic here.
"""

from __future__ import annotations

from app.config import get_settings


class MusicBrainzClient:
    def __init__(self, user_agent: str | None = None, rate_limit_per_sec: float | None = None) -> None:
        settings = get_settings()
        self._user_agent = user_agent or settings.musicbrainz_user_agent
        self._rate_limit_per_sec = rate_limit_per_sec or settings.musicbrainz_rate_limit_per_sec

    def work_relations_for_isrc(self, isrc: str) -> dict:
        raise NotImplementedError(
            "Phase 1: look up recording by ISRC, follow work-relations to ISWC + writers."
        )
