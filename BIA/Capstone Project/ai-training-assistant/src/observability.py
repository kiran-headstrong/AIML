"""Observability for the AI Training Assistant.

Provides lightweight, dependency-free observability built on the Python
standard library:

- **Structured logging**: human-readable console logs plus machine-readable
  JSONL event logs written to ``data/logs/``.
- **Tracing**: a ``trace_span`` context manager that times a unit of work
  (routing, retrieval, generation, or a full query) and records structured
  metadata and errors.
- **Metrics**: an in-process :class:`MetricsCollector` that aggregates counts,
  latencies (with p50/p95), token usage, retrieval scores, routing category
  distribution, confidence distribution, and error counts.

The design intentionally avoids heavy third-party APM/OTEL dependencies so the
install stays lightweight (matching the project's ONNX-over-PyTorch choice),
while still giving production-style visibility that can later be exported to a
backend (e.g. OpenTelemetry, Prometheus) if desired.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterator


LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "logs"
EVENTS_FILE = LOG_DIR / "events.jsonl"

# Bounded history so a long-running session never grows memory without limit.
_MAX_LATENCY_SAMPLES = 1000
# Bounded history of per-query records used for admin charts and reports.
_MAX_QUERY_RECORDS = 5000


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Returns:
        The current UTC timestamp, e.g. ``"2026-08-23T12:34:56.789+00:00"``.
    """
    return datetime.now(timezone.utc).isoformat()


class _JsonlHandler(logging.Handler):
    """A logging handler that appends structured records as JSONL.

    Each emitted record is written as a single JSON object per line to
    ``EVENTS_FILE``. Extra structured fields attached to the log record via the
    ``extra={"event": {...}}`` mechanism are merged into the JSON payload.
    """

    def __init__(self, path: Path) -> None:
        """Initialize the handler.

        Args:
            path: Destination JSONL file. Parent directories are created.
        """
        super().__init__()
        self._path = path
        self._lock = Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        """Write a single log record as one JSON line.

        Args:
            record: The log record to serialize.
        """
        try:
            payload: dict[str, Any] = {
                "ts": _utc_now_iso(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            event = getattr(record, "event", None)
            if isinstance(event, dict):
                payload.update(event)
            line = json.dumps(payload, ensure_ascii=False, default=str)
            with self._lock, self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa: BLE001 - logging must never crash the app
            self.handleError(record)


_configured = False
_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    """Return the shared, configured observability logger.

    Configures a console handler (human-readable) and a JSONL file handler
    (machine-readable) exactly once, then returns the singleton logger.

    Returns:
        The configured ``ai_training_assistant`` logger.
    """
    global _configured, _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("ai_training_assistant")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not _configured:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(console)

        try:
            logger.addHandler(_JsonlHandler(EVENTS_FILE))
        except Exception as exc:  # noqa: BLE001 - file logging is best-effort
            logger.warning("JSONL event logging disabled: %s", exc)

        _configured = True

    _logger = logger
    return logger


def log_event(level: int, message: str, **fields: Any) -> None:
    """Log a structured event to console and the JSONL event log.

    Args:
        level: A ``logging`` level, e.g. ``logging.INFO``.
        message: Human-readable message for the console log.
        **fields: Arbitrary structured key/value pairs merged into the JSONL
            event payload (e.g. ``span="retrieval"``, ``duration_ms=42.1``).
    """
    get_logger().log(level, message, extra={"event": fields})


@dataclass
class MetricsCollector:
    """Thread-safe, in-process aggregator of runtime metrics.

    Tracks query volume, error counts, latency distributions per span, token
    usage, retrieval score stats, and category/confidence distributions. A
    single shared instance is exposed via :data:`metrics`.
    """

    total_queries: int = 0
    total_errors: int = 0
    total_fallbacks: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Retrieval was scoped to a routing category via the vector-DB metadata
    # filter (as opposed to an unfiltered search).
    total_category_filtered: int = 0
    # A category-scoped search found nothing relevant and was retried unfiltered.
    total_unfiltered_retries: int = 0
    # User answer feedback (thumbs up / down).
    feedback_up: int = 0
    feedback_down: int = 0
    category_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    confidence_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    filter_category_counts: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    error_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _latencies: dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=_MAX_LATENCY_SAMPLES))
    )
    _retrieval_scores: deque = field(
        default_factory=lambda: deque(maxlen=_MAX_LATENCY_SAMPLES)
    )
    # Per-query records (timestamped) that power the admin charts and reports.
    _query_records: deque = field(
        default_factory=lambda: deque(maxlen=_MAX_QUERY_RECORDS)
    )
    _lock: Lock = field(default_factory=Lock)

    def record_latency(self, span: str, duration_ms: float) -> None:
        """Record a latency sample for a named span.

        Args:
            span: The span name, e.g. ``"routing"`` or ``"query"``.
            duration_ms: The measured duration in milliseconds.
        """
        with self._lock:
            self._latencies[span].append(duration_ms)

    def record_query(
        self,
        *,
        category: str,
        confidence: str,
        is_fallback: bool,
        top_score: float | None,
        filter_category: str | None = None,
        unfiltered_retry: bool = False,
        username: str = "anonymous",
        latency_ms: float | None = None,
    ) -> None:
        """Record the outcome of a completed query.

        Args:
            category: The routed category (e.g. ``"policy"``).
            confidence: The confidence label (``"high"``/``"medium"``/``"low"``).
            is_fallback: Whether the fallback (no relevant context) path fired.
            top_score: The best retrieval similarity score, if any.
            filter_category: The category retrieval was scoped to, or ``None``
                if the search was unfiltered.
            unfiltered_retry: Whether a category-scoped search returned nothing
                relevant and was retried unfiltered.
            username: The user who issued the query (for audit + admin charts).
            latency_ms: Total end-to-end query latency in milliseconds, if known.
        """
        with self._lock:
            self.total_queries += 1
            self.category_counts[category] += 1
            self.confidence_counts[confidence] += 1
            if is_fallback:
                self.total_fallbacks += 1
            if filter_category is not None:
                self.total_category_filtered += 1
                self.filter_category_counts[filter_category] += 1
            if unfiltered_retry:
                self.total_unfiltered_retries += 1
            if top_score is not None:
                self._retrieval_scores.append(top_score)
            self._query_records.append({
                "ts": _utc_now_iso(),
                "username": username,
                "category": category,
                "confidence": confidence,
                "is_fallback": is_fallback,
                "filter_category": filter_category or "none",
                "unfiltered_retry": unfiltered_retry,
                "top_score": round(top_score, 4) if top_score is not None else None,
                "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
            })

    def query_records(self) -> list[dict]:
        """Return a copy of the per-query records for charts and reports.

        Returns:
            A list of timestamped per-query record dicts (oldest first).
        """
        with self._lock:
            return list(self._query_records)

    def record_feedback(self, positive: bool) -> None:
        """Record a user's thumbs up/down feedback on an answer.

        Args:
            positive: True for a thumbs-up, False for a thumbs-down.
        """
        with self._lock:
            if positive:
                self.feedback_up += 1
            else:
                self.feedback_down += 1

    def record_tokens(self, prompt: int, completion: int) -> None:
        """Record token usage reported by the LLM API.

        Args:
            prompt: Number of prompt tokens consumed.
            completion: Number of completion tokens generated.
        """
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.total_tokens += prompt + completion

    def record_error(self, error_type: str) -> None:
        """Record an error occurrence by type.

        Args:
            error_type: The exception class name or a short error label.
        """
        with self._lock:
            self.total_errors += 1
            self.error_counts[error_type] += 1

    @staticmethod
    def _percentile(samples: list[float], pct: float) -> float:
        """Compute a percentile from a list of samples.

        Args:
            samples: The latency samples (unsorted is fine).
            pct: The percentile in ``[0, 100]``.

        Returns:
            The percentile value, or ``0.0`` if there are no samples.
        """
        if not samples:
            return 0.0
        ordered = sorted(samples)
        k = (len(ordered) - 1) * (pct / 100.0)
        lo = int(k)
        hi = min(lo + 1, len(ordered) - 1)
        if lo == hi:
            return ordered[lo]
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)

    def snapshot(self) -> dict[str, Any]:
        """Return a point-in-time summary of all collected metrics.

        Returns:
            A JSON-serializable dict with counts, latency stats (avg/p50/p95),
            token usage, and retrieval score stats.
        """
        with self._lock:
            latency_stats: dict[str, dict[str, float]] = {}
            for span, samples in self._latencies.items():
                data = list(samples)
                if not data:
                    continue
                latency_stats[span] = {
                    "count": len(data),
                    "avg_ms": round(sum(data) / len(data), 1),
                    "p50_ms": round(self._percentile(data, 50), 1),
                    "p95_ms": round(self._percentile(data, 95), 1),
                    "max_ms": round(max(data), 1),
                }

            scores = list(self._retrieval_scores)
            retrieval = {
                "count": len(scores),
                "avg_top_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
                "min_top_score": round(min(scores), 3) if scores else 0.0,
                "max_top_score": round(max(scores), 3) if scores else 0.0,
            }

            return {
                "total_queries": self.total_queries,
                "total_errors": self.total_errors,
                "total_fallbacks": self.total_fallbacks,
                "error_rate": (
                    round(self.total_errors / self.total_queries, 3)
                    if self.total_queries
                    else 0.0
                ),
                "fallback_rate": (
                    round(self.total_fallbacks / self.total_queries, 3)
                    if self.total_queries
                    else 0.0
                ),
                "total_category_filtered": self.total_category_filtered,
                "category_filter_rate": (
                    round(self.total_category_filtered / self.total_queries, 3)
                    if self.total_queries
                    else 0.0
                ),
                "total_unfiltered_retries": self.total_unfiltered_retries,
                "unfiltered_retry_rate": (
                    round(self.total_unfiltered_retries / self.total_queries, 3)
                    if self.total_queries
                    else 0.0
                ),
                "filter_categories": dict(self.filter_category_counts),
                "feedback": {
                    "up": self.feedback_up,
                    "down": self.feedback_down,
                    "total": self.feedback_up + self.feedback_down,
                    "satisfaction_rate": (
                        round(
                            self.feedback_up
                            / (self.feedback_up + self.feedback_down),
                            3,
                        )
                        if (self.feedback_up + self.feedback_down)
                        else 0.0
                    ),
                },
                "tokens": {
                    "prompt": self.prompt_tokens,
                    "completion": self.completion_tokens,
                    "total": self.total_tokens,
                },
                "latency": latency_stats,
                "retrieval": retrieval,
                "categories": dict(self.category_counts),
                "confidence": dict(self.confidence_counts),
                "errors": dict(self.error_counts),
            }

    def reset(self) -> None:
        """Reset all counters and samples to their initial state."""
        with self._lock:
            self.total_queries = 0
            self.total_errors = 0
            self.total_fallbacks = 0
            self.total_tokens = 0
            self.prompt_tokens = 0
            self.completion_tokens = 0
            self.total_category_filtered = 0
            self.total_unfiltered_retries = 0
            self.feedback_up = 0
            self.feedback_down = 0
            self.category_counts.clear()
            self.confidence_counts.clear()
            self.filter_category_counts.clear()
            self.error_counts.clear()
            self._latencies.clear()
            self._retrieval_scores.clear()
            self._query_records.clear()


# Shared, process-wide metrics collector.
metrics = MetricsCollector()


@contextmanager
def trace_span(
    span: str,
    *,
    trace_id: str | None = None,
    **attributes: Any,
) -> Iterator[dict[str, Any]]:
    """Time a unit of work and emit a structured trace event.

    Records the span duration into :data:`metrics`, logs a structured event on
    completion (or error), and yields a mutable ``attributes`` dict so callers
    can attach result metadata (e.g. token counts, scores) during the span.

    Args:
        span: The span name, e.g. ``"routing"``, ``"retrieval"``,
            ``"generation"``, or ``"query"``.
        trace_id: Optional correlation id. A new one is generated if omitted.
        **attributes: Initial structured attributes for the span.

    Yields:
        The mutable attributes dict for the span. Add keys to enrich the trace.

    Raises:
        Exception: Re-raises any exception from the wrapped block after
            recording it as an error metric and logging it.
    """
    trace_id = trace_id or uuid.uuid4().hex[:12]
    attributes = dict(attributes)
    attributes["trace_id"] = trace_id
    start = time.perf_counter()
    try:
        yield attributes
    except Exception as exc:  # noqa: BLE001 - record then re-raise
        duration_ms = (time.perf_counter() - start) * 1000.0
        metrics.record_latency(span, duration_ms)
        metrics.record_error(type(exc).__name__)
        log_event(
            logging.ERROR,
            f"span '{span}' failed: {exc}",
            span=span,
            status="error",
            error_type=type(exc).__name__,
            duration_ms=round(duration_ms, 2),
            **attributes,
        )
        raise
    else:
        duration_ms = (time.perf_counter() - start) * 1000.0
        metrics.record_latency(span, duration_ms)
        log_event(
            logging.INFO,
            f"span '{span}' ok ({duration_ms:.1f} ms)",
            span=span,
            status="ok",
            duration_ms=round(duration_ms, 2),
            **attributes,
        )


def format_metrics_markdown() -> str:
    """Render the current metrics snapshot as a compact markdown report.

    Returns:
        A markdown string suitable for display in the Gradio UI.
    """
    snap = metrics.snapshot()
    if snap["total_queries"] == 0:
        return "_No queries yet. Ask a question to see live metrics._"

    lines: list[str] = ["### 📊 Live Metrics", ""]
    lines.append(f"- **Queries:** {snap['total_queries']}")
    lines.append(
        f"- **Errors:** {snap['total_errors']} "
        f"(rate {snap['error_rate']:.0%})"
    )
    lines.append(
        f"- **Fallbacks:** {snap['total_fallbacks']} "
        f"(rate {snap['fallback_rate']:.0%})"
    )

    tokens = snap["tokens"]
    lines.append(
        f"- **Tokens:** {tokens['total']:,} "
        f"(prompt {tokens['prompt']:,} / completion {tokens['completion']:,})"
    )

    query_lat = snap["latency"].get("query")
    if query_lat:
        lines.append(
            f"- **Latency (query):** avg {query_lat['avg_ms']:.0f} ms · "
            f"p95 {query_lat['p95_ms']:.0f} ms"
        )

    retrieval = snap["retrieval"]
    if retrieval["count"]:
        lines.append(
            f"- **Retrieval top-score:** avg {retrieval['avg_top_score']:.2f} "
            f"(min {retrieval['min_top_score']:.2f} / "
            f"max {retrieval['max_top_score']:.2f})"
        )

    if snap["categories"]:
        cats = " · ".join(f"{k}: {v}" for k, v in snap["categories"].items())
        lines.append(f"- **Routes:** {cats}")

    lines.append(
        f"- **Category-filtered retrieval:** {snap['total_category_filtered']} "
        f"(rate {snap['category_filter_rate']:.0%}) · "
        f"unfiltered retries {snap['total_unfiltered_retries']} "
        f"(rate {snap['unfiltered_retry_rate']:.0%})"
    )
    if snap["filter_categories"]:
        fcats = " · ".join(
            f"{k}: {v}" for k, v in snap["filter_categories"].items()
        )
        lines.append(f"- **Filter scope:** {fcats}")

    if snap["confidence"]:
        conf = " · ".join(f"{k}: {v}" for k, v in snap["confidence"].items())
        lines.append(f"- **Confidence:** {conf}")

    fb = snap["feedback"]
    if fb["total"]:
        lines.append(
            f"- **Feedback:** 👍 {fb['up']} · 👎 {fb['down']} "
            f"(satisfaction {fb['satisfaction_rate']:.0%})"
        )
    else:
        lines.append("- **Feedback:** _none yet_")

    return "\n".join(lines)


# Directory where generated admin reports (CSV) are written.
REPORTS_DIR = LOG_DIR / "reports"


def export_query_records_csv(path: Path | None = None) -> Path | None:
    """Write the per-query records to a CSV report.

    Args:
        path: Optional destination path. Defaults to a timestamped file under
            ``data/logs/reports/``.

    Returns:
        The written CSV path, or ``None`` if there are no records yet.
    """
    import csv

    records = metrics.query_records()
    if not records:
        return None

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = REPORTS_DIR / f"query_report_{stamp}.csv"

    fieldnames = list(records[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return path


def export_metrics_summary_csv(path: Path | None = None) -> Path | None:
    """Write the current aggregated metrics snapshot to a flat CSV report.

    Args:
        path: Optional destination path. Defaults to a timestamped file under
            ``data/logs/reports/``.

    Returns:
        The written CSV path, or ``None`` if no queries have been recorded.
    """
    import csv

    snap = metrics.snapshot()
    if snap["total_queries"] == 0:
        return None

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = REPORTS_DIR / f"metrics_summary_{stamp}.csv"

    # Flatten the nested snapshot into metric/value rows for a portable report.
    rows: list[tuple[str, Any]] = []

    def _flatten(prefix: str, value: Any) -> None:
        """Recursively flatten nested dicts into dotted metric keys."""
        if isinstance(value, dict):
            for key, sub in value.items():
                _flatten(f"{prefix}.{key}" if prefix else str(key), sub)
        else:
            rows.append((prefix, value))

    _flatten("", snap)

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        writer.writerows(rows)
    return path
