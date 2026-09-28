"""Vector_Index: abstract interface plus a persistent Chroma implementation.

Defines the ``VectorIndex`` Protocol used by the retrieval layer along with the
``IndexEntry`` and ``Match`` value types, and provides a Chroma-backed
implementation that persists to ``config.CHROMA_STORE_DIR`` (Req 6.3, 6.4, 7.2).

Cosine distances returned by Chroma are normalized into a stable ``[0, 1]``
similarity so that retrieval thresholds behave consistently across backends.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import config

logger = logging.getLogger(__name__)

# Name of the single Chroma collection that holds all chunk embeddings.
_COLLECTION_NAME = "training_chunks"


class VectorIndexError(RuntimeError):
    """Base error for vector-index problems."""


class IndexNotBuiltError(VectorIndexError):
    """Raised when a persisted index is missing.

    The message directs the user to build the index with ``scripts/build.py``.
    """


class IndexCorruptError(VectorIndexError):
    """Raised when a persisted index exists but cannot be read/opened.

    The message instructs the user to rebuild the index rather than proceeding
    with possibly-wrong results.
    """


@dataclass
class IndexEntry:
    """An embedding to be stored, keyed by its chunk id (Req 6.3)."""

    chunk_id: str
    vector: list[float]
    metadata: dict = field(default_factory=dict)


@dataclass
class Match:
    """A search hit: a chunk id and its normalized similarity in ``[0, 1]``."""

    chunk_id: str
    score: float


@runtime_checkable
class VectorIndex(Protocol):
    """Narrow interface over a persistent vector store."""

    def upsert(self, entries: list[IndexEntry]) -> None:
        """Insert or update the given embeddings (Req 6.3)."""
        ...

    def search(self, query_vec: list[float], top_k: int) -> list[Match]:
        """Return up to ``top_k`` matches ordered by descending score (Req 7.2)."""
        ...

    def persist(self) -> None:
        """Flush the index to durable storage (Req 6.3)."""
        ...

    @classmethod
    def load(cls, path: str) -> "VectorIndex":
        """Load a previously persisted index from ``path`` (Req 6.4)."""
        ...


def _normalize_cosine_distance(distance: float) -> float:
    """Normalize a Chroma cosine distance into a ``[0, 1]`` similarity.

    Chroma's cosine ``distance`` lies in ``[0, 2]`` (``distance = 1 - cosine``,
    where cosine similarity is in ``[-1, 1]``). Mapping ``similarity = 1 -
    distance / 2`` yields a stable ``[0, 1]`` score where higher means more
    similar. The result is clamped to guard against tiny floating-point drift.

    Args:
        distance: The cosine distance reported by Chroma.

    Returns:
        A similarity score in ``[0, 1]``.
    """
    similarity = 1.0 - (distance / 2.0)
    if similarity < 0.0:
        return 0.0
    if similarity > 1.0:
        return 1.0
    return similarity


class ChromaVectorIndex:
    """A persistent Chroma-backed vector index.

    Uses a ``chromadb.PersistentClient`` rooted at a store directory with a
    single cosine-space collection. Similarity scores are normalized into
    ``[0, 1]`` before being returned.
    """

    def __init__(self, store_dir: str = str(config.CHROMA_STORE_DIR)) -> None:
        """Open (or create) a persistent Chroma store at ``store_dir``.

        Args:
            store_dir: Directory where Chroma persists its data. Defaults to
                ``config.CHROMA_STORE_DIR``.

        Raises:
            IndexCorruptError: If Chroma cannot open the store directory.
        """
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)

        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise VectorIndexError(
                "The 'chromadb' package is not installed. Install the project "
                "requirements (pip install -r requirements.txt) to enable the "
                "vector index."
            ) from exc

        try:
            self._client = chromadb.PersistentClient(
                path=str(self._store_dir),
                settings=Settings(anonymized_telemetry=False, allow_reset=True),
            )
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as a specific error
            raise IndexCorruptError(
                f"The vector index at '{self._store_dir}' could not be opened and "
                "may be corrupt or partially written. Rebuild it by running "
                "'python scripts/build.py'."
            ) from exc

    def upsert(self, entries: list[IndexEntry]) -> None:
        """Insert or update embeddings in the collection (Req 6.3).

        Args:
            entries: The embeddings to store. An empty list is a no-op.
        """
        if not entries:
            return
        ids = [entry.chunk_id for entry in entries]
        embeddings = [entry.vector for entry in entries]
        metadatas = [entry.metadata or {} for entry in entries]
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(self, query_vec: list[float], top_k: int) -> list[Match]:
        """Search for the ``top_k`` most similar embeddings (Req 7.2).

        Args:
            query_vec: The query embedding vector.
            top_k: The maximum number of matches to return.

        Returns:
            A list of ``Match`` ordered by descending normalized similarity,
            containing at most ``top_k`` items. Empty when the index has no
            entries or ``top_k <= 0``.

        Raises:
            IndexCorruptError: If the underlying query fails unexpectedly.
        """
        if top_k <= 0:
            return []
        count = self._collection.count()
        if count == 0:
            return []

        try:
            result = self._collection.query(
                query_embeddings=[query_vec],
                n_results=min(top_k, count),
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as a specific error
            raise IndexCorruptError(
                f"Querying the vector index at '{self._store_dir}' failed; it may "
                "be corrupt. Rebuild it by running 'python scripts/build.py'."
            ) from exc

        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        matches: list[Match] = []
        for chunk_id, distance in zip(ids, distances):
            matches.append(
                Match(chunk_id=chunk_id, score=_normalize_cosine_distance(distance))
            )
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches

    def persist(self) -> None:
        """Flush the index to disk (Req 6.3).

        ``PersistentClient`` writes eagerly, so this is a no-op retained for
        interface compatibility with backends that require an explicit flush.
        """
        return None

    @classmethod
    def load(cls, path: str) -> "ChromaVectorIndex":
        """Load a previously persisted Chroma index (Req 6.4).

        Args:
            path: The store directory of the persisted index.

        Returns:
            A ``ChromaVectorIndex`` bound to the persisted store.

        Raises:
            IndexNotBuiltError: If no persisted store exists at ``path``.
            IndexCorruptError: If the store exists but cannot be opened.
        """
        store_dir = Path(path)
        if not store_dir.exists() or not any(store_dir.iterdir()):
            raise IndexNotBuiltError(
                f"No vector index found at '{store_dir}'. Build it first by "
                "running 'python scripts/build.py'."
            )
        return cls(store_dir=str(store_dir))
