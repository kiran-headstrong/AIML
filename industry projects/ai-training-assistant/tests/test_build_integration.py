"""Integration test: build → persist → reload → query.

Exercises the full offline build pipeline programmatically against a small
fixture corpus, persists to disk, reloads fresh instances, and asserts that
query results are identical before and after reload.

Marked ``@pytest.mark.slow`` because it loads the real sentence-transformers
embedding model.  Skips gracefully when the model library is not installed.

Validates: Requirements 6.4
"""

from __future__ import annotations

import pytest

pytest.importorskip(
    "sentence_transformers",
    reason="sentence-transformers not installed; skipping build integration test.",
)

from src.index.embedder import Embedder, EmbedderModelUnavailableError
from src.index.metadata_store import MetadataStore
from src.index.vector_index import ChromaVectorIndex, IndexEntry
from src.ingestion.ingest import IngestionComponent


# -- Fixture corpus content ------------------------------------------------- #

_ONBOARDING_TXT = """\
Employee Onboarding Steps

Step 1 - Complete new hire paperwork including tax forms, emergency contacts, \
and direct deposit enrollment.

Step 2 - Attend the orientation session covering company culture, mission, \
and core values.

Step 3 - Set up your workstation including laptop configuration, VPN access, \
and email activation.

Step 4 - Meet your assigned buddy who will guide you through the first two weeks.
"""

_SOP_MD = """\
# Password Reset SOP

## Overview

This document describes the standard operating procedure for resetting a \
user's password in the internal portal.

## Steps

1. Navigate to the Admin Console and select User Management.
2. Search for the affected user by employee ID or email address.
3. Click Reset Password and choose whether to send a temporary link or set a \
manual password.
4. Notify the user via their secondary contact method.

## Escalation

If the reset fails after two attempts, escalate to the IT Security team.
"""


def _create_fixture_corpus(tmp_path):
    """Write a small fixture corpus into *tmp_path* and return the corpus dir."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    (corpus / "onboarding.txt").write_text(_ONBOARDING_TXT, encoding="utf-8")
    (corpus / "password_reset.md").write_text(_SOP_MD, encoding="utf-8")

    # A tiny PNG stub (1×1 white pixel) so the screenshot indexer has a real file.
    # Minimal valid PNG: signature + IHDR + IDAT + IEND.
    import struct, zlib

    def _minimal_png() -> bytes:
        sig = b"\x89PNG\r\n\x1a\n"

        def _chunk(chunk_type: bytes, data: bytes) -> bytes:
            raw = chunk_type + data
            return struct.pack(">I", len(data)) + raw + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        # Raw scanline: filter byte 0 + RGB white.
        scanline = b"\x00\xff\xff\xff"
        idat = zlib.compress(scanline)
        return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")

    (corpus / "screenshot_example.png").write_bytes(_minimal_png())
    return corpus


# -- Test ------------------------------------------------------------------- #


@pytest.mark.slow
def test_build_persist_reload_query(tmp_path):
    """Build a fixture corpus, persist, reload, and assert identical results.

    Validates: Requirements 6.4
    """

    # ── 0. Warm up embedder early so we can skip if model is unavailable ── #
    embedder = Embedder()
    try:
        embedder.embed_query("warm up")
    except EmbedderModelUnavailableError as exc:  # pragma: no cover
        pytest.skip(f"Embedding model unavailable: {exc}")

    # ── 1. Create fixture corpus ────────────────────────────────────────── #
    corpus_dir = _create_fixture_corpus(tmp_path)

    # ── 2. Build: ingest → embed → index → persist metadata ────────────── #
    ingestion = IngestionComponent()
    result = ingestion.ingest_folder(str(corpus_dir))

    # Sanity: we expect 2 text docs and 1 screenshot.
    assert result.ingested_doc_count == 2
    assert result.ingested_screenshot_count == 1
    assert len(result.text_chunks) > 0

    # Embed all text chunks.
    texts = [chunk.text for chunk in result.text_chunks]
    vectors = embedder.embed(texts)
    assert len(vectors) == len(texts)

    # Create vector index and upsert.
    chroma_dir = tmp_path / "chroma_store"
    vector_index = ChromaVectorIndex(str(chroma_dir))
    entries = [
        IndexEntry(
            chunk_id=chunk.chunk_id,
            vector=vector,
            metadata={"source_file": chunk.source_file},
        )
        for chunk, vector in zip(result.text_chunks, vectors)
    ]
    vector_index.upsert(entries)
    vector_index.persist()

    # Create and persist metadata store.
    metadata_store = MetadataStore()
    metadata_store.save_chunks(result.text_chunks)
    metadata_store.save_screenshots(result.screenshot_items)

    db_path = tmp_path / "metadata.db"
    json_path = tmp_path / "metadata.json"
    metadata_store.persist(str(db_path), str(json_path))

    # ── 3. Query and record results ─────────────────────────────────────── #
    test_query = "onboarding steps"
    query_vec = embedder.embed_query(test_query)
    top_k = 5

    original_results = vector_index.search(query_vec, top_k)
    assert len(original_results) > 0, "Expected at least one result from the fixture corpus"

    # ── 4. Reload from persisted files ──────────────────────────────────── #
    reloaded_index = ChromaVectorIndex.load(str(chroma_dir))
    reloaded_store = MetadataStore.load(str(db_path))

    # ── 5. Query reloaded and assert identical results ──────────────────── #
    reloaded_results = reloaded_index.search(query_vec, top_k)

    assert len(reloaded_results) == len(original_results), (
        f"Result count mismatch: {len(original_results)} vs {len(reloaded_results)}"
    )

    original_ids = [m.chunk_id for m in original_results]
    reloaded_ids = [m.chunk_id for m in reloaded_results]
    assert original_ids == reloaded_ids, (
        f"Chunk ID order mismatch:\n  original: {original_ids}\n  reloaded: {reloaded_ids}"
    )

    original_scores = [m.score for m in original_results]
    reloaded_scores = [m.score for m in reloaded_results]
    assert reloaded_scores == pytest.approx(original_scores), (
        f"Score mismatch:\n  original: {original_scores}\n  reloaded: {reloaded_scores}"
    )

    # ── 6. Verify metadata lookups work ─────────────────────────────────── #
    # Every chunk from the original results should be retrievable.
    for match in original_results:
        chunk = reloaded_store.get_chunk(match.chunk_id)
        assert chunk is not None, f"Chunk {match.chunk_id!r} not found in reloaded store"
        assert chunk.source_file != "", "source_file should be non-empty"

    # Every screenshot item should be retrievable.
    for item in result.screenshot_items:
        reloaded_item = reloaded_store.get_screenshot(item.item_id)
        assert reloaded_item is not None, f"Screenshot {item.item_id!r} not found in reloaded store"
        assert reloaded_item.file_name == item.file_name
        assert reloaded_item.file_path == item.file_path
