"""Spotify client wrapper (Phase 1). Wraps spotipy with our credentials.

Returns track metadata incl. ISRC (master side). Spotify gives NO writers / ISWC — that's
why Stage 1 has a separate work_resolver step. No pipeline logic here.

Live network is gated behind `settings.allow_live_network`: when it's False (the default,
and always in tests) `get_track` raises instead of authenticating or calling Spotify, so no
test path can hit the network. Tests inject a fake client whose `get_track` returns a
captured fixture dict.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings


class SpotifyClient:
    """Thin wrapper over spotipy's client-credentials track lookup.

    The spotipy client is created lazily on first live call so that constructing this object
    (and the SpotifyIdentifier that holds it) never needs real credentials or network.
    """

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        settings = get_settings()
        self._client_id = client_id or settings.spotify_client_id
        self._client_secret = client_secret or settings.spotify_client_secret
        self._sp: Any | None = None

    def _spotify(self) -> Any:
        if self._sp is None:
            # Imported lazily: keeps spotipy off the import path for tests that never go live.
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials

            auth_manager = SpotifyClientCredentials(
                client_id=self._client_id,
                client_secret=self._client_secret,
            )
            self._sp = spotipy.Spotify(auth_manager=auth_manager)
        return self._sp

    def get_track(self, spotify_id: str) -> dict:
        """Return the raw Spotify track object for `spotify_id`.

        Keys of interest downstream: `id`, `name`, `artists` (list of {`name`, ...}),
        `duration_ms`, and `external_ids.isrc`.
        """
        if not get_settings().allow_live_network:
            raise RuntimeError("live network disabled; set allow_live_network=True")
        return self._spotify().track(spotify_id)
