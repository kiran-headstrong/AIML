"""
Match router: compute and retrieve resume-to-JD match results, edit
suggestions, and skill-gap analysis.

Exposes the ``/api/match`` endpoints described in the design document's API
Routes table that belong to tasks 6.3:

* ``POST /api/match/{jd_id}``             — compute (or recompute) the match
  between the current user's base resume and the scraped JD, persist the
  breakdown to ``match_results``, and update ``job_entries.match_score``
  (Requirements 4.1-4.4).
* ``GET  /api/match/{jd_id}``             — fetch the persisted match result.
* ``GET  /api/match/{jd_id}/suggestions`` — resume edit suggestions generated
  by the Resume Editor Service, categorised and prioritised by impact
  (Requirements 5.1-5.4).
* ``POST /api/match/{jd_id}/generate-resume`` — generate a tailored ``.docx``
  by applying the edit suggestions to a copy of the base resume, persist it to
  ``tailored_resumes``, and associate it with the job entry
  (Requirements 5.1, 6.1, 6.4, 6.7).
* ``GET  /api/match/{jd_id}/download-resume`` — download the generated tailored
  resume ``.docx`` (Requirement 6.4).
* ``GET  /api/match/{jd_id}/skill-gaps``  — skill-gap analysis alongside the
  match-score breakdown (Requirements 11.1-11.4).

Scoping: scraped JDs are shared rows. A JD (and its match result) is accessible
to a user only when the user has a ``job_entry`` referencing it; the helpers
enforce this and return ``404`` otherwise, mirroring the JD router.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``. Note the
name clash between ``models.ScrapedJD`` (ORM) and ``schemas.ScrapedJD``
(Pydantic): the ORM model is imported aliased as ``ScrapedJDModel``.
"""
from __future__ import annotations

import re
from decimal import Decimal
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
    JobEntry,
    MatchResult,
    ScrapedJD as ScrapedJDModel,
    TailoredResume,
    TechStackItem,
    User,
)
from schemas import (
    EditSuggestion,
    MatchBreakdown,
    MatchRequest,
    MatchResponse,
    ParsedResume,
    ScrapedJD as ScrapedJDSchema,
    SkillGapResult,
    SuggestionsResponse,
    TailoredResumeResponse,
    TechStackItem as TechStackItemSchema,
    TechStackResult,
)
from services.resume_editor import ResumeEditorService
from services.resume_matcher import ResumeMatcherService
from services.tech_stack_extractor import TechStackExtractorService

router = APIRouter(prefix="/api/match", tags=["match"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_job_entry(
    jd_id: UUID,
    user: User,
    db: AsyncSession,
) -> JobEntry:
    """Return the current user's job entry for ``jd_id``, or raise ``404``.

    Match results hang off a ``job_entry`` (not the shared JD), so every match
    operation is scoped through the user's own job entry for the JD.
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

    A match requires both a resume and a JD (Requirement 4.1); a missing resume
    is a client-correctable precondition rather than a not-found.
    """
    result = await db.execute(
        select(BaseResume).where(BaseResume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No resume found. Please upload a resume before matching.",
        )
    return resume


def _scraped_jd_schema(model: ScrapedJDModel) -> ScrapedJDSchema:
    """Build a :class:`schemas.ScrapedJD` from the ORM row for the matcher."""
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
        # so matching can still run (yielding a low-but-valid score).
        return ParsedResume(raw_text=resume.raw_text or "")


def _persist_breakdown(
    match_result: MatchResult | None,
    job_entry: JobEntry,
    breakdown: MatchBreakdown,
    db: AsyncSession,
) -> MatchResult:
    """Create or update the ``match_results`` row and sync ``match_score``.

    Returns the (new or updated) :class:`MatchResult` row, added to the session
    but not yet committed.
    """
    if match_result is None:
        match_result = MatchResult(
            job_entry_id=job_entry.id,
            overall_score=Decimal(str(breakdown.overall_score)),
            skills_score=Decimal(str(breakdown.skills_score)),
            experience_score=Decimal(str(breakdown.experience_score)),
            education_score=Decimal(str(breakdown.education_score)),
            matched_skills=breakdown.matched_skills,
            missing_skills=breakdown.missing_skills,
            matched_experience_kw=breakdown.matched_experience_keywords,
            missing_experience_kw=breakdown.missing_experience_keywords,
            category=breakdown.category,
        )
        db.add(match_result)
    else:
        match_result.overall_score = Decimal(str(breakdown.overall_score))
        match_result.skills_score = Decimal(str(breakdown.skills_score))
        match_result.experience_score = Decimal(str(breakdown.experience_score))
        match_result.education_score = Decimal(str(breakdown.education_score))
        match_result.matched_skills = breakdown.matched_skills
        match_result.missing_skills = breakdown.missing_skills
        match_result.matched_experience_kw = breakdown.matched_experience_keywords
        match_result.missing_experience_kw = breakdown.missing_experience_keywords
        match_result.category = breakdown.category

    # Keep the denormalised score on the job entry in sync (Requirement 9.1).
    job_entry.match_score = Decimal(str(breakdown.overall_score))
    return match_result


def _breakdown_from_result(match_result: MatchResult) -> MatchBreakdown:
    """Reconstruct a :class:`MatchBreakdown` from a persisted ``MatchResult``.

    Used to feed the Resume Editor Service, which reasons over the breakdown
    (missing skills, sub-scores) when producing edit suggestions.
    """
    return MatchBreakdown(
        overall_score=float(match_result.overall_score),
        skills_score=float(match_result.skills_score),
        experience_score=float(match_result.experience_score),
        education_score=float(match_result.education_score),
        matched_skills=list(match_result.matched_skills or []),
        missing_skills=list(match_result.missing_skills or []),
        matched_experience_keywords=list(match_result.matched_experience_kw or []),
        missing_experience_keywords=list(match_result.missing_experience_kw or []),
        category=match_result.category,
    )


def _remove_file_quietly(file_path: str | None) -> None:
    """Best-effort deletion of a file from disk, ignoring any errors.

    Used when overwriting a previously-generated tailored resume so stale files
    do not accumulate; a failure here must not block regeneration.
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
    return (cleaned or "resume")[:60]


async def _get_match_result(job_entry: JobEntry, db: AsyncSession) -> MatchResult:
    """Fetch the job entry's persisted match result, or raise ``400``.

    Suggestions and tailored-resume generation both build on a computed match
    (Requirement 5.1); a missing match is a client-correctable precondition.
    """
    result = await db.execute(
        select(MatchResult).where(MatchResult.job_entry_id == job_entry.id)
    )
    match_result = result.scalars().first()
    if match_result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No match result found. Compute the match first.",
        )
    return match_result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{jd_id}",
    response_model=MatchResponse,
    summary="Compute the resume-to-JD match score",
)
async def compute_match(
    jd_id: UUID,
    payload: MatchRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatchResponse:
    """Compute (or recompute) the match between the user's resume and the JD.

    Computes a weighted match breakdown (Requirements 4.1-4.4), persists it to
    ``match_results`` (one row per job entry), and updates the job entry's
    denormalised ``match_score``.

    When a match result already exists it is returned as-is unless
    ``recompute`` is set in the request body, in which case it is recomputed
    and overwritten.

    Raises ``404`` when the JD is not accessible to the user and ``400`` when
    the user has not uploaded a resume.
    """
    recompute = bool(payload.recompute) if payload is not None else False

    job_entry = await _get_user_job_entry(jd_id, current_user, db)

    existing = await db.execute(
        select(MatchResult).where(MatchResult.job_entry_id == job_entry.id)
    )
    match_result = existing.scalars().first()

    if match_result is not None and not recompute:
        return MatchResponse.model_validate(match_result)

    scraped_jd = await _get_scraped_jd(jd_id, db)
    resume = await _get_user_resume(current_user, db)

    breakdown = ResumeMatcherService().compute_match(
        parsed_resume=_parsed_resume(resume),
        scraped_jd=_scraped_jd_schema(scraped_jd),
    )

    match_result = _persist_breakdown(match_result, job_entry, breakdown, db)
    await db.commit()
    await db.refresh(match_result)

    return MatchResponse.model_validate(match_result)


@router.get(
    "/{jd_id}",
    response_model=MatchResponse,
    summary="Get the persisted match result",
)
async def get_match(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatchResponse:
    """Return the persisted match result for the JD.

    Raises ``404`` when the JD is not accessible to the user or no match has
    been computed yet.
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)

    result = await db.execute(
        select(MatchResult).where(MatchResult.job_entry_id == job_entry.id)
    )
    match_result = result.scalars().first()
    if match_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No match result found. Compute the match first.",
        )
    return MatchResponse.model_validate(match_result)


@router.get(
    "/{jd_id}/suggestions",
    response_model=SuggestionsResponse,
    summary="Get prioritised resume edit suggestions",
)
async def get_suggestions(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuggestionsResponse:
    """Return categorised, impact-prioritised resume edit suggestions.

    Builds on the persisted match result and the user's base resume to generate
    actionable suggestions via the Resume Editor Service (Requirements 5.1-5.4),
    ordered high-impact first.

    Raises ``404`` when the JD is not accessible to the user, and ``400`` when
    no match has been computed or no resume has been uploaded.
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)
    match_result = await _get_match_result(job_entry, db)
    scraped_jd = await _get_scraped_jd(jd_id, db)
    resume = await _get_user_resume(current_user, db)

    suggestions = await ResumeEditorService().generate_suggestions(
        match=_breakdown_from_result(match_result),
        resume=_parsed_resume(resume),
        jd=_scraped_jd_schema(scraped_jd),
    )
    return SuggestionsResponse(suggestions=suggestions)


@router.post(
    "/{jd_id}/generate-resume",
    response_model=TailoredResumeResponse,
    summary="Generate a tailored resume .docx for the JD",
)
async def generate_resume(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TailoredResumeResponse:
    """Generate (or regenerate) a tailored resume for the JD.

    Generates edit suggestions, applies them to a copy of the base resume to
    produce a new ``.docx`` (preserving the base resume on disk), persists the
    file path and applied suggestions to ``tailored_resumes``, and associates
    the document with the user's job entry (Requirements 5.1, 6.1, 6.4, 6.7).

    When a tailored resume already exists for the job entry it is overwritten:
    the row is updated in place, the previous file is removed, and the job
    entry's association is kept in sync.

    Raises ``404`` when the JD is not accessible to the user, and ``400`` when
    no match has been computed or no resume has been uploaded.
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)
    match_result = await _get_match_result(job_entry, db)
    scraped_jd = await _get_scraped_jd(jd_id, db)
    resume = await _get_user_resume(current_user, db)

    editor = ResumeEditorService()
    parsed_resume = _parsed_resume(resume)

    suggestions = await editor.generate_suggestions(
        match=_breakdown_from_result(match_result),
        resume=parsed_resume,
        jd=_scraped_jd_schema(scraped_jd),
    )

    try:
        file_path = editor.generate_tailored_docx(
            base_resume_path=resume.file_path,
            suggestions=suggestions,
            parsed_resume=parsed_resume,
            base_file_type=resume.file_type,
        )
    except Exception as exc:  # noqa: BLE001 - surface generation failures as 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate the tailored resume document.",
        ) from exc

    applied = [s.model_dump() for s in suggestions]

    # Upsert the tailored_resumes row (UNIQUE per job entry).
    existing = await db.execute(
        select(TailoredResume).where(
            TailoredResume.job_entry_id == job_entry.id
        )
    )
    tailored = existing.scalars().first()
    if tailored is not None:
        _remove_file_quietly(tailored.file_path)
        tailored.file_path = file_path
        tailored.applied_suggestions = applied
    else:
        tailored = TailoredResume(
            job_entry_id=job_entry.id,
            file_path=file_path,
            applied_suggestions=applied,
        )
        db.add(tailored)
        await db.flush()  # assign PK before linking from the job entry

    # Associate the document with the job entry (Requirement 6.7).
    job_entry.tailored_resume_id = tailored.id

    await db.commit()
    await db.refresh(tailored)

    return TailoredResumeResponse(
        id=tailored.id,
        job_entry_id=tailored.job_entry_id,
        file_path=tailored.file_path,
        applied_suggestions=suggestions,
        generated_at=tailored.generated_at,
    )


@router.get(
    "/{jd_id}/download-resume",
    response_class=FileResponse,
    summary="Download the generated tailored resume .docx",
)
async def download_resume(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Return the generated tailored resume ``.docx`` as a file download.

    Raises ``404`` when the JD is not accessible to the user, when no tailored
    resume has been generated, or when the generated file is missing on disk.
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)

    result = await db.execute(
        select(TailoredResume).where(
            TailoredResume.job_entry_id == job_entry.id
        )
    )
    tailored = result.scalars().first()
    if tailored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tailored resume found. Generate it first.",
        )

    path = Path(tailored.file_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The tailored resume file is no longer available.",
        )

    scraped_jd = await _get_scraped_jd(jd_id, db)
    safe_company = _safe_filename_part(scraped_jd.company_name)
    safe_title = _safe_filename_part(scraped_jd.job_title)
    download_name = f"resume_{safe_company}_{safe_title}.docx"

    return FileResponse(
        path=str(path),
        filename=download_name,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )


@router.get(
    "/{jd_id}/skill-gaps",
    response_model=SkillGapResult,
    summary="Get skill-gap analysis alongside the match breakdown",
)
async def get_skill_gaps(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillGapResult:
    """Return the skill-gap analysis for the JD against the user's resume.

    Rebuilds the JD's persisted tech stack, compares it against the resume's
    skills, and returns gaps categorised as Critical/Recommended with learning
    resources (Requirements 11.1-11.4).

    Raises ``404`` when the JD is not accessible to the user and ``400`` when
    the user has not uploaded a resume.
    """
    await _get_user_job_entry(jd_id, current_user, db)
    resume = await _get_user_resume(current_user, db)

    # Rebuild the persisted tech stack for the JD.
    tech_rows = await db.execute(
        select(TechStackItem).where(TechStackItem.jd_id == jd_id)
    )
    items = [TechStackItemSchema.model_validate(row) for row in tech_rows.scalars().all()]
    tech_stack = TechStackResult(
        items=items,
        required=[item for item in items if item.priority == "required"],
        nice_to_have=[item for item in items if item.priority == "nice_to_have"],
    )

    resume_skills = (resume.parsed_data or {}).get("skills") or []

    return await TechStackExtractorService().identify_skill_gaps(
        tech_stack=tech_stack,
        resume_skills=resume_skills,
    )
