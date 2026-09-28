"""Size-bounded text chunking utility shared by the PDF and note readers.

The :class:`Chunker` splits extracted text into segments that never exceed a
configured maximum size, preferring natural boundaries (paragraphs, then
sentences, then words) and hard-splitting only when a single unit still exceeds
the limit. It optionally prepends up to ``overlap`` characters of the preceding
chunk's content to each subsequent chunk to preserve context across boundaries.

Design references: Req 2.2, 3.1 and Correctness Property 3 (chunk size is
bounded, and the concatenation of chunks — ignoring overlap — covers the
non-whitespace content of the original text).
"""

from __future__ import annotations

import re

# Split on blank-line paragraph boundaries (one or more lines that are empty or
# whitespace-only), keeping this deliberately simple and deterministic.
_PARAGRAPH_BOUNDARY = re.compile(r"\n[ \t]*\n")

# Split a paragraph into sentences after ., !, or ? followed by whitespace.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# Any run of whitespace, used to break an oversized sentence on word boundaries.
_WHITESPACE = re.compile(r"\s+")


class Chunker:
    """Split text into size-bounded segments on natural boundaries.

    Attributes:
        max_chunk_size: The maximum length (in characters) of any produced chunk.
        overlap: The number of characters of preceding content prepended to each
            chunk after the first (0 disables overlap).
    """

    def __init__(self, max_chunk_size: int, overlap: int = 0) -> None:
        """Initialize the chunker.

        Args:
            max_chunk_size: Maximum number of characters per chunk. Must be > 0.
            overlap: Number of characters of preceding content to repeat at the
                start of each subsequent chunk. Must be >= 0 and strictly less
                than ``max_chunk_size`` to guarantee forward progress.

        Raises:
            ValueError: If ``max_chunk_size`` is not positive, ``overlap`` is
                negative, or ``overlap`` is greater than or equal to
                ``max_chunk_size``.
        """
        if max_chunk_size <= 0:
            raise ValueError("max_chunk_size must be a positive integer")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= max_chunk_size:
            raise ValueError("overlap must be strictly less than max_chunk_size")

        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        """Split ``text`` into segments each ``<= max_chunk_size`` characters.

        Empty or whitespace-only input produces no chunks. Otherwise the text is
        broken on paragraph boundaries, then sentence boundaries, then word
        boundaries, hard-splitting only when a single unit still exceeds the
        limit. When ``overlap`` is positive, each chunk after the first begins
        with up to ``overlap`` trailing characters of the previous chunk.

        Args:
            text: The extracted text to split.

        Returns:
            A list of non-empty text segments, each of length
            ``<= max_chunk_size``. Returns an empty list for empty or
            whitespace-only input.
        """
        if not text or not text.strip():
            return []

        units = self._split_into_units(text)
        base_chunks = self._pack_units(units)
        if self.overlap == 0:
            return base_chunks
        return self._apply_overlap(base_chunks)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _split_into_units(self, text: str) -> list[str]:
        """Break ``text`` into bounded, non-empty units.

        Splits progressively on paragraph, then sentence, then word boundaries,
        and finally performs fixed-width hard splits so that no returned unit
        exceeds ``max_chunk_size``.

        Args:
            text: The text to break into units.

        Returns:
            A list of non-empty units, each of length ``<= max_chunk_size``.
        """
        units: list[str] = []
        for paragraph in _PARAGRAPH_BOUNDARY.split(text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(paragraph) <= self.max_chunk_size:
                units.append(paragraph)
                continue
            units.extend(self._split_paragraph(paragraph))
        return units

    def _split_paragraph(self, paragraph: str) -> list[str]:
        """Split an oversized paragraph on sentence, then word, boundaries.

        Args:
            paragraph: A paragraph longer than ``max_chunk_size``.

        Returns:
            A list of non-empty units, each of length ``<= max_chunk_size``.
        """
        units: list[str] = []
        for sentence in _SENTENCE_BOUNDARY.split(paragraph):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= self.max_chunk_size:
                units.append(sentence)
                continue
            units.extend(self._split_words(sentence))
        return units

    def _split_words(self, sentence: str) -> list[str]:
        """Split an oversized sentence on word boundaries, hard-splitting words.

        Words are accumulated greedily up to ``max_chunk_size``; any single word
        longer than the limit is hard-split into fixed-width fragments.

        Args:
            sentence: A sentence longer than ``max_chunk_size``.

        Returns:
            A list of non-empty units, each of length ``<= max_chunk_size``.
        """
        units: list[str] = []
        current = ""
        for word in _WHITESPACE.split(sentence):
            if not word:
                continue
            if len(word) > self.max_chunk_size:
                if current:
                    units.append(current)
                    current = ""
                units.extend(self._hard_split(word))
                continue
            candidate = f"{current} {word}" if current else word
            if len(candidate) <= self.max_chunk_size:
                current = candidate
            else:
                units.append(current)
                current = word
        if current:
            units.append(current)
        return units

    def _hard_split(self, unit: str) -> list[str]:
        """Break a unit into fixed-width fragments of ``max_chunk_size``.

        Args:
            unit: A string longer than ``max_chunk_size`` with no usable
                internal boundary.

        Returns:
            A list of fragments, each of length ``<= max_chunk_size``.
        """
        size = self.max_chunk_size
        return [unit[i : i + size] for i in range(0, len(unit), size)]

    def _pack_units(self, units: list[str]) -> list[str]:
        """Greedily combine units into chunks bounded by ``max_chunk_size``.

        Consecutive units are joined with a single space where they fit; a unit
        that would overflow the current chunk starts a new one. Each unit is
        already guaranteed to fit within the limit on its own.

        Args:
            units: Non-empty units, each of length ``<= max_chunk_size``.

        Returns:
            A list of non-empty chunks, each of length ``<= max_chunk_size``.
        """
        chunks: list[str] = []
        current = ""
        for unit in units:
            candidate = f"{current} {unit}" if current else unit
            if len(candidate) <= self.max_chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = unit
        if current:
            chunks.append(current)
        return chunks

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """Prepend trailing context from each chunk onto the next.

        Each chunk after the first is prefixed with up to ``overlap`` characters
        taken from the end of the *original* preceding chunk. If adding the
        overlap would exceed ``max_chunk_size``, the overlap is trimmed so the
        size bound is never violated.

        Args:
            chunks: Base chunks, each of length ``<= max_chunk_size``.

        Returns:
            Chunks with overlap applied, each still of length
            ``<= max_chunk_size``.
        """
        if len(chunks) <= 1:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            body = chunks[i]
            # Available room for prepended overlap while respecting the bound.
            room = self.max_chunk_size - len(body)
            if room <= 0:
                result.append(body)
                continue
            overlap_len = min(self.overlap, room)
            prefix = chunks[i - 1][-overlap_len:]
            result.append(f"{prefix}{body}")
        return result
