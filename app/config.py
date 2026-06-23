"""Application settings, loaded from environment / .env via pydantic-settings.

Why a single Settings object: secrets and tunables (DB URL, API keys, MusicBrainz
etiquette) live in one typed, validated place instead of scattered os.getenv calls.
get_settings() is cached so the .env is parsed once per process.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    database_url: str = "postgresql://audentify:audentify_dev@localhost:5432/audentify_dev"

    # --- Stage 1 external APIs (optional until Phase 1) ---
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    acoustid_api_key: str | None = None

    # --- MusicBrainz etiquette (a custom UA + ~1 req/sec is required by their ToS) ---
    musicbrainz_user_agent: str = "Audentify/0.1 (maruthibirudavolu@gmail.com)"
    musicbrainz_rate_limit_per_sec: float = 1.0

    # --- Network master switch -------------------------------------------------------
    # OFF by default so tests and CI NEVER hit the network and no scraper runs by
    # accident. Every external caller (Spotify/MusicBrainz/AcoustID clients, the Stage 2
    # registry HTTP client) must check this before making a real request and raise a clear
    # "live network disabled" error when it's False. Flipping it on is a deliberate, manual
    # act — and even then, registry ToS may prohibit automated access (see CLAUDE.md /
    # PLAN.md "Risks"): the flag protects us technically, not legally.
    allow_live_network: bool = False

    # --- App ---
    app_name: str = "Audentify"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
