"""Fuzzy-matching tests (Phase 3). The highest-value UNIT test in the codebase: confidence
thresholds and false-positive avoidance. TDD'd with synthetic data before any scraper
exists — telling someone they leak money when they don't is the worst failure mode.

The binding contract these tests pin:
  * an exact title is HIGH (the caller may assert REGISTERED);
  * a near-miss (extra word / reordered) is NOT HIGH — it lands MEDIUM/LOW so the caller
    marks it AMBIGUOUS and flags a human, never asserting a gap;
  * a clearly different string is LOW (treated as "no match").
"""

from __future__ import annotations

import pytest

from app.domain import ConfidenceBand
from app.pipeline.stage2_gaps.matching import (
    HIGH_THRESHOLD,
    MEDIUM_THRESHOLD,
    band_for_score,
    score_match,
)


def test_score_is_normalized_0_to_1():
    # rapidfuzz is 0..100; score_match must hand back 0..1 for the CONFIDENCE column.
    assert 0.0 <= score_match("anything", "anything else") <= 1.0
    assert score_match("Midnight City", "Midnight City") == pytest.approx(1.0)


def test_exact_title_is_high_confidence():
    score = score_match("Midnight City", "Midnight City")
    assert score >= HIGH_THRESHOLD
    assert band_for_score(score) is ConfidenceBand.HIGH


def test_case_and_whitespace_insensitive():
    # "MIDNIGHT  city" must match "Midnight City" — registries vary on case/spacing.
    score = score_match("MIDNIGHT  city", "Midnight City")
    assert band_for_score(score) is ConfidenceBand.HIGH


@pytest.mark.parametrize(
    "candidate",
    [
        "Midnight City Lights",       # extra word appended
        "Remastered Midnight City",   # reordered + extra word
    ],
)
def test_near_miss_is_flagged_not_asserted(candidate):
    # THE point of the suite: a near-miss must NOT reach HIGH, so the caller can only ever
    # mark it AMBIGUOUS (flag a human) — never assert a confident match / a gap.
    score = score_match("Midnight City", candidate)
    band = band_for_score(score)
    assert band is not ConfidenceBand.HIGH
    assert band in (ConfidenceBand.MEDIUM, ConfidenceBand.LOW)


def test_clearly_different_is_low():
    score = score_match("Midnight City", "Daylight Town")
    assert score < MEDIUM_THRESHOLD
    assert band_for_score(score) is ConfidenceBand.LOW


def test_empty_inputs_score_zero_and_low():
    # An empty candidate is never a confident match (don't assert a gap on nothing).
    assert score_match("", "Midnight City") == 0.0
    assert score_match("Midnight City", "   ") == 0.0
    assert band_for_score(0.0) is ConfidenceBand.LOW


def test_band_thresholds_are_ordered_and_strict():
    # Pin the threshold contract so a future "relax HIGH" can't silently re-enable false
    # positives without a failing test.
    assert MEDIUM_THRESHOLD < HIGH_THRESHOLD
    assert band_for_score(HIGH_THRESHOLD) is ConfidenceBand.HIGH
    assert band_for_score(HIGH_THRESHOLD - 0.001) is ConfidenceBand.MEDIUM
    assert band_for_score(MEDIUM_THRESHOLD) is ConfidenceBand.MEDIUM
    assert band_for_score(MEDIUM_THRESHOLD - 0.001) is ConfidenceBand.LOW
