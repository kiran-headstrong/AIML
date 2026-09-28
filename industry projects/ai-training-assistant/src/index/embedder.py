"""Embedding_Component: local, CPU-only sentence-transformers wrapper.

Wraps ``sentence-transformers/all-MiniLM-L6-v2`` (a 384-dimensional, CPU-friendly
model) so text chunks and queries embed with the *same* model (Req 6.1, 6.2,
7.1). The model is downloaded once and cached under ``data/model/`` for offline
reuse; when the cache is empty and the machine is offline, the embedder fails
fast with a clear, actionable message rather than hanging or crashing obscurely.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sentence_transformers import SentenceTransformer


class EmbedderModelUnavailableError(RuntimeError):
    """Raised when the embedding model cannot be loaded from cache while offline.

    The message directs the user to run ``scripts/build.py`` once while online to
    download and cache the model under ``data/model/``.
    """


class Embedder:
    """Local sentence-transformers embedder, forced onto the CPU.

    The underlying model is loaded lazily on first use so that constructing an
    ``Embedder`` is cheap and does not touch the network or disk until an
    embedding is actually requested.
    """

    def __init__(
        self,
        model_name: str = config.EMBEDDING_MODEL,
        cache_dir: str = str(config.MODEL_CACHE_DIR),
    ) -> None:
        """Initialize the embedder.

        Args:
            model_name: The sentence-transformers model identifier. Defaults to
                ``config.EMBEDDING_MODEL`` (``all-MiniLM-L6-v2``).
            cache_dir: Directory used to cache the downloaded model, enabling
                offline reuse. Defaults to ``config.MODEL_CACHE_DIR``
                (``data/model/``).
        """
        self._model_name = model_name
        self._cache_dir = Path(cache_dir)
        self._model: "SentenceTransformer | None" = None

    def _load_model(self) -> "SentenceTransformer":
        """Load and cache the sentence-transformers model on the CPU.

        The model is created only once and reused for the lifetime of this
        ``Embedder``. The CPU device is forced so the prototype never requires a
        GPU (Req 6.2).

        Returns:
            The loaded ``SentenceTransformer`` instance.

        Raises:
            EmbedderModelUnavailableError: If the model is not present in the
                cache and cannot be downloaded (e.g., the machine is offline).
        """
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise EmbedderModelUnavailableError(
                "The 'sentence-transformers' package is not installed. Install the "
                "project requirements (pip install -r requirements.txt) to enable "
                "local embeddings."
            ) from exc

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._model = SentenceTransformer(
                self._model_name,
                cache_folder=str(self._cache_dir),
                device="cpu",
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as a specific error
            raise EmbedderModelUnavailableError(
                f"Could not load embedding model '{self._model_name}' from cache "
                f"'{self._cache_dir}'. If this is the first run, connect to the "
                "internet and run 'python scripts/build.py' once to download and "
                "cache the model under data/model/, then retry offline."
            ) from exc

        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed a list of texts on the CPU (Req 6.1, 6.2).

        Args:
            texts: The texts to embed. An empty list yields an empty result.

        Returns:
            A list of 384-dimensional embedding vectors, one per input text, in
            the same order as ``texts``.
        """
        if not texts:
            return []
        model = self._load_model()
        vectors = model.encode(
            texts,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query with the same model used for chunks (Req 7.1).

        Args:
            query: The query text to embed.

        Returns:
            A single 384-dimensional embedding vector.
        """
        model = self._load_model()
        vector = model.encode(
            query,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return vector.tolist()
