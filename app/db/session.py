"""SQLAlchemy engine + session factory.

The engine is created once at import time from the configured DATABASE_URL. get_session()
is a generator so it can back a FastAPI dependency (`Depends(get_session)`) or be used as a
context-managed unit of work in scripts/tests.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# pool_pre_ping avoids handing out a dead connection after the DB restarts (common in dev).
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
