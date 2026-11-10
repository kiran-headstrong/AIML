"""
Job Description router: scrape, retrieve, and inspect scraped JDs.

Exposes the ``/api/jd`` endpoints described in the design document's API
Routes table:

* ``POST /api/jd/scrape``           — scrape a LinkedIn/Naukri posting, persist
  the structured JD, extract and persist its tech stack, auto-create a tracking
  ``job_entry`` (status ``not_applied``), and return structured + pretty-printed
  data for user confirmation.
* ``GET  /api/jd/{id}``             — fetch a persisted scraped JD.
* ``GET  /api/jd/{id}/tech-stack``  — fetch the persisted tech-stack items for a
  scraped JD, rebuilt into a categorized result.

Scraped JDs are shared rows (not directly user-scoped). To avoid leaking other
users' data, the read endpoints verify the current user has a ``job_entry``
referencing the JD before returning it.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``. Note the
name clash between ``models.ScrapedJD`` (ORM) and ``schemas.ScrapedJD``
(Pydantic): the ORM model is imported aliased as ``ScrapedJDModel``.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import JobEntry, ScrapedJD as ScrapedJDModel, TechStackItem, User
from schemas import (
    JDScrapeRequest,
    JDScrapeResponse,
    ScrapedJDResponse,
    TechStackItem as TechStackItemSchema,
    TechStackResult,
)
from services.jd_scraper import JDScraperService, ScrapeError, UnsupportedURLError
from services.tech_stack_extractor import TechStackExtractorService

router = APIRouter(prefix="/api/jd", tags=["jd"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_scoped_jd(
    jd_id: UUID,
    user: User,
    db: AsyncSession,
) -> ScrapedJDModel:
    """Return a scraped JD the current user may access, or raise ``404``.

    A JD is accessible to a user when the user has a ``job_entry`` referencing
    it. This keeps shared ``scraped_jds`` rows from leaking across users while
    matching the schema design (scraped JDs are not directly user-scoped).
    """
    result = await db.execute(
        select(ScrapedJDModel)
        .join(JobEntry, JobEntry.jd_id == ScrapedJDModel.id)
        .where(ScrapedJDModel.id == jd_id, JobEntry.user_id == user.id)
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


@router.post(
    "/scrape",
    response_model=JDScrapeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Scrape a job posting URL and persist the structured JD",
)
async def scrape_jd(
    payload: JDScrapeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JDScrapeResponse:
    """Scrape, persist, and analyse a job posting URL.

    Scrapes the LinkedIn/Naukri posting, stores the structured JD in
    ``scraped_jds``, extracts and stores its tech stack in ``tech_stack_items``,
    and auto-creates a ``job_entries`` row for the current user with status
    ``not_applied`` (Requirements 1.1, 1.2, 1.5, 2.1-2.3, 9.7, 15.1, 15.2).

    Returns the persisted JD, the new job-entry id, a pretty-printed rendering,
    and the categorized tech stack for user confirmation.

    Raises ``400`` when the URL is unsupported (Requirement 1.3) and ``502``
    when a valid URL cannot be fetched (Requirement 1.4).
    """
    scraper = JDScraperService()
    try:
        scraped = await scraper.scrape(payload.url)
    except UnsupportedURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ScrapeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    # Persist the structured JD.
    jd_model = ScrapedJDModel(
        job_title=scraped.job_title,
        company_name=scraped.company_name,
        location=scraped.location,
        experience_required=scraped.experience_required,
        description_body=scraped.description_body,
        required_skills=scraped.required_skills,
        preferred_skills=scraped.preferred_skills,
        raw_html=scraped.raw_html,
    )
    db.add(jd_model)
    await db.flush()  # assign jd_model.id for the tech-stack/job-entry FKs

    # Extract and persist the tech stack.
    tech_stack = await TechStackExtractorService().extract(
        scraped.description_body or scraper.format_pretty(scraped)
    )
    for item in tech_stack.items:
        db.add(
            TechStackItem(
                jd_id=jd_model.id,
                name=item.name,
                category=item.category,
                priority=item.priority,
            )
        )

    # Auto-create a tracking job entry for the current user (Requirement 9.7).
    job_entry = JobEntry(
        user_id=current_user.id,
        jd_id=jd_model.id,
        status="not_applied",
    )
    db.add(job_entry)

    await db.commit()
    await db.refresh(jd_model)
    await db.refresh(job_entry)

    return JDScrapeResponse(
        jd=ScrapedJDResponse.model_validate(jd_model),
        job_entry_id=job_entry.id,
        pretty=scraper.format_pretty(scraped),
        tech_stack=tech_stack,
    )


@router.get(
    "/{jd_id}",
    response_model=ScrapedJDResponse,
    summary="Get a persisted scraped job description",
)
async def get_jd(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScrapedJDResponse:
    """Return a persisted scraped JD the current user can access.

    Returns ``404`` when the JD does not exist or is not referenced by any of
    the current user's job entries.
    """
    scraped_jd = await _get_user_scoped_jd(jd_id, current_user, db)
    return ScrapedJDResponse.model_validate(scraped_jd)


@router.get(
    "/{jd_id}/tech-stack",
    response_model=TechStackResult,
    summary="Get the extracted tech stack for a scraped JD",
)
async def get_jd_tech_stack(
    jd_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TechStackResult:
    """Return the persisted tech-stack items for a scraped JD.

    Rebuilds a :class:`~schemas.TechStackResult` from ``tech_stack_items``,
    splitting items into ``required`` and ``nice_to_have`` and attaching an
    informational message when no technologies were found (Requirements 2.1,
    2.2, 2.3). Returns ``404`` when the JD does not exist or is not accessible
    to the current user.
    """
    # Enforce existence + user scoping first (raises 404 otherwise).
    await _get_user_scoped_jd(jd_id, current_user, db)

    result = await db.execute(
        select(TechStackItem).where(TechStackItem.jd_id == jd_id)
    )
    rows = result.scalars().all()

    items = [TechStackItemSchema.model_validate(row) for row in rows]
    required = [item for item in items if item.priority == "required"]
    nice_to_have = [item for item in items if item.priority == "nice_to_have"]

    message = None
    if not items:
        message = (
            "No specific tech stack could be identified in this job "
            "description. Please review the posting manually to determine "
            "the required technologies."
        )

    return TechStackResult(
        items=items,
        required=required,
        nice_to_have=nice_to_have,
        message=message,
    )
