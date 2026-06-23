"""MusicBrainz client wrapper (Phase 1).

Used by work_resolver: recording (ISRC) -> work-relations -> ISWC + writers. MusicBrainz
requires a custom User-Agent and ~1 req/sec rate limiting (enforced here, not in the
stage). No pipeline logic here.

Two-step lookup, because MusicBrainz models it as two entities:
  1. recording-by-ISRC including `work-rels` gives the recording -> WORK link (the work stub
     carries id + title + iswc).
  2. work-by-id including `artist-rels` gives the WRITERS (composer/lyricist/writer
     relations, each artist carrying an IPI).
`work_relations_for_isrc` does both and returns a single combined raw dict so the resolver
has everything it needs without itself knowing the MusicBrainz call shape.

Live network is gated behind `settings.allow_live_network`: when False (default, and always
in tests) it raises rather than calling out. Tests inject a fake client returning a captured
fixture dict.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings


class MusicBrainzClient:
    def __init__(
        self, user_agent: str | None = None, rate_limit_per_sec: float | None = None
    ) -> None:
        settings = get_settings()
        self._user_agent = user_agent or settings.musicbrainz_user_agent
        self._rate_limit_per_sec = rate_limit_per_sec or settings.musicbrainz_rate_limit_per_sec
        self._configured = False

    def _configure(self) -> None:
        """Set UA + rate limit on the musicbrainzngs module (idempotent, lazy)."""
        if self._configured:
            return
        import musicbrainzngs

        # musicbrainzngs wants (app, version, contact); our settings keep a single UA string.
        # Pass it as the app name with our app version + contact email so the outgoing
        # User-Agent still satisfies MusicBrainz's etiquette requirement.
        musicbrainzngs.set_useragent(
            self._user_agent, "0.1", "maruthibirudavolu@gmail.com"
        )
        # interval = seconds between requests; honor ~1 req/sec from settings.
        interval = 1.0 / self._rate_limit_per_sec if self._rate_limit_per_sec else 1.0
        musicbrainzngs.set_rate_limit(limit_or_interval=interval)
        self._configured = True

    def work_relations_for_isrc(self, isrc: str) -> dict:
        """Return a combined raw dict for `isrc`:

            {
              "isrc": {"recording-list": [ <recording incl. work-relation-list> ]},
              "works": { <work_mbid>: <work incl. artist-relation-list> },
            }

        `works` is keyed by MBID so the resolver can join a recording's work-relation to the
        fully-expanded work (writers + iswc) without a second round-trip of its own.
        """
        if not get_settings().allow_live_network:
            raise RuntimeError("live network disabled; set allow_live_network=True")
        self._configure()
        import musicbrainzngs

        recordings_result: dict[str, Any] = musicbrainzngs.get_recordings_by_isrc(
            isrc, includes=["artists", "work-rels"]
        )

        works: dict[str, Any] = {}
        recording_list = recordings_result.get("isrc", {}).get("recording-list", [])
        for recording in recording_list:
            for rel in recording.get("work-relation-list", []):
                work = rel.get("work")
                if not work:
                    continue
                work_id = work.get("id")
                if not work_id or work_id in works:
                    continue
                # Expand the work to pull its writer artist-relations + ISWC.
                work_detail = musicbrainzngs.get_work_by_id(
                    work_id, includes=["artist-rels"]
                )
                works[work_id] = work_detail.get("work", work_detail)

        return {"isrc": recordings_result.get("isrc", {}), "works": works}
