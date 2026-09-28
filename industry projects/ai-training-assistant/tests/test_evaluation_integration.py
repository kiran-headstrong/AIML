"""Integration and smoke tests for the evaluation harness.

Integration test: runs the bundled sample queries end-to-end through a test
pipeline using fakes (FakeEmbedder, FakeVectorIndex) and asserts that output
files are written with the expected number of rows.

Smoke tests: verify CPU-only and no-network defaults, and that the sample
query set meets the minimum requirements.

Validates: Requirements 6.2, 12.1, 12.2, 13.1, 13.3
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

import config
from scripts.evaluate import (
    _load_sample_queries,
    _write_evaluation_csv,
    _write_evaluation_summary,
    run_evaluation,
)
from src.index.metadata_store import MetadataStore
from src.index.vector_index import IndexEntry
from src.models import (
    DocType,
    QueryCategory,
    RetrievalConfig,
    ScreenshotItem,
    TextChunk,
)
from src.retrieval.retriever import Retriever
from tests.conftest import FakeEmbedder, FakeVectorIndex


# --------------------------------------------------------------------------- #
# Integration test: end-to-end evaluation with fakes (Req 13.3)
# --------------------------------------------------------------------------- #
class TestEvaluationIntegration:
    """Run the bundled sample queries through a fake pipeline and assert
    output files are written with the expected number of rows."""

    def test_end_to_end_evaluation_writes_expected_output(self, tmp_path: Path) -> None:
        """Integration: load real sample_queries.csv, run through a fake
        retriever, write CSV and summary, and assert row counts.

        Validates: Requirements 13.3
        """
        # 1. Create fake embedder and vector index
        embedder = FakeEmbedder()
        index = FakeVectorIndex()

        # 2. Create a MetadataStore with some test chunks and screenshots
        store = MetadataStore()

        test_chunks = [
            TextChunk(
                chunk_id=f"doc{i}.pdf::1::{i}",
                text=f"Test chunk content number {i} about operations and onboarding.",
                source_file=f"doc{i}.pdf",
                doc_type=DocType.PDF,
                page_reference=1,
                section_reference=None,
                topic_tag="onboarding",
                title=f"Document {i}",
            )
            for i in range(5)
        ]
        test_screenshots = [
            ScreenshotItem(
                item_id=f"screen{i}.png",
                file_name=f"screen{i}.png",
                file_path=f"/imgs/screen{i}.png",
                topic_tag="dashboard",
                description=f"Screenshot {i} of the dashboard",
                ocr_text=None,
            )
            for i in range(3)
        ]

        store.save_chunks(test_chunks)
        store.save_screenshots(test_screenshots)

        # 3. Upsert chunk embeddings into the fake vector index
        for chunk in test_chunks:
            vec = embedder.embed_query(chunk.text)
            index.upsert([IndexEntry(chunk_id=chunk.chunk_id, vector=vec, metadata={})])

        # Also upsert screenshot embeddings so they can be retrieved
        for screenshot in test_screenshots:
            desc = screenshot.description or screenshot.file_name
            vec = embedder.embed_query(desc)
            index.upsert(
                [IndexEntry(chunk_id=screenshot.item_id, vector=vec, metadata={})]
            )

        # 4. Create a Retriever using the fakes
        retrieval_config = RetrievalConfig(
            top_k=config.TOP_K,
            min_similarity=config.MIN_SIMILARITY,
            medium_confidence_threshold=config.MEDIUM_CONFIDENCE_THRESHOLD,
            high_confidence_threshold=config.HIGH_CONFIDENCE_THRESHOLD,
        )
        retriever = Retriever(index, store, embedder, retrieval_config)

        # 5. Load the real sample_queries.csv
        queries = _load_sample_queries(config.SAMPLE_QUERIES_PATH)
        assert len(queries) > 0, "sample_queries.csv should not be empty"

        # 6. Run the evaluation
        results = run_evaluation(retriever, queries)

        # 7. Write output files to tmp dir
        output_csv = tmp_path / "evaluation_output.csv"
        summary_md = tmp_path / "evaluation_summary.md"
        _write_evaluation_csv(results, output_csv)
        _write_evaluation_summary(results, summary_md)

        # 8. Assert the output CSV has exactly one row per query (25 rows)
        assert output_csv.exists(), "evaluation_output.csv was not written"
        with open(output_csv, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        expected_count = len(queries)
        assert len(rows) == expected_count, (
            f"Expected {expected_count} rows in output CSV, got {len(rows)}"
        )

        # Verify each row has the required fields
        required_fields = {
            "query",
            "category",
            "confidence",
            "text_references",
            "screenshot_matches",
            "num_text_matches",
            "num_screenshot_matches",
        }
        for i, row in enumerate(rows):
            assert required_fields.issubset(set(row.keys())), (
                f"Row {i} missing fields: {required_fields - set(row.keys())}"
            )

        # 9. Assert the summary Markdown file is also written
        assert summary_md.exists(), "evaluation_summary.md was not written"
        summary_content = summary_md.read_text(encoding="utf-8")
        assert "Evaluation Summary" in summary_content
        assert f"Total queries run:** {expected_count}" in summary_content


# --------------------------------------------------------------------------- #
# Smoke tests (Req 6.2, 12.1, 12.2, 13.1)
# --------------------------------------------------------------------------- #


@pytest.mark.smoke
class TestCPUOnlyNoGPU:
    """Smoke: CPU-only build/query with no GPU (Req 6.2, 12.1)."""

    def test_config_does_not_require_gpu_settings(self) -> None:
        """Verify that config.py doesn't require GPU settings.

        Validates: Requirements 6.2, 12.1
        """
        # The config module should not have any GPU-related settings that
        # default to requiring a GPU.
        assert not hasattr(config, "REQUIRE_GPU") or not config.REQUIRE_GPU
        assert not hasattr(config, "GPU_DEVICE") or config.GPU_DEVICE is None

    def test_answer_model_default_is_extractive(self) -> None:
        """Verify that ANSWER_MODEL default is "extractive" (no external model needed).

        Validates: Requirements 6.2, 12.1
        """
        assert config.ANSWER_MODEL == "extractive", (
            f"Expected ANSWER_MODEL='extractive', got '{config.ANSWER_MODEL}'"
        )


@pytest.mark.smoke
class TestDefaultExtractiveNoNetwork:
    """Smoke: Default ANSWER_MODEL=extractive with no network (Req 12.2)."""

    def test_answer_model_is_extractive(self) -> None:
        """Verify config.ANSWER_MODEL == 'extractive' by default.

        Validates: Requirements 12.2
        """
        assert config.ANSWER_MODEL == "extractive", (
            f"Expected ANSWER_MODEL='extractive', got '{config.ANSWER_MODEL}'"
        )

    def test_ocr_disabled_by_default(self) -> None:
        """Verify config.OCR_ENABLED == False by default.

        Validates: Requirements 12.2
        """
        assert config.OCR_ENABLED is False, (
            f"Expected OCR_ENABLED=False, got {config.OCR_ENABLED}"
        )


@pytest.mark.smoke
class TestSampleQuerySet:
    """Smoke: Sample query set has at least 20 queries (Req 13.1)."""

    def test_sample_queries_has_at_least_20(self) -> None:
        """Load data/sample_queries.csv and assert len >= 20.

        Validates: Requirements 13.1
        """
        queries = _load_sample_queries(config.SAMPLE_QUERIES_PATH)
        assert len(queries) >= 20, (
            f"Expected at least 20 sample queries, got {len(queries)}"
        )

    def test_each_row_has_query_column(self) -> None:
        """Assert each row has a 'query' column.

        Validates: Requirements 13.1
        """
        queries = _load_sample_queries(config.SAMPLE_QUERIES_PATH)
        for i, row in enumerate(queries):
            assert "query" in row, f"Row {i} missing 'query' column"
            assert row["query"].strip(), f"Row {i} has an empty query"

    def test_each_row_has_valid_expected_category(self) -> None:
        """Assert each row has an 'expected_category' that's a valid
        QueryCategory value.

        Validates: Requirements 13.1
        """
        valid_categories = {cat.value for cat in QueryCategory}
        queries = _load_sample_queries(config.SAMPLE_QUERIES_PATH)
        for i, row in enumerate(queries):
            assert "expected_category" in row, (
                f"Row {i} missing 'expected_category' column"
            )
            assert row["expected_category"] in valid_categories, (
                f"Row {i} expected_category '{row['expected_category']}' "
                f"not in {valid_categories}"
            )
