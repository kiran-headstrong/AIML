"""Property-based and example tests for the :class:`Chunker` chunking utility.

This module validates **Correctness Property 3 (Chunk size is bounded)** for the
size-bounded text chunker used by the PDF and note readers:

    For any extracted text and any configured maximum chunk size ``N > 0``,
    every produced Text_Chunk has length ``<= N``, and the concatenation of
    chunks (ignoring overlap) covers the non-whitespace content of the original
    text.

Coverage is asserted precisely by comparing the ordered sequence of
non-whitespace characters. Because the chunker normalizes whitespace when it
joins units (inserting single spaces and stripping boundaries), the invariant
is expressed over non-whitespace characters rather than raw string equality. The
coverage equality is tested with ``overlap=0`` so that overlap-duplicated
characters do not complicate the comparison; the size bound is exercised across
arbitrary valid overlaps.

Validates: Requirements 2.2, 3.1
Feature: internal-training-content-search, Property 3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

import config
from src.ingestion.chunker import Chunker


def _non_whitespace(text: str) -> str:
    """Return ``text`` with all whitespace characters removed.

    Args:
        text: The source string.

    Returns:
        A string containing only the non-whitespace characters of ``text`` in
        their original order.
    """
    return "".join(c for c in text if not c.isspace())


def _concatenated_non_whitespace(chunks: list[str]) -> str:
    """Return the non-whitespace characters across all ``chunks`` in order.

    Args:
        chunks: The chunks produced by :meth:`Chunker.chunk`.

    Returns:
        The concatenation of every non-whitespace character of every chunk,
        preserving order.
    """
    return "".join(c for chunk in chunks for c in chunk if not c.isspace())


# A text strategy spanning empty, whitespace-only, unicode, punctuation, and
# long inputs so both natural boundaries and hard-splits are exercised.
_text_strategy = st.text(
    alphabet=st.characters(
        min_codepoint=1,
        max_codepoint=0x2FFF,
        blacklist_categories=("Cs",),
    ),
    min_size=0,
    max_size=2000,
)


@settings(max_examples=100, deadline=None)
@given(
    text=_text_strategy,
    data=st.data(),
)
def test_property3_chunk_size_is_bounded(text: str, data: st.DataObject) -> None:
    """Every produced chunk length is ``<= max_chunk_size`` for any valid params.

    Validates: Requirements 2.2, 3.1

    Args:
        text: Arbitrary input text.
        data: Hypothesis data object used to draw dependent parameters
            (``overlap`` must be strictly less than ``max_chunk_size``).
    """
    max_chunk_size = data.draw(st.integers(min_value=1, max_value=1000))
    overlap = data.draw(st.integers(min_value=0, max_value=max_chunk_size - 1))

    chunker = Chunker(max_chunk_size=max_chunk_size, overlap=overlap)
    chunks = chunker.chunk(text)

    for chunk in chunks:
        assert len(chunk) <= max_chunk_size


@settings(max_examples=100, deadline=None)
@given(
    text=_text_strategy,
    max_chunk_size=st.integers(min_value=1, max_value=1000),
)
def test_property3_chunks_cover_non_whitespace_content(
    text: str, max_chunk_size: int
) -> None:
    """With ``overlap=0`` the chunks cover the original non-whitespace content.

    The ordered sequence of non-whitespace characters in the concatenated
    chunks equals the ordered sequence of non-whitespace characters in the
    original text (no loss, no reordering, no duplication).

    Validates: Requirements 2.2, 3.1

    Args:
        text: Arbitrary input text.
        max_chunk_size: The maximum chunk size to configure.
    """
    chunker = Chunker(max_chunk_size=max_chunk_size, overlap=0)
    chunks = chunker.chunk(text)

    assert _concatenated_non_whitespace(chunks) == _non_whitespace(text)


@settings(max_examples=100, deadline=None)
@given(
    whitespace=st.text(alphabet=" \t\n\r\f\v", min_size=0, max_size=50),
    max_chunk_size=st.integers(min_value=1, max_value=1000),
)
def test_property3_empty_or_whitespace_yields_no_chunks(
    whitespace: str, max_chunk_size: int
) -> None:
    """Empty or whitespace-only input produces an empty chunk list.

    Validates: Requirements 3.1

    Args:
        whitespace: A string composed solely of whitespace (possibly empty).
        max_chunk_size: The maximum chunk size to configure.
    """
    chunker = Chunker(max_chunk_size=max_chunk_size, overlap=0)
    assert chunker.chunk(whitespace) == []


# --------------------------------------------------------------------------- #
# Example unit tests (specific cases and boundary behavior)
# --------------------------------------------------------------------------- #
def test_short_text_returns_single_chunk() -> None:
    """Text shorter than the limit is returned unchanged as one chunk."""
    chunker = Chunker(max_chunk_size=100, overlap=0)
    assert chunker.chunk("hello world") == ["hello world"]


def test_oversized_word_is_hard_split_within_bound() -> None:
    """A single word longer than the limit is split into bounded fragments."""
    chunker = Chunker(max_chunk_size=10, overlap=0)
    chunks = chunker.chunk("a" * 25)

    assert chunks == ["aaaaaaaaaa", "aaaaaaaaaa", "aaaaa"]
    assert all(len(chunk) <= 10 for chunk in chunks)


def test_coverage_holds_with_config_defaults() -> None:
    """The size bound and coverage hold using the config default chunk size."""
    text = "\n\n".join(f"Paragraph {i}. " + ("word " * 60) for i in range(5))
    chunker = Chunker(max_chunk_size=config.MAX_CHUNK_SIZE, overlap=0)
    chunks = chunker.chunk(text)

    assert all(len(chunk) <= config.MAX_CHUNK_SIZE for chunk in chunks)
    assert _concatenated_non_whitespace(chunks) == _non_whitespace(text)
