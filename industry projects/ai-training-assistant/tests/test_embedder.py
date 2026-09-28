"""Example unit tests for the Embedder (Req 6.1).

These exercise the *real* ``all-MiniLM-L6-v2`` model, so they are marked
``slow`` and skip gracefully when sentence-transformers or the model itself is
unavailable (e.g., not installed, or offline with an empty cache).
"""

from __future__ import annotations

import pytest

pytest.importorskip(
    "sentence_transformers",
    reason="sentence-transformers not installed; skipping real-model embedder tests.",
)

from src.index.embedder import Embedder, EmbedderModelUnavailableError

# Expected embedding dimensionality for all-MiniLM-L6-v2.
_EXPECTED_DIM = 384


@pytest.fixture(scope="module")
def embedder() -> Embedder:
    """Provide an Embedder, skipping the module if the model cannot load offline."""
    instance = Embedder()
    try:
        # Trigger a load to fail fast (and skip) when the model is unavailable.
        instance.embed_query("warm up")
    except EmbedderModelUnavailableError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Embedding model unavailable (offline / not cached): {exc}")
    return instance


@pytest.mark.slow
def test_embed_query_returns_384_dim_vector(embedder: Embedder) -> None:
    """A single query embeds to a 384-dimensional float vector (Req 6.1)."""
    vector = embedder.embed_query("How do I reset my password?")

    assert isinstance(vector, list)
    assert len(vector) == _EXPECTED_DIM
    assert all(isinstance(value, float) for value in vector)


@pytest.mark.slow
def test_embed_batch_returns_one_384_dim_vector_per_text(embedder: Embedder) -> None:
    """Batch embedding returns one 384-dim vector per input text (Req 6.1)."""
    texts = ["onboarding checklist", "policy on refunds", "reset the router"]

    vectors = embedder.embed(texts)

    assert len(vectors) == len(texts)
    assert all(len(vector) == _EXPECTED_DIM for vector in vectors)


@pytest.mark.slow
def test_embed_empty_list_returns_empty(embedder: Embedder) -> None:
    """Embedding an empty batch yields an empty result without loading work."""
    assert embedder.embed([]) == []


@pytest.mark.slow
def test_embedding_is_deterministic_for_identical_input(embedder: Embedder) -> None:
    """Identical input yields identical embeddings across calls (Req 6.1)."""
    text = "Where is the SOP for closing a ticket?"

    first = embedder.embed_query(text)
    second = embedder.embed_query(text)

    assert first == second
