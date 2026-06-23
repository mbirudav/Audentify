"""Stage 3 contracts: estimated annual leak as a RANGE, per royalty type.

Never a single flat number. Each line item is one royalty type with its own rate base, a
low/high band, the rate version it used (for reproducibility), and the assumptions it made
(exposed so the UI can show + let the user adjust them). No false precision.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.domain import RoyaltyType


class RoyaltyAssumptions(BaseModel):
    """Artist-entered / defaulted inputs. Volume means different things per royalty type
    (streams for mechanical, spins for SoundExchange), so it's a per-type map."""

    # royalty_type value -> assumed annual volume (streams or spins, per type)
    annual_volume: dict[RoyaltyType, int] = Field(default_factory=dict)
    # Optional override of which rate version to pin; None = latest effective.
    rate_version: str | None = None
    notes: str | None = None


class RoyaltyLineItem(BaseModel):
    royalty_type: RoyaltyType
    low: Decimal
    high: Decimal
    currency: str = "USD"
    rate_version: str | None = None
    rate_effective_date: str | None = None
    assumptions: dict[str, str] = Field(default_factory=dict)


class EstimateResult(BaseModel):
    line_items: list[RoyaltyLineItem] = Field(default_factory=list)
    total_low: Decimal = Decimal("0")
    total_high: Decimal = Decimal("0")
    currency: str = "USD"
