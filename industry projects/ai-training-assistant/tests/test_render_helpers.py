"""Unit tests for ``src.retrieval.render_helpers``.

Covers the four public helpers: ``render_text_match``, ``render_screenshot_match``,
``category_label``, and ``render_full_result``.

**Validates: Requirements 8.2, 10.1, 10.2**
"""

from __future__ import annotations

from src.models import (
    Confidence,
    DocType,
    QueryCategory,
    RetrievalOutcome,
    ScreenshotItem,
    ScreenshotMatch,
    SourceRef,
    TextChunk,
    TextMatch,
)
from src.retrieval.drafter import AnswerDraft
from src.retrieval.render_helpers import (
    category_label,
    render_full_result,
    render_screenshot_match,
    render_text_match,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_chunk(
    text: str = "Some chunk text.",
    source_file: str = "guide.pdf",
    page: int | None = 1,
    section: str | None = None,
    title: str | None = None,
) -> TextChunk:
    return TextChunk(
        chunk_id=f"{source_file}::{page or section}::0",
        text=text,
        source_file=source_file,
        doc_type=DocType.PDF,
        page_reference=page,
        section_reference=section,
        topic_tag=None,
        title=title,
    )


def _make_text_match(
    text: str = "Some chunk text.",
    source_file: str = "guide.pdf",
    page: int | None = 1,
    section: str | None = None,
    title: str | None = None,
    score: float = 0.8,
) -> TextMatch:
    chunk = _make_chunk(
        text=text,
        source_file=source_file,
        page=page,
        section=section,
        title=title,
    )
    return TextMatch(chunk=chunk, score=score)


def _make_screenshot_item(
    file_name: str = "screen.png",
    topic_tag: str | None = "onboarding",
    description: str | None = "Login screen",
    ocr_text: str | None = None,
) -> ScreenshotItem:
    return ScreenshotItem(
        item_id=file_name,
        file_name=file_name,
        file_path=f"/imgs/{file_name}",
        topic_tag=topic_tag,
        description=description,
        ocr_text=ocr_text,
    )


def _make_screenshot_match(
    file_name: str = "screen.png",
    topic_tag: str | None = "onboarding",
    description: str | None = "Login screen",
    ocr_text: str | None = None,
    score: float = 0.7,
) -> ScreenshotMatch:
    item = _make_screenshot_item(
        file_name=file_name,
        topic_tag=topic_tag,
        description=description,
        ocr_text=ocr_text,
    )
    return ScreenshotMatch(item=item, score=score)


# ------------------------------------------------------------------ #
# 1. render_text_match
# ------------------------------------------------------------------ #


class TestRenderTextMatch:
    """Tests for ``render_text_match`` (Req 10.1)."""

    def test_all_fields_present(self):
        """Returned dict has the four required keys."""
        result = render_text_match(
            _make_text_match(title="Getting Started", text="Step 1: Open the app.")
        )
        assert set(result.keys()) == {"title", "page_or_section", "source_file", "excerpt"}

    def test_title_page_and_text_populated(self):
        """A match with title and page_reference populates all fields."""
        match = _make_text_match(
            title="Getting Started",
            source_file="onboarding.pdf",
            page=5,
            text="Open the application and click Start.",
        )
        result = render_text_match(match)
        assert result["title"] == "Getting Started"
        assert result["page_or_section"] == "Page 5"
        assert result["source_file"] == "onboarding.pdf"
        assert result["excerpt"] == "Open the application and click Start."

    def test_no_title_falls_back_to_source_file(self):
        """When chunk.title is None the title falls back to source_file."""
        match = _make_text_match(title=None, source_file="procedures.pdf")
        result = render_text_match(match)
        assert result["title"] == "procedures.pdf"

    def test_section_reference_instead_of_page(self):
        """When page_reference is None but section_reference is set, use it."""
        match = _make_text_match(
            page=None,
            section="Installation",
            source_file="setup.md",
        )
        result = render_text_match(match)
        assert result["page_or_section"] == "Installation"

    def test_long_text_truncated_with_ellipsis(self):
        """Text longer than 200 chars is truncated and ends with '…'."""
        long_text = "A" * 300
        match = _make_text_match(text=long_text)
        result = render_text_match(match)
        assert len(result["excerpt"]) <= 201  # 200 chars + the '…'
        assert result["excerpt"].endswith("…")


# ------------------------------------------------------------------ #
# 2. render_screenshot_match
# ------------------------------------------------------------------ #


class TestRenderScreenshotMatch:
    """Tests for ``render_screenshot_match`` (Req 10.2)."""

    def test_all_fields_present(self):
        """Returned dict has the three required keys."""
        result = render_screenshot_match(_make_screenshot_match())
        assert set(result.keys()) == {"file_name", "topic_tag", "metadata_or_ocr_text"}

    def test_description_preferred(self):
        """When description is set it is used for metadata_or_ocr_text."""
        result = render_screenshot_match(
            _make_screenshot_match(description="Login screen", ocr_text="username password")
        )
        assert result["metadata_or_ocr_text"] == "Login screen"

    def test_ocr_text_fallback(self):
        """When description is None but ocr_text is set, use ocr_text."""
        result = render_screenshot_match(
            _make_screenshot_match(description=None, ocr_text="username password")
        )
        assert result["metadata_or_ocr_text"] == "username password"

    def test_file_name_fallback(self):
        """When both description and ocr_text are None, use file_name."""
        result = render_screenshot_match(
            _make_screenshot_match(
                file_name="dashboard.png", description=None, ocr_text=None
            )
        )
        assert result["metadata_or_ocr_text"] == "dashboard.png"


# ------------------------------------------------------------------ #
# 3. category_label
# ------------------------------------------------------------------ #


class TestCategoryLabel:
    """Tests for ``category_label`` (Req 8.2)."""

    def test_each_category_returns_human_readable_label(self):
        """Every QueryCategory member maps to a human-readable label that
        is not the raw enum value."""
        for cat in QueryCategory:
            label = category_label(cat)
            assert isinstance(label, str)
            assert len(label) > 0
            # The label should not be the raw enum value (e.g. "sop_lookup")
            assert label != cat.value


# ------------------------------------------------------------------ #
# 4. render_full_result
# ------------------------------------------------------------------ #


class TestRenderFullResult:
    """Tests for ``render_full_result`` (Req 8.2, 10.1–10.4)."""

    def test_all_top_level_keys_present(self):
        """The rendered dict contains all required top-level keys."""
        outcome = RetrievalOutcome(
            query="How do I reset my password?",
            category=QueryCategory.TROUBLESHOOTING,
            text_matches=[_make_text_match(text="Go to Settings.", score=0.75)],
            screenshot_matches=[_make_screenshot_match(score=0.6)],
            confidence=Confidence.HIGH,
            no_match=False,
        )
        answer = AnswerDraft(
            text="Go to Settings.",
            sources=[
                SourceRef(
                    source_file="guide.pdf", reference="Page 1", excerpt="Go to Settings."
                )
            ],
            low_confidence_note=False,
        )
        result = render_full_result(
            outcome, answer, medium_threshold=0.45, high_threshold=0.65
        )

        expected_keys = {
            "text_references",
            "screenshot_matches",
            "category_label",
            "confidence",
            "suggested_next_step",
            "answer_text",
            "answer_sources",
            "low_confidence_note",
        }
        assert set(result.keys()) == expected_keys

    def test_category_label_appears_in_result(self):
        """The category_label in the result matches the human-readable label."""
        outcome = RetrievalOutcome(
            query="onboarding steps",
            category=QueryCategory.ONBOARDING,
            text_matches=[_make_text_match(score=0.7)],
            screenshot_matches=[],
            confidence=Confidence.MEDIUM,
            no_match=False,
        )
        answer = AnswerDraft(text="Welcome aboard.", sources=[], low_confidence_note=False)
        result = render_full_result(
            outcome, answer, medium_threshold=0.45, high_threshold=0.65
        )
        assert result["category_label"] == "Onboarding"
