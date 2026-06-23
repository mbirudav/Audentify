"""FastAPI entrypoint.

Phase 0 skeleton: a health check plus app metadata. Phase 4 adds the synchronous audit
endpoint that wires Stage 1 -> 2 -> 3 via services/audit.run_audit (see that module for the
sync-vs-async rationale and the offline-degradation contract).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.schemas.audit import AuditRequest, AuditResponse
from app.services.audit import run_audit

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Surfaces royalties indie artists are unknowingly losing.",
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.post("/audit", response_model=AuditResponse, tags=["audit"])
def audit(
    request: AuditRequest,
    self_report_soundexchange: bool | None = None,
) -> AuditResponse:
    """Run the synchronous core audit loop and return the full result.

    `self_report_soundexchange` is an optional query param carrying the artist's
    SoundExchange self-report (None = unknown -> UNRESOLVED, True -> REGISTERED,
    False -> NOT_FOUND). SoundExchange has no public lookup, so this toggle is how the
    master side gets answered. With live network OFF (the default), Stage 1 uses the
    no-network manual path and the network-gated composition adapters degrade to ERROR.
    """
    return run_audit(
        request,
        soundexchange_self_report=self_report_soundexchange,
    )
