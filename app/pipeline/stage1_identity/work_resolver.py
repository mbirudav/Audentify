"""Work resolver (Phase 1, [P]). Recording -> WORK (ISWC + writers) via MusicBrainz.

THE composition-side step. This is what makes Stage 2's ASCAP/BMI checks possible at all.
Hard dependency for those registries. Returns None when the work can't be resolved (common
for indie tracks) so callers degrade gracefully instead of asserting 'no gap'.
"""

from __future__ import annotations

from app.pipeline.interfaces import WorkResolver
from app.schemas.identity import RecordingResult, WorkResult


class MusicBrainzWorkResolver(WorkResolver):
    source = "musicbrainz"

    def resolve_work(self, recording: RecordingResult) -> WorkResult | None:
        raise NotImplementedError(
            "Phase 1: follow MusicBrainz work-relations from the recording to ISWC + writers."
        )
