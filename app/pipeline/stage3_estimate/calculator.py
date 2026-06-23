"""Per-royalty-type estimator (Phase 2, [P]). The easiest parallel win.

Each royalty type has a DIFFERENT rate base:
  - MECHANICAL (MLC): per-stream.
  - PERFORMANCE (PRO): pooled/survey distribution — a per-stream rate is an approximation.
  - DIGITAL_PERFORMANCE (SoundExchange): per-play on non-interactive only.
'Volume' means streams for some types, spins for others. Output a RANGE with assumptions
exposed and adjustable — no false precision. Rates come from the versioned RateCard table,
never hardcoded; each estimate is stamped with the rate version it used.

Range formula (per royalty type):
    point = annual_volume * rate          (rate read from the RateCard table)
    low   = point * (1 - band)
    high  = point * (1 + band)
`band` is the uncertainty spread (default ±30%). It exists *because* the rates are
placeholders and PRO/SoundExchange distributions are pooled, not per-unit — so a point
figure would be false precision. The band is exposed in each line item's `assumptions`.

Gap -> leak framing:
    Each gap's `registry` maps to a royalty type via REGISTRY_ROYALTY. We aggregate the
    per-registry statuses up to the royalty-type level:
      - NOT_FOUND        -> candidate leak (checked, no registration found): counts to total.
      - REGISTERED       -> not leaking (a confident match exists): excluded from total.
      - UNRESOLVED/AMBIGUOUS/ERROR -> we can't assert anything: excluded from total, flagged.
    A royalty type is a candidate leak iff it has at least one NOT_FOUND and NO REGISTERED.
    total_low/total_high sum ONLY the candidate-leak line items — the headline number is
    "money you're plausibly leaking," not "all royalties you could theoretically earn."
    When `gaps` is empty we never checked registration, so we estimate every type that has
    volume, flag it as unchecked, and report the totals as *potential exposure* (all line
    items) — clearly labelled so the UI doesn't present it as an asserted leak.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RateCard
from app.domain import REGISTRY_ROYALTY, RegistrationStatus, RoyaltyType
from app.pipeline.interfaces import Estimator
from app.schemas.estimate import EstimateResult, RoyaltyAssumptions, RoyaltyLineItem
from app.schemas.gaps import RegistrationResult
from app.schemas.identity import IdentityResult


class RateCardEstimator(Estimator):
    """Estimate the annual leak per royalty type as a low/high range, reading rates from the
    versioned RateCard table (never a literal). Session is injected because the Estimator ABC
    method takes no session — we hold one for the lifetime of the estimator."""

    def __init__(self, session: Session, *, band: Decimal = Decimal("0.30")) -> None:
        self._session = session
        self._band = band

    # --- rate lookup -------------------------------------------------------------------

    def _lookup_rate(
        self, royalty_type: RoyaltyType, rate_version: str | None
    ) -> RateCard | None:
        """Return the applicable RateCard row for a royalty type from the TABLE.

        Pinned: the row whose `version` == rate_version (latest effective_date if a version
        was reissued). Unpinned: the latest row with effective_date <= today. Returns None if
        no rate is seeded for this royalty type (caller skips it rather than inventing one).
        """
        stmt = select(RateCard).where(RateCard.royalty_type == royalty_type)
        if rate_version is not None:
            stmt = stmt.where(RateCard.version == rate_version)
        else:
            stmt = stmt.where(RateCard.effective_date <= dt.date.today())
        # Newest effective rate first; id as a stable tiebreaker.
        stmt = stmt.order_by(RateCard.effective_date.desc(), RateCard.id.desc()).limit(1)
        return self._session.scalars(stmt).first()

    # --- gap -> royalty-type status aggregation ----------------------------------------

    @staticmethod
    def _status_by_royalty_type(
        gaps: list[RegistrationResult],
    ) -> dict[RoyaltyType, set[RegistrationStatus]]:
        """Collapse per-registry gap results into the set of statuses seen per royalty type."""
        by_type: dict[RoyaltyType, set[RegistrationStatus]] = {}
        for gap in gaps:
            royalty_type = REGISTRY_ROYALTY.get(gap.registry)
            if royalty_type is None:
                continue
            by_type.setdefault(royalty_type, set()).add(gap.status)
        return by_type

    @staticmethod
    def _is_candidate_leak(statuses: set[RegistrationStatus]) -> bool:
        """A royalty type leaks iff something was NOT_FOUND and nothing was REGISTERED."""
        return (
            RegistrationStatus.NOT_FOUND in statuses
            and RegistrationStatus.REGISTERED not in statuses
        )

    @staticmethod
    def _leak_note(statuses: set[RegistrationStatus]) -> str:
        if RegistrationStatus.REGISTERED in statuses:
            return "registered — not a leak"
        if RegistrationStatus.NOT_FOUND in statuses:
            return "not found at registry — candidate leak"
        if RegistrationStatus.AMBIGUOUS in statuses:
            return "ambiguous match — flagged for human review, not asserted as a leak"
        if RegistrationStatus.ERROR in statuses:
            return "registry check errored — cannot assert"
        return "registration unresolved — cannot assert a leak"

    # --- estimate ----------------------------------------------------------------------

    def estimate(
        self,
        identity: IdentityResult,
        assumptions: RoyaltyAssumptions,
        gaps: list[RegistrationResult],
    ) -> EstimateResult:
        status_by_type = self._status_by_royalty_type(gaps)
        gaps_checked = bool(gaps)

        line_items: list[RoyaltyLineItem] = []
        total_low = Decimal("0")
        total_high = Decimal("0")

        for royalty_type, volume in assumptions.annual_volume.items():
            card = self._lookup_rate(royalty_type, assumptions.rate_version)
            if card is None:
                # No seeded rate for this type — skip rather than fabricate a number.
                continue

            volume_dec = Decimal(str(volume))
            point = volume_dec * card.rate
            low = point * (Decimal("1") - self._band)
            high = point * (Decimal("1") + self._band)

            statuses = status_by_type.get(royalty_type, set())
            if gaps_checked:
                is_leak = self._is_candidate_leak(statuses)
                leak_note = self._leak_note(statuses)
            else:
                # Registration was never checked: estimate as POTENTIAL exposure, not an
                # asserted leak. We still surface it in the total so the headline reflects
                # what's at stake — clearly labelled below.
                is_leak = True
                leak_note = "registration not checked — potential exposure, not asserted"

            item_assumptions: dict[str, str] = {
                "annual_volume": str(volume),
                "volume_unit": card.unit,
                "rate": str(card.rate),
                "rate_unit": card.unit,
                "band": str(self._band),
                "formula": "low/high = volume * rate * (1 -/+ band)",
                "leak_status": leak_note,
                "counts_toward_total": str(is_leak),
                "registration_checked": str(gaps_checked),
            }
            if royalty_type is RoyaltyType.PERFORMANCE:
                item_assumptions["approximation_note"] = (
                    "PRO performance is a pooled/survey distribution, not per-stream; this "
                    "per-stream rate is an explicit approximation, hence the wide band."
                )

            line_items.append(
                RoyaltyLineItem(
                    royalty_type=royalty_type,
                    low=low,
                    high=high,
                    rate_version=card.version,
                    rate_effective_date=card.effective_date.isoformat(),
                    assumptions=item_assumptions,
                )
            )

            if is_leak:
                total_low += low
                total_high += high

        return EstimateResult(
            line_items=line_items,
            total_low=total_low,
            total_high=total_high,
        )
