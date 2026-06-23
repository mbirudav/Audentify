"""Work resolver (Phase 1, [P]). Recording -> WORK (ISWC + writers) via MusicBrainz.

THE composition-side step. This is what makes Stage 2's ASCAP/BMI checks possible at all.
Hard dependency for those registries. Returns None when the work can't be resolved (common
for indie tracks) so callers degrade gracefully instead of asserting 'no gap'.

The MusicBrainzClient is constructor-injected so tests pass a fake whose
`work_relations_for_isrc` returns a captured fixture dict — no network.

Shape contract (Stage 2 depends on it): each writer is a
`PartyRef(name=..., role=PartyRole.WRITER, ipi=...)`. We map any composer/lyricist/writer/
arranger MusicBrainz relation to the WRITER role and pull the IPI from the artist's
`ipi-list` when present.
"""

from __future__ import annotations

from typing import Any

from app.clients.musicbrainz import MusicBrainzClient
from app.domain import PartyRole
from app.pipeline.interfaces import WorkResolver
from app.schemas.identity import PartyRef, RecordingResult, WorkResult

# MusicBrainz artist-relation `type` values that mean "this person wrote the composition".
_WRITER_RELATION_TYPES = {"composer", "lyricist", "writer", "songwriter", "arranger"}


def _first_ipi(artist: dict[str, Any]) -> str | None:
    ipi_list = artist.get("ipi-list") or []
    return ipi_list[0] if ipi_list else artist.get("ipi")


def _writers_from_work(work: dict[str, Any]) -> list[PartyRef]:
    writers: list[PartyRef] = []
    for rel in work.get("artist-relation-list", []):
        if rel.get("type") not in _WRITER_RELATION_TYPES:
            continue
        artist = rel.get("artist") or {}
        name = artist.get("name")
        if not name:
            continue
        writers.append(
            PartyRef(name=name, role=PartyRole.WRITER, ipi=_first_ipi(artist))
        )
    return writers


def _iswc_from_work(work: dict[str, Any]) -> str | None:
    # MusicBrainz exposes either a single `iswc` or an `iswc-list`.
    iswc_list = work.get("iswc-list") or []
    return work.get("iswc") or (iswc_list[0] if iswc_list else None)


class MusicBrainzWorkResolver(WorkResolver):
    source = "musicbrainz"

    def __init__(self, client: MusicBrainzClient | None = None) -> None:
        self._client = client or MusicBrainzClient()

    def resolve_work(self, recording: RecordingResult) -> WorkResult | None:
        # Composition resolution keys on the recording's ISRC. No ISRC -> nothing to follow.
        if not recording.isrc:
            return None

        data = self._client.work_relations_for_isrc(recording.isrc)
        works: dict[str, Any] = data.get("works") or {}

        recording_list = data.get("isrc", {}).get("recording-list", [])
        for mb_recording in recording_list:
            for rel in mb_recording.get("work-relation-list", []):
                work_stub = rel.get("work") or {}
                work_id = work_stub.get("id")
                # Prefer the fully-expanded work (carries writers); fall back to the stub.
                work = works.get(work_id, work_stub) if work_id else work_stub
                if not work:
                    continue

                title = work.get("title") or recording.title
                return WorkResult(
                    title=title,
                    iswc=_iswc_from_work(work),
                    writers=_writers_from_work(work),
                    source=self.source,
                )

        # No work-relation at all — common for indie tracks. Degrade gracefully.
        return None
