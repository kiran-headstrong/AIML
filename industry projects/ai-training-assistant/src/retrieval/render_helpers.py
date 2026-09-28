"""Pure render helpers for building display payloads from retrieval results.

All functions in this module are **pure** (no Streamlit imports, no side effects)
so they can be unit-tested independently of the UI layer.

They translate the retrieval-layer data models (``TextMatch``,
``ScreenshotMatch``, ``RetrievalOutcome``, ``AnswerDraft``) into plain
dictionaries suitable for presentation by any front-end.

Design reference: Requirements 8.2, 10.1, 10.2, 10.3, 10.4.
"""

from __future__ import annotations

from typing import Any

from src.models import (
    Confidence,
    QueryCategory,
    RetrievalOutcome,
    ScreenshotMatch,
    TextMatch,
)
from src.retrieval.confidence import assess_confidence
from src.retrieval.drafter import AnswerDraft


# --------------------------------------------------------------------- #
# Human-readable category labels (Req 8.2)
# --------------------------------------------------------------------- #
_CATEGORY_LABELS: dict[QueryCategory, str] = {
    QueryCategory.ONBOARDING: "Onboarding",
    QueryCategory.SOP_LOOKUP: "SOP Lookup",
    QueryCategory.SCREENSHOT_LOOKUP: "Screenshot Lookup",
    QueryCategory.POLICY_REFERENCE: "Policy Reference",
    QueryCategory.TROUBLESHOOTING: "Troubleshooting Support",
}

_EXCERPT_MAX_CHARS: int = 200


# --------------------------------------------------------------------- #
# 3. Category label
# --------------------------------------------------------------------- #
def category_label(category: QueryCategory) -> str:
    """Return a human-readable label for *category* (Req 8.2).

    Falls back to the enum's ``value`` when the category is not in the
    lookup table (should never happen for the fixed set).

    Parameters
    ----------
    category:
        One of the five fixed ``QueryCategory`` members.

    Returns
    -------
    str
        A display-friendly label such as ``"SOP Lookup"``.
    """
    return _CATEGORY_LABELS.get(category, category.value)


# --------------------------------------------------------------------- #
# 1. Text reference payload (Req 10.1)
# --------------------------------------------------------------------- #
def render_text_match(match: TextMatch) -> dict[str, Any]:
    """Build the display payload for a single text reference.

    Parameters
    ----------
    match:
        A ``TextMatch`` containing the matched ``TextChunk`` and its score.

    Returns
    -------
    dict
        Keys: ``title``, ``page_or_section``, ``source_file``, ``excerpt``.
    """
    chunk = match.chunk

    # Title: prefer chunk.title, fall back to source_file.
    title = chunk.title if chunk.title else chunk.source_file

    # Page or section reference.
    page_or_section: str | None = None
    if chunk.page_reference is not None:
        page_or_section = f"Page {chunk.page_reference}"
    elif chunk.section_reference is not None:
        page_or_section = chunk.section_reference

    # Excerpt: first ~200 chars of the chunk text.
    text = chunk.text.strip()
    if len(text) > _EXCERPT_MAX_CHARS:
        excerpt = text[:_EXCERPT_MAX_CHARS].rstrip() + "…"
    else:
        excerpt = text

    return {
        "title": title,
        "page_or_section": page_or_section,
        "source_file": chunk.source_file,
        "excerpt": excerpt,
    }


# --------------------------------------------------------------------- #
# 2. Screenshot match payload (Req 10.2)
# --------------------------------------------------------------------- #
def render_screenshot_match(match: ScreenshotMatch) -> dict[str, Any]:
    """Build the display payload for a single screenshot match.

    Parameters
    ----------
    match:
        A ``ScreenshotMatch`` containing the matched ``ScreenshotItem``
        and its score.

    Returns
    -------
    dict
        Keys: ``file_name``, ``topic_tag``, ``metadata_or_ocr_text``.
    """
    item = match.item

    # Prefer the manual description; fall back to OCR text; then file_name.
    metadata_or_ocr_text: str = (
        item.description or item.ocr_text or item.file_name
    )

    return {
        "file_name": item.file_name,
        "topic_tag": item.topic_tag,
        "metadata_or_ocr_text": metadata_or_ocr_text,
    }


# --------------------------------------------------------------------- #
# 4. Full result rendering (Req 8.2, 10.1–10.4)
# --------------------------------------------------------------------- #
def render_full_result(
    outcome: RetrievalOutcome,
    answer: AnswerDraft,
    medium_threshold: float,
    high_threshold: float,
) -> dict[str, Any]:
    """Assemble the complete display payload for the UI.

    Parameters
    ----------
    outcome:
        The ``RetrievalOutcome`` from the retrieval layer.
    answer:
        The ``AnswerDraft`` produced by the drafter.
    medium_threshold:
        The medium-confidence threshold (passed through to
        ``assess_confidence`` to derive the suggested next step).
    high_threshold:
        The high-confidence threshold.

    Returns
    -------
    dict
        A dictionary containing all presentation data:

        - ``text_references``: list of text-match payloads (Req 10.1)
        - ``screenshot_matches``: list of screenshot-match payloads (Req 10.2)
        - ``category_label``: human-readable category (Req 8.2)
        - ``confidence``: the confidence value string (Req 10.3)
        - ``suggested_next_step``: one of three fixed labels (Req 10.4)
        - ``answer_text``: the drafted answer text
        - ``answer_sources``: serialised source references
        - ``low_confidence_note``: whether the draft flagged low confidence
    """
    # Text references
    text_references = [render_text_match(tm) for tm in outcome.text_matches]

    # Screenshot matches
    screenshot_payloads = [
        render_screenshot_match(sm) for sm in outcome.screenshot_matches
    ]

    # Category label (Req 8.2)
    cat_label = category_label(outcome.category)

    # Confidence indicator (Req 10.3) — reuse the value already on outcome.
    confidence_value = outcome.confidence.value  # "High" / "Medium" / "Low"

    # Suggested next step (Req 10.4) — derive from the top score via the
    # same monotonic mapping used during retrieval.
    top_score = 0.0
    all_scores = [tm.score for tm in outcome.text_matches] + [
        sm.score for sm in outcome.screenshot_matches
    ]
    if all_scores:
        top_score = max(all_scores)

    _confidence, suggested_next_step = assess_confidence(
        top_score, medium_threshold, high_threshold
    )

    # Answer sources serialised to plain dicts.
    answer_sources = [
        {
            "source_file": s.source_file,
            "reference": s.reference,
            "excerpt": s.excerpt,
        }
        for s in answer.sources
    ]

    return {
        "text_references": text_references,
        "screenshot_matches": screenshot_payloads,
        "category_label": cat_label,
        "confidence": confidence_value,
        "suggested_next_step": suggested_next_step,
        "answer_text": answer.text,
        "answer_sources": answer_sources,
        "low_confidence_note": answer.low_confidence_note,
    }
