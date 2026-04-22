"""
api.py — FastAPI REST API for AeroManual AI.

Endpoints:
    POST /upload        — Upload and index a document (with validation)
    POST /query         — Ask a question (synchronous, returns full answer)
    POST /query/stream  — Ask a question (streaming, returns SSE tokens)
    GET  /health        — Health check for K8s liveness/readiness probes
    GET  /metrics       — Prometheus metrics (auto-instrumented)

Security & Performance:
    - CORS middleware for cross-origin requests
    - Rate limiting (20 requests/minute per IP)
    - File validation (size, extension, filename sanitization)
    - Async thread pool for CPU-bound operations
    - Prometheus instrumentation for monitoring
"""

import asyncio
import hashlib
import logging
import shutil
import re
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import UPLOAD_DIR, MAX_FILE_SIZE_MB, ALLOWED_EXTENSIONS
from app.document_loader import load_and_split
from app.vector_store import add_documents, is_duplicate, search
from app.rag_chain import ask, ask_stream

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------
app = FastAPI(title="AeroManual AI", version="2.0.0")

# ---------------------------------------------------------------------------
# CORS: allow cross-origin requests from any origin (restrict in production)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Rate limiting: 20 requests/minute per client IP
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Return 429 when a client exceeds the rate limit."""
    logger.warning("Rate limit exceeded for IP=%s", get_remote_address(request))
    raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")


# ---------------------------------------------------------------------------
# Prometheus: auto-instrument all endpoints and expose /metrics
# ---------------------------------------------------------------------------
Instrumentator().instrument(app).expose(app)


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    """Request body for /query and /query/stream endpoints."""
    question: str
    chat_history: str = ""


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize an uploaded filename to prevent path traversal attacks.

    Strips directory components and replaces unsafe characters with
    underscores. Only the base filename is kept.

    Args:
        filename: Original filename from the upload.

    Returns:
        Safe filename string.
    """
    name = filename.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\-]", "_", name)
    return name


def _validate_file(file: UploadFile, content: bytes) -> None:
    """
    Validate an uploaded file for size and extension.

    Args:
        file: FastAPI UploadFile object.
        content: Raw file bytes.

    Raises:
        HTTPException: If the file exceeds size limit or has a disallowed extension.
    """
    # Check file size
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        logger.warning("File too large: %s (%.1f MB)", file.filename, size_mb)
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f} MB). Max allowed: {MAX_FILE_SIZE_MB} MB.",
        )

    # Check file extension
    from pathlib import Path
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("Disallowed file extension: %s", ext)
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Supported: {', '.join(ALLOWED_EXTENSIONS)}",
        )


# ---------------------------------------------------------------------------
# POST /upload — Upload and index a document
# ---------------------------------------------------------------------------
@app.post("/upload")
@limiter.limit("20/minute")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """
    Upload a document, validate it, and index its contents into FAISS.

    Steps:
        1. Read file content and validate (size, extension)
        2. Sanitize filename to prevent path traversal
        3. Check for duplicate uploads
        4. Save file to uploads/ directory
        5. Load, split, and embed document chunks (in thread pool)
        6. Return filename and chunk count

    Returns:
        JSON with filename and chunks_indexed count.
    """
    logger.info("Upload request: filename=%s", file.filename)

    # Read and validate file content
    content = await file.read()
    _validate_file(file, content)

    # Sanitize filename and prepare destination path
    safe_name = _sanitize_filename(file.filename)
    dest = UPLOAD_DIR / safe_name

    # Check for duplicate uploads
    if is_duplicate(str(dest)):
        logger.info("Duplicate upload skipped: %s", safe_name)
        return {"filename": safe_name, "chunks_indexed": 0, "status": "duplicate"}

    # Save file to disk
    with open(dest, "wb") as f:
        f.write(content)
    logger.info("File saved: %s (%.2f MB)", dest, len(content) / (1024 * 1024))

    # Load, split, and index in a thread pool to avoid blocking the event loop
    try:
        chunks = await asyncio.to_thread(load_and_split, str(dest))
        count = await asyncio.to_thread(add_documents, chunks, str(dest))
    except Exception as e:
        logger.error("Failed to process file %s: %s", safe_name, e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to process file: {e}")

    logger.info("Upload complete: %s → %d chunks indexed", safe_name, count)
    return {"filename": safe_name, "chunks_indexed": count}


# ---------------------------------------------------------------------------
# POST /query — Synchronous Q&A (returns full answer)
# ---------------------------------------------------------------------------
@app.post("/query")
@limiter.limit("20/minute")
async def query_documents(request: Request, req: QueryRequest):
    """
    Answer a question using the RAG pipeline.

    Runs the synchronous ask() function in a thread pool so it doesn't
    block the async event loop, allowing concurrent request handling.

    Returns:
        JSON with answer string and sources list.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    logger.info("Query request: '%s'", req.question[:100])
    result = await asyncio.to_thread(ask, req.question, req.chat_history)
    return result


# ---------------------------------------------------------------------------
# POST /query/stream — Streaming Q&A (returns SSE tokens)
# ---------------------------------------------------------------------------
@app.post("/query/stream")
@limiter.limit("20/minute")
async def query_stream(request: Request, req: QueryRequest):
    """
    Stream an answer token-by-token using Server-Sent Events (SSE).

    The LLM response is streamed as it's generated, so the first token
    appears in ~200ms instead of waiting 2-5s for the full response.

    Returns:
        StreamingResponse with text/event-stream media type.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    logger.info("Stream request: '%s'", req.question[:100])

    async def generate():
        """Async generator that yields SSE-formatted token chunks."""
        async for token in ask_stream(req.question, req.chat_history):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /health — Health check for Kubernetes probes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """
    Health check endpoint for Kubernetes liveness and readiness probes.

    Returns:
        JSON with status "ok".
    """
    return {"status": "ok"}
