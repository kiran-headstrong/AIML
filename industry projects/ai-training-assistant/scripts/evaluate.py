#!/usr/bin/env python3
"""Evaluation harness: run sample queries and record retrieval outputs.

Loads sample queries from ``data/sample_queries.csv``, runs each through the
retriever, and writes structured results to ``data/evaluation_output.csv``
plus a Markdown summary at ``data/evaluation_summary.md``.

Usage::

    python scripts/evaluate.py

The vector index and metadata store must already be built via
``python scripts/build.py`` before running this script.

Requirements: 13.1, 13.2, 13.3
"""

from __future__ import annotations

import csv
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so ``config`` and ``src.*`` resolve.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config  # noqa: E402  (must come after path fixup)
from src.models import RetrievalConfig, RetrievalOutcome  # noqa: E402


# ---------------------------------------------------------------------------
# Protocol for the retriever so run_evaluation can accept a fake in tests.
# ---------------------------------------------------------------------------
class RetrieverLike(Protocol):
    """Minimal interface expected by ``run_evaluation``."""

    def retrieve(self, query: str) -> RetrievalOutcome: ...


# ---------------------------------------------------------------------------
# Reusable evaluation logic
# ---------------------------------------------------------------------------
def run_evaluation(
    retriever: RetrieverLike,
    queries: list[dict[str, str]],
) -> list[dict]:
    """Run each query through *retriever* and return one record per query.

    This function is intentionally decoupled from file I/O so it can be called
    in tests with a fake retriever.

    Args:
        retriever: Anything with a ``retrieve(query) -> RetrievalOutcome`` method.
        queries: A list of dicts, each containing at least a ``"query"`` key.

    Returns:
        A list of result dicts (one per query) with keys: ``query``,
        ``category``, ``confidence``, ``text_references``,
        ``screenshot_matches``, ``num_text_matches``, ``num_screenshot_matches``.
    """
    results: list[dict] = []
    for entry in queries:
        query_text = entry["query"]
        outcome: RetrievalOutcome = retriever.retrieve(query_text)

        # Build semicolon-separated text references
        text_refs: list[str] = []
        for tm in outcome.text_matches:
            ref = tm.chunk.source_file
            if tm.chunk.page_reference is not None:
                ref += f":{tm.chunk.page_reference}"
            elif tm.chunk.section_reference is not None:
                ref += f":{tm.chunk.section_reference}"
            text_refs.append(ref)

        # Build semicolon-separated screenshot matches
        screenshot_refs: list[str] = [
            sm.item.file_name for sm in outcome.screenshot_matches
        ]

        results.append(
            {
                "query": query_text,
                "category": outcome.category.value,
                "confidence": outcome.confidence.value,
                "text_references": ";".join(text_refs),
                "screenshot_matches": ";".join(screenshot_refs),
                "num_text_matches": len(outcome.text_matches),
                "num_screenshot_matches": len(outcome.screenshot_matches),
            }
        )
    return results


def _load_sample_queries(path: Path) -> list[dict[str, str]]:
    """Load sample queries from a CSV file.

    The CSV must have at least a ``query`` column. An optional
    ``expected_category`` column is preserved but not required.

    Args:
        path: Path to the CSV file.

    Returns:
        A list of dicts, one per row.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the CSV has no ``query`` column.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Sample queries file not found at '{path}'. "
            "Create it or check config.SAMPLE_QUERIES_PATH."
        )
    rows: list[dict[str, str]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "query" not in reader.fieldnames:
            raise ValueError(
                f"Sample queries CSV at '{path}' must have a 'query' column."
            )
        for row in reader:
            rows.append(dict(row))
    return rows


def _write_evaluation_csv(results: list[dict], path: Path) -> None:
    """Write evaluation results to a CSV file.

    Args:
        results: The result dicts produced by ``run_evaluation``.
        path: The output CSV path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "query",
        "category",
        "confidence",
        "text_references",
        "screenshot_matches",
        "num_text_matches",
        "num_screenshot_matches",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def _write_evaluation_summary(results: list[dict], path: Path) -> None:
    """Write a Markdown summary of the evaluation results.

    The summary includes:
    - Total queries run
    - Category distribution
    - Confidence distribution
    - Number of no-match results (zero text and screenshot matches)

    Args:
        results: The result dicts produced by ``run_evaluation``.
        path: The output Markdown path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    category_counts = Counter(r["category"] for r in results)
    confidence_counts = Counter(r["confidence"] for r in results)
    no_match_count = sum(
        1
        for r in results
        if r["num_text_matches"] == 0 and r["num_screenshot_matches"] == 0
    )

    lines: list[str] = [
        "# Evaluation Summary",
        "",
        f"**Total queries run:** {total}",
        "",
        "## Category Distribution",
        "",
        "| Category | Count |",
        "|---|---|",
    ]
    for cat, count in sorted(category_counts.items()):
        lines.append(f"| {cat} | {count} |")

    lines.extend(
        [
            "",
            "## Confidence Distribution",
            "",
            "| Confidence | Count |",
            "|---|---|",
        ]
    )
    for conf, count in sorted(confidence_counts.items()):
        lines.append(f"| {conf} | {count} |")

    lines.extend(
        [
            "",
            "## No-Match Results",
            "",
            f"**Queries with no matches:** {no_match_count} / {total}",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the evaluation harness."""

    # 1. Load sample queries --------------------------------------------- #
    print(f"[1/5] Loading sample queries from {config.SAMPLE_QUERIES_PATH} …")
    try:
        queries = _load_sample_queries(config.SAMPLE_QUERIES_PATH)
    except (FileNotFoundError, ValueError) as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  Loaded {len(queries)} queries.")

    # 2. Load pre-built index and metadata ------------------------------- #
    print("[2/5] Loading vector index and metadata store …")
    try:
        from src.index.embedder import Embedder  # noqa: E402
        from src.index.metadata_store import MetadataStore  # noqa: E402
        from src.index.vector_index import ChromaVectorIndex  # noqa: E402
        from src.retrieval.retriever import Retriever  # noqa: E402

        index = ChromaVectorIndex(str(config.CHROMA_STORE_DIR))
        store = MetadataStore.load(str(config.METADATA_DB_PATH))
    except Exception as exc:
        print(
            f"\n✗ Could not load the index or metadata store: {exc}\n"
            "  Build the index first by running: python scripts/build.py",
            file=sys.stderr,
        )
        sys.exit(1)
    print("  Index and metadata store loaded.")

    # 3. Create retriever ------------------------------------------------ #
    print("[3/5] Initialising embedder and retriever …")
    try:
        embedder = Embedder(
            model_name=config.EMBEDDING_MODEL,
            cache_dir=str(config.MODEL_CACHE_DIR),
        )
        retrieval_config = RetrievalConfig(
            top_k=config.TOP_K,
            min_similarity=config.MIN_SIMILARITY,
            medium_confidence_threshold=config.MEDIUM_CONFIDENCE_THRESHOLD,
            high_confidence_threshold=config.HIGH_CONFIDENCE_THRESHOLD,
        )
        retriever = Retriever(index, store, embedder, retrieval_config)
    except Exception as exc:
        print(f"\n✗ Could not initialise the retriever: {exc}", file=sys.stderr)
        sys.exit(1)
    print("  Retriever ready.")

    # 4. Run evaluation -------------------------------------------------- #
    print(f"[4/5] Running {len(queries)} queries …")
    results = run_evaluation(retriever, queries)
    print(f"  Completed {len(results)} queries.")

    # 5. Write outputs --------------------------------------------------- #
    output_csv = config.EVALUATION_OUTPUT_PATH
    summary_md = output_csv.parent / "evaluation_summary.md"

    print(f"[5/5] Writing results to {output_csv} and {summary_md} …")
    _write_evaluation_csv(results, output_csv)
    _write_evaluation_summary(results, summary_md)

    print()
    print("✓ Evaluation complete.")
    print(f"  Output CSV : {output_csv}")
    print(f"  Summary MD : {summary_md}")


if __name__ == "__main__":
    main()
