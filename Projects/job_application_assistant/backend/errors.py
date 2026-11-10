"""
Centralised error handling and consistent response formatting.

This module defines exception handlers that normalise every error raised by the
API into a single, predictable JSON envelope::

    {
        "error": {
            "type": "<machine_readable_code>",
            "message": "<human readable message>",
            "details": <optional structured details, e.g. validation errors>
        }
    }

The handlers are registered onto the FastAPI app via :func:`register_exception_handlers`
in ``main.py`` so that every router benefits from the same formatting without
having to repeat boilerplate. Routers may still raise :class:`fastapi.HTTPException`
with a ``status_code`` and ``detail``; the handler here wraps that ``detail`` in
the common envelope while preserving the status code.

Service-layer exceptions (``UnsupportedURLError``, ``ScrapeError``,
``UnsupportedResumeFormatError``, ``ResumeParseError``, ``LLMConfigurationError``)
are mapped to sensible HTTP status codes as a safety net, so that even if a
router forgets to translate them they do not surface as opaque 500s.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.jd_scraper import ScrapeError, UnsupportedURLError
from services.llm import LLMConfigurationError
from services.resume_parser import ResumeParseError, UnsupportedResumeFormatError

logger = logging.getLogger("job_application_assistant")


def _envelope(
    *,
    status_code: int,
    error_type: str,
    message: str,
    details: object | None = None,
) -> JSONResponse:
    """Build a JSONResponse using the common error envelope."""
    body: dict[str, object] = {"type": error_type, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body})


def _error_type_for_status(status_code: int) -> str:
    """Return a machine-readable error code for a given HTTP status."""
    mapping = {
        status.HTTP_400_BAD_REQUEST: "bad_request",
        status.HTTP_401_UNAUTHORIZED: "unauthorized",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
        status.HTTP_502_BAD_GATEWAY: "upstream_error",
        status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
    }
    if status_code in mapping:
        return mapping[status_code]
    if 400 <= status_code < 500:
        return "client_error"
    return "server_error"


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Wrap HTTPException/StarletteHTTPException detail in the common envelope."""
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    details = None if isinstance(exc.detail, str) else exc.detail
    response = _envelope(
        status_code=exc.status_code,
        error_type=_error_type_for_status(exc.status_code),
        message=message,
        details=details,
    )
    # Preserve auth-related headers (e.g. WWW-Authenticate) if present.
    if exc.headers:
        for key, value in exc.headers.items():
            response.headers[key] = value
    return response


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format request-validation failures consistently."""
    return _envelope(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_type="validation_error",
        message="Request validation failed.",
        details=exc.errors(),
    )


async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Map uncaught domain ValueErrors to 400 responses.

    Covers ``UnsupportedURLError`` and ``UnsupportedResumeFormatError`` as a
    safety net; these subclass :class:`ValueError`.
    """
    return _envelope(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_type="bad_request",
        message=str(exc) or "Invalid request.",
    )


async def _scrape_error_handler(request: Request, exc: ScrapeError) -> JSONResponse:
    """Map scraping/fetch failures to 502 (upstream error)."""
    return _envelope(
        status_code=status.HTTP_502_BAD_GATEWAY,
        error_type="upstream_error",
        message=str(exc) or "Failed to fetch the requested resource.",
    )


async def _resume_parse_error_handler(
    request: Request, exc: ResumeParseError
) -> JSONResponse:
    """Map resume parsing failures to 422 (unprocessable entity)."""
    return _envelope(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_type="parse_error",
        message=str(exc) or "The uploaded resume could not be parsed.",
    )


async def _llm_configuration_error_handler(
    request: Request, exc: LLMConfigurationError
) -> JSONResponse:
    """Map LLM misconfiguration to 503 (service unavailable)."""
    logger.error("LLM configuration error: %s", exc)
    return _envelope(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        error_type="service_unavailable",
        message=(
            "The AI service is not configured correctly. Please contact the "
            "administrator."
        ),
    )


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Safety net for unexpected errors: log and return an opaque 500."""
    logger.exception("Unhandled exception while processing %s %s",
                     request.method, request.url.path)
    return _envelope(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_type="internal_error",
        message="An unexpected error occurred. Please try again later.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application.

    Order of registration does not matter for FastAPI; it matches the most
    specific exception type. More specific service errors are registered
    before the broad ``ValueError`` and ``Exception`` handlers for clarity.
    """
    # Framework / validation errors.
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)

    # Service-layer errors (safety net; routers normally translate these).
    app.add_exception_handler(ScrapeError, _scrape_error_handler)
    app.add_exception_handler(ResumeParseError, _resume_parse_error_handler)
    app.add_exception_handler(LLMConfigurationError, _llm_configuration_error_handler)
    # UnsupportedURLError / UnsupportedResumeFormatError subclass ValueError.
    app.add_exception_handler(ValueError, _value_error_handler)

    # Catch-all safety net.
    app.add_exception_handler(Exception, _unhandled_exception_handler)
