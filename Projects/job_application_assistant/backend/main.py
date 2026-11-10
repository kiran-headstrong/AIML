"""
Job Application Assistant - FastAPI Backend

Application entry point. Wires together:

* CORS middleware for the frontend SPA.
* All feature routers (auth, jd, resume, match, interview, cover_letter,
  dashboard, compare).
* Centralised exception handlers for consistent error-response formatting
  across every endpoint (see ``errors.py``).
* Health/liveness endpoints.

Run locally:
    python backend/main.py
or:
    uvicorn backend.main:app --reload
"""
import sys
from pathlib import Path

# Ensure the backend package directory is importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from errors import register_exception_handlers
from routers.auth import router as auth_router
from routers.compare import router as compare_router
from routers.cover_letter import router as cover_letter_router
from routers.dashboard import router as dashboard_router
from routers.interview import router as interview_router
from routers.jd import router as jd_router
from routers.match import router as match_router
from routers.resume import router as resume_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: prepare resources on startup."""
    # Ensure file-storage directories exist.
    settings.ensure_directories()
    yield
    # Place teardown logic here if needed.


app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend API for the Job Application Assistant: JD scraping, resume "
        "parsing & matching, tailored resume and cover letter generation, "
        "interview preparation, and application tracking."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS middleware for the frontend SPA.
#
# Note: when ``cors_origins`` is the wildcard ``["*"]`` the CORS spec forbids
# combining it with credentialed requests. We therefore only enable
# ``allow_credentials`` when explicit origins are configured, and fall back to
# the wildcard (without credentials) otherwise. The frontend uses a JWT Bearer
# token in the Authorization header rather than cookies, so this is safe.
_wildcard_origins = settings.cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=not _wildcard_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralised exception handlers for consistent error responses.
register_exception_handlers(app)

# Feature routers. Each router declares its own ``/api/...`` prefix and tags.
app.include_router(auth_router)
app.include_router(jd_router)
app.include_router(resume_router)
app.include_router(match_router)
app.include_router(interview_router)
app.include_router(cover_letter_router)
app.include_router(dashboard_router)
app.include_router(compare_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok", "service": settings.app_name}


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    """Root endpoint with basic service info."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    print(f"🚀 Starting {settings.app_name} on "
          f"http://{settings.backend_host}:{settings.backend_port}")
    print(f"📖 API Docs: http://localhost:{settings.backend_port}/docs")
    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
    )
