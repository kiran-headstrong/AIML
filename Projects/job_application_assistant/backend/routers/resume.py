"""
Resume router: upload and retrieve the current user's single base resume.

Exposes the ``/api/resume`` endpoints described in the design document's API
Routes table:

* ``POST /api/resume/upload`` — accept a PDF/DOCX upload, persist the file to
  the configured uploads directory, parse it into structured sections, and
  store the file path and parsed data on the ``base_resumes`` row. Only one
  base resume may exist per user, so re-uploading replaces the existing resume
  (Requirements 3.1-3.6). Unsupported file types and unreadable files are
  rejected with descriptive errors (Requirements 3.7, 3.8).
* ``GET /api/resume`` — return the stored resume's details (file name, upload
  date, and the extracted skills summary).

A ``base_resumes`` row is directly user-scoped (``user_id`` foreign key with a
UNIQUE constraint), so the handlers always operate on the current user's own
resume.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from config import settings
from database import get_db
from models import BaseResume, User
from schemas import ParsedResume, ResumeDetailResponse, ResumeUploadResponse
from services.resume_parser import (
    ResumeParseError,
    ResumeParserService,
    UnsupportedResumeFormatError,
)

router = APIRouter(prefix="/api/resume", tags=["resume"])

#: Supported resume upload extensions mapped to their stored ``file_type``.
_SUPPORTED_EXTENSIONS: dict[str, str] = {".pdf": "pdf", ".docx": "docx"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_file_type(filename: str | None) -> str:
    """Determine the stored file type from an uploaded filename's extension.

    Only ``.pdf`` and ``.docx`` are accepted (Requirement 3.7). Any other
    extension (or a missing filename) raises a ``400`` describing the supported
    formats.
    """
    extension = Path(filename or "").suffix.lower()
    file_type = _SUPPORTED_EXTENSIONS.get(extension)
    if file_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '{extension or filename or ''}'. "
                "Supported formats are PDF (.pdf) and Word (.docx)."
            ),
        )
    return file_type


def _build_storage_path(user_id: uuid.UUID, filename: str | None) -> Path:
    """Build a safe, unique on-disk path for a user's uploaded resume.

    Combines the user's id, a uuid4, and the original extension so the stored
    filename cannot collide and cannot traverse outside the uploads directory
    (the original filename is only used for its extension).
    """
    extension = Path(filename or "").suffix.lower()
    unique_name = f"{user_id}_{uuid.uuid4().hex}{extension}"
    return settings.upload_dir / unique_name


def _remove_file_quietly(file_path: str | None) -> None:
    """Best-effort deletion of a file from disk, ignoring any errors."""
    if not file_path:
        return
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError:
        # Deleting the old resume file is best-effort; a failure here must not
        # block replacing the resume row.
        pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload (or replace) the current user's base resume",
)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeUploadResponse:
    """Upload a PDF/DOCX resume, parse it, and persist it for the current user.

    Validates the file type (Requirement 3.7), saves the bytes to the uploads
    directory, parses the resume into structured sections (Requirements 3.1,
    3.2), and persists the file path and parsed data to ``base_resumes``. Only
    one base resume may exist per user, so an existing resume is replaced —
    both its database row and its on-disk file (Requirements 3.3, 3.5, 3.6).

    Raises ``400`` for an unsupported file type (Requirement 3.7) and ``422``
    when the file cannot be read/parsed (Requirement 3.8).
    """
    file_type = _resolve_file_type(file.filename)

    # Ensure the uploads directory exists before writing.
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    storage_path = _build_storage_path(current_user.id, file.filename)
    contents = await file.read()
    try:
        with open(storage_path, "wb") as fh:
            fh.write(contents)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the uploaded resume file.",
        ) from exc

    # Parse the resume into structured sections.
    try:
        parsed: ParsedResume = await ResumeParserService().parse(
            file_path=str(storage_path),
            file_type=file_type,
        )
    except UnsupportedResumeFormatError as exc:
        _remove_file_quietly(str(storage_path))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ResumeParseError as exc:
        _remove_file_quietly(str(storage_path))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Enforce one resume per user: update the existing row in place (respecting
    # the UNIQUE(user_id) constraint) and delete the previous file from disk.
    result = await db.execute(
        select(BaseResume).where(BaseResume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()

    if resume is not None:
        _remove_file_quietly(resume.file_path)
        resume.file_name = file.filename or ""
        resume.file_type = file_type
        resume.file_path = str(storage_path)
        resume.parsed_data = parsed.model_dump()
        resume.raw_text = parsed.raw_text
    else:
        resume = BaseResume(
            user_id=current_user.id,
            file_name=file.filename or "",
            file_type=file_type,
            file_path=str(storage_path),
            parsed_data=parsed.model_dump(),
            raw_text=parsed.raw_text,
        )
        db.add(resume)

    await db.commit()
    await db.refresh(resume)

    return ResumeUploadResponse(
        id=resume.id,
        file_name=resume.file_name,
        file_type=resume.file_type,
        uploaded_at=resume.uploaded_at,
        parsed=parsed,
    )


@router.get(
    "",
    response_model=ResumeDetailResponse,
    summary="Get the current user's stored base resume details",
)
async def get_resume(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDetailResponse:
    """Return the current user's stored resume details.

    Includes the file name, upload date, and the extracted skills summary
    (pulled from the persisted ``parsed_data``). Raises ``404`` when the user
    has not uploaded a resume yet.
    """
    result = await db.execute(
        select(BaseResume).where(BaseResume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resume found. Please upload a resume first.",
        )

    parsed_data = resume.parsed_data or {}
    skills = parsed_data.get("skills") or []
    warning = parsed_data.get("warning")

    return ResumeDetailResponse(
        id=resume.id,
        file_name=resume.file_name,
        file_type=resume.file_type,
        uploaded_at=resume.uploaded_at,
        skills=skills,
        warning=warning,
    )
