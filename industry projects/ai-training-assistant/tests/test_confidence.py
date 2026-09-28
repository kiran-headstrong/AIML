"""Unit tests for the confidence and next-step mapping logic.

Covers the three confidence bands (High, Medium, Low), boundary values,
and the requirement that Low confidence always maps to the escalation
next step (Req 11.1).
"""

from __future__ import annotations

from src.models import Confidence
from src.retrieval.confidence import (
    NEXT_STEP_HIGH,
    NEXT_STEP_LOW,
    NEXT_STEP_MEDIUM,
    assess_confidence,
)

# Default thresholds from config / design
MEDIUM = 0.45
HIGH = 0.65


class TestAssessConfidence:
    """Example-based tests for assess_confidence."""

    # ------------------------------------------------------------------ #
    # High confidence band
    # ------------------------------------------------------------------ #
    def test_high_confidence_above_threshold(self) -> None:
        conf, step = assess_confidence(0.80, MEDIUM, HIGH)
        assert conf is Confidence.HIGH
        assert step == NEXT_STEP_HIGH

    def test_high_confidence_at_threshold(self) -> None:
        conf, step = assess_confidence(0.65, MEDIUM, HIGH)
        assert conf is Confidence.HIGH
        assert step == NEXT_STEP_HIGH

    # ------------------------------------------------------------------ #
    # Medium confidence band
    # ------------------------------------------------------------------ #
    def test_medium_confidence_mid_range(self) -> None:
        conf, step = assess_confidence(0.55, MEDIUM, HIGH)
        assert conf is Confidence.MEDIUM
        assert step == NEXT_STEP_MEDIUM

    def test_medium_confidence_at_threshold(self) -> None:
        conf, step = assess_confidence(0.45, MEDIUM, HIGH)
        assert conf is Confidence.MEDIUM
        assert step == NEXT_STEP_MEDIUM

    def test_medium_confidence_just_below_high(self) -> None:
        conf, step = assess_confidence(0.6499, MEDIUM, HIGH)
        assert conf is Confidence.MEDIUM
        assert step == NEXT_STEP_MEDIUM

    # ------------------------------------------------------------------ #
    # Low confidence band
    # ------------------------------------------------------------------ #
    def test_low_confidence_below_medium(self) -> None:
        conf, step = assess_confidence(0.30, MEDIUM, HIGH)
        assert conf is Confidence.LOW
        assert step == NEXT_STEP_LOW

    def test_low_confidence_zero(self) -> None:
        conf, step = assess_confidence(0.0, MEDIUM, HIGH)
        assert conf is Confidence.LOW
        assert step == NEXT_STEP_LOW

    def test_low_confidence_just_below_medium(self) -> None:
        conf, step = assess_confidence(0.4499, MEDIUM, HIGH)
        assert conf is Confidence.LOW
        assert step == NEXT_STEP_LOW

    def test_low_always_escalates(self) -> None:
        """Req 11.1: Low confidence must always suggest escalation."""
        for score in [0.0, 0.10, 0.20, 0.30, 0.44]:
            conf, step = assess_confidence(score, MEDIUM, HIGH)
            assert conf is Confidence.LOW
            assert step == NEXT_STEP_LOW

    # ------------------------------------------------------------------ #
    # Monotonicity
    # ------------------------------------------------------------------ #
    def test_monotonic_across_boundaries(self) -> None:
        """Increasing score ⇒ same or higher confidence level."""
        levels = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
        scores = [0.0, 0.30, 0.44, 0.45, 0.55, 0.64, 0.65, 0.80, 1.0]
        prev_level = -1
        for s in scores:
            conf, _ = assess_confidence(s, MEDIUM, HIGH)
            assert levels[conf] >= prev_level, (
                f"Monotonicity violated at score {s}: got {conf}"
            )
            prev_level = levels[conf]

    # ------------------------------------------------------------------ #
    # Custom thresholds
    # ------------------------------------------------------------------ #
    def test_custom_thresholds(self) -> None:
        """The function respects caller-supplied thresholds, not just defaults."""
        conf, step = assess_confidence(0.50, 0.60, 0.80)
        assert conf is Confidence.LOW
        assert step == NEXT_STEP_LOW

        conf, step = assess_confidence(0.70, 0.60, 0.80)
        assert conf is Confidence.MEDIUM
        assert step == NEXT_STEP_MEDIUM

        conf, step = assess_confidence(0.90, 0.60, 0.80)
        assert conf is Confidence.HIGH
        assert step == NEXT_STEP_HIGH

    # ------------------------------------------------------------------ #
    # Next-step values are from the fixed set
    # ------------------------------------------------------------------ #
    def test_next_step_values_in_fixed_set(self) -> None:
        fixed = {NEXT_STEP_HIGH, NEXT_STEP_MEDIUM, NEXT_STEP_LOW}
        for score in [0.0, 0.45, 0.65, 1.0]:
            _, step = assess_confidence(score, MEDIUM, HIGH)
            assert step in fixed


# --------------------------------------------------------------------------- #
# Property-based tests (Hypothesis)
# --------------------------------------------------------------------------- #
from hypothesis import given, settings, strategies as st


# Feature: internal-training-content-search, Property 11: Confidence and next-step mapping
class TestConfidenceProperty:
    """Property 11: Confidence and next-step mapping — exactly one confidence
    label, monotonic in ``s`` per thresholds, next step in the fixed set, and
    Low ⇒ escalate next step.

    **Validates: Requirements 10.3, 10.4, 11.1**
    """

    FIXED_NEXT_STEPS = {
        "use the source directly",
        "review the original file",
        "escalate to the operations lead if unclear",
    }

    CONFIDENCE_ORDER = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}

    @staticmethod
    @st.composite
    def _ordered_thresholds(draw):
        """Generate ``(medium_threshold, high_threshold)`` with medium <= high,
        both in [0, 1]."""
        a = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
        b = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
        low, high = sorted([a, b])
        return low, high

    @given(
        score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_single_confidence_and_valid_next_step(self, score: float, data) -> None:
        """For any score in [0, 1] and valid thresholds, assess_confidence
        returns exactly one Confidence member and a next step from the fixed set."""
        med, high = data.draw(self._ordered_thresholds())

        conf, step = assess_confidence(score, med, high)

        # Exactly one confidence label (is a member of Confidence enum)
        assert isinstance(conf, Confidence), f"Expected Confidence enum, got {type(conf)}"
        assert conf in list(Confidence)

        # Next step is one of the fixed set
        assert step in self.FIXED_NEXT_STEPS, f"Unexpected next step: {step!r}"

    @given(
        s1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        s2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_monotonicity(self, s1: float, s2: float, data) -> None:
        """If s1 <= s2, then confidence(s1) <= confidence(s2) for the same
        thresholds — the mapping is monotonic in score."""
        med, high = data.draw(self._ordered_thresholds())

        lo, hi = sorted([s1, s2])
        conf_lo, _ = assess_confidence(lo, med, high)
        conf_hi, _ = assess_confidence(hi, med, high)

        assert self.CONFIDENCE_ORDER[conf_lo] <= self.CONFIDENCE_ORDER[conf_hi], (
            f"Monotonicity violated: score {lo} → {conf_lo}, score {hi} → {conf_hi}"
        )

    @given(
        score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_low_implies_escalate(self, score: float, data) -> None:
        """When confidence is Low, next step is ALWAYS 'escalate to the
        operations lead if unclear'."""
        med, high = data.draw(self._ordered_thresholds())

        conf, step = assess_confidence(score, med, high)

        if conf is Confidence.LOW:
            assert step == NEXT_STEP_LOW, (
                f"Low confidence with score={score} got step={step!r}, "
                f"expected {NEXT_STEP_LOW!r}"
            )
