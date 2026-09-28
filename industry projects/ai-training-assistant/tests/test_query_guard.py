"""Property-based tests for the empty-query guard (Req 7.4).

# Feature: internal-training-content-search, Property 10: Empty queries are rejected without retrieval
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from src.retrieval.query_guard import QueryGuardResult, check_query


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #

def st_whitespace_only() -> st.SearchStrategy[str]:
    """Generate whitespace-only strings: empty, spaces, tabs, newlines, and
    combinations thereof."""
    return st.one_of(
        st.just(""),
        st.just(" "),
        st.just("   "),
        st.just("\t"),
        st.just("\n"),
        st.just("\r\n"),
        st.just("\t\n  \r"),
        st.text(
            alphabet=st.sampled_from([" ", "\t", "\n", "\r"]),
            min_size=0,
            max_size=50,
        ),
    )


def st_non_whitespace_queries() -> st.SearchStrategy[str]:
    """Generate strings that contain at least one non-whitespace character."""
    return st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != "")


# --------------------------------------------------------------------------- #
# Property 10 — whitespace-only / empty queries are rejected
# --------------------------------------------------------------------------- #


@given(query=st_whitespace_only())
@settings(max_examples=100, deadline=None)
def test_empty_or_whitespace_queries_are_rejected(query: str) -> None:
    """**Validates: Requirements 7.4**

    For ANY whitespace-only or empty query string, ``check_query`` returns
    ``is_valid=False`` with a non-None ``prompt_message``.  Because
    ``is_valid`` is ``False``, the retriever is never called — the guard is
    a pure predicate that gates retrieval.
    """
    result = check_query(query)

    assert isinstance(result, QueryGuardResult), (
        f"Expected QueryGuardResult, got {type(result)}"
    )

    # The query must be rejected.
    assert result.is_valid is False, (
        f"Whitespace-only query {query!r} should be invalid, got is_valid=True"
    )

    # A prompt message must be provided to the user.
    assert result.prompt_message is not None, (
        f"Rejected query {query!r} should have a non-None prompt_message"
    )

    # The prompt message should be a non-empty string.
    assert isinstance(result.prompt_message, str) and len(result.prompt_message) > 0, (
        f"prompt_message should be a non-empty string, got {result.prompt_message!r}"
    )


# --------------------------------------------------------------------------- #
# Property 10 — non-whitespace queries are accepted
# --------------------------------------------------------------------------- #


@given(query=st_non_whitespace_queries())
@settings(max_examples=100, deadline=None)
def test_non_whitespace_queries_are_accepted(query: str) -> None:
    """**Validates: Requirements 7.4**

    For ANY query that contains at least one non-whitespace character,
    ``check_query`` returns ``is_valid=True`` with ``prompt_message=None``.
    """
    result = check_query(query)

    assert isinstance(result, QueryGuardResult), (
        f"Expected QueryGuardResult, got {type(result)}"
    )

    # The query must be accepted.
    assert result.is_valid is True, (
        f"Non-whitespace query {query!r} should be valid, got is_valid=False"
    )

    # No prompt message for valid queries.
    assert result.prompt_message is None, (
        f"Valid query {query!r} should have prompt_message=None, got {result.prompt_message!r}"
    )
