"""FastAPI entrypoint.

Phase 0 skeleton: a health check plus app metadata. The audit endpoint lands in Phase 4
when services/audit.py wires the three stages together (kept stubbed against interfaces
until then so the API contract can exist before the implementations do).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Surfaces royalties indie artists are unknowingly losing.",
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
