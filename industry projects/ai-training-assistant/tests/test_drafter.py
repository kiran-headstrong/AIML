"""Unit tests for ``src.retrieval.drafter``.

Covers the ``ExtractiveDrafter``, ``OllamaDrafter``, ``OpenAIDrafter``,
and the ``draft_answer`` fallback orchestrator.
"""

from __future__ import annotations

import pytest

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
from src.retrieval.drafter import (
    AnswerDraft,
    DrafterUnavailableError,
    ExtractiveDrafter,
    OllamaDrafter,
    OpenAIDrafter,
    draft_answer,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_chunk(text: str, source_file: str = "doc.pdf", page: int | None = 1) -> TextChunk:
    return TextChunk(
        chunk_id=f"{source_file}::{page}::0",
        text=text,
        source_file=source_file,
        doc_type=DocType.PDF,
        page_reference=page,
        section_reference=None,
        topic_tag=None,
        title=None,
    )


def _make_note_chunk(text: str, source_file: str = "sop.md", section: str | None = "Setup") -> TextChunk:
    return TextChunk(
        chunk_id=f"{source_file}::{section}::0",
        text=text,
        source_file=source_file,
        doc_type=DocType.NOTE,
        page_reference=None,
        section_reference=section,
        topic_tag=None,
        title=None,
    )


def _make_screenshot(name: str = "screen.png") -> ScreenshotItem:
    return ScreenshotItem(
        item_id=name,
        file_name=name,
        file_path=f"/imgs/{name}",
        topic_tag="onboarding",
        description="Login screen",
        ocr_text=None,
    )


def _outcome_with_matches(
    confidence: Confidence = Confidence.HIGH,
    text_chunks: list[TextChunk] | None = None,
    screenshot_items: list[ScreenshotItem] | None = None,
) -> RetrievalOutcome:
    chunks = text_chunks or [_make_chunk("Step 1: Open the application.")]
    text_matches = [TextMatch(chunk=c, score=0.8) for c in chunks]
    ss_items = screenshot_items or []
    ss_matches = [ScreenshotMatch(item=s, score=0.7) for s in ss_items]
    return RetrievalOutcome(
        query="How do I start?",
        category=QueryCategory.ONBOARDING,
        text_matches=text_matches,
        screenshot_matches=ss_matches,
        confidence=confidence,
        no_match=False,
    )


def _outcome_no_match() -> RetrievalOutcome:
    return RetrievalOutcome(
        query="Something obscure",
        category=QueryCategory.TROUBLESHOOTING,
        text_matches=[],
        screenshot_matches=[],
        confidence=Confidence.LOW,
        no_match=True,
    )


# ------------------------------------------------------------------ #
# ExtractiveDrafter — matches present
# ------------------------------------------------------------------ #


class TestExtractiveDrafterWithMatches:
    """ExtractiveDrafter when outcome has matches."""

    def test_draft_text_is_nonempty(self):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(_outcome_with_matches())
        assert draft.text.strip() != ""

    def test_draft_text_within_max_lines(self):
        drafter = ExtractiveDrafter(max_lines=6)
        # Use multiple chunks to produce many lines.
        chunks = [_make_chunk(f"Line {i}: some content here.") for i in range(10)]
        outcome = _outcome_with_matches(text_chunks=chunks)
        draft = drafter.draft(outcome)
        non_empty_lines = [ln for ln in draft.text.splitlines() if ln.strip()]
        assert len(non_empty_lines) <= 6

    def test_sources_are_nonempty(self):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(_outcome_with_matches())
        assert len(draft.sources) > 0

    def test_source_refs_reference_actual_chunks(self):
        chunk = _make_chunk("Open the app and click start.", source_file="guide.pdf", page=3)
        outcome = _outcome_with_matches(text_chunks=[chunk])
        drafter = ExtractiveDrafter()
        draft = drafter.draft(outcome)
        assert draft.sources[0].source_file == "guide.pdf"
        assert draft.sources[0].reference == "Page 3"

    def test_source_ref_uses_section_for_notes(self):
        chunk = _make_note_chunk("Follow the SOP.", section="Procedures")
        outcome = _outcome_with_matches(text_chunks=[chunk])
        drafter = ExtractiveDrafter()
        draft = drafter.draft(outcome)
        assert draft.sources[0].reference == "Procedures"

    def test_low_confidence_note_true_when_low(self):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(_outcome_with_matches(confidence=Confidence.LOW))
        assert draft.low_confidence_note is True

    def test_low_confidence_note_false_when_high(self):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(_outcome_with_matches(confidence=Confidence.HIGH))
        assert draft.low_confidence_note is False

    def test_low_confidence_note_false_when_medium(self):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(_outcome_with_matches(confidence=Confidence.MEDIUM))
        assert draft.low_confidence_note is False

    def test_draft_text_grounded_in_chunks(self):
        """The draft text should only contain content from the chunks."""
        chunk = _make_chunk("Navigate to Settings > Preferences.")
        outcome = _outcome_with_matches(text_chunks=[chunk])
        drafter = ExtractiveDrafter()
        draft = drafter.draft(outcome)
        # The draft text should be derived from the chunk text.
        assert "Settings" in draft.text or "Preferences" in draft.text

    def test_screenshot_sources_included(self):
        ss = _make_screenshot("login.png")
        outcome = _outcome_with_matches(screenshot_items=[ss])
        drafter = ExtractiveDrafter()
        draft = drafter.draft(outcome)
        source_files = [s.source_file for s in draft.sources]
        assert "login.png" in source_files


# ------------------------------------------------------------------ #
# ExtractiveDrafter — no-match
# ------------------------------------------------------------------ #


class TestExtractiveDrafterNoMatch:
    """ExtractiveDrafter when outcome is a no-match (Req 9.3)."""

    def test_no_match_text(self):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(_outcome_no_match())
        assert "no supporting content" in draft.text.lower()

    def test_no_match_sources_empty(self):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(_outcome_no_match())
        assert draft.sources == []

    def test_no_match_low_confidence_note_false(self):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(_outcome_no_match())
        assert draft.low_confidence_note is False


# ------------------------------------------------------------------ #
# OllamaDrafter — unavailability
# ------------------------------------------------------------------ #


class TestOllamaDrafter:
    """OllamaDrafter raises DrafterUnavailableError on connection failure."""

    def test_raises_on_connection_error(self):
        drafter = OllamaDrafter(endpoint="http://localhost:99999")
        with pytest.raises(DrafterUnavailableError):
            drafter.draft(_outcome_with_matches())


# ------------------------------------------------------------------ #
# OpenAIDrafter — unavailability
# ------------------------------------------------------------------ #


class TestOpenAIDrafter:
    """OpenAIDrafter raises DrafterUnavailableError on failure."""

    def test_raises_on_missing_api_key(self):
        drafter = OpenAIDrafter(api_key="invalid-key")
        with pytest.raises(DrafterUnavailableError):
            drafter.draft(_outcome_with_matches())


# ------------------------------------------------------------------ #
# draft_answer fallback orchestrator
# ------------------------------------------------------------------ #


class _FailingDrafter:
    """A drafter that always fails."""

    def draft(self, outcome: RetrievalOutcome) -> AnswerDraft:
        raise DrafterUnavailableError("always fails")


class _UnexpectedErrorDrafter:
    """A drafter that raises a non-DrafterUnavailableError."""

    def draft(self, outcome: RetrievalOutcome) -> AnswerDraft:
        raise RuntimeError("unexpected boom")


class TestDraftAnswerFallback:
    """The ``draft_answer`` helper orchestrates fallback to extractive."""

    def test_uses_primary_when_available(self):
        called = []

        class _TrackingDrafter:
            def draft(self, outcome: RetrievalOutcome) -> AnswerDraft:
                called.append(True)
                return AnswerDraft(text="From primary", sources=[], low_confidence_note=False)

        result = draft_answer(_outcome_with_matches(), primary_drafter=_TrackingDrafter())
        assert result.text == "From primary"
        assert called

    def test_falls_back_on_drafter_unavailable(self):
        result = draft_answer(_outcome_with_matches(), primary_drafter=_FailingDrafter())
        # Should get a valid extractive draft, not an error.
        assert isinstance(result, AnswerDraft)
        assert result.text.strip() != ""

    def test_falls_back_on_unexpected_error(self):
        result = draft_answer(_outcome_with_matches(), primary_drafter=_UnexpectedErrorDrafter())
        assert isinstance(result, AnswerDraft)
        assert result.text.strip() != ""

    def test_no_primary_uses_extractive(self):
        result = draft_answer(_outcome_with_matches(), primary_drafter=None)
        assert isinstance(result, AnswerDraft)
        assert result.text.strip() != ""

    def test_fallback_on_no_match(self):
        result = draft_answer(_outcome_no_match(), primary_drafter=_FailingDrafter())
        assert "no supporting content" in result.text.lower()
        assert result.sources == []


# ------------------------------------------------------------------ #
# Property-based test: Property 12 — Answer drafts are grounded
# Feature: internal-training-content-search, Property 12: Answer drafts are grounded
# ------------------------------------------------------------------ #

from hypothesis import given, settings
from tests.conftest import st_retrieval_outcomes


class TestProperty12GroundedAnswerDrafts:
    """Property 12: Answer drafts are grounded.

    **Validates: Requirements 9.1, 9.2, 9.3, 11.2**

    For ANY RetrievalOutcome the ExtractiveDrafter must produce a draft where:
      a) The text has at most 6 non-empty lines
      b) Matches present ⇒ non-empty sources referencing actual items,
         text drawn only from retrieved content
      c) No-match ⇒ "no supporting content", no sources, no guidance
      d) Low confidence ⇒ low_confidence_note is True
    """

    _SCREENSHOT_FALLBACK = "See the referenced screenshots for details."

    @given(outcome=st_retrieval_outcomes())
    @settings(max_examples=100, deadline=None)
    def test_grounded_answer_drafts(self, outcome):
        drafter = ExtractiveDrafter()
        draft = drafter.draft(outcome)

        # (a) At most 6 non-empty lines (Req 9.1)
        non_empty_lines = [ln for ln in draft.text.splitlines() if ln.strip()]
        assert len(non_empty_lines) <= 6, (
            f"Draft has {len(non_empty_lines)} non-empty lines, expected <= 6"
        )

        if outcome.no_match:
            # (c) No-match ⇒ "no supporting content", no sources (Req 9.3)
            assert "no supporting content" in draft.text.lower(), (
                "No-match draft must state 'no supporting content'"
            )
            assert draft.sources == [], (
                "No-match draft must have no sources"
            )
            # No-match always returns low_confidence_note=False per implementation
            assert draft.low_confidence_note is False, (
                "No-match draft must have low_confidence_note=False"
            )
        else:
            # (b) Matches present ⇒ non-empty sources referencing actual items
            has_text_matches = len(outcome.text_matches) > 0
            has_screenshot_matches = len(outcome.screenshot_matches) > 0

            if has_text_matches or has_screenshot_matches:
                assert len(draft.sources) > 0, (
                    "Draft with matches must have non-empty sources"
                )

                # Collect all actual source files from the outcome
                actual_text_source_files = {
                    m.chunk.source_file for m in outcome.text_matches
                }
                actual_screenshot_source_files = {
                    m.item.file_name for m in outcome.screenshot_matches
                }
                all_source_files = actual_text_source_files | actual_screenshot_source_files

                # Each source ref must reference an actual retrieved item
                for src_ref in draft.sources:
                    assert src_ref.source_file in all_source_files, (
                        f"Source ref '{src_ref.source_file}' does not reference "
                        f"an actual retrieved item. Valid: {all_source_files}"
                    )

                # Text drawn only from retrieved content: each non-empty line
                # must appear as a substring of at least one chunk's text or a
                # screenshot's description/ocr/topic, OR be the fixed screenshot
                # fallback string.
                all_chunk_texts = [
                    m.chunk.text for m in outcome.text_matches
                ]
                all_ss_texts = []
                for m in outcome.screenshot_matches:
                    it = m.item
                    for val in (it.description, it.ocr_text, it.topic_tag):
                        if val:
                            all_ss_texts.append(val)
                            all_ss_texts.append(val.replace("_", " "))
                grounding_texts = all_chunk_texts + all_ss_texts
                for line in non_empty_lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # The fallback text for screenshot-only outcomes
                    if stripped == self._SCREENSHOT_FALLBACK.strip():
                        continue
                    if stripped == "See the referenced screenshots below for details.":
                        continue
                    # Check if line is grounded in any chunk or screenshot text
                    # (the drafter may truncate with "…", so strip that)
                    check_line = stripped.rstrip("…")
                    found = any(
                        check_line in gt or gt in check_line for gt in grounding_texts
                    )
                    assert found, (
                        f"Draft line '{stripped}' is not grounded in any "
                        f"retrieved chunk or screenshot text"
                    )

            # (d) Low confidence ⇒ low_confidence_note is True (Req 11.2)
            if outcome.confidence == Confidence.LOW:
                assert draft.low_confidence_note is True, (
                    "Draft with Low confidence must have low_confidence_note=True"
                )


# ------------------------------------------------------------------ #
# Property-based test: Property 13 — Answer drafting falls back to grounded extraction
# Feature: internal-training-content-search, Property 13: Answer drafting falls back to grounded extraction
# ------------------------------------------------------------------ #


class TestProperty13DrafterFallback:
    """Property 13: Answer drafting falls back to grounded extraction.

    **Validates: Requirements 12.3**

    For ANY RetrievalOutcome, when the primary drafter is unavailable or raises,
    ``draft_answer()`` still returns a valid ``AnswerDraft`` (not an error) that
    satisfies the same grounding rules as the extractive drafter:
      a) At most 6 non-empty lines
      b) Matches present ⇒ non-empty sources, text drawn from retrieved content
      c) No-match ⇒ "no supporting content" text, empty sources
      d) Low confidence ⇒ low_confidence_note True
    """

    _SCREENSHOT_FALLBACK = "See the referenced screenshots for details."

    def _assert_grounded(self, draft: AnswerDraft, outcome: RetrievalOutcome) -> None:
        """Shared assertions verifying the fallback draft is properly grounded."""

        # (a) At most 6 non-empty lines
        non_empty_lines = [ln for ln in draft.text.splitlines() if ln.strip()]
        assert len(non_empty_lines) <= 6, (
            f"Fallback draft has {len(non_empty_lines)} non-empty lines, expected <= 6"
        )

        if outcome.no_match:
            # (c) No-match ⇒ "no supporting content", empty sources
            assert "no supporting content" in draft.text.lower(), (
                "No-match fallback draft must state 'no supporting content'"
            )
            assert draft.sources == [], (
                "No-match fallback draft must have no sources"
            )
            assert draft.low_confidence_note is False, (
                "No-match fallback draft must have low_confidence_note=False"
            )
        else:
            has_text = len(outcome.text_matches) > 0
            has_screenshots = len(outcome.screenshot_matches) > 0

            if has_text or has_screenshots:
                # (b) Matches present ⇒ non-empty sources referencing actual items
                assert len(draft.sources) > 0, (
                    "Fallback draft with matches must have non-empty sources"
                )

                actual_text_files = {m.chunk.source_file for m in outcome.text_matches}
                actual_ss_files = {m.item.file_name for m in outcome.screenshot_matches}
                all_source_files = actual_text_files | actual_ss_files

                for src_ref in draft.sources:
                    assert src_ref.source_file in all_source_files, (
                        f"Source ref '{src_ref.source_file}' not in actual items: {all_source_files}"
                    )

                # Text drawn from retrieved content (chunks or screenshots)
                all_chunk_texts = [m.chunk.text for m in outcome.text_matches]
                all_ss_texts = []
                for m in outcome.screenshot_matches:
                    it = m.item
                    for val in (it.description, it.ocr_text, it.topic_tag):
                        if val:
                            all_ss_texts.append(val)
                            all_ss_texts.append(val.replace("_", " "))
                grounding_texts = all_chunk_texts + all_ss_texts
                for line in non_empty_lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped == self._SCREENSHOT_FALLBACK.strip():
                        continue
                    if stripped == "See the referenced screenshots below for details.":
                        continue
                    check_line = stripped.rstrip("…")
                    found = any(
                        check_line in gt or gt in check_line for gt in grounding_texts
                    )
                    assert found, (
                        f"Fallback draft line '{stripped}' is not grounded in any chunk or screenshot text"
                    )

            # (d) Low confidence ⇒ low_confidence_note True
            if outcome.confidence == Confidence.LOW:
                assert draft.low_confidence_note is True, (
                    "Fallback draft with Low confidence must have low_confidence_note=True"
                )

    @given(outcome=st_retrieval_outcomes())
    @settings(max_examples=100, deadline=None)
    def test_fallback_on_drafter_unavailable_error(self, outcome: RetrievalOutcome) -> None:
        """When the primary drafter raises DrafterUnavailableError,
        draft_answer() returns a valid grounded AnswerDraft."""
        draft = draft_answer(outcome, primary_drafter=_FailingDrafter())

        assert isinstance(draft, AnswerDraft), (
            "draft_answer must return an AnswerDraft, not propagate an error"
        )
        self._assert_grounded(draft, outcome)

    @given(outcome=st_retrieval_outcomes())
    @settings(max_examples=100, deadline=None)
    def test_fallback_on_unexpected_error(self, outcome: RetrievalOutcome) -> None:
        """When the primary drafter raises an unexpected error (not
        DrafterUnavailableError), draft_answer() still returns a valid
        grounded AnswerDraft."""
        draft = draft_answer(outcome, primary_drafter=_UnexpectedErrorDrafter())

        assert isinstance(draft, AnswerDraft), (
            "draft_answer must return an AnswerDraft on unexpected errors too"
        )
        self._assert_grounded(draft, outcome)
