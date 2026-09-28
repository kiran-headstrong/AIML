"""Central configuration for the Internal Training Content Search Assistant.

All settings are overridable via environment variables (and an optional ``.env``
file loaded through ``python-dotenv`` when available). Defaults come from the
design's *Configuration Defaults* table and are tuned for local, CPU-only,
zero-paid-dependency operation.

The module never requires a ``.env`` file to exist; every setting falls back to a
sensible default read from ``os.environ``.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Optional .env loading (best-effort; never required)
# --------------------------------------------------------------------------- #
try:  # pragma: no cover - trivial import guard
    from dotenv import load_dotenv

    # Load a .env from the project root if one happens to exist. Missing file is fine.
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:  # pragma: no cover - dotenv is optional
    pass


# --------------------------------------------------------------------------- #
# Small env-parsing helpers
# --------------------------------------------------------------------------- #
def _env_str(name: str, default: str) -> str:
    """Read a string setting from the environment with a default."""
    value = os.environ.get(name)
    return value if value is not None and value != "" else default


def _env_int(name: str, default: int) -> int:
    """Read an integer setting from the environment with a default."""
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float setting from the environment with a default."""
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean setting from the environment with a default.

    Truthy values: 1, true, yes, on (case-insensitive).
    """
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------- #
# Core configuration defaults (design: Configuration Defaults table)
# --------------------------------------------------------------------------- #

# Local sentence-transformers model used for both chunk and query embeddings (Req 6.1).
EMBEDDING_MODEL: str = _env_str("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Maximum chunk size in characters (Req 2.2, 3.1).
MAX_CHUNK_SIZE: int = _env_int("MAX_CHUNK_SIZE", 800)

# Overlap in characters between adjacent chunks (Req 2.2).
CHUNK_OVERLAP: int = _env_int("CHUNK_OVERLAP", 100)

# Maximum number of results returned per query (Req 7.2).
TOP_K: int = _env_int("TOP_K", 5)

# Minimum normalized similarity for a match; below this yields no-match (Req 7.5).
MIN_SIMILARITY: float = _env_float("MIN_SIMILARITY", 0.30)

# Confidence thresholds on the top normalized similarity score (Req 11.1, 10.3).
MEDIUM_CONFIDENCE_THRESHOLD: float = _env_float("MEDIUM_CONFIDENCE_THRESHOLD", 0.45)
HIGH_CONFIDENCE_THRESHOLD: float = _env_float("HIGH_CONFIDENCE_THRESHOLD", 0.65)

# OCR is optional and disabled by default; requires a system Tesseract binary (Req 4.4).
OCR_ENABLED: bool = _env_bool("OCR_ENABLED", False)

# Answer drafting strategy: "extractive" (default), "ollama", or "openai" (Req 12.3).
ANSWER_MODEL: str = _env_str("ANSWER_MODEL", "extractive")

# Maximum number of lines in a drafted answer (Req 9.1).
ANSWER_MAX_LINES: int = _env_int("ANSWER_MAX_LINES", 6)


# --------------------------------------------------------------------------- #
# Resolved data paths (rooted under the project's data/ folder)
# --------------------------------------------------------------------------- #

# Project root is the directory containing this config module.
PROJECT_ROOT: Path = Path(__file__).resolve().parent

# Base data directory; overridable via DATA_DIR.
DATA_DIR: Path = Path(_env_str("DATA_DIR", str(PROJECT_ROOT / "data")))

# Source corpus folder (the design uses data/documents/corpus/).
CORPUS_DIR: Path = Path(_env_str("CORPUS_DIR", str(DATA_DIR / "documents" / "corpus")))

# Persisted Chroma vector index directory.
CHROMA_STORE_DIR: Path = Path(_env_str("CHROMA_STORE_DIR", str(DATA_DIR / "chroma_store")))

# SQLite metadata store file.
METADATA_DB_PATH: Path = Path(_env_str("METADATA_DB_PATH", str(DATA_DIR / "metadata.db")))

# Human-readable JSON metadata export.
METADATA_JSON_PATH: Path = Path(_env_str("METADATA_JSON_PATH", str(DATA_DIR / "metadata.json")))

# Logs directory and ingestion log file.
LOGS_DIR: Path = Path(_env_str("LOGS_DIR", str(DATA_DIR / "logs")))
INGESTION_LOG_PATH: Path = Path(_env_str("INGESTION_LOG_PATH", str(LOGS_DIR / "ingestion.log")))

# Cached embedding-model directory (download-once, reuse-offline).
MODEL_CACHE_DIR: Path = Path(_env_str("MODEL_CACHE_DIR", str(DATA_DIR / "model")))

# Evaluation harness inputs/outputs.
SAMPLE_QUERIES_PATH: Path = Path(_env_str("SAMPLE_QUERIES_PATH", str(DATA_DIR / "sample_queries.csv")))
EVALUATION_OUTPUT_PATH: Path = Path(
    _env_str("EVALUATION_OUTPUT_PATH", str(DATA_DIR / "evaluation_output.csv"))
)

# Files to exclude from ingestion (meta-documents that match queries but don't
# contain training content). Comma-separated base filenames.
EXCLUDE_FILES: list[str] = [
    s.strip()
    for s in _env_str("EXCLUDE_FILES", "internal_search_use_cases.md").split(",")
    if s.strip()
]


def ensure_data_dirs() -> None:
    """Create the data directories that the pipeline writes into.

    Safe to call repeatedly; missing directories are created and existing ones
    are left untouched. Files (db/json/log) are not created here, only their
    parent directories.
    """
    for directory in (DATA_DIR, CORPUS_DIR, CHROMA_STORE_DIR, LOGS_DIR, MODEL_CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    METADATA_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
