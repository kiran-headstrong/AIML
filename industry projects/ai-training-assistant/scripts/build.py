#!/usr/bin/env python3
"""Build pipeline: ingest corpus → embed → index → persist metadata.

Runs the full offline ingestion and indexing pipeline, producing:
- ``data/chroma_store/``  — persisted Chroma vector index
- ``data/metadata.db``    — SQLite metadata store
- ``data/metadata.json``  — human-readable JSON metadata export

Usage::

    python scripts/build.py

The script must be run at least once while online so the embedding model is
downloaded and cached under ``data/model/``.  Subsequent runs work offline.

Requirements: 1.5, 5.2, 6.3
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so ``config`` and ``src.*`` resolve.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402  (must come after path fixup)
from src.index.embedder import Embedder, EmbedderModelUnavailableError  # noqa: E402
from src.index.metadata_store import MetadataStore  # noqa: E402
from src.index.vector_index import ChromaVectorIndex, IndexEntry  # noqa: E402
from src.ingestion.ingest import IngestionComponent  # noqa: E402


def main() -> None:
    """Run the full build pipeline."""

    # 1. Create data directories ----------------------------------------- #
    print("[1/6] Ensuring data directories exist …")
    config.ensure_data_dirs()

    # 2. Ingest corpus --------------------------------------------------- #
    corpus_dir = str(config.CORPUS_DIR)
    print(f"[2/6] Ingesting corpus from {corpus_dir} …")

    if not config.CORPUS_DIR.is_dir():
        print(
            f"  ⚠  Corpus directory does not exist: {corpus_dir}\n"
            "     Create the directory and add files, then re-run."
        )
        return

    ingestion = IngestionComponent()
    result = ingestion.ingest_folder(corpus_dir)

    # Filter out excluded files (meta-documents that match queries
    # semantically but don't contain actual training content).
    if config.EXCLUDE_FILES:
        excluded = set(f.lower() for f in config.EXCLUDE_FILES)
        before_count = len(result.text_chunks)
        result.text_chunks = [
            c for c in result.text_chunks
            if os.path.basename(c.source_file).lower() not in excluded
        ]
        filtered = before_count - len(result.text_chunks)
        if filtered:
            print(f"  Excluded {filtered} chunk(s) from: {config.EXCLUDE_FILES}")

    print(f"  Ingested documents : {result.ingested_doc_count}")
    print(f"  Ingested screenshots: {result.ingested_screenshot_count}")
    print(f"  Skipped files      : {len(result.skipped)}")

    if not result.text_chunks and not result.screenshot_items:
        print("  ⚠  No content was ingested. The corpus may be empty.")

    # 3. Embed text chunks ----------------------------------------------- #
    print(f"[3/7] Embedding {len(result.text_chunks)} text chunk(s) …")

    embedder = Embedder()
    texts = [chunk.text for chunk in result.text_chunks]
    vectors = embedder.embed(texts)

    print(f"  Produced {len(vectors)} embedding(s).")

    # 3b. Embed screenshot descriptions ---------------------------------- #
    screenshot_texts = []
    embeddable_screenshots = []
    for item in result.screenshot_items:
        # Build a searchable text from available metadata fields
        parts = []
        if item.topic_tag:
            parts.append(item.topic_tag.replace("_", " "))
        if item.description:
            parts.append(item.description)
        if item.ocr_text:
            parts.append(item.ocr_text)
        if not parts:
            parts.append(item.file_name)  # fallback: at least the filename
        embeddable_screenshots.append(item)
        screenshot_texts.append(" ".join(parts))

    screenshot_vectors = []
    if screenshot_texts:
        print(f"[3b/7] Embedding {len(screenshot_texts)} screenshot description(s) …")
        screenshot_vectors = embedder.embed(screenshot_texts)
        print(f"  Produced {len(screenshot_vectors)} screenshot embedding(s).")

    # 4. Upsert into vector index ---------------------------------------- #
    print("[4/7] Upserting embeddings into vector index …")

    vector_index = ChromaVectorIndex(str(config.CHROMA_STORE_DIR))

    entries = [
        IndexEntry(
            chunk_id=chunk.chunk_id,
            vector=vector,
            metadata={"source_file": chunk.source_file},
        )
        for chunk, vector in zip(result.text_chunks, vectors)
    ]

    # Add screenshot entries to the vector index
    for item, vec in zip(embeddable_screenshots, screenshot_vectors):
        entries.append(
            IndexEntry(
                chunk_id=item.item_id,
                vector=vec,
                metadata={"source_file": item.file_name},
            )
        )

    vector_index.upsert(entries)

    # 5. Persist vector index -------------------------------------------- #
    print("[5/7] Persisting vector index …")
    vector_index.persist()

    # 6. Persist metadata store ------------------------------------------ #
    print("[6/7] Persisting metadata store …")

    metadata_store = MetadataStore()
    metadata_store.save_chunks(result.text_chunks)
    metadata_store.save_screenshots(result.screenshot_items)
    metadata_store.persist(
        str(config.METADATA_DB_PATH),
        str(config.METADATA_JSON_PATH),
    )

    print()
    print("✓ Build complete.")
    print(f"  Text chunks      : {len(result.text_chunks)}")
    print(f"  Screenshots      : {len(embeddable_screenshots)}")
    print(f"  Vector index     : {config.CHROMA_STORE_DIR}")
    print(f"  Metadata DB      : {config.METADATA_DB_PATH}")
    print(f"  Metadata JSON    : {config.METADATA_JSON_PATH}")


if __name__ == "__main__":
    try:
        main()
    except EmbedderModelUnavailableError as exc:
        print(f"\n✗ Embedding model unavailable: {exc}", file=sys.stderr)
        print(
            "\n  Run this script once while connected to the internet so the\n"
            "  model is downloaded and cached under data/model/.\n",
            file=sys.stderr,
        )
        sys.exit(1)
