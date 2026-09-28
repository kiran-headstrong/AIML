"""Pure empty-query guard for the search interface.

Provides a predicate that checks whether a query string is valid for
retrieval.  Whitespace-only and empty queries are rejected with a
user-friendly prompt message, preventing unnecessary retriever invocations.

This module is **pure** — no Streamlit imports, no retriever calls, no side
effects — so it can be verified with property-based tests (Property 10).

Design reference: Requirement 7.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QueryGuardResult:
    """Result of the empty-query guard check.

    Attributes
    ----------
    is_valid:
        ``True`` when the query contains at least one non-whitespace
        character and retrieval should proceed.  ``False`` when the query
        is empty or whitespace-only and retrieval must be skipped.
    prompt_message:
        A user-facing message explaining why the query was rejected.
        Non-``None`` only when ``is_valid`` is ``False``.
    """

    is_valid: bool
    prompt_message: Optional[str]  # non-None when is_valid is False


def check_query(query: str) -> QueryGuardResult:
    """Check whether *query* is valid for retrieval.

    Returns a ``QueryGuardResult`` where ``is_valid=True`` means proceed
    with retrieval, and ``is_valid=False`` means show ``prompt_message``
    and skip retrieval.

    Req 7.4.
    """
    if not query or not query.strip():
        return QueryGuardResult(
            is_valid=False,
            prompt_message="Please enter a non-empty query to search.",
        )
    return QueryGuardResult(is_valid=True, prompt_message=None)
