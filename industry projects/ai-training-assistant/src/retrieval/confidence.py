"""Confidence indicator and suggested-next-step logic.

Maps the top similarity score from a retrieval pass to a qualitative
confidence level (High / Medium / Low) and selects a suggested next step
from the fixed set defined in the requirements.

The mapping is **monotonic**: a higher score always yields the same or a
higher confidence level.  When confidence is Low the next step is always
"escalate to the operations lead if unclear" (Req 11.1).

Design reference: Property 11 — Confidence and next-step mapping.
"""

from __future__ import annotations

from src.models import Confidence

# --------------------------------------------------------------------- #
# Fixed next-step labels (Req 10.4)
# --------------------------------------------------------------------- #
NEXT_STEP_HIGH: str = "use the source directly"
NEXT_STEP_MEDIUM: str = "review the original file"
NEXT_STEP_LOW: str = "escalate to the operations lead if unclear"


def assess_confidence(
    top_score: float,
    medium_threshold: float,
    high_threshold: float,
) -> tuple[Confidence, str]:
    """Return ``(confidence, next_step)`` for a given top similarity score.

    Parameters
    ----------
    top_score:
        The highest normalised similarity score among retrieval results.
    medium_threshold:
        Scores **at or above** this value (but below *high_threshold*) are
        Medium confidence.  Default from config: 0.45.
    high_threshold:
        Scores **at or above** this value are High confidence.  Default
        from config: 0.65.

    Returns
    -------
    tuple[Confidence, str]
        A ``(confidence, next_step)`` pair where *confidence* is one of
        ``Confidence.HIGH``, ``Confidence.MEDIUM``, or ``Confidence.LOW``
        and *next_step* is drawn from the fixed set of three labels.

    The mapping is monotonic in *top_score*:

    * ``top_score >= high_threshold``  → High, "use the source directly"
    * ``medium_threshold <= top_score < high_threshold`` → Medium,
      "review the original file"
    * ``top_score < medium_threshold`` → Low, "escalate to the operations
      lead if unclear"
    """
    if top_score >= high_threshold:
        return Confidence.HIGH, NEXT_STEP_HIGH
    if top_score >= medium_threshold:
        return Confidence.MEDIUM, NEXT_STEP_MEDIUM
    return Confidence.LOW, NEXT_STEP_LOW
