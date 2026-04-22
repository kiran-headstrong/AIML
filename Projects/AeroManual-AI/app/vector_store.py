"""
vector_store.py — Manages the FAISS vector index for document embeddings.

Key optimizations over the original implementation:
    - In-memory cache: FAISS index is loaded once and kept in memory,
      eliminating disk I/O on every search request (~200ms → ~1ms).
    - Thread lock: Prevents race conditions when multiple concurrent
      uploads modify the index simultaneously.
    - Duplicate detection: Tracks indexed filenames to avoid re-indexing
      the same document twice.
    - Batch embeddings: Configured batch_size=64 for faster bulk indexing.
"""

import logging
import threading
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from app.config import EMBEDDING_MODEL, VECTORSTORE_DIR, TOP_K, RELEVANCE_THRESHOLD

logger = logging.getLogger(__name__)

# Embedding model with batch processing for faster indexing
_embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL,
    encode_kwargs={"batch_size": 64},
)

_index_path = str(VECTORSTORE_DIR / "index")

# In-memory FAISS index cache — avoids disk I/O on every query
_store_cache = None

# Thread lock — prevents race conditions during concurrent add_documents calls
_lock = threading.Lock()

# Tracks which files have been indexed to prevent duplicate ingestion
_indexed_files: set = set()


def _load_from_disk():
    """
    Attempt to load a previously persisted FAISS index from disk.

    Returns:
        FAISS store instance if found, None otherwise.
    """
    try:
        store = FAISS.load_local(
            _index_path, _embeddings, allow_dangerous_deserialization=True
        )
        logger.info("Loaded FAISS index from disk: %s", _index_path)
        return store
    except Exception:
        logger.info("No existing FAISS index found at %s", _index_path)
        return None


def _get_store():
    """
    Return the cached FAISS store, loading from disk on first access.

    This is the core performance optimization — the index is read from
    disk only once, then served from memory for all subsequent queries.

    Returns:
        Cached FAISS store instance, or None if no index exists yet.
    """
    global _store_cache
    if _store_cache is None:
        _store_cache = _load_from_disk()
    return _store_cache


def is_duplicate(source_path: str) -> bool:
    """
    Check if a file has already been indexed.

    Args:
        source_path: Path of the file to check.

    Returns:
        True if the file was already indexed in this session.
    """
    return source_path in _indexed_files


def add_documents(docs: list, source_path: str = "") -> int:
    """
    Add document chunks to the FAISS index with thread safety.

    Steps:
        1. Acquire thread lock to prevent concurrent write conflicts
        2. Load existing index from cache (or create new one)
        3. Add new document embeddings (batched at 64 chunks)
        4. Persist updated index to disk
        5. Update in-memory cache

    Args:
        docs: List of LangChain Document objects to index.
        source_path: Original file path (used for duplicate tracking).

    Returns:
        Number of chunks indexed.
    """
    global _store_cache

    with _lock:
        logger.info("Adding %d chunks to FAISS index (lock acquired)", len(docs))
        store = _get_store()

        if store:
            store.add_documents(docs)
        else:
            store = FAISS.from_documents(docs, _embeddings)

        store.save_local(_index_path)
        _store_cache = store

        if source_path:
            _indexed_files.add(source_path)

        logger.info(
            "FAISS index updated: +%d chunks, saved to %s", len(docs), _index_path
        )
    return len(docs)


def search(query: str, k: int = TOP_K) -> list:
    """
    Search the FAISS index for chunks most similar to the query.

    Uses the in-memory cached index (no disk I/O) and filters results
    by the configurable RELEVANCE_THRESHOLD (FAISS L2 distance — lower
    scores indicate higher similarity).

    Args:
        query: User's natural language question.
        k: Number of top results to retrieve.

    Returns:
        List of relevant Document objects, filtered by relevance threshold.
    """
    store = _get_store()
    if not store:
        logger.warning("Search called but no FAISS index exists yet")
        return []

    results = store.similarity_search_with_score(query, k=k)
    filtered = [doc for doc, score in results if score < RELEVANCE_THRESHOLD]
    logger.info(
        "Search query='%s' → %d candidates, %d after threshold filter (< %.1f)",
        query[:80], len(results), len(filtered), RELEVANCE_THRESHOLD,
    )
    return filtered
