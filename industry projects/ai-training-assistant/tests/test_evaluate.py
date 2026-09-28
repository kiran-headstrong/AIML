"""Unit tests for the evaluation harness (scripts/evaluate.py).

Tests the reusable ``run_evaluation`` function with a fake retriever to verify
that output records are produced correctly without requiring the real index.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

# Ensure project root is importable.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.evaluate import (
    _load_sample_queries,
    _write_evaluation_csv,
    _write_evaluation_summary,
    run_evaluation,
)
from src.models import (
    Confidence,
    DocType,
    QueryCategory,
    RetrievalOutcome,
    ScreenshotItem,
    ScreenshotMatch,
    TextChunk,
    TextMatch,
)


# --------------------------------------------------------------------------- #
# Fake retriever for unit testing
# --------------------------------------------------------------------------- #
class _FakeRetriever:
    """Returns a canned ``RetrievalOutcome`` for any query."""

    def __init__(self, outcome: RetrievalOutcome) -> None:
        self._outcome = outcome

    def retrieve(self, query: str) -> RetrievalOutcome:
        # Override the query field so we can verify round-trip.
        return RetrievalOutcome(
            query=query,
            category=self._outcome.category,
            text_matches=self._outcome.text_matches,
            screenshot_matches=self._outcome.screenshot_matches,
            confidence=self._outcome.confidence,
            no_match=self._outcome.no_match,
        )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
_SAMPLE_CHUNK = TextChunk(
    chunk_id="doc.pdf::1::0",
    text="Sample chunk text",
    source_file="doc.pdf",
    doc_type=DocType.PDF,
    page_reference=1,
    section_reference=None,
    topic_tag="onboarding",
    title="Doc Title",
)

_SAMPLE_SCREENSHOT = ScreenshotItem(
    item_id="screen.png",
    file_name="screen.png",
    file_path="/imgs/screen.png",
    topic_tag="dashboard",
    description="Dashboard view",
    ocr_text=None,
)

_OUTCOME_WITH_MATCHES = RetrievalOutcome(
    query="",
    category=QueryCategory.ONBOARDING,
    text_matches=[TextMatch(chunk=_SAMPLE_CHUNK, score=0.85)],
    screenshot_matches=[ScreenshotMatch(item=_SAMPLE_SCREENSHOT, score=0.70)],
    confidence=Confidence.HIGH,
    no_match=False,
)

_OUTCOME_NO_MATCH = RetrievalOutcome(
    query="",
    category=QueryCategory.TROUBLESHOOTING,
    text_matches=[],
    screenshot_matches=[],
    confidence=Confidence.LOW,
    no_match=True,
)


# --------------------------------------------------------------------------- #
# Tests for run_evaluation
# --------------------------------------------------------------------------- #
class TestRunEvaluation:
    """Tests for the reusable ``run_evaluation`` function."""

    def test_produces_one_record_per_query(self) -> None:
        queries = [{"query": "q1"}, {"query": "q2"}, {"query": "q3"}]
        retriever = _FakeRetriever(_OUTCOME_WITH_MATCHES)
        results = run_evaluation(retriever, queries)
        assert len(results) == 3

    def test_record_contains_required_keys(self) -> None:
        queries = [{"query": "test query"}]
        retriever = _FakeRetriever(_OUTCOME_WITH_MATCHES)
        results = run_evaluation(retriever, queries)
        record = results[0]
        expected_keys = {
            "query",
            "category",
            "confidence",
            "text_references",
            "screenshot_matches",
            "num_text_matches",
            "num_screenshot_matches",
        }
        assert set(record.keys()) == expected_keys

    def test_query_text_is_preserved(self) -> None:
        queries = [{"query": "How do I onboard?"}]
        retriever = _FakeRetriever(_OUTCOME_WITH_MATCHES)
        results = run_evaluation(retriever, queries)
        assert results[0]["query"] == "How do I onboard?"

    def test_category_and_confidence_values(self) -> None:
        queries = [{"query": "test"}]
        retriever = _FakeRetriever(_OUTCOME_WITH_MATCHES)
        results = run_evaluation(retriever, queries)
        assert results[0]["category"] == "onboarding"
        assert results[0]["confidence"] == "High"

    def test_text_references_format(self) -> None:
        queries = [{"query": "test"}]
        retriever = _FakeRetriever(_OUTCOME_WITH_MATCHES)
        results = run_evaluation(retriever, queries)
        # source_file:page_reference
        assert results[0]["text_references"] == "doc.pdf:1"

    def test_screenshot_matches_format(self) -> None:
        queries = [{"query": "test"}]
        retriever = _FakeRetriever(_OUTCOME_WITH_MATCHES)
        results = run_evaluation(retriever, queries)
        assert results[0]["screenshot_matches"] == "screen.png"

    def test_match_counts(self) -> None:
        queries = [{"query": "test"}]
        retriever = _FakeRetriever(_OUTCOME_WITH_MATCHES)
        results = run_evaluation(retriever, queries)
        assert results[0]["num_text_matches"] == 1
        assert results[0]["num_screenshot_matches"] == 1

    def test_no_match_outcome(self) -> None:
        queries = [{"query": "unknown"}]
        retriever = _FakeRetriever(_OUTCOME_NO_MATCH)
        results = run_evaluation(retriever, queries)
        record = results[0]
        assert record["num_text_matches"] == 0
        assert record["num_screenshot_matches"] == 0
        assert record["text_references"] == ""
        assert record["screenshot_matches"] == ""
        assert record["confidence"] == "Low"

    def test_empty_query_list(self) -> None:
        retriever = _FakeRetriever(_OUTCOME_WITH_MATCHES)
        results = run_evaluation(retriever, [])
        assert results == []

    def test_section_reference_used_when_no_page(self) -> None:
        """When a chunk has section_reference but no page_reference, the
        text reference should use the section."""
        chunk_with_section = TextChunk(
            chunk_id="notes.md::intro::0",
            text="Introduction text",
            source_file="notes.md",
            doc_type=DocType.NOTE,
            page_reference=None,
            section_reference="intro",
            topic_tag=None,
            title=None,
        )
        outcome = RetrievalOutcome(
            query="",
            category=QueryCategory.SOP_LOOKUP,
            text_matches=[TextMatch(chunk=chunk_with_section, score=0.6)],
            screenshot_matches=[],
            confidence=Confidence.MEDIUM,
            no_match=False,
        )
        retriever = _FakeRetriever(outcome)
        results = run_evaluation(retriever, [{"query": "sop"}])
        assert results[0]["text_references"] == "notes.md:intro"


# --------------------------------------------------------------------------- #
# Tests for CSV I/O helpers
# --------------------------------------------------------------------------- #
class TestCSVIO:
    """Tests for loading sample queries and writing evaluation output."""

    def test_load_sample_queries(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "queries.csv"
        csv_path.write_text("query,expected_category\nhello,onboarding\n", encoding="utf-8")
        rows = _load_sample_queries(csv_path)
        assert len(rows) == 1
        assert rows[0]["query"] == "hello"

    def test_load_sample_queries_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _load_sample_queries(tmp_path / "nonexistent.csv")

    def test_load_sample_queries_missing_query_column(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("col1,col2\na,b\n", encoding="utf-8")
        with pytest.raises(ValueError, match="query"):
            _load_sample_queries(csv_path)

    def test_write_evaluation_csv(self, tmp_path: Path) -> None:
        results = [
            {
                "query": "q1",
                "category": "onboarding",
                "confidence": "High",
                "text_references": "doc.pdf:1",
                "screenshot_matches": "img.png",
                "num_text_matches": 1,
                "num_screenshot_matches": 1,
            }
        ]
        out = tmp_path / "output.csv"
        _write_evaluation_csv(results, out)
        assert out.exists()

        with open(out, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["query"] == "q1"
        assert rows[0]["category"] == "onboarding"

    def test_write_evaluation_summary(self, tmp_path: Path) -> None:
        results = [
            {
                "query": "q1",
                "category": "onboarding",
                "confidence": "High",
                "text_references": "",
                "screenshot_matches": "",
                "num_text_matches": 0,
                "num_screenshot_matches": 0,
            },
            {
                "query": "q2",
                "category": "sop_lookup",
                "confidence": "Low",
                "text_references": "doc.pdf:1",
                "screenshot_matches": "",
                "num_text_matches": 1,
                "num_screenshot_matches": 0,
            },
        ]
        out = tmp_path / "summary.md"
        _write_evaluation_summary(results, out)
        assert out.exists()

        content = out.read_text(encoding="utf-8")
        assert "Total queries run:** 2" in content
        assert "onboarding" in content
        assert "sop_lookup" in content
        assert "High" in content
        assert "Low" in content
        # One no-match result (q1 has 0 text + 0 screenshot matches)
        assert "1 / 2" in content


# --------------------------------------------------------------------------- #
# Property-based tests (Hypothesis)
# --------------------------------------------------------------------------- #
from hypothesis import given, settings, strategies as st

from src.models import QueryCategory, Confidence

# Import the RetrievalOutcome strategy from conftest.
from tests.conftest import st_retrieval_outcomes


# Feature: internal-training-content-search, Property 14: Evaluation output is complete
class _PropertyFakeRetriever:
    """Fake retriever for property testing that returns a fixed
    ``RetrievalOutcome`` (pre-drawn from ``st_retrieval_outcomes``) for every
    query, overriding the query field to match the incoming query text."""

    def __init__(self, outcome: RetrievalOutcome) -> None:
        self._outcome = outcome

    def retrieve(self, query: str) -> RetrievalOutcome:
        return RetrievalOutcome(
            query=query,
            category=self._outcome.category,
            text_matches=self._outcome.text_matches,
            screenshot_matches=self._outcome.screenshot_matches,
            confidence=self._outcome.confidence,
            no_match=self._outcome.no_match,
        )


# Strategies for generating random query lists
_st_query_text = st.text(min_size=1, max_size=120)
_st_query_dicts = st.lists(
    st.fixed_dictionaries({"query": _st_query_text}),
    min_size=0,
    max_size=15,
)

_VALID_CATEGORIES = {c.value for c in QueryCategory}
_VALID_CONFIDENCES = {c.value for c in Confidence}


# Validates: Requirements 13.2
@given(queries=_st_query_dicts, outcome=st_retrieval_outcomes())
@settings(max_examples=100, deadline=None)
def test_evaluation_output_is_complete(
    queries: list[dict[str, str]],
    outcome: RetrievalOutcome,
) -> None:
    """Property 14: For any list of sample queries, ``run_evaluation`` produces
    exactly one output record per query, and each record contains the retrieved
    text references, the retrieved screenshot matches, the assigned
    QueryCategory, and the Confidence_Indicator."""

    retriever = _PropertyFakeRetriever(outcome)
    results = run_evaluation(retriever, queries)

    # Exactly one record per query.
    assert len(results) == len(queries)

    required_keys = {
        "query",
        "category",
        "confidence",
        "text_references",
        "screenshot_matches",
        "num_text_matches",
        "num_screenshot_matches",
    }

    for i, record in enumerate(results):
        # Each record has all required keys.
        assert set(record.keys()) == required_keys, (
            f"Record {i} keys mismatch: expected {required_keys}, got {set(record.keys())}"
        )

        # Query text is preserved.
        assert record["query"] == queries[i]["query"]

        # Category is a valid QueryCategory value.
        assert record["category"] in _VALID_CATEGORIES, (
            f"Record {i} category '{record['category']}' not in {_VALID_CATEGORIES}"
        )

        # Confidence is a valid Confidence value.
        assert record["confidence"] in _VALID_CONFIDENCES, (
            f"Record {i} confidence '{record['confidence']}' not in {_VALID_CONFIDENCES}"
        )

        # text_references and screenshot_matches are strings (possibly empty).
        assert isinstance(record["text_references"], str)
        assert isinstance(record["screenshot_matches"], str)

        # Numeric counts are non-negative integers.
        assert isinstance(record["num_text_matches"], int)
        assert isinstance(record["num_screenshot_matches"], int)
        assert record["num_text_matches"] >= 0
        assert record["num_screenshot_matches"] >= 0
