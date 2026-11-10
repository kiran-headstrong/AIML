#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Container entrypoint for the Job Application Assistant backend.
#
#  1. Wait for the database to accept connections.
#  2. Apply Alembic migrations (upgrade to head).
#  3. Launch the FastAPI app with uvicorn.
# ---------------------------------------------------------------------------

cd /app/backend

echo "Applying database migrations..."
alembic upgrade head

echo "Starting API server on ${BACKEND_HOST:-0.0.0.0}:${BACKEND_PORT:-8000}..."
exec uvicorn main:app \
    --host "${BACKEND_HOST:-0.0.0.0}" \
    --port "${BACKEND_PORT:-8000}"
