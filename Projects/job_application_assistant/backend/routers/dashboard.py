"""
Dashboard router: track, update, and summarise the user's job applications.

Exposes the ``/api/dashboard`` endpoints described in the design document's API
Routes table that belong to tasks 13.1 and 13.2:

* ``GET    /api/dashboard``            — list all of the current user's tracked
  job entries, each joined to its scraped JD for the job title and company
  name, with optional status filtering and sorting (Requirements 9.1, 9.2,
  9.8).
* ``GET    /api/dashboard/summary``    — aggregate counts for the dashboard
  summary view: total analysed, total applied, interviews scheduled, and
  offers received (Requirement 9.9).
* ``PATCH  /api/dashboard/{entry_id}`` — update a job entry's status, notes,
  and/or deadline (Requirements 9.3, 9.4, 9.5, 12.1, 12.4).
* ``DELETE /api/dashboard/{entry_id}`` — delete a job entry and its associated
  data (Requirement 9.6).

Deadline tracking (Requirements 12.1-12.5) is computed per entry: the number of
days remaining until the deadline and an "urgent" flag are surfaced for
``not_applied`` entries with a deadline, and ``sort_by=deadline`` orders entries
by their approaching deadlines.

Scoping: every operation is scoped to the authenticated user via
``JobEntry.user_id == current_user.id``; entries that do not exist or are not
owned by the user yield ``404``.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``. Note the
name clash between ``models.ScrapedJD`` (ORM) and ``schemas.ScrapedJD``
(Pydantic): only the ORM model is used here and is imported aliased as
``ScrapedJDModel`` for clarity and consistency with the match router.
"""
from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import (
    JobEntry,
    ScrapedJD as ScrapedJDModel,
    User,
)
from schemas import (
    DashboardEntry,
    DashboardResponse,
    DashboardSummary,
    DashboardUpdate,
    JobStatus,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


#: Allowed values for the ``sort_by`` query parameter on ``GET /api/dashboard``.
SortBy = Literal["status", "date", "company", "match_score", "deadline"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_dashboard_entry(
    job_entry: JobEntry,
    scraped_jd: ScrapedJDModel,
) -> DashboardEntry:
    """Build a :class:`schemas.DashboardEntry` from a job entry and its JD.

    Flattens the JD's title/company onto the entry and computes the deadline
    tracking fields (Requirements 12.2, 12.3):

    * ``days_remaining`` — the whole number of days from today until the
      ``deadline``, surfaced ONLY when the entry has a deadline AND its status
      is ``not_applied`` (per Requirement 12.2). ``None`` otherwise. The value
      may be negative when a deadline has already passed.
    * ``is_urgent`` — ``True`` when ``days_remaining`` is within the next two
      days (``0 <= days_remaining <= 2``), i.e. an approaching deadline on an
      un-applied entry (Requirement 12.3). ``False`` otherwise.
    """
    days_remaining: int | None = None
    is_urgent = False

    if job_entry.deadline is not None and job_entry.status == "not_applied":
        days_remaining = (job_entry.deadline - date.today()).days
        is_urgent = 0 <= days_remaining <= 2

    return DashboardEntry(
        id=job_entry.id,
        jd_id=job_entry.jd_id,
        job_title=scraped_jd.job_title,
        company_name=scraped_jd.company_name,
        status=job_entry.status,
        match_score=(
            float(job_entry.match_score)
            if job_entry.match_score is not None
            else None
        ),
        notes=job_entry.notes,
        deadline=job_entry.deadline,
        tailored_resume_id=job_entry.tailored_resume_id,
        cover_letter_id=job_entry.cover_letter_id,
        created_at=job_entry.created_at,
        updated_at=job_entry.updated_at,
        days_remaining=days_remaining,
        is_urgent=is_urgent,
    )


async def _get_user_job_entry(
    entry_id: UUID,
    user: User,
    db: AsyncSession,
) -> JobEntry:
    """Return the current user's job entry by id, or raise ``404``.

    Every entry-scoped operation (PATCH/DELETE) resolves the row through this
    helper so an entry that does not exist, or belongs to another user, is
    indistinguishably reported as not found.
    """
    result = await db.execute(
        select(JobEntry).where(
            JobEntry.id == entry_id, JobEntry.user_id == user.id
        )
    )
    job_entry = result.scalars().first()
    if job_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job entry not found",
        )
    return job_entry


async def _get_scraped_jd(jd_id: UUID, db: AsyncSession) -> ScrapedJDModel:
    """Fetch the scraped JD row referenced by a job entry, or raise ``404``."""
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# NOTE: the static ``/summary`` route is declared before any ``/{entry_id}``
# path so it is never shadowed by path-parameter capture.


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Get dashboard summary statistics",
)
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    """Return aggregate counts for the current user's dashboard summary view.

    Uses a single grouped ``COUNT`` over the user's job entries to derive
    (Requirement 9.9):

    * ``total_analyzed``       — every tracked job entry (all statuses).
    * ``total_applied``        — entries with status ``applied``.
    * ``interviews_scheduled`` — entries with status ``interview_scheduled``.
    * ``offers_received``      — entries with status ``offered``.
    """
    result = await db.execute(
        select(JobEntry.status, func.count())
        .where(JobEntry.user_id == current_user.id)
        .group_by(JobEntry.status)
    )
    counts = {row_status: count for row_status, count in result.all()}

    return DashboardSummary(
        total_analyzed=sum(counts.values()),
        total_applied=counts.get("applied", 0),
        interviews_scheduled=counts.get("interview_scheduled", 0),
        offers_received=counts.get("offered", 0),
    )


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Get the job application tracking dashboard",
)
async def get_dashboard(
    status_filter: JobStatus | None = Query(
        default=None,
        description="Only return entries with this application status.",
    ),
    sort_by: SortBy = Query(
        default="date",
        description=(
            "Sort order: 'status' (alphabetical), 'date' (newest first), "
            "'company' (A-Z), 'match_score' (highest first, NULLs last), or "
            "'deadline' (soonest first, NULLs last)."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Return all of the current user's tracked job entries.

    Each entry is joined to its scraped JD so the response carries the job
    title and company name alongside the tracked status, match score, notes,
    deadline, and generated-document associations (Requirement 9.1). Results
    are rendered as cards/rows by the frontend (Requirement 9.2).

    Query parameters (Requirements 9.8, 12.5):

    * ``status_filter`` — restrict the result to a single application status.
    * ``sort_by`` — one of ``status``, ``date``, ``company``, ``match_score``,
      or ``deadline``. Defaults to ``date`` (newest first). ``match_score`` is
      highest-first with NULL scores last; ``deadline`` is soonest-first with
      NULL deadlines last (Requirement 12.5).

    The deadline tracking fields (``days_remaining``/``is_urgent``) are computed
    per entry by :func:`_to_dashboard_entry`.
    """
    stmt = (
        select(JobEntry, ScrapedJDModel)
        .join(ScrapedJDModel, JobEntry.jd_id == ScrapedJDModel.id)
        .where(JobEntry.user_id == current_user.id)
    )

    if status_filter is not None:
        stmt = stmt.where(JobEntry.status == status_filter)

    if sort_by == "status":
        stmt = stmt.order_by(JobEntry.status.asc())
    elif sort_by == "company":
        stmt = stmt.order_by(ScrapedJDModel.company_name.asc())
    elif sort_by == "match_score":
        # Highest match first; entries without a score sort last.
        stmt = stmt.order_by(JobEntry.match_score.desc().nullslast())
    elif sort_by == "deadline":
        # Soonest deadline first; entries without a deadline sort last.
        stmt = stmt.order_by(JobEntry.deadline.asc().nullslast())
    else:  # "date" (default)
        stmt = stmt.order_by(JobEntry.created_at.desc())

    result = await db.execute(stmt)
    entries = [
        _to_dashboard_entry(job_entry, scraped_jd)
        for job_entry, scraped_jd in result.all()
    ]
    return DashboardResponse(entries=entries)


@router.patch(
    "/{entry_id}",
    response_model=DashboardEntry,
    summary="Update a job entry's status, notes, and/or deadline",
)
async def update_dashboard_entry(
    entry_id: UUID,
    payload: DashboardUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardEntry:
    """Update the status, notes, and/or deadline of a tracked job entry.

    Only fields explicitly present in the request body are applied
    (``model_dump(exclude_unset=True)``). This distinguishes "field omitted"
    (left unchanged) from "field set to null": sending ``deadline: null``
    removes the deadline (Requirement 12.4), whereas omitting ``deadline``
    leaves the existing value intact. The same distinction applies to
    ``notes``. The ``status`` value is constrained to the valid set by the
    ``JobStatus`` literal on :class:`schemas.DashboardUpdate`, enforced at the
    request boundary (Requirements 9.3, 9.5).

    Returns the updated entry as a :class:`schemas.DashboardEntry`, including
    the JD title/company and recomputed deadline fields. Raises ``404`` when
    the entry does not exist or is not owned by the user.
    """
    job_entry = await _get_user_job_entry(entry_id, current_user, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(job_entry, field, value)

    await db.commit()
    await db.refresh(job_entry)

    scraped_jd = await _get_scraped_jd(job_entry.jd_id, db)
    return _to_dashboard_entry(job_entry, scraped_jd)


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a job entry from the dashboard",
)
async def delete_dashboard_entry(
    entry_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a tracked job entry and its associated data (Requirement 9.6).

    Deleting the ``JobEntry`` row cascades to its dependent records: the match
    result, interview topics, and interview Q&A are removed via the ORM
    ``cascade="all, delete-orphan"`` relationships, while the tailored resume
    and cover letter rows are removed via their ``ON DELETE CASCADE`` foreign
    keys at the database level.

    Raises ``404`` when the entry does not exist or is not owned by the user.
    Returns no content (``204``) on success.
    """
    job_entry = await _get_user_job_entry(entry_id, current_user, db)

    await db.delete(job_entry)
    await db.commit()
    return None
