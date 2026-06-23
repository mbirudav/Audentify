"""Shared httpx client for the Stage 2 registry lookups (Phase 3).

Centralizes timeouts, headers/User-Agent and connection retries so each registry adapter
stays focused on parsing, not transport. No pipeline logic here.

LIVE-ONLY. This build does NO live scraping: there are no captured network calls in any
tested path — adapters parse fixtures. This client exists solely so a future, deliberate,
licensed-or-permitted integration has one transport to configure. It is gated behind
`settings.allow_live_network` (default False) and raises when off, so a scraper can never
run by accident. Note that "public" data is NOT the same as "permitted to scrape": registry
ToS may prohibit automated access, and this flag protects us technically, not legally.
"""

from __future__ import annotations

import httpx

from app.config import Settings, get_settings

# Politeness defaults. A descriptive UA (with contact) and conservative timeouts; retries
# cover transient connection errors only (not 4xx/5xx, which adapters must handle).
DEFAULT_USER_AGENT = "Audentify/0.1 (+https://audentify.app; maruthibirudavolu@gmail.com)"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_RETRIES = 2


class LiveNetworkDisabledError(RuntimeError):
    """Raised when a live HTTP client is requested but `allow_live_network` is False."""


def get_http_client(settings: Settings | None = None) -> httpx.Client:
    """Return a configured httpx.Client (timeouts, UA, connection retries/backoff).

    Raises LiveNetworkDisabledError unless `settings.allow_live_network` is True — flipping
    that on is a deliberate manual act (and even then ToS may forbid automated access).
    """
    settings = settings or get_settings()
    if not settings.allow_live_network:
        raise LiveNetworkDisabledError(
            "Live network is disabled (allow_live_network=False). Stage 2 parses captured "
            "fixtures; no live scraping runs in this build."
        )

    # connect gets a longer budget than read/write; httpx.Timeout(default, connect=...).
    timeout = httpx.Timeout(DEFAULT_TIMEOUT_SECONDS, connect=30.0)
    # HTTPTransport(retries=N) retries connection-level failures with exponential backoff.
    transport = httpx.HTTPTransport(retries=DEFAULT_RETRIES)
    return httpx.Client(
        timeout=timeout,
        transport=transport,
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
    )
