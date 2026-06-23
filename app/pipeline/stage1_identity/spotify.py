"""Spotify identifier (Phase 1, [P]). Easiest path — returns ISRC directly.

Covers most distributed tracks. Master side only: Spotify gives no writers/ISWC.
"""

from __future__ import annotations

from app.pipeline.interfaces import Identifier
from app.schemas.identity import RecordingResult, TrackInput


class SpotifyIdentifier(Identifier):
    source = "spotify"

    def identify(self, track: TrackInput) -> RecordingResult:
        raise NotImplementedError(
            "Phase 1: resolve a Spotify URL/id to a RecordingResult (title, artist, ISRC)."
        )
