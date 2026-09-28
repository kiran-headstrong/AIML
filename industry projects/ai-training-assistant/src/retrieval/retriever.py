"""Retrieval_Component: embed query, search, threshold, rank, categorize, assess.

Orchestrates the full retrieval flow: embeds the user query, searches the vector
index, applies the ``min_similarity`` threshold, resolves match ids to stored
chunks and screenshots via the metadata store, ranks by descending score (limited
to ``top_k``), classifies the query, computes confidence from the top score, and
returns a complete ``RetrievalOutcome``.

Design reference: Properties 7, 8 — Retrieval ranking/limit/reference consistency
and below-threshold no-match behaviour.
"""

from __future__ import annotations

from typing import Optional

from src.index.metadata_store import MetadataStore
from src.index.vector_index import VectorIndex
from src.models import (
    Confidence,
    RetrievalConfig,
    RetrievalOutcome,
    ScreenshotMatch,
    TextMatch,
)
from src.retrieval.categorizer import Categorizer
from src.retrieval.confidence import assess_confidence


class Retriever:
    """Retrieval_Component: search, threshold, rank, categorize, assess.

    Accepts a ``VectorIndex``, ``MetadataStore``, an embedder (anything with
    ``embed_query``), and a ``RetrievalConfig``.  Optionally accepts a
    ``Categorizer``; a default one is created (with the embedder for
    tie-breaking) when none is provided.

    Req 6.3, 7.1, 7.2, 7.3, 7.5, 8.1.
    """

    def __init__(
        self,
        index: VectorIndex,
        store: MetadataStore,
        embedder: object,
        config: RetrievalConfig,
        categorizer: Optional[Categorizer] = None,
    ) -> None:
        self._index = index
        self._store = store
        self._embedder = embedder
        self._config = config
        self._categorizer = categorizer or Categorizer(embedder=embedder)

    def retrieve(self, query: str) -> RetrievalOutcome:
        """Run the full retrieval flow for *query* and return a ``RetrievalOutcome``.

        Steps:
        1. Embed the query (Req 7.1).
        2. Search the vector index for top matches (Req 7.2).
        3. Filter matches below ``min_similarity`` (Req 7.5).
        4. Resolve each match id to a ``TextChunk`` or ``ScreenshotItem``.
        5. Build ranked ``TextMatch`` / ``ScreenshotMatch`` lists (descending
           score), limited to ``top_k`` each.
        6. Categorize the query (Req 8.1).
        7. Compute confidence from the top score (Req 10.3, 11.1).
        8. Set ``no_match`` when nothing clears the threshold (Req 7.5).
        """
        # 1. Embed the query
        query_vec: list[float] = self._embedder.embed_query(query)

        # 2. Search the vector index
        raw_matches = self._index.search(query_vec, self._config.top_k)

        # 3. Filter by min_similarity threshold
        above_threshold = [
            m for m in raw_matches if m.score >= self._config.min_similarity
        ]

        # 4 & 5. Resolve ids → TextMatch / ScreenshotMatch, ranked by score
        text_matches: list[TextMatch] = []
        screenshot_matches: list[ScreenshotMatch] = []

        for match in above_threshold:
            # Try text chunk first
            chunk = self._store.get_chunk(match.chunk_id)
            if chunk is not None:
                text_matches.append(TextMatch(chunk=chunk, score=match.score))
                continue

            # Try screenshot item
            screenshot = self._store.get_screenshot(match.chunk_id)
            if screenshot is not None:
                screenshot_matches.append(
                    ScreenshotMatch(item=screenshot, score=match.score)
                )
                continue

            # Id resolves to neither → skip silently

        # Sort by descending score and limit to top_k each
        text_matches.sort(key=lambda tm: tm.score, reverse=True)
        screenshot_matches.sort(key=lambda sm: sm.score, reverse=True)

        # Deduplicate: keep only the highest-scored match per source file
        seen_text_sources: set[str] = set()
        deduped_text: list[TextMatch] = []
        for tm in text_matches:
            src = tm.chunk.source_file
            if src not in seen_text_sources:
                seen_text_sources.add(src)
                deduped_text.append(tm)
        text_matches = deduped_text[: self._config.top_k]

        seen_ss_sources: set[str] = set()
        deduped_ss: list[ScreenshotMatch] = []
        for sm in screenshot_matches:
            src = sm.item.file_name
            if src not in seen_ss_sources:
                seen_ss_sources.add(src)
                deduped_ss.append(sm)
        screenshot_matches = deduped_ss[: self._config.top_k]

        # 6. Categorize the query
        category = self._categorizer.categorize(query)

        # 7. Compute confidence from the top score
        top_score = 0.0
        if text_matches or screenshot_matches:
            all_scores = [tm.score for tm in text_matches] + [
                sm.score for sm in screenshot_matches
            ]
            top_score = max(all_scores)

        confidence, _next_step = assess_confidence(
            top_score,
            self._config.medium_confidence_threshold,
            self._config.high_confidence_threshold,
        )

        # 8. Determine no_match
        no_match = len(text_matches) == 0 and len(screenshot_matches) == 0

        return RetrievalOutcome(
            query=query,
            category=category,
            text_matches=text_matches,
            screenshot_matches=screenshot_matches,
            confidence=confidence,
            no_match=no_match,
        )
