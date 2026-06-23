"""Fuzzy matching + confidence scoring (Phase 3, [P]). PURE functions — only rapidfuzz.

rapidfuzz on title/writer -> a confidence score and band. Low confidence flags for a human
(AMBIGUOUS) instead of asserting a gap. TDD this with synthetic data BEFORE any scraper
exists — a false positive (telling someone they leak money when they don't) is the worst
outcome, so the thresholds here are the highest-value test in the codebase.

Scorer choice: `token_sort_ratio`. It tokenizes and sorts words before comparing, so
"Midnight City (Remastered)" vs "Remastered Midnight City" still scores high while a
genuinely different title scores low. We normalize the 0..100 rapidfuzz scale to 0..1
because the rest of the system (RegistrationResult.confidence_score, the CONFIDENCE
Numeric(5,4) column) speaks 0..1.

Threshold reasoning (false-positive avoidance):
- HIGH (>= 0.90): only a near-exact match. A HIGH band lets the caller assert REGISTERED,
  so the bar is deliberately high — a typo or an extra word must NOT reach it.
- MEDIUM (0.70 .. 0.90): a plausible but uncertain match. The caller marks this AMBIGUOUS
  and flags a human; it never asserts a gap either way.
- LOW (< 0.70): clearly different. Treated as "no candidate matched" by the caller.

The gap between a clean string and a one-word/typo near-miss is what these thresholds
exploit: an exact title lands ~1.0 (HIGH); a near-miss lands in the 0.70..0.90 MEDIUM band;
unrelated strings fall well below 0.70 (LOW). The point is that a near-miss can never be
mistaken for a confident match.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from app.domain import ConfidenceBand

# Tunable thresholds. Kept module-level so the tests can pin them and a future calibration
# pass has one obvious place to adjust. HIGH is intentionally strict (see module docstring).
HIGH_THRESHOLD = 0.90
MEDIUM_THRESHOLD = 0.70


def score_match(query: str, candidate: str) -> float:
    """Similarity of `query` vs `candidate`, normalized to 0..1.

    Case- and whitespace-insensitive (rapidfuzz's token_sort_ratio lowercases-via-sort and
    we strip/normalize first). Empty/whitespace-only inputs score 0.0 — an empty candidate
    is never a confident match.
    """
    q = (query or "").strip()
    c = (candidate or "").strip()
    if not q or not c:
        return 0.0
    # token_sort_ratio is case-sensitive on raw input; normalize case so "ABC" == "abc".
    return fuzz.token_sort_ratio(q.lower(), c.lower()) / 100.0


def band_for_score(score: float) -> ConfidenceBand:
    """Map a 0..1 score to a confidence band via the module thresholds.

    HIGH only at >= 0.90 so a near-miss can never be asserted as a confident match.
    """
    if score >= HIGH_THRESHOLD:
        return ConfidenceBand.HIGH
    if score >= MEDIUM_THRESHOLD:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW
