"""Answer drafting strategies: extractive, Ollama, and OpenAI.

Provides a pluggable ``AnswerDrafter`` protocol with three concrete strategies:

- ``ExtractiveDrafter`` — default, no external dependencies.  Assembles a
  grounded answer draft (≤ 6 lines) directly from the retrieved text chunks
  with source references attached.  When confidence is Low the draft carries
  a ``low_confidence_note``.  On no-match, emits a fixed "no supporting
  content found" statement with no guidance and no sources (Req 9.3).

- ``OllamaDrafter`` — calls a local Ollama instance.  On *any* error
  (connection, timeout, import, etc.) raises ``DrafterUnavailableError`` so
  the caller can fall back to the extractive drafter (Req 12.3).

- ``OpenAIDrafter`` — calls the OpenAI API.  Same error-handling contract as
  ``OllamaDrafter``.

The ``draft_answer`` helper orchestrates the fallback: try the primary
drafter (if provided), catch ``DrafterUnavailableError``, and return a
grounded extractive draft instead.

Design reference: Property 12 (grounded drafts), Property 13 (fallback).
"""

from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

import config
from src.models import (
    Confidence,
    QueryCategory,
    RetrievalOutcome,
    SourceRef,
    TextMatch,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Exceptions
# ------------------------------------------------------------------ #


class DrafterUnavailableError(Exception):
    """Raised when an external drafter cannot fulfil a request.

    The caller should fall back to ``ExtractiveDrafter``.
    """


# ------------------------------------------------------------------ #
# AnswerDraft dataclass
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class AnswerDraft:
    """A drafted answer grounded in retrieved content.

    Attributes
    ----------
    text:
        The answer text, at most ``config.ANSWER_MAX_LINES`` lines (default 6).
    sources:
        Source references from the retrieved items that support the answer.
    low_confidence_note:
        ``True`` when the retrieval confidence is ``Low`` (Req 11.2).
    """

    text: str
    sources: list[SourceRef] = field(default_factory=list)
    low_confidence_note: bool = False


# ------------------------------------------------------------------ #
# Protocol
# ------------------------------------------------------------------ #


@runtime_checkable
class AnswerDrafter(Protocol):
    """Strategy interface for answer drafting."""

    def draft(self, outcome: RetrievalOutcome) -> AnswerDraft: ...


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

_NO_MATCH_TEXT = "No supporting content was found for this query."


def _build_source_ref(match: TextMatch) -> SourceRef:
    """Build a ``SourceRef`` from a ``TextMatch``."""
    chunk = match.chunk
    # Prefer page_reference for PDFs, section_reference for notes.
    reference: Optional[str] = None
    if chunk.page_reference is not None:
        reference = f"Page {chunk.page_reference}"
    elif chunk.section_reference is not None:
        reference = chunk.section_reference

    # Excerpt: first ~120 chars of the chunk text.
    excerpt = chunk.text[:120].strip()
    if len(chunk.text) > 120:
        excerpt += "…"

    return SourceRef(
        source_file=chunk.source_file,
        reference=reference,
        excerpt=excerpt,
    )


def _truncate_to_max_lines(text: str, max_lines: int) -> str:
    """Ensure *text* has at most *max_lines* non-empty lines."""
    lines = text.splitlines()
    # Keep only non-empty lines up to max_lines.
    kept: list[str] = []
    for line in lines:
        if line.strip():
            kept.append(line)
        else:
            # Preserve blank lines in the count if they appear between content.
            kept.append(line)
        if sum(1 for ln in kept if ln.strip()) > max_lines:
            kept.pop()
            break
    return "\n".join(kept).strip()


# ------------------------------------------------------------------ #
# ExtractiveDrafter (default — Req 12.3 fallback)
# ------------------------------------------------------------------ #


class ExtractiveDrafter:
    """Grounded extractive drafter — no external dependencies.

    Rules (Req 9.1, 9.2, 9.3, 11.2):
    - Text is directly extracted from retrieved chunk text.
    - At most ``config.ANSWER_MAX_LINES`` lines (default 6).
    - Each contributing chunk produces a ``SourceRef``.
    - ``low_confidence_note`` is ``True`` when ``outcome.confidence`` is Low.
    - On no-match: text = fixed statement, sources = [], low_confidence_note = False.
    """

    def __init__(self, max_lines: int | None = None) -> None:
        self._max_lines = max_lines if max_lines is not None else config.ANSWER_MAX_LINES

    def draft(self, outcome: RetrievalOutcome) -> AnswerDraft:
        """Draft an answer grounded only in *outcome* content."""

        # No-match path (Req 9.3): no guidance, no sources.
        if outcome.no_match:
            return AnswerDraft(
                text=_NO_MATCH_TEXT,
                sources=[],
                low_confidence_note=False,
            )

        # Build sources and collect text snippets from text matches.
        # Prefer the highest-scored chunk that contains a substantive answer
        # (longer text, fewer question marks) as the lead snippet.
        sources: list[SourceRef] = []
        snippets: list[str] = []

        for match in outcome.text_matches:
            sources.append(_build_source_ref(match))
            snippets.append(match.chunk.text.strip())

        # Reorder snippets: push question-heavy chunks to the end so the
        # answer starts with substantive content.
        if len(snippets) > 1:
            scored = []
            for i, s in enumerate(snippets):
                question_ratio = s.count("?") / max(len(s), 1)
                # Prefer longer content with fewer questions; keep original
                # order as a tiebreaker (lower index = higher relevance score).
                scored.append((question_ratio, i, s))
            scored.sort(key=lambda t: (t[0], t[1]))
            snippets = [t[2] for t in scored]

        # Also include screenshot matches in sources (they don't contribute
        # text snippets but are valid source references).
        for sm in outcome.screenshot_matches:
            item = sm.item
            excerpt = item.description or item.ocr_text or item.file_name
            sources.append(
                SourceRef(
                    source_file=item.file_name,
                    reference=item.topic_tag,
                    excerpt=excerpt[:120] if excerpt else item.file_name,
                )
            )

        # Collect grounded screenshot snippets (verbatim description/OCR text).
        ss_snippets = []
        for sm in outcome.screenshot_matches:
            item = sm.item
            detail = item.description or item.ocr_text
            if detail:
                ss_snippets.append(detail)

        # For screenshot-focused queries, lead the answer with the screenshot
        # content so it directly answers "show/find screenshot" requests.
        screenshot_intent = (
            outcome.category == QueryCategory.SCREENSHOT_LOOKUP
            and len(ss_snippets) > 0
        )

        # Assemble the draft text, respecting max_lines.
        if screenshot_intent:
            combined = "\n\n".join(ss_snippets + snippets)
            draft_text = _truncate_to_max_lines(combined, self._max_lines)
        elif snippets:
            combined = "\n\n".join(snippets)
            draft_text = _truncate_to_max_lines(combined, self._max_lines)
        elif ss_snippets:
            # Only screenshot matches — use their description/OCR text verbatim.
            draft_text = _truncate_to_max_lines("\n\n".join(ss_snippets), self._max_lines)
        else:
            draft_text = "See the referenced screenshots below for details."

        low_confidence = outcome.confidence == Confidence.LOW

        return AnswerDraft(
            text=draft_text,
            sources=sources,
            low_confidence_note=low_confidence,
        )


# ------------------------------------------------------------------ #
# OllamaDrafter (optional local LLM)
# ------------------------------------------------------------------ #


class OllamaDrafter:
    """Answer drafter backed by a local Ollama instance.

    On **any** error (connection, timeout, import, HTTP, etc.) raises
    ``DrafterUnavailableError`` so the caller can fall back to
    ``ExtractiveDrafter`` (Req 12.3).
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        model: str = "llama3",
        max_lines: int | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._model = model
        self._max_lines = max_lines if max_lines is not None else config.ANSWER_MAX_LINES

    def draft(self, outcome: RetrievalOutcome) -> AnswerDraft:
        """Attempt to draft via Ollama; raise on failure."""
        try:
            import requests  # noqa: F811 — lazy import

            # Build a prompt from the retrieved content.
            context_parts: list[str] = []
            for match in outcome.text_matches:
                context_parts.append(match.chunk.text.strip())
            for sm in outcome.screenshot_matches:
                desc = sm.item.description or sm.item.ocr_text or sm.item.file_name
                context_parts.append(f"[Screenshot: {desc}]")

            context = "\n---\n".join(context_parts) if context_parts else ""
            prompt = (
                f"Based ONLY on the following retrieved content, answer the query "
                f"in at most {self._max_lines} lines. Do not add information not "
                f"present in the content.\n\n"
                f"Query: {outcome.query}\n\n"
                f"Content:\n{context}\n\nAnswer:"
            )

            url = f"{self._endpoint.rstrip('/')}/api/generate"
            response = requests.post(
                url,
                json={"model": self._model, "prompt": prompt, "stream": False},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            raw_text = data.get("response", "").strip()

            # Truncate and build sources.
            draft_text = _truncate_to_max_lines(raw_text, self._max_lines)
            sources = [_build_source_ref(m) for m in outcome.text_matches]
            for sm in outcome.screenshot_matches:
                item = sm.item
                excerpt = item.description or item.ocr_text or item.file_name
                sources.append(
                    SourceRef(
                        source_file=item.file_name,
                        reference=item.topic_tag,
                        excerpt=excerpt[:120] if excerpt else item.file_name,
                    )
                )

            low_confidence = outcome.confidence == Confidence.LOW

            return AnswerDraft(
                text=draft_text,
                sources=sources,
                low_confidence_note=low_confidence,
            )

        except Exception as exc:
            logger.warning("Ollama drafter unavailable: %s", exc)
            raise DrafterUnavailableError(str(exc)) from exc


# ------------------------------------------------------------------ #
# OpenAIDrafter (optional external API)
# ------------------------------------------------------------------ #


class OpenAIDrafter:
    """Answer drafter backed by the OpenAI API.

    On **any** error raises ``DrafterUnavailableError`` so the caller can
    fall back to ``ExtractiveDrafter`` (Req 12.3).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-3.5-turbo",
        max_lines: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_lines = max_lines if max_lines is not None else config.ANSWER_MAX_LINES

    def draft(self, outcome: RetrievalOutcome) -> AnswerDraft:
        """Attempt to draft via OpenAI; raise on failure."""
        try:
            import openai  # noqa: F811 — lazy import

            # Build context from retrieved content.
            context_parts: list[str] = []
            for match in outcome.text_matches:
                context_parts.append(match.chunk.text.strip())
            for sm in outcome.screenshot_matches:
                desc = sm.item.description or sm.item.ocr_text or sm.item.file_name
                context_parts.append(f"[Screenshot: {desc}]")

            context = "\n---\n".join(context_parts) if context_parts else ""
            system_msg = (
                f"You are a grounded answer drafter. Produce an answer of at most "
                f"{self._max_lines} lines based ONLY on the provided content. "
                f"Do not add information not present in the content."
            )
            user_msg = f"Query: {outcome.query}\n\nContent:\n{context}"

            client = openai.OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=500,
                temperature=0.2,
            )
            raw_text = response.choices[0].message.content.strip()

            draft_text = _truncate_to_max_lines(raw_text, self._max_lines)
            sources = [_build_source_ref(m) for m in outcome.text_matches]
            for sm in outcome.screenshot_matches:
                item = sm.item
                excerpt = item.description or item.ocr_text or item.file_name
                sources.append(
                    SourceRef(
                        source_file=item.file_name,
                        reference=item.topic_tag,
                        excerpt=excerpt[:120] if excerpt else item.file_name,
                    )
                )

            low_confidence = outcome.confidence == Confidence.LOW

            return AnswerDraft(
                text=draft_text,
                sources=sources,
                low_confidence_note=low_confidence,
            )

        except Exception as exc:
            logger.warning("OpenAI drafter unavailable: %s", exc)
            raise DrafterUnavailableError(str(exc)) from exc


# ------------------------------------------------------------------ #
# Fallback orchestrator
# ------------------------------------------------------------------ #

_extractive_fallback = ExtractiveDrafter()


def draft_answer(
    outcome: RetrievalOutcome,
    primary_drafter: AnswerDrafter | None = None,
) -> AnswerDraft:
    """Try *primary_drafter*, fall back to ``ExtractiveDrafter`` on failure.

    If *primary_drafter* is ``None`` the extractive drafter is used directly.
    """
    if primary_drafter is not None:
        try:
            return primary_drafter.draft(outcome)
        except DrafterUnavailableError:
            logger.info("Primary drafter unavailable; falling back to extractive.")
        except Exception:
            logger.warning(
                "Unexpected error from primary drafter; falling back to extractive.",
                exc_info=True,
            )
    return _extractive_fallback.draft(outcome)
