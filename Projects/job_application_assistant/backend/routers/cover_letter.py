"""
Cover letter router: generate, persist, and download a tailored cover letter
for a scraped job description.

Exposes the ``/api/cover-letter`` endpoints described in the design document's
API Routes table that belong to task 10.2:

* ``POST /api/cover-letter/{jd_id}``          — generate a cover letter tailored
  to the user's base resume and the scraped JD via the Cover Letter Service,
  export it to a downloadable ``.docx``, (re)persist it to ``cover_letters``,
  associate it with the user's job entry, and return the generated content so
  the user can review/edit before downloading (Requirements 10.1, 10.2, 10.3,
  10.4, 10.6).
* ``GET  /api/cover-letter/{jd_id}/download``  — download the generated cover
  letter ``.docx`` (Requirement 10.5).

Scoping: scraped JDs are shared rows. A JD (and its cover letter) is accessible
to a user only when the user has a ``job_entry`` referencing it; the helpers
enforce this and return ``404`` otherwise, mirroring the match and interview
routers.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``. Note the
name clash between ``models.ScrapedJD`` (ORM) and ``schemas.ScrapedJD``
(Pydantic), and likewise between ``models.CoverLetter`` (ORM) and
``schemas.CoverLetter`` (Pydantic): the ORM models are imported aliased as
``ScrapedJDModel`` and ``CoverLetterModel``.
"""
from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import (
    BaseResume,
    CoverLetter as CoverLetterModel,
    JobEntry,
    ScrapedJD as ScrapedJDModel,
    User,
)
from schemas import (
    CoverLetterRequest,
    CoverLetterResponse,
    ParsedResume,
    ScrapedJD as ScrapedJDSchema,
)
from services.cover_letter import CoverLetterService

router = APIRouter(prefix="/api/cover-letter", tags=["cover-letter"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_job_entry(
    jd_id: UUID,
    user: User,
    db: AsyncSession,
) -> JobEntry:
    """Return the current user's job entry for ``jd_id``, or raise ``404``.

    Cover letters hang off a ``job_entry`` (not the shared JD), so every cover
    letter operation is scoped through the user's own job entry for the JD.
    """
    result = await db.execute(
        select(JobEntry).where(
            JobEntry.jd_id == jd_id, JobEntry.user_id == user.id
        )
    )
    job_entry = result.scalars().first()
    if job_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job description not found",
        )
    return job_entry


async def _get_scraped_jd(jd_id: UUID, db: AsyncSession) -> ScrapedJDModel:
    """Fetch the persisted scraped JD row, or raise ``404``."""
    result = await db.execute(
        select(ScrapedJDModel).where(ScrapedJDModel.id == jd_id)
    )
    scraped_jd = result.scalars().first()
    if scraped_jd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job description not found",
        )
    return scraped_jd


async def _get_user_resume(user: User, db: AsyncSession) -> BaseResume:
    """Fetch the current user's base resume, or raise ``400``.

    A cover letter requires both a resume and a JD (Requirement 10.1); a missing
    resume is a client-correctable precondition rather than a not-found.
    """
    result = await db.execute(
        select(BaseResume).where(BaseResume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No resume found. Please upload a resume before generating a "
                "cover letter."
            ),
        )
    return resume


def _scraped_jd_schema(model: ScrapedJDModel) -> ScrapedJDSchema:
    """Build a :class:`schemas.ScrapedJD` from the ORM row for the service."""
    return ScrapedJDSchema(
        job_title=model.job_title,
        company_name=model.company_name,
        location=model.location,
        experience_required=model.experience_required,
        description_body=model.description_body,
        required_skills=list(model.required_skills or []),
        preferred_skills=list(model.preferred_skills or []),
        raw_html="",
    )


def _parsed_resume(resume: BaseResume) -> ParsedResume:
    """Reconstruct a :class:`ParsedResume` from the persisted ``parsed_data``."""
    data = resume.parsed_data or {}
    try:
        return ParsedResume.model_validate(data)
    except Exception:
        # Defensive: if persisted data is malformed, fall back to raw text only
        # so generation can still run from whatever content is available.
        return ParsedResume(raw_text=resume.raw_text or "")


def _remove_file_quietly(file_path: str | None) -> None:
    """Best-effort deletion of a file from disk, ignoring any errors.

    Used when overwriting a previously-generated cover letter so stale files do
    not accumulate; a failure here must not block regeneration.
    """
    if not file_path:
        return
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError:
        pass


def _safe_filename_part(value: str | None) -> str:
    """Sanitise a string into a filesystem-safe filename fragment.

    Collapses non-alphanumeric characters into underscores and trims length so
    the generated download name is portable across platforms.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (value or "").strip()).strip("_")
    return (cleaned or "cover_letter")[:60]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{jd_id}",
    response_model=CoverLetterResponse,
    summary="Generate a tailored cover letter for the JD",
)
async def generate_cover_letter(
    jd_id: UUID,
    payload: CoverLetterRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CoverLetterResponse:
    """Generate (or regenerate) a tailored cover letter for the JD.

    Generates a structured cover letter from the user's base resume and the
    scraped JD, tailored to the resolved experience level (Requirements 10.1,
    10.2, 10.3), exports it to a downloadable ``.docx``, (re)persists it to
    ``cover_letters``, and associates the document with the user's job entry
    (Requirement 10.6). The generated content is returned so the user can
    review and edit it before downloading (Requirement 10.4).

    The experience level is resolved from the request body when provided,
    otherwise it falls back to the user's stored ``experience_level``.

    When a cover letter already exists for the job entry it is overwritten: the
    row is updated in place and the previous file is removed.

    Raises ``404`` when the JD is not accessible to the user, and ``400`` when
    the user has not uploaded a resume.
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)
    scraped_jd = await _get_scraped_jd(jd_id, db)
    resume = await _get_user_resume(current_user, db)

    # Resolve the experience level used to tailor the letter's tone and depth.
    override = payload.experience_level if payload is not None else None
    level = override or current_user.experience_level or ""

    service = CoverLetterService()
    scraped_jd_schema = _scraped_jd_schema(scraped_jd)

    content = await service.generate(
        resume=_parsed_resume(resume),
        jd=scraped_jd_schema,
        experience_level=level,
    )

    try:
        file_path = service.export_docx(
            content,
            scraped_jd.job_title,
            scraped_jd.company_name,
        )
    except Exception as exc:  # noqa: BLE001 - surface export failures as 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate the cover letter document.",
        ) from exc

    # Upsert the cover_letters row (UNIQUE per job entry).
    existing = await db.execute(
        select(CoverLetterModel).where(
            CoverLetterModel.job_entry_id == job_entry.id
        )
    )
    cover_letter = existing.scalars().first()
    if cover_letter is not None:
        _remove_file_quietly(cover_letter.file_path)
        cover_letter.content = content
        cover_letter.file_path = file_path
    else:
        cover_letter = CoverLetterModel(
            job_entry_id=job_entry.id,
            content=content,
            file_path=file_path,
        )
        db.add(cover_letter)
        await db.flush()  # assign PK before linking from the job entry

    # Associate the document with the job entry (Requirement 10.6).
    job_entry.cover_letter_id = cover_letter.id

    await db.commit()
    await db.refresh(cover_letter)

    return CoverLetterResponse(
        id=cover_letter.id,
        job_entry_id=cover_letter.job_entry_id,
        content=cover_letter.content,
        file_path=cover_letter.file_path,
        generated_at=cover_letter.generated_at,
    )


@router.get(
    "/{jd_id}/download",
    response_class=FileResponse,
    summary="Download the generated cover letter .docx",
)
async def download_cover_letter(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Return the generated cover letter ``.docx`` as a file download.

    Raises ``404`` when the JD is not accessible to the user, when no cover
    letter has been generated, or when the generated file is missing on disk
    (Requirement 10.5).
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)

    result = await db.execute(
        select(CoverLetterModel).where(
            CoverLetterModel.job_entry_id == job_entry.id
        )
    )
    cover_letter = result.scalars().first()
    if cover_letter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cover letter found. Generate it first.",
        )

    path = Path(cover_letter.file_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The cover letter file is no longer available.",
        )

    scraped_jd = await _get_scraped_jd(jd_id, db)
    safe_company = _safe_filename_part(scraped_jd.company_name)
    safe_title = _safe_filename_part(scraped_jd.job_title)
    download_name = f"cover_letter_{safe_company}_{safe_title}.docx"

    return FileResponse(
        path=str(path),
        filename=download_name,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )
