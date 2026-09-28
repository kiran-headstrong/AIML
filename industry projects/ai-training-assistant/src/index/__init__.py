"""Index layer: embeddings, vector store, and metadata store."""

from src.index.embedder import Embedder, EmbedderModelUnavailableError
from src.index.metadata_store import (
    MetadataStore,
    MetadataStoreError,
    MetadataStoreNotFoundError,
)
from src.index.vector_index import (
    ChromaVectorIndex,
    IndexCorruptError,
    IndexEntry,
    IndexNotBuiltError,
    Match,
    VectorIndex,
    VectorIndexError,
)

__all__ = [
    "Embedder",
    "EmbedderModelUnavailableError",
    "MetadataStore",
    "MetadataStoreError",
    "MetadataStoreNotFoundError",
    "ChromaVectorIndex",
    "IndexCorruptError",
    "IndexEntry",
    "IndexNotBuiltError",
    "Match",
    "VectorIndex",
    "VectorIndexError",
]
