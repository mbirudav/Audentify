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
from app.domain import REGISTRY_ROYALTY, RegistrationStatus, RegistryName, RoyaltyType
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

    def _applicable_rate_rows(
        self, royalty_type: RoyaltyType, rate_version: str | None
    ) -> list[RateCard]:
        """Return the applicable RateCard rows for a royalty type — the latest-effective row
        PER registry — read from the TABLE.

        A royalty type can span multiple registries (PERFORMANCE = ASCAP + BMI), so we return
        one row per registry rather than arbitrarily picking a single one; the caller blends
        them (mean rate) so the estimate reflects all the relevant collectors, not whichever
        seed row happened to be inserted last. Pinned: rows whose `version` == rate_version.
        Unpinned: rows with effective_date <= today. Empty list if nothing is seeded (the
        caller skips that type rather than inventing a number).
        """
        stmt = select(RateCard).where(RateCard.royalty_type == royalty_type)
        if rate_version is not None:
            stmt = stmt.where(RateCard.version == rate_version)
        else:
            stmt = stmt.where(RateCard.effective_date <= dt.date.today())
        # Newest effective rate first; id as a stable tiebreaker. Keep the first row seen per
        # registry (registry None — a statutory/registry-agnostic rate — is a valid key).
        stmt = stmt.order_by(RateCard.effective_date.desc(), RateCard.id.desc())
        latest_by_registry: dict[RegistryName | None, RateCard] = {}
        for row in self._session.scalars(stmt):
            if row.registry not in latest_by_registry:
                latest_by_registry[row.registry] = row
        return list(latest_by_registry.values())

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
            rate_rows = self._applicable_rate_rows(royalty_type, assumptions.rate_version)
            if not rate_rows:
                # No seeded rate for this type — skip rather than fabricate a number.
                continue

            # Blend across registries (e.g. ASCAP + BMI for PERFORMANCE): the mean of the
            # per-registry rates. The most-recent effective row is the representative we stamp
            # the line item's version/effective_date with (reproducibility).
            rep = max(rate_rows, key=lambda r: (r.effective_date, r.id))
            rate = sum((r.rate for r in rate_rows), Decimal("0")) / Decimal(len(rate_rows))

            volume_dec = Decimal(str(volume))
            point = volume_dec * rate
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
                "volume_unit": rep.unit,
                "rate": str(rate),
                "rate_unit": rep.unit,
                "band": str(self._band),
                "formula": "low/high = volume * rate * (1 -/+ band)",
                "leak_status": leak_note,
                "counts_toward_total": str(is_leak),
                "registration_checked": str(gaps_checked),
            }
            if len(rate_rows) > 1:
                # Be transparent that the rate is a blend across collectors for this type.
                item_assumptions["rate_blended_across"] = ", ".join(
                    sorted(r.registry.value for r in rate_rows if r.registry is not None)
                )
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
                    rate_version=rep.version,
                    rate_effective_date=rep.effective_date.isoformat(),
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
