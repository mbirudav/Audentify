"""Per-royalty-type estimator (Phase 2, [P]). The easiest parallel win.

Each royalty type has a DIFFERENT rate base:
  - MECHANICAL (MLC): per-stream.
  - PERFORMANCE (PRO): pooled/survey distribution — a per-stream rate is an approximation.
  - DIGITAL_PERFORMANCE (SoundExchange): per-play on non-interactive only.
'Volume' means streams for some types, spins for others. Output a RANGE with assumptions
exposed and adjustable — no false precision. Rates come from the versioned RateCard table,
never hardcoded; each estimate is stamped with the rate version it used.
"""

from __future__ import annotations

from app.pipeline.interfaces import Estimator
from app.schemas.estimate import EstimateResult, RoyaltyAssumptions
from app.schemas.gaps import RegistrationResult
from app.schemas.identity import IdentityResult


class RateCardEstimator(Estimator):
    def estimate(
        self,
        identity: IdentityResult,
        assumptions: RoyaltyAssumptions,
        gaps: list[RegistrationResult],
    ) -> EstimateResult:
        raise NotImplementedError(
            "Phase 2: per-royalty-type low/high using RateCard rows + assumed volume."
        )
