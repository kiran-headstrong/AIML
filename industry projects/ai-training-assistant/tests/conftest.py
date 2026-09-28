"""Shared pytest configuration for the test suite.

Ensures the project root (the directory that contains ``config.py`` and the
``src`` package) is importable so tests can use absolute imports such as
``from src.ingestion.chunker import Chunker`` and ``import config`` regardless
of the directory pytest is invoked from.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The project root is the parent of this ``tests`` directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# --------------------------------------------------------------------------- #
# Test doubles and Hypothesis strategies for the retrieval layer (Task 7.1)
# --------------------------------------------------------------------------- #
import hashlib
import struct
from dataclasses import field
from typing import Optional

from hypothesis import strategies as st

from src.index.vector_index import IndexEntry, Match
from src.models import (
    Confidence,
    DocType,
    QueryCategory,
    RetrievalConfig,
    RetrievalOutcome,
    ScreenshotItem,
    ScreenshotMatch,
    TextChunk,
    TextMatch,
)

# --------------------------------------------------------------------------- #
# Fake Embedder — deterministic, no real ML model (Req 7.1)
# --------------------------------------------------------------------------- #
_EMBED_DIM = 384  # matches all-MiniLM-L6-v2 output dimension


class FakeEmbedder:
    """A deterministic embedder that always produces the same 384-dim vector for
    the same input text, without loading any real ML model.

    The vector is derived by hashing the text with SHA-512 and unpacking the
    digest bytes into 384 floats in ``[-1, 1]``.  This is *not* semantically
    meaningful but guarantees:
      - identical text → identical vector  (determinism)
      - different text → (overwhelmingly) different vector  (collision-resistant)
      - 384-dimensional output  (shape parity with the real model)
    """

    @staticmethod
    def _hash_to_vector(text: str) -> list[float]:
        """Map ``text`` to a deterministic 384-dimensional vector."""
        # SHA-512 gives 64 bytes.  We need 384 floats.  Rehash in rounds.
        raw = b""
        seed = text.encode("utf-8", errors="replace")
        counter = 0
        while len(raw) < _EMBED_DIM * 2:  # 2 bytes per float entry
            raw += hashlib.sha512(seed + struct.pack(">I", counter)).digest()
            counter += 1
        # Take 384 unsigned shorts and map to [-1, 1].
        values: list[float] = []
        for i in range(_EMBED_DIM):
            (u16,) = struct.unpack_from(">H", raw, i * 2)
            values.append((u16 / 65535.0) * 2.0 - 1.0)
        return values

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed a list of texts deterministically."""
        if not texts:
            return []
        return [self._hash_to_vector(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query deterministically."""
        return self._hash_to_vector(query)


# --------------------------------------------------------------------------- #
# Fake VectorIndex — in-memory, sorted-by-score (Req 7.2)
# --------------------------------------------------------------------------- #

class FakeVectorIndex:
    """An in-memory ``VectorIndex`` that stores ``IndexEntry`` items and returns
    ``Match`` items sorted by descending score.

    Score computation uses the *cosine similarity* between the query vector and
    each stored vector, clamped to ``[0, 1]``.  This keeps the fake
    behaviourally close to the real Chroma backend.
    """

    def __init__(self) -> None:
        self._entries: dict[str, IndexEntry] = {}

    # -- VectorIndex protocol methods ----------------------------------------

    def upsert(self, entries: list[IndexEntry]) -> None:
        for entry in entries:
            self._entries[entry.chunk_id] = entry

    def search(self, query_vec: list[float], top_k: int) -> list[Match]:
        if top_k <= 0 or not self._entries:
            return []
        matches: list[Match] = []
        for entry in self._entries.values():
            score = self._cosine_similarity(query_vec, entry.vector)
            matches.append(Match(chunk_id=entry.chunk_id, score=score))
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]

    def persist(self) -> None:
        pass  # in-memory only

    @classmethod
    def load(cls, path: str) -> "FakeVectorIndex":
        return cls()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity clamped to ``[0, 1]``."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        sim = dot / (norm_a * norm_b)
        # Clamp to [0, 1] (cosine can be negative for opposed vectors).
        return max(0.0, min(1.0, sim))


# --------------------------------------------------------------------------- #
# Hypothesis strategies
# --------------------------------------------------------------------------- #

# --- Text body strategy (Property 3, 10) ------------------------------------

def st_text_body() -> st.SearchStrategy[str]:
    """Random text bodies: empty, whitespace-only, unicode, long strings."""
    return st.one_of(
        st.just(""),
        st.just("   "),
        st.just("\t\n  \r"),
        st.text(min_size=0, max_size=3000),
        # Intentionally include printable-ascii-heavy strings alongside unicode.
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z", "S"),
            ),
            min_size=0,
            max_size=500,
        ),
    )


# --- Text doc types (only PDF and NOTE for text chunks) ----------------------

_TEXT_DOC_TYPES = [DocType.PDF, DocType.NOTE]
_optional_text = st.one_of(st.none(), st.text(min_size=1, max_size=40))


# --- TextChunk strategy (Property 4, 6, 7) ----------------------------------

@st.composite
def st_text_chunks(draw: st.DrawFn) -> list[TextChunk]:
    """Generate a list of ``TextChunk`` items with unique ``chunk_id``s."""
    ids = draw(
        st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=8, unique=True)
    )
    chunks: list[TextChunk] = []
    for chunk_id in ids:
        chunks.append(
            TextChunk(
                chunk_id=chunk_id,
                text=draw(st.text(min_size=1, max_size=200)),
                source_file=draw(st.text(min_size=1, max_size=40)),
                doc_type=draw(st.sampled_from(_TEXT_DOC_TYPES)),
                page_reference=draw(st.one_of(st.none(), st.integers(1, 500))),
                section_reference=draw(_optional_text),
                topic_tag=draw(_optional_text),
                title=draw(_optional_text),
            )
        )
    return chunks


# --- ScreenshotItem strategy (Property 5, 6, 7) -----------------------------

@st.composite
def st_screenshot_items(draw: st.DrawFn) -> list[ScreenshotItem]:
    """Generate a list of ``ScreenshotItem`` items with unique ``item_id``s."""
    ids = draw(
        st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=8, unique=True)
    )
    items: list[ScreenshotItem] = []
    for item_id in ids:
        items.append(
            ScreenshotItem(
                item_id=item_id,
                file_name=draw(st.text(min_size=1, max_size=40)),
                file_path=draw(st.text(min_size=1, max_size=80)),
                topic_tag=draw(_optional_text),
                description=draw(_optional_text),
                ocr_text=draw(_optional_text),
            )
        )
    return items


# --- Scored IndexEntry strategy (Property 7, 8, 11) -------------------------

@st.composite
def st_index_entries(
    draw: st.DrawFn,
    min_score: float = 0.0,
    max_score: float = 1.0,
) -> list[tuple[IndexEntry, float]]:
    """Generate a list of ``(IndexEntry, desired_score)`` pairs.

    The ``desired_score`` is a float in ``[min_score, max_score]``.  The
    companion ``FakeVectorIndex`` computes actual cosine similarity from the
    stored vectors, so these scores are *metadata* that tests can use to set up
    expectations (e.g., by constructing vectors that yield specific scores).
    """
    ids = draw(
        st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=10, unique=True)
    )
    entries: list[tuple[IndexEntry, float]] = []
    for chunk_id in ids:
        score = draw(st.floats(min_value=min_score, max_value=max_score))
        vec = draw(
            st.lists(
                st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
                min_size=_EMBED_DIM,
                max_size=_EMBED_DIM,
            )
        )
        entry = IndexEntry(
            chunk_id=chunk_id,
            vector=vec,
            metadata={},
        )
        entries.append((entry, score))
    return entries


# --- Query string strategy (Property 9, 10) ---------------------------------

def st_query_strings() -> st.SearchStrategy[str]:
    """Query strings including whitespace-only and empty variants."""
    return st.one_of(
        st.just(""),
        st.just("   "),
        st.just("\t\n"),
        st.text(min_size=1, max_size=200),
        # Short keyword-like queries.
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
            min_size=1,
            max_size=60,
        ),
    )


# --- RetrievalOutcome strategy (Property 12, 13) ----------------------------

@st.composite
def st_retrieval_outcomes(draw: st.DrawFn) -> RetrievalOutcome:
    """Generate a ``RetrievalOutcome`` spanning match/no-match and all
    confidence levels.  Text and screenshot matches are built from
    ``st_text_chunks`` / ``st_screenshot_items`` with random scores.
    """
    query = draw(st.text(min_size=0, max_size=120))
    category = draw(st.sampled_from(list(QueryCategory)))
    confidence = draw(st.sampled_from(list(Confidence)))

    # Decide match vs. no-match.
    no_match = draw(st.booleans())

    if no_match:
        text_matches: list[TextMatch] = []
        screenshot_matches: list[ScreenshotMatch] = []
    else:
        chunks = draw(st_text_chunks())
        text_matches = [
            TextMatch(
                chunk=c,
                score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
            )
            for c in chunks
        ]
        ss_items = draw(st_screenshot_items())
        screenshot_matches = [
            ScreenshotMatch(
                item=s,
                score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
            )
            for s in ss_items
        ]

    return RetrievalOutcome(
        query=query,
        category=category,
        text_matches=text_matches,
        screenshot_matches=screenshot_matches,
        confidence=confidence,
        no_match=no_match,
    )
