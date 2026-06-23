"""Manual identifier (Phase 1, [P]). Core, not optional.

New artists are badly indexed, and manual entry is also the fallback for the WORK side
(title + ISRC + writer entry). Populates both recording and work from user-supplied fields.
"""

from __future__ import annotations

from app.pipeline.interfaces import Identifier
from app.schemas.identity import RecordingResult, TrackInput


class ManualIdentifier(Identifier):
    source = "manual"

    def identify(self, track: TrackInput) -> RecordingResult:
        raise NotImplementedError(
            "Phase 1: build a RecordingResult from manually-entered title/artist/ISRC."
        )
