"""Reader for TXT and Markdown notes with section-reference derivation.

The :class:`NoteReader` reads a plain-text or Markdown note and splits it into
:class:`NoteSegment` objects, each pairing a body of text with an optional
``section_reference`` derived from Markdown headings (leading ``#`` markers).
For Markdown, the text under each heading becomes a segment tagged with that
heading; content preceding the first heading (and all plain TXT content) becomes
a segment with ``section_reference=None``.

The output is intentionally shaped for the ingestion orchestrator (task 4): each
segment's ``text`` is fed to the shared :class:`~src.ingestion.chunker.Chunker`
and each resulting chunk inherits the segment's ``section_reference`` (Req 3.2).

Design references: Req 3.1 (extract note text for chunking) and Req 3.2 (derive
a section reference from headings/file structure where available).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Markdown ATX heading: 1-6 leading '#' then at least one space then the title.
_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

# Extensions treated as Markdown (heading-aware); everything else is plain text.
_MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})


@dataclass(frozen=True)
class NoteSegment:
    """A section of a note: text plus its optional heading-derived reference."""

    section_reference: str | None  # heading title, or None when unavailable
    text: str


class NoteReader:
    """Read TXT/Markdown notes into section-tagged segments for chunking."""

    def read(self, path: str) -> list[NoteSegment]:
        """Read the note at ``path`` and split it into section segments.

        Markdown files (``.md`` / ``.markdown``) are split on ATX headings, with
        each segment tagged by its enclosing heading title; content before the
        first heading is tagged ``None``. Plain-text files produce a single
        untagged segment containing the whole file. Segments whose text is empty
        or whitespace-only are omitted, so an empty file yields ``[]``.

        Args:
            path: Filesystem path to the ``.txt``, ``.md``, or ``.markdown`` file.

        Returns:
            A list of :class:`NoteSegment` in document order. Empty when the file
            has no non-whitespace content.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            UnicodeDecodeError: If the file cannot be decoded as UTF-8.
        """
        note_path = Path(path)
        if not note_path.is_file():
            raise FileNotFoundError(f"Note file not found: {path}")

        content = note_path.read_text(encoding="utf-8")
        if note_path.suffix.lower() in _MARKDOWN_EXTENSIONS:
            return self._split_markdown(content)
        return self._single_segment(content)

    @staticmethod
    def _single_segment(content: str) -> list[NoteSegment]:
        """Wrap whole-file content as one untagged segment (or none if empty).

        Args:
            content: The full text content of a plain-text note.

        Returns:
            A single-element list with ``section_reference=None``, or an empty
            list when ``content`` is empty or whitespace-only.
        """
        if not content.strip():
            return []
        return [NoteSegment(section_reference=None, text=content)]

    @classmethod
    def _split_markdown(cls, content: str) -> list[NoteSegment]:
        """Split Markdown ``content`` into heading-tagged segments.

        Args:
            content: The full Markdown text.

        Returns:
            Section segments in document order, omitting any whose body is empty
            or whitespace-only.
        """
        segments: list[NoteSegment] = []
        current_heading: str | None = None
        current_lines: list[str] = []

        def flush() -> None:
            body = "\n".join(current_lines)
            if body.strip():
                segments.append(
                    NoteSegment(section_reference=current_heading, text=body)
                )

        for line in content.splitlines():
            match = _ATX_HEADING.match(line)
            if match:
                flush()
                current_heading = match.group(2).strip() or None
                current_lines = []
            else:
                current_lines.append(line)
        flush()
        return segments
