"""Shared httpx client for the Stage 2 scrapers (Phase 3).

Centralizes timeouts, headers/User-Agent, retry/backoff and per-host politeness so each
registry adapter stays focused on parsing, not transport. No pipeline logic here.
"""

from __future__ import annotations


def get_http_client():
    raise NotImplementedError(
        "Phase 3: return a configured httpx.Client (timeouts, UA, retry/backoff)."
    )
