"""Query categorizer: rule-based keyword classifier with embedding tie-breaker.

Classifies every query string into exactly one ``QueryCategory`` from the fixed
set of five categories (Req 8.1). The primary classification uses keyword rules;
when keyword matching is ambiguous (zero or multiple categories tie), an
embedding-similarity tie-breaker compares the query against prototype phrases
for each category. If no embedder is available, a deterministic fallback
category (``ONBOARDING``) is used instead.
"""

from __future__ import annotations

import math
from typing import Optional, Protocol

from src.models import QueryCategory


# --------------------------------------------------------------------------- #
# Embedder protocol (duck-typed so we accept both the real and fake embedders)
# --------------------------------------------------------------------------- #
class _EmbedderLike(Protocol):
    """Minimal interface expected from an embedder for the tie-breaker."""

    def embed_query(self, query: str) -> list[float]: ...


# --------------------------------------------------------------------------- #
# Keyword rules — maps each category to its trigger terms
# --------------------------------------------------------------------------- #
_KEYWORD_MAP: dict[QueryCategory, list[str]] = {
    QueryCategory.ONBOARDING: [
        "onboard",
        "new hire",
        "orientation",
        "getting started",
        "first day",
        "welcome",
        "access request",
        "access role",
        "user access",
        "routing",
        "role type",
        "temporary access",
        "expiry",
    ],
    QueryCategory.SOP_LOOKUP: [
        "sop",
        "procedure",
        "process",
        "steps",
        "how to",
        "instruction",
        "workflow",
        "guide",
        "escalation",
        "escalate",
        "approval",
        "approve",
        "review",
        "queue",
        "supervisor",
        "l2",
        "included",
        "include",
        "note",
        "what should",
        "what can",
        "what does",
        "how many",
        "when should",
        "which",
        "what fields",
    ],
    QueryCategory.SCREENSHOT_LOOKUP: [
        "screenshot",
        "screen",
        "image",
        "picture",
        "visual",
        "capture",
        "ui",
        "interface",
        "show screenshot",
        "find screenshot",
        "png",
    ],
    QueryCategory.POLICY_REFERENCE: [
        "policy",
        "rule",
        "regulation",
        "compliance",
        "requirement",
        "standard",
        "guideline",
        "refund",
        "exception",
        "finance",
        "validation",
        "freeze",
        "manual freeze",
        "promise",
        "naming format",
        "naming",
        "format",
        "filter",
        "saved filter",
        "dashboard",
        "quality",
        "monthly",
        "sample",
    ],
    QueryCategory.TROUBLESHOOTING: [
        "error",
        "issue",
        "problem",
        "fix",
        "troubleshoot",
        "debug",
        "broken",
        "fail",
        "not working",
        "missing",
        "no expiry",
        "repeated error",
    ],
}

# --------------------------------------------------------------------------- #
# Prototype phrases for embedding tie-breaker
# --------------------------------------------------------------------------- #
_PROTOTYPE_PHRASES: dict[QueryCategory, list[str]] = {
    QueryCategory.ONBOARDING: [
        "new hire onboarding process",
        "first day orientation guide",
        "welcome to the team getting started",
    ],
    QueryCategory.SOP_LOOKUP: [
        "standard operating procedure steps",
        "how to follow the workflow instructions",
        "process guide for operations",
    ],
    QueryCategory.SCREENSHOT_LOOKUP: [
        "screenshot of the user interface",
        "screen capture image of the tool",
        "visual reference picture of the application",
    ],
    QueryCategory.POLICY_REFERENCE: [
        "company policy rules and regulations",
        "compliance requirement standards",
        "guideline for regulatory compliance",
    ],
    QueryCategory.TROUBLESHOOTING: [
        "troubleshoot error and fix the problem",
        "debug issue with broken system",
        "problem not working needs fix",
    ],
}

# Deterministic fallback when no embedder is available and keywords are ambiguous.
_FALLBACK_CATEGORY = QueryCategory.ONBOARDING


# --------------------------------------------------------------------------- #
# Categorizer
# --------------------------------------------------------------------------- #
class Categorizer:
    """Rule-based keyword classifier over the fixed 5 categories with an
    embedding-similarity tie-breaker against category prototype phrases.

    Always returns exactly one ``QueryCategory`` for *any* input string,
    including empty or whitespace-only strings (Req 8.1).
    """

    CATEGORIES = (
        "onboarding",
        "sop_lookup",
        "screenshot_lookup",
        "policy_reference",
        "troubleshooting_support",
    )

    def __init__(self, embedder: Optional[_EmbedderLike] = None) -> None:
        """Initialize the categorizer.

        Args:
            embedder: An optional embedder instance used for the embedding-
                similarity tie-breaker. When ``None``, keyword ambiguity is
                resolved by a deterministic fallback (``ONBOARDING``).
        """
        self._embedder = embedder
        # Pre-compute prototype embeddings lazily (only when first needed).
        self._prototype_embeddings: Optional[dict[QueryCategory, list[list[float]]]] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def categorize(self, query: str) -> QueryCategory:
        """Return exactly one category for the given query string. Req 8.1.

        Classification strategy:
        1. Normalize and scan keywords. Count how many categories match.
        2. If exactly one category matches → return it.
        3. If zero or multiple categories match → use embedding tie-breaker.
        4. If no embedder → return the deterministic fallback.

        Args:
            query: The user query. May be empty, whitespace-only, or any string.

        Returns:
            Exactly one ``QueryCategory``.
        """
        normalized = (query or "").lower().strip()

        # Edge case: empty / whitespace-only → fallback immediately.
        if not normalized:
            return _FALLBACK_CATEGORY

        # --- Step 1: keyword matching ---
        matched_categories = self._keyword_match(normalized)

        # --- Step 2: single match → done ---
        if len(matched_categories) == 1:
            return matched_categories[0]

        # --- Step 3: zero or multiple matches → tie-breaker ---
        candidates = matched_categories if matched_categories else list(QueryCategory)
        return self._embedding_tiebreak(query, candidates)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _keyword_match(self, normalized_query: str) -> list[QueryCategory]:
        """Return categories whose keywords appear in the query, ranked by hit count.

        If one category has strictly more keyword hits than all others, only
        that category is returned (avoiding unnecessary tie-breaking).
        """
        scores: dict[QueryCategory, int] = {}
        for category, keywords in _KEYWORD_MAP.items():
            count = sum(1 for kw in keywords if kw in normalized_query)
            if count > 0:
                scores[category] = count

        if not scores:
            return []

        max_score = max(scores.values())
        top = [cat for cat, s in scores.items() if s == max_score]
        return top

    def _embedding_tiebreak(
        self,
        query: str,
        candidates: list[QueryCategory],
    ) -> QueryCategory:
        """Use embedding similarity against prototype phrases to pick the best
        category from ``candidates``.

        Falls back to the deterministic ``_FALLBACK_CATEGORY`` (or the first
        candidate) when no embedder is available.
        """
        if self._embedder is None:
            # No embedder → deterministic fallback.
            if _FALLBACK_CATEGORY in candidates:
                return _FALLBACK_CATEGORY
            return candidates[0] if candidates else _FALLBACK_CATEGORY

        # Ensure prototype embeddings are computed.
        if self._prototype_embeddings is None:
            self._prototype_embeddings = self._compute_prototype_embeddings()

        query_vec = self._embedder.embed_query(query)

        best_category = _FALLBACK_CATEGORY
        best_score = -1.0

        for category in candidates:
            proto_vecs = self._prototype_embeddings.get(category, [])
            if not proto_vecs:
                continue
            # Average cosine similarity against the category's prototype phrases.
            avg_sim = sum(
                self._cosine_similarity(query_vec, pv) for pv in proto_vecs
            ) / len(proto_vecs)
            if avg_sim > best_score:
                best_score = avg_sim
                best_category = category

        return best_category

    def _compute_prototype_embeddings(self) -> dict[QueryCategory, list[list[float]]]:
        """Embed all prototype phrases once and cache the results."""
        assert self._embedder is not None  # noqa: S101 - guarded by caller
        result: dict[QueryCategory, list[list[float]]] = {}
        for category, phrases in _PROTOTYPE_PHRASES.items():
            result[category] = self._embedder.embed(phrases)
        return result

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Returns a value in ``[-1, 1]``; for non-normalized vectors this is
        the standard dot-product / (norm_a * norm_b).
        """
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
