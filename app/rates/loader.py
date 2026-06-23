"""Seed the versioned RateCard table from rates.yaml.

The YAML is a SEED, not the source of truth — the table is. This loader reads the seed and
*upserts* rows idempotently on the `rate_card_version_unique` constraint
(royalty_type, registry, version, effective_date), so re-running it never duplicates a row:
a matching row is updated in place, a missing one is inserted.

We do the upsert with an explicit select-then-write rather than a dialect-specific
`INSERT ... ON CONFLICT` so the same code path works on both SQLite (tests, in-memory) and
Postgres (prod). Returns how many rows were seeded or updated.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RateCard
from app.domain import RegistryName, RoyaltyType

# Default seed location: app/rates/rates.yaml, sitting next to this module.
DEFAULT_RATES_PATH = Path(__file__).with_name("rates.yaml")


def _parse_date(value: str | dt.date) -> dt.date:
    """YAML may hand us a `datetime.date` (it auto-parses ISO dates) or a string."""
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def seed_rate_cards(session: Session, yaml_path: str | Path | None = None) -> int:
    """Upsert RateCard rows from the seed YAML. Idempotent on the unique constraint.

    Returns the number of rows seeded (inserted) or updated. Does NOT commit — the caller
    owns the transaction boundary (a script can commit, a test can roll back).
    """
    path = Path(yaml_path) if yaml_path is not None else DEFAULT_RATES_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = data.get("rates", []) or []

    count = 0
    for row in rows:
        royalty_type = RoyaltyType(row["royalty_type"])
        registry = RegistryName(row["registry"]) if row.get("registry") is not None else None
        version = str(row["version"])
        effective_date = _parse_date(row["effective_date"])
        # Decimal(str(...)) so a YAML float never injects binary float noise into the rate.
        rate = Decimal(str(row["rate"]))
        unit = str(row["unit"])
        currency = str(row.get("currency", "USD"))
        notes = row.get("notes")

        # Look the row up on the exact unique key, then update-in-place or insert.
        existing = session.scalars(
            select(RateCard).where(
                RateCard.royalty_type == royalty_type,
                RateCard.registry == registry,
                RateCard.version == version,
                RateCard.effective_date == effective_date,
            )
        ).first()

        if existing is None:
            session.add(
                RateCard(
                    royalty_type=royalty_type,
                    registry=registry,
                    version=version,
                    effective_date=effective_date,
                    rate=rate,
                    unit=unit,
                    currency=currency,
                    notes=notes,
                )
            )
        else:
            existing.rate = rate
            existing.unit = unit
            existing.currency = currency
            existing.notes = notes

        count += 1

    session.flush()
    return count
