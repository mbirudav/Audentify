"""Fuzzy matching + confidence scoring (Phase 3, [P]). PURE function — zero dependencies.

rapidfuzz on title/writer -> a confidence score and band. Low confidence flags for a human
(AMBIGUOUS) instead of asserting a gap. TDD this with synthetic data BEFORE any scraper
exists — a false positive (telling someone they leak when they don't) is the worst outcome,
so the thresholds here are the highest-value test in the codebase.
"""

from __future__ import annotations

from app.domain import ConfidenceBand


def score_match(query: str, candidate: str) -> float:
    raise NotImplementedError("Phase 3: rapidfuzz similarity -> 0..1 confidence score.")


def band_for_score(score: float) -> ConfidenceBand:
    raise NotImplementedError("Phase 3: map a score to HIGH/MEDIUM/LOW via thresholds.")
