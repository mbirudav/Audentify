"""Fingerprint identifier (Phase 1, [P], last). Chromaprint + AcoustID + MusicBrainz.

For raw audio files with no metadata. Needs the `fpcalc` (Chromaprint) BINARY in the deploy
image — Railway/Render won't have it by default. Most setup overhead, so built last.
"""

from __future__ import annotations

from app.pipeline.interfaces import Identifier
from app.schemas.identity import RecordingResult, TrackInput


class FingerprintIdentifier(Identifier):
    source = "fingerprint"

    def identify(self, track: TrackInput) -> RecordingResult:
        raise NotImplementedError(
            "Phase 1: fpcalc fingerprint -> AcoustID -> MusicBrainz -> RecordingResult."
        )
