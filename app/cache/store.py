"""Persistence helpers for raw registry responses (Phase 3).

Writes/reads RawRegistryResponse rows — the evidence trail behind every gap claim. Each row
captures what was requested, the raw body, and a sha256 `content_hash` (so we can dedupe
identical responses and detect when a registry's HTML changed under us). `save_raw_response`
flushes so the row's `.id` is populated and a RegistrationCheck can point at the exact
evidence it was derived from.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.db.models import RawRegistryResponse
from app.domain import RegistryName


def _hash_body(response_body: str | None) -> str | None:
    """sha256 hex digest of the response body, or None when there's no body."""
    if response_body is None:
        return None
    return hashlib.sha256(response_body.encode("utf-8")).hexdigest()


def save_raw_response(
    session: Session,
    registry: RegistryName,
    *,
    request_url: str | None = None,
    request_params: dict | None = None,
    status_code: int | None = None,
    response_body: str | None = None,
) -> RawRegistryResponse:
    """Persist a RawRegistryResponse and return it with `.id` populated.

    Computes a sha256 `content_hash` of the body for dedupe/change-detection, adds the row,
    and flushes (not commits — the caller owns the transaction boundary) so `.id` is
    available to link from a RegistrationCheck.
    """
    row = RawRegistryResponse(
        registry=registry,
        request_url=request_url,
        request_params=request_params,
        status_code=status_code,
        response_body=response_body,
        content_hash=_hash_body(response_body),
    )
    session.add(row)
    session.flush()  # populate row.id without committing the caller's unit of work
    return row


def find_by_hash(session: Session, content_hash: str) -> RawRegistryResponse | None:
    """Return the most recent cached response with this content hash, if any (dedupe)."""
    return (
        session.query(RawRegistryResponse)
        .filter(RawRegistryResponse.content_hash == content_hash)
        .order_by(RawRegistryResponse.fetched_at.desc())
        .first()
    )
