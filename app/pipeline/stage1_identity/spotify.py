"""Spotify identifier (Phase 1, [P]). Easiest path — returns ISRC directly.

Covers most distributed tracks. Master side only: Spotify gives no writers/ISWC, so this
NEVER populates a work — that is deliberately the WorkResolver's job (see CLAUDE.md "The
two copyrights").

The SpotifyClient is constructor-injected so tests pass a fake whose `get_track` returns a
captured fixture dict — no network, no credentials.
"""

from __future__ import annotations

import re

from app.clients.spotify import SpotifyClient
from app.pipeline.interfaces import Identifier
from app.schemas.identity import RecordingResult, TrackInput

# Accepts open.spotify.com/track/<id>, spotify:track:<id>, or a bare 22-char base62 id.
_SPOTIFY_ID_RE = re.compile(
    r"(?:spotify:track:|/track/)?([A-Za-z0-9]{22})(?:[/?].*)?$"
)


def _extract_spotify_id(track: TrackInput) -> str:
    """Pull a Spotify track id out of the TrackInput (explicit id wins over a URL)."""
    if track.spotify_id:
        match = _SPOTIFY_ID_RE.search(track.spotify_id)
        if match:
            return match.group(1)
    if track.spotify_url:
        match = _SPOTIFY_ID_RE.search(track.spotify_url)
        if match:
            return match.group(1)
    raise ValueError(
        "SpotifyIdentifier needs a spotify_id or spotify_url on the TrackInput."
    )


class SpotifyIdentifier(Identifier):
    source = "spotify"

    def __init__(self, client: SpotifyClient | None = None) -> None:
        self._client = client or SpotifyClient()

    def identify(self, track: TrackInput) -> RecordingResult:
        spotify_id = _extract_spotify_id(track)
        data = self._client.get_track(spotify_id)

        artists = data.get("artists") or []
        artist_name = ", ".join(a["name"] for a in artists if a.get("name")) or None

        return RecordingResult(
            title=data["name"],
            artist_name=artist_name,
            isrc=(data.get("external_ids") or {}).get("isrc"),
            duration_ms=data.get("duration_ms"),
            spotify_id=data.get("id", spotify_id),
            source=self.source,
        )
