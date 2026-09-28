"""Property-based tests for the Retriever (Req 6.3, 7.1, 7.2, 7.3).

# Feature: internal-training-content-search, Property 7: Retrieval ranking, limit, and reference consistency
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from src.index.metadata_store import MetadataStore
from src.index.vector_index import IndexEntry
from src.models import RetrievalConfig
from src.retrieval.retriever import Retriever
from tests.conftest import (
    FakeEmbedder,
    FakeVectorIndex,
    st_screenshot_items,
    st_text_chunks,
)


# --------------------------------------------------------------------------- #
# Property 7 — Retrieval ranking, limit, and reference consistency
# --------------------------------------------------------------------------- #


@given(
    chunks=st_text_chunks(),
    screenshots=st_screenshot_items(),
    query=st.text(min_size=1, max_size=100),
    top_k=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=100, deadline=None)
def test_retrieval_ranking_limit_and_reference_consistency(
    chunks,
    screenshots,
    query: str,
    top_k: int,
) -> None:
    """**Validates: Requirements 6.3, 7.1, 7.2, 7.3**

    For ANY set of indexed chunks/screenshots and any non-empty query:
    - Text matches are ordered by descending score
    - Screenshot matches are ordered by descending score
    - Each result set contains at most ``top_k`` items
    - Every returned match id resolves to an actual stored chunk or screenshot
    """
    embedder = FakeEmbedder()

    # --- Set up MetadataStore with chunks and screenshots ---
    store = MetadataStore()
    store.save_chunks(chunks)
    store.save_screenshots(screenshots)

    # --- Set up FakeVectorIndex with entries for all chunks and screenshots ---
    index = FakeVectorIndex()

    chunk_entries = []
    for chunk in chunks:
        vec = embedder.embed_query(chunk.text)
        chunk_entries.append(IndexEntry(chunk_id=chunk.chunk_id, vector=vec))

    screenshot_entries = []
    for item in screenshots:
        # Use description or file_name for embedding, matching the task description
        embed_text = item.description or item.file_name
        vec = embedder.embed_query(embed_text)
        screenshot_entries.append(IndexEntry(chunk_id=item.item_id, vector=vec))

    if chunk_entries:
        index.upsert(chunk_entries)
    if screenshot_entries:
        index.upsert(screenshot_entries)

    # --- Configure retriever with min_similarity=0.0 so most matches pass ---
    config = RetrievalConfig(
        top_k=top_k,
        min_similarity=0.0,
        medium_confidence_threshold=0.45,
        high_confidence_threshold=0.65,
    )
    retriever = Retriever(
        index=index,
        store=store,
        embedder=embedder,
        config=config,
    )

    # --- Execute retrieval ---
    outcome = retriever.retrieve(query)

    # --- Property: text matches ordered by descending score ---
    text_scores = [m.score for m in outcome.text_matches]
    for i in range(len(text_scores) - 1):
        assert text_scores[i] >= text_scores[i + 1], (
            f"Text matches not in descending order: "
            f"score[{i}]={text_scores[i]} < score[{i + 1}]={text_scores[i + 1]}"
        )

    # --- Property: screenshot matches ordered by descending score ---
    ss_scores = [m.score for m in outcome.screenshot_matches]
    for i in range(len(ss_scores) - 1):
        assert ss_scores[i] >= ss_scores[i + 1], (
            f"Screenshot matches not in descending order: "
            f"score[{i}]={ss_scores[i]} < score[{i + 1}]={ss_scores[i + 1]}"
        )

    # --- Property: at most top_k items in each result set ---
    assert len(outcome.text_matches) <= top_k, (
        f"Text matches ({len(outcome.text_matches)}) exceeds top_k ({top_k})"
    )
    assert len(outcome.screenshot_matches) <= top_k, (
        f"Screenshot matches ({len(outcome.screenshot_matches)}) exceeds top_k ({top_k})"
    )

    # --- Property: every returned match id resolves to a stored item ---
    chunk_ids = {c.chunk_id for c in chunks}
    screenshot_ids = {s.item_id for s in screenshots}

    for tm in outcome.text_matches:
        assert tm.chunk.chunk_id in chunk_ids, (
            f"Text match chunk_id {tm.chunk.chunk_id!r} not found in stored chunks"
        )
        # Verify it resolves via the store as well
        assert store.get_chunk(tm.chunk.chunk_id) is not None, (
            f"Text match chunk_id {tm.chunk.chunk_id!r} does not resolve in MetadataStore"
        )

    for sm in outcome.screenshot_matches:
        assert sm.item.item_id in screenshot_ids, (
            f"Screenshot match item_id {sm.item.item_id!r} not found in stored screenshots"
        )
        # Verify it resolves via the store as well
        assert store.get_screenshot(sm.item.item_id) is not None, (
            f"Screenshot match item_id {sm.item.item_id!r} does not resolve in MetadataStore"
        )


# --------------------------------------------------------------------------- #
# Property 8 — Below-threshold retrieval yields a no-match result
# Feature: internal-training-content-search, Property 8: Below-threshold retrieval yields a no-match result
# --------------------------------------------------------------------------- #


@given(
    chunks=st_text_chunks(),
    screenshots=st_screenshot_items(),
    query=st.text(min_size=1, max_size=100),
)
@settings(max_examples=100, deadline=None)
def test_below_threshold_no_match(
    chunks,
    screenshots,
    query: str,
) -> None:
    """**Validates: Requirements 7.5**

    For ANY set of indexed chunks/screenshots and any non-empty query, when
    ``min_similarity`` is set to 1.01 (above the maximum possible cosine
    similarity of 1.0), ALL matches are below threshold and the outcome must
    have empty text and screenshot match sets with ``no_match=True``.
    """
    embedder = FakeEmbedder()

    # --- Set up MetadataStore with chunks and screenshots ---
    store = MetadataStore()
    store.save_chunks(chunks)
    store.save_screenshots(screenshots)

    # --- Set up FakeVectorIndex with entries for all chunks and screenshots ---
    index = FakeVectorIndex()

    chunk_entries = []
    for chunk in chunks:
        vec = embedder.embed_query(chunk.text)
        chunk_entries.append(IndexEntry(chunk_id=chunk.chunk_id, vector=vec))

    screenshot_entries = []
    for item in screenshots:
        embed_text = item.description or item.file_name
        vec = embedder.embed_query(embed_text)
        screenshot_entries.append(IndexEntry(chunk_id=item.item_id, vector=vec))

    if chunk_entries:
        index.upsert(chunk_entries)
    if screenshot_entries:
        index.upsert(screenshot_entries)

    # --- Configure retriever with min_similarity=1.01 (above max cosine) ---
    config = RetrievalConfig(
        top_k=10,
        min_similarity=1.01,
        medium_confidence_threshold=0.45,
        high_confidence_threshold=0.65,
    )
    retriever = Retriever(
        index=index,
        store=store,
        embedder=embedder,
        config=config,
    )

    # --- Execute retrieval ---
    outcome = retriever.retrieve(query)

    # --- Property: text_matches is empty ---
    assert outcome.text_matches == [], (
        f"Expected no text matches with min_similarity=1.01, got {len(outcome.text_matches)}"
    )

    # --- Property: screenshot_matches is empty ---
    assert outcome.screenshot_matches == [], (
        f"Expected no screenshot matches with min_similarity=1.01, got {len(outcome.screenshot_matches)}"
    )

    # --- Property: no_match is True ---
    assert outcome.no_match is True, (
        f"Expected no_match=True with min_similarity=1.01, got no_match={outcome.no_match}"
    )


@given(
    query=st.text(min_size=1, max_size=100),
)
@settings(max_examples=100, deadline=None)
def test_below_threshold_no_match_empty_index(
    query: str,
) -> None:
    """**Validates: Requirements 7.5**

    With an empty index (no entries at all), retrieval should also yield
    a no-match result: empty text and screenshot match sets, ``no_match=True``.
    """
    embedder = FakeEmbedder()

    # --- Empty store and empty index ---
    store = MetadataStore()
    index = FakeVectorIndex()

    # --- Configure retriever with any min_similarity ---
    config = RetrievalConfig(
        top_k=10,
        min_similarity=0.0,
        medium_confidence_threshold=0.45,
        high_confidence_threshold=0.65,
    )
    retriever = Retriever(
        index=index,
        store=store,
        embedder=embedder,
        config=config,
    )

    # --- Execute retrieval ---
    outcome = retriever.retrieve(query)

    # --- Property: text_matches is empty ---
    assert outcome.text_matches == [], (
        f"Expected no text matches on empty index, got {len(outcome.text_matches)}"
    )

    # --- Property: screenshot_matches is empty ---
    assert outcome.screenshot_matches == [], (
        f"Expected no screenshot matches on empty index, got {len(outcome.screenshot_matches)}"
    )

    # --- Property: no_match is True ---
    assert outcome.no_match is True, (
        f"Expected no_match=True on empty index, got no_match={outcome.no_match}"
    )
