"""Manual identifier (Phase 1, [P]). Core, not optional.

New artists are badly indexed, so manual entry is the fallback when Spotify/fingerprint
can't resolve a track. Builds the RECORDING (master side) from user-supplied
title/artist/ISRC.

CONTRACT FRICTION — manual WORK entry cannot flow through this stage:
    `TrackInput` carries an `iswc` field, but it has NO writers list, and the frozen
    `WorkResolver.resolve_work(recording: RecordingResult)` only ever receives a
    RecordingResult (which has no iswc/writers either). So neither this Identifier nor any
    WorkResolver can turn a user's manually-entered ISWC/writers into a WorkResult under the
    frozen interfaces. Manual work entry is therefore the ORCHESTRATOR's job (Session D):
    it reads `TrackInput.iswc` directly and constructs the WorkResult itself. This module
    deliberately does NOT try to populate a work and does NOT edit the interface.
"""

from __future__ import annotations

from app.pipeline.interfaces import Identifier
from app.schemas.identity import RecordingResult, TrackInput


class ManualIdentifier(Identifier):
    source = "manual"

    def identify(self, track: TrackInput) -> RecordingResult:
        # Need at least something to key the recording on. Title is the human handle; ISRC is
        # the master key. With neither, there is nothing to identify.
        if not track.title and not track.isrc:
            raise ValueError(
                "ManualIdentifier needs at least a title or an isrc on the TrackInput."
            )

        # If only an ISRC was given, fall back to it as a placeholder title so the required
        # RecordingResult.title field is populated; callers can refine later.
        title = track.title or f"Unknown title (ISRC {track.isrc})"

        return RecordingResult(
            title=title,
            artist_name=track.artist_name,
            isrc=track.isrc,
            source=self.source,
        )
