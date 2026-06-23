"""Shared test factories + fixture loaders (the cross-session test harness).

Built up front so every Stage's tests load from ONE read-only surface — no test session
needs to edit a shared file, which is what keeps the parallel build conflict-free.

Two things live here:
  * `make_*` builders that construct the FROZEN Pydantic result types (RecordingResult,
    WorkResult, IdentityResult, PartyRef) with sensible defaults — so a test can say
    `make_identity(with_work=False)` instead of hand-assembling nested models.
  * `load_fixture` / `load_json_fixture` that read captured external payloads from
    `tests/fixtures/<name>` — NEVER the network. Each session drops its own distinctly
    named fixture files in that dir (spotify_*.json, mlc_*.html, …) so they don't collide.

Import directly: `from tests.factories import make_identity, load_json_fixture`. The
matching `tests/conftest.py` also exposes these as pytest fixtures for convenience.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.domain import PartyRole
from app.schemas.identity import (
    IdentityResult,
    PartyRef,
    RecordingResult,
    WorkResult,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- Fixture loaders (captured payloads only — never a live call) ----------------------


def load_fixture(name: str) -> str:
    """Return the raw text of `tests/fixtures/<name>`."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def load_json_fixture(name: str) -> dict:
    """Return a parsed JSON fixture from `tests/fixtures/<name>`."""
    return json.loads(load_fixture(name))


# --- Builders over the frozen result schemas -------------------------------------------


def make_party(
    name: str = "Jane Writer",
    role: PartyRole = PartyRole.WRITER,
    ipi: str | None = "00000000250",
    percent: Decimal | float | None = 100,
) -> PartyRef:
    return PartyRef(
        name=name,
        role=role,
        ipi=ipi,
        percent=None if percent is None else Decimal(str(percent)),
    )


def make_recording(
    title: str = "Test Track",
    artist_name: str | None = "Test Artist",
    isrc: str | None = "US-S1Z-99-00001",
    duration_ms: int | None = 210_000,
    spotify_id: str | None = "1abcDEFghiJKLmnoPQRstu",
    source: str | None = "spotify",
) -> RecordingResult:
    return RecordingResult(
        title=title,
        artist_name=artist_name,
        isrc=isrc,
        duration_ms=duration_ms,
        spotify_id=spotify_id,
        source=source,
    )


def make_work(
    title: str = "Test Track",
    iswc: str | None = "T-123.456.789-0",
    writers: list[PartyRef] | None = None,
    source: str | None = "musicbrainz",
) -> WorkResult:
    return WorkResult(
        title=title,
        iswc=iswc,
        writers=writers if writers is not None else [make_party()],
        source=source,
    )


def make_identity(
    *,
    with_work: bool = True,
    recording: RecordingResult | None = None,
    work: WorkResult | None = None,
) -> IdentityResult:
    """Build an IdentityResult. `with_work=False` yields the UNRESOLVED-work case that the
    composition-side gap checks must degrade on (return UNRESOLVED, never NOT_FOUND)."""
    rec = recording or make_recording()
    if work is not None:
        resolved = work
    elif with_work:
        resolved = make_work(title=rec.title)
    else:
        resolved = None
    return IdentityResult(recording=rec, work=resolved)
