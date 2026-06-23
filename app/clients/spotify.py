"""Spotify client wrapper (Phase 1). Wraps spotipy with our credentials.

Returns track metadata incl. ISRC (master side). Spotify gives NO writers / ISWC — that's
why Stage 1 has a separate work_resolver step. No pipeline logic here.
"""

from __future__ import annotations


class SpotifyClient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def get_track(self, spotify_id: str) -> dict:
        raise NotImplementedError("Phase 1: wrap spotipy track lookup (returns ISRC).")
