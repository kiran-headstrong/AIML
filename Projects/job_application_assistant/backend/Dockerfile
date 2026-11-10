# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Backend image: FastAPI + SQLAlchemy (asyncpg) + WeasyPrint
#
# WeasyPrint needs native GTK/Pango/Cairo system libraries. These are easy to
# install on a Debian base, which is why running the full app in a container is
# the most reliable way to get PDF export working.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Native libraries required by WeasyPrint (Pango/Cairo/GDK-Pixbuf) plus libpq
# tooling for building wheels if needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

# Copy the application source.
COPY backend ./backend

# Runtime storage directories (also created at startup, but ensure they exist).
RUN mkdir -p /app/uploads /app/generated

EXPOSE 8000

# The entrypoint runs migrations then starts the API.
COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
