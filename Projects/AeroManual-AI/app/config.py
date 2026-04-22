"""
config.py — Centralized configuration for AeroManual AI.

Loads environment variables from .env file (local dev) or from
container-injected env vars (Docker/K8s). Defines all tunable
parameters for the RAG pipeline, file handling, and logging.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment: load .env for local development; containers inject env vars
# ---------------------------------------------------------------------------
env_path = Path(__file__).resolve().parents[3] / ".env"
if env_path.exists():
    load_dotenv(env_path)

# ---------------------------------------------------------------------------
# Logging: structured JSON-style logging across all modules
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ---------------------------------------------------------------------------
# Paths: base directories for uploads and vector store persistence
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
VECTORSTORE_DIR = BASE_DIR / "vectorstore"

UPLOAD_DIR.mkdir(exist_ok=True)
VECTORSTORE_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# LLM: Groq API configuration
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"

# ---------------------------------------------------------------------------
# Embeddings: HuggingFace sentence-transformer model
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Chunking: text splitter parameters (increased for better context)
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1000       # characters per chunk (was 500)
CHUNK_OVERLAP = 200     # overlap between chunks (was 100)

# ---------------------------------------------------------------------------
# Retrieval: vector search parameters
# ---------------------------------------------------------------------------
TOP_K = 8                       # number of chunks to retrieve
RELEVANCE_THRESHOLD = 1.5       # FAISS L2 distance cutoff (lower = stricter)

# ---------------------------------------------------------------------------
# FAISS: backend selection (cpu or gpu)
# Set FAISS_BACKEND=gpu on servers with CUDA GPUs for ~10-100x faster search.
# Defaults to 'cpu' for laptop/local development.
# ---------------------------------------------------------------------------
FAISS_BACKEND = os.getenv("FAISS_BACKEND", "cpu").lower()

# ---------------------------------------------------------------------------
# Upload: file validation constraints
# ---------------------------------------------------------------------------
MAX_FILE_SIZE_MB = 50
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".csv"}
