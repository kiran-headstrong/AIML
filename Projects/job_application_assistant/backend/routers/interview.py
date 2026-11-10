"""
Interview router: generate, persist, and export interview preparation material
(ranked topics and categorized Q&A sets) for a scraped job description.

Exposes the ``/api/interview`` endpoints described in the design document's API
Routes table that belong to task 9.2:

* ``POST /api/interview/{jd_id}/topics`` — generate ranked interview topics via
  the Interview Prep Service, (re)persist them to ``interview_topics``, and
  return them (Requirements 7.1, 7.2, 7.3).
* ``POST /api/interview/{jd_id}/qa``     — generate categorized Q&A sets per
  topic (tailored to the user's experience level), ensuring topics exist first,
  persist them to ``interview_qas``, and return topics + Q&A
  (Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6).
* ``GET  /api/interview/{jd_id}/export-pdf`` — export the prepared material as a
  formatted PDF. This belongs to task 11 (Export Service, task 11.1) and is NOT
  implemented here; the route is registered as a stub returning ``501 Not
  Implemented`` so the router surface matches the design. Task 11 wires it.

Scoping: scraped JDs are shared rows, and interview topics/Q&A hang off the
user's ``job_entry`` (not the shared JD). A JD is accessible to a user only when
the user has a ``job_entry`` referencing it; the helpers enforce this and return
``404`` otherwise, mirroring the match router.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``. Note the
name clash between ``models.ScrapedJD`` (ORM) and ``schemas.ScrapedJD``
(Pydantic): the ORM model is imported aliased as ``ScrapedJDModel``.
"""
from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import (
    InterviewQA as InterviewQAModel,
    InterviewTopic as InterviewTopicModel,
    JobEntry,
    ScrapedJD as ScrapedJDModel,
    User,
)
from schemas import (
    InterviewQA as InterviewQASchema,
    InterviewQARequest,
    InterviewQAResponse,
    InterviewTopic as InterviewTopicSchema,
    InterviewTopicsResponse,
    ScrapedJD as ScrapedJDSchema,
)
from services.export_service import ExportService
from services.interview_prep import InterviewPrepService

router = APIRouter(prefix="/api/interview", tags=["interview"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_job_entry(
    jd_id: UUID,
    user: User,
    db: AsyncSession,
) -> JobEntry:
    """Return the current user's job entry for ``jd_id``, or raise ``404``.

    Interview topics/Q&A hang off a ``job_entry`` (not the shared JD), so every
    interview operation is scoped through the user's own job entry for the JD.
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


async def _regenerate_topics(
    job_entry: JobEntry,
    scraped_jd: ScrapedJDModel,
    db: AsyncSession,
) -> list[InterviewTopicModel]:
    """Generate fresh topics and (re)persist them for the job entry.

    Deletes the job entry's existing ``interview_topics`` rows first (the
    ``ON DELETE CASCADE`` on ``interview_qas.topic_id`` removes their Q&A), then
    generates and inserts the newly ranked topics. The rows are added and
    flushed (so their PKs are assigned) but not committed; the caller owns the
    transaction boundary.

    Returns the persisted :class:`models.InterviewTopic` rows in ranked order.
    """
    # Clear existing topics (cascade removes their Q&A) before regenerating.
    await db.execute(
        delete(InterviewTopicModel).where(
            InterviewTopicModel.job_entry_id == job_entry.id
        )
    )

    generated = await InterviewPrepService().generate_topics(
        _scraped_jd_schema(scraped_jd)
    )

    topic_rows: list[InterviewTopicModel] = []
    for topic in generated:
        row = InterviewTopicModel(
            job_entry_id=job_entry.id,
            name=topic.name,
            category=topic.category,
            relevance_rank=topic.relevance_rank,
        )
        db.add(row)
        topic_rows.append(row)

    # Assign PKs so Q&A persistence can map topic names -> topic ids.
    await db.flush()
    return topic_rows


async def _fetch_topics(
    job_entry: JobEntry, db: AsyncSession
) -> list[InterviewTopicModel]:
    """Return the job entry's persisted topics ordered by relevance rank."""
    result = await db.execute(
        select(InterviewTopicModel)
        .where(InterviewTopicModel.job_entry_id == job_entry.id)
        .order_by(InterviewTopicModel.relevance_rank)
    )
    return list(result.scalars().all())


async def _fetch_qa(
    job_entry: JobEntry, db: AsyncSession
) -> list[InterviewQAModel]:
    """Return the job entry's persisted interview Q&A rows."""
    result = await db.execute(
        select(InterviewQAModel).where(
            InterviewQAModel.job_entry_id == job_entry.id
        )
    )
    return list(result.scalars().all())


def _safe_filename_part(value: str | None) -> str:
    """Sanitise a string into a filesystem-safe filename fragment.

    Collapses non-alphanumeric characters into underscores and trims length so
    the generated download name is portable across platforms.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (value or "").strip()).strip("_")
    return (cleaned or "interview_prep")[:60]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{jd_id}/topics",
    response_model=InterviewTopicsResponse,
    summary="Generate ranked interview topics for the JD",
)
async def generate_topics(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewTopicsResponse:
    """Generate (regenerating on each call) ranked interview topics for the JD.

    Uses the Interview Prep Service to produce topics categorised as
    ``technical``/``domain``/``behavioral`` and ranked by relevance
    (Requirements 7.1, 7.2, 7.3). Existing topics for the user's job entry are
    cleared and replaced so the persisted set reflects the latest generation.

    Raises ``404`` when the JD is not accessible to the user.
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)
    scraped_jd = await _get_scraped_jd(jd_id, db)

    topic_rows = await _regenerate_topics(job_entry, scraped_jd, db)
    await db.commit()

    topics = [InterviewTopicSchema.model_validate(row) for row in topic_rows]
    return InterviewTopicsResponse(topics=topics)


@router.post(
    "/{jd_id}/qa",
    response_model=InterviewQAResponse,
    summary="Generate interview Q&A sets for the JD",
)
async def generate_qa(
    jd_id: UUID,
    payload: InterviewQARequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewQAResponse:
    """Generate categorized Q&A sets per topic, tailored to experience level.

    Resolves the experience level from the request body if provided, otherwise
    falls back to the user's stored ``experience_level`` (Requirement 8.4).
    Ensures topics exist first (generating and persisting them when absent),
    produces Q&A across difficulty tiers with scenario-based questions and key
    points (Requirements 8.1, 8.2, 8.3, 8.5, 8.6), and (re)persists the Q&A to
    ``interview_qas`` — clearing any previous Q&A for the job entry so
    regeneration does not accumulate duplicates.

    Each generated Q&A is associated with its topic by case-insensitive name
    match; a Q&A referencing an unknown topic is skipped for persistence but the
    returned payload reflects what was persisted.

    Raises ``404`` when the JD is not accessible to the user.
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)
    scraped_jd = await _get_scraped_jd(jd_id, db)

    # Determine the experience level used to tailor question depth.
    override = payload.experience_level if payload is not None else None
    experience_level = override or current_user.experience_level or ""

    # Ensure topics exist for the job entry; generate+persist them if not.
    topic_rows = await _fetch_topics(job_entry, db)
    if not topic_rows:
        topic_rows = await _regenerate_topics(job_entry, scraped_jd, db)

    topic_schemas = [InterviewTopicSchema.model_validate(row) for row in topic_rows]

    # Case-insensitive lookup from topic name -> persisted topic row.
    topic_by_name = {row.name.lower(): row for row in topic_rows}

    generated_qa = await InterviewPrepService().generate_qa(
        topics=topic_schemas,
        jd=_scraped_jd_schema(scraped_jd),
        experience_level=experience_level,
    )

    # Clear existing Q&A for the job entry before inserting the fresh set.
    await db.execute(
        delete(InterviewQAModel).where(
            InterviewQAModel.job_entry_id == job_entry.id
        )
    )

    persisted_qa: list[InterviewQASchema] = []
    for qa in generated_qa:
        topic_row = topic_by_name.get(qa.topic.lower())
        if topic_row is None:
            # Unknown topic name: skip persistence but keep the loop going.
            continue
        db.add(
            InterviewQAModel(
                job_entry_id=job_entry.id,
                topic_id=topic_row.id,
                question=qa.question,
                answer=qa.answer,
                key_points=qa.key_points,
                difficulty=qa.difficulty,
                is_scenario_based=qa.is_scenario_based,
            )
        )
        persisted_qa.append(qa)

    await db.commit()

    return InterviewQAResponse(topics=topic_schemas, qa=persisted_qa)


@router.get(
    "/{jd_id}/export-pdf",
    response_class=FileResponse,
    summary="Export interview prep as a formatted PDF",
)
async def export_pdf(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Export the prepared interview material as a formatted PDF download.

    Fetches the user's persisted interview topics (ordered by relevance rank)
    and their Q&A, renders them into a formatted PDF via the Export Service —
    with clear section headings per topic, a difficulty label on each question,
    readable answer formatting, and the job title/company name in the header
    (Requirements 14.1, 14.2, 14.3) — and returns the file as a download
    (Requirement 14.4).

    Raises ``404`` when the JD is not accessible to the user, or when no
    interview topics/Q&A have been generated yet (prompting the user to
    generate interview prep first).
    """
    job_entry = await _get_user_job_entry(jd_id, current_user, db)
    scraped_jd = await _get_scraped_jd(jd_id, db)

    topic_rows = await _fetch_topics(job_entry, db)
    qa_rows = await _fetch_qa(job_entry, db)

    if not topic_rows and not qa_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No interview preparation found. Generate interview topics "
                "and Q&A before exporting."
            ),
        )

    # Map topic ids -> names so each Q&A can carry its topic name (the ORM row
    # stores only ``topic_id``, while the schema expects the topic name).
    topic_name_by_id = {row.id: row.name for row in topic_rows}

    topics = [InterviewTopicSchema.model_validate(row) for row in topic_rows]
    qa = [
        InterviewQASchema(
            question=row.question,
            answer=row.answer,
            key_points=list(row.key_points or []),
            difficulty=row.difficulty,
            is_scenario_based=row.is_scenario_based,
            topic=topic_name_by_id.get(row.topic_id, ""),
        )
        for row in qa_rows
    ]

    try:
        file_path = ExportService().export_interview_prep_pdf(
            topics=topics,
            qa=qa,
            job_title=scraped_jd.job_title,
            company_name=scraped_jd.company_name,
        )
    except Exception as exc:  # noqa: BLE001 - surface export failures as 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate the interview preparation PDF.",
        ) from exc

    safe_company = _safe_filename_part(scraped_jd.company_name)
    safe_title = _safe_filename_part(scraped_jd.job_title)
    download_name = f"interview_prep_{safe_company}_{safe_title}.pdf"

    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/pdf",
    )
