"""Property-based tests for the Categorizer (Req 8.1).

# Feature: internal-training-content-search, Property 9: Query categorization is total and single-valued
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from src.models import QueryCategory
from src.retrieval.categorizer import Categorizer
from tests.conftest import FakeEmbedder, st_query_strings

# The complete fixed set of category values (Req 8.1).
_VALID_CATEGORIES = {
    QueryCategory.ONBOARDING,
    QueryCategory.SOP_LOOKUP,
    QueryCategory.SCREENSHOT_LOOKUP,
    QueryCategory.POLICY_REFERENCE,
    QueryCategory.TROUBLESHOOTING,
}

_VALID_CATEGORY_VALUES = {
    "onboarding",
    "sop_lookup",
    "screenshot_lookup",
    "policy_reference",
    "troubleshooting_support",
}


# --------------------------------------------------------------------------- #
# Property 9 — with FakeEmbedder (tie-breaker path)
# --------------------------------------------------------------------------- #


@given(query=st_query_strings())
@settings(max_examples=100, deadline=None)
def test_categorize_total_and_single_valued_with_embedder(query: str) -> None:
    """**Validates: Requirements 8.1**

    For ANY query string the Categorizer (with an embedder for the tie-breaker
    path) returns exactly one QueryCategory from the fixed 5-category set.
    """
    categorizer = Categorizer(embedder=FakeEmbedder())
    result = categorizer.categorize(query)

    # Returns exactly one value (not a list, not None).
    assert isinstance(result, QueryCategory), (
        f"Expected a QueryCategory, got {type(result)}"
    )

    # The value is a member of the fixed set.
    assert result in _VALID_CATEGORIES, (
        f"Category {result!r} is not in the fixed set {_VALID_CATEGORIES}"
    )

    # Its string value matches one of the 5 defined values.
    assert result.value in _VALID_CATEGORY_VALUES, (
        f"Category value {result.value!r} is not in {_VALID_CATEGORY_VALUES}"
    )


# --------------------------------------------------------------------------- #
# Property 9 — with embedder=None (fallback path)
# --------------------------------------------------------------------------- #


@given(query=st_query_strings())
@settings(max_examples=100, deadline=None)
def test_categorize_total_and_single_valued_without_embedder(query: str) -> None:
    """**Validates: Requirements 8.1**

    For ANY query string the Categorizer (without an embedder, exercising the
    deterministic fallback path) returns exactly one QueryCategory from the
    fixed 5-category set.
    """
    categorizer = Categorizer(embedder=None)
    result = categorizer.categorize(query)

    assert isinstance(result, QueryCategory), (
        f"Expected a QueryCategory, got {type(result)}"
    )
    assert result in _VALID_CATEGORIES, (
        f"Category {result!r} is not in the fixed set {_VALID_CATEGORIES}"
    )
    assert result.value in _VALID_CATEGORY_VALUES, (
        f"Category value {result.value!r} is not in {_VALID_CATEGORY_VALUES}"
    )


# --------------------------------------------------------------------------- #
# Property 9 — broad coverage with st.text() + FakeEmbedder
# --------------------------------------------------------------------------- #


@given(query=st.text(min_size=0, max_size=500))
@settings(max_examples=100, deadline=None)
def test_categorize_total_and_single_valued_broad_text(query: str) -> None:
    """**Validates: Requirements 8.1**

    Broader coverage using st.text() (including empty, whitespace-only, and
    arbitrary unicode) with the FakeEmbedder to exercise the tie-breaker path.
    """
    categorizer = Categorizer(embedder=FakeEmbedder())
    result = categorizer.categorize(query)

    assert isinstance(result, QueryCategory), (
        f"Expected a QueryCategory, got {type(result)}"
    )
    assert result in _VALID_CATEGORIES, (
        f"Category {result!r} is not in the fixed set {_VALID_CATEGORIES}"
    )
    assert result.value in _VALID_CATEGORY_VALUES, (
        f"Category value {result.value!r} is not in {_VALID_CATEGORY_VALUES}"
    )
