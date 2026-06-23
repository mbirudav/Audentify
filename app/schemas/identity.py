"""Stage 1 contracts: raw input → recording (master) + work (composition).

The split into RecordingResult and WorkResult mirrors the two copyrights. An Identifier
produces the RecordingResult (ISRC); a WorkResolver produces the WorkResult (ISWC +
writers). IdentityResult carries both, and `work` is optional — work resolution degrades
gracefully rather than blocking the recording side.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain import PartyRole


class TrackInput(BaseModel):
    """What the artist hands us. Exactly one resolution path is expected to be populated,
    but manual fields can also supplement an automated lookup (e.g. writers Spotify omits).
    """

    spotify_url: str | None = None
    spotify_id: str | None = None
    audio_file_path: str | None = None  # for fingerprint.py
    # Manual entry / supplements:
    title: str | None = None
    artist_name: str | None = None
    isrc: str | None = None
    iswc: str | None = None


class PartyRef(BaseModel):
    """A writer/publisher/performer reference, with an optional split percentage."""

    name: str
    role: PartyRole
    ipi: str | None = None
    percent: Decimal | None = Field(default=None, ge=0, le=100)


class RecordingResult(BaseModel):
    """The master side. ISRC is the key; writers/ISWC are NOT here (Spotify omits them)."""

    title: str
    artist_name: str | None = None
    isrc: str | None = None
    duration_ms: int | None = None
    spotify_id: str | None = None
    source: str | None = None  # which Identifier produced this (spotify | manual | fingerprint)


class WorkResult(BaseModel):
    """The composition side. ISWC + writers are what ASCAP/BMI/MLC key on."""

    title: str
    iswc: str | None = None
    writers: list[PartyRef] = Field(default_factory=list)
    source: str | None = None  # musicbrainz | manual

    model_config = ConfigDict(from_attributes=True)


class IdentityResult(BaseModel):
    """Stage 1's full output: both copyrights. `work` is None when unresolvable."""

    recording: RecordingResult
    work: WorkResult | None = None
