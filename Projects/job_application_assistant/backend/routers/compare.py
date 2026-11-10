"""
Compare router: side-by-side comparison of analysed job descriptions.

Exposes the ``/api/compare`` endpoint described in the design document's API
Routes table that belongs to task 14.1:

* ``POST /api/compare`` — accept a list of JD ids, fetch each JD's structured
  data together with the current user's match score for it, and return a
  structured comparison (Requirements 13.1-13.4):

  - Per-JD data: job title, company, required skills, preferred skills,
    experience required, and match score (Requirements 13.1, 13.2).
  - ``common_skills``: required skills shared across *all* compared JDs, and
    ``unique_skills``: for each JD, the required skills that appear in no other
    compared JD — surfacing both commonalities and differences
    (Requirement 13.3).
  - ``highest_match_jd_id``: the compared role with the highest match score
    relative to the user's base resume (Requirement 13.4).

Scoping: scraped JDs are shared rows (not directly user-scoped). As with the
JD and match routers, a JD is accessible to a user only when the user has a
``job_entry`` referencing it; any requested id that the user cannot access —
or that does not exist — yields ``404``. Fetching the JD through the user's
job entry also provides the user-specific ``match_score`` for that JD.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``. Note the
name clash between ``models.ScrapedJD`` (ORM) and ``schemas.ScrapedJD``
(Pydantic): only the ORM model is used here and is imported aliased as
``ScrapedJDModel`` for clarity and consistency with the other routers.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import JobEntry, ScrapedJD as ScrapedJDModel, User
from schemas import CompareItem, CompareRequest, CompareResponse

router = APIRouter(prefix="/api/compare", tags=["compare"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedupe_preserve_order(skills: list[str]) -> list[str]:
    """Normalise and de-duplicate a skill list, preserving first-seen order.

    Skills are compared case-insensitively on their trimmed form so that, e.g.,
    ``"Python"`` and ``"python "`` are treated as the same skill; the first
    occurrence's original casing is retained for display.
    """
    seen: set[str] = set()
    result: list[str] = []
    for skill in skills:
        key = skill.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(skill.strip())
    return result


def _build_common_and_unique(
    items: list[CompareItem],
) -> tuple[list[str], dict[str, list[str]]]:
    """Compute required-skill commonalities and per-JD differences.

    Returns a ``(common_skills, unique_skills)`` pair (Requirement 13.3):

    * ``common_skills`` — required skills present (case-insensitively) in
      *every* compared JD. Only meaningful when two or more JDs are compared;
      with a single JD there is nothing to share, so this is empty.
    * ``unique_skills`` — maps each JD's id (as a string) to the required
      skills that appear in that JD and in no other compared JD.

    Comparison is case-insensitive; the display casing for common skills is
    taken from the first JD that contains the skill.
    """
    # Case-folded skill sets per JD, plus a display-casing lookup.
    folded_sets: list[set[str]] = []
    display_by_key: dict[str, str] = {}
    for item in items:
        folded: set[str] = set()
        for skill in item.required_skills:
            key = skill.casefold()
            folded.add(key)
            display_by_key.setdefault(key, skill)
        folded_sets.append(folded)

    # Common skills: intersection across all JDs (only when 2+ JDs compared).
    common_keys: set[str] = set()
    if len(folded_sets) >= 2:
        common_keys = set.intersection(*folded_sets)

    common_skills = [
        display_by_key[key]
        for key in dict.fromkeys(  # preserve first-JD order
            k for s in folded_sets for k in s if k in common_keys
        )
    ]

    # Unique skills per JD: present in this JD but in no other compared JD.
    unique_skills: dict[str, list[str]] = {}
    for idx, item in enumerate(items):
        others: set[str] = set()
        for other_idx, other_set in enumerate(folded_sets):
            if other_idx != idx:
                others |= other_set
        unique = [
            skill for skill in item.required_skills
            if skill.casefold() not in others
        ]
        unique_skills[str(item.jd_id)] = unique

    return common_skills, unique_skills


def _highest_match_jd_id(items: list[CompareItem]) -> UUID | None:
    """Return the id of the JD with the highest match score, or ``None``.

    Entries without a computed match score are ignored (Requirement 13.4). When
    no compared JD has a score, ``None`` is returned. Ties resolve to the first
    JD with the maximum score in request order.
    """
    scored = [item for item in items if item.match_score is not None]
    if not scored:
        return None
    best = max(scored, key=lambda item: item.match_score or 0.0)
    return best.jd_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CompareResponse,
    summary="Compare multiple analysed job descriptions side by side",
)
async def compare_jds(
    payload: CompareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompareResponse:
    """Compare two or more of the user's analysed JDs side by side.

    Fetches each requested JD through the current user's ``job_entry`` so the
    response carries the user-specific match score alongside the JD's title,
    company, required/preferred skills, and experience required
    (Requirements 13.1, 13.2). The comparison also highlights the required
    skills common to all compared JDs and those unique to each
    (Requirement 13.3), and flags the role with the highest match score
    (Requirement 13.4).

    Duplicate ids in the request are collapsed to a single comparison entry
    while preserving request order. Raises ``404`` when any requested JD does
    not exist or is not accessible to the current user.
    """
    # Collapse duplicates while preserving the caller's ordering.
    requested_ids = list(dict.fromkeys(payload.jd_ids))

    # Fetch each JD joined to the user's own job entry (provides scoping + the
    # user-specific match score in a single query per JD).
    rows = await db.execute(
        select(ScrapedJDModel, JobEntry.match_score)
        .join(JobEntry, JobEntry.jd_id == ScrapedJDModel.id)
        .where(
            ScrapedJDModel.id.in_(requested_ids),
            JobEntry.user_id == current_user.id,
        )
    )
    by_id: dict[UUID, tuple[ScrapedJDModel, float | None]] = {}
    for scraped_jd, match_score in rows.all():
        by_id[scraped_jd.id] = (
            scraped_jd,
            float(match_score) if match_score is not None else None,
        )

    # Any requested id the user can't access (or that doesn't exist) is a 404.
    missing = [jd_id for jd_id in requested_ids if jd_id not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "One or more job descriptions were not found: "
                + ", ".join(str(jd_id) for jd_id in missing)
            ),
        )

    # Build the per-JD comparison items in the caller's requested order.
    items = [
        CompareItem(
            jd_id=scraped_jd.id,
            job_title=scraped_jd.job_title,
            company_name=scraped_jd.company_name,
            required_skills=_dedupe_preserve_order(
                list(scraped_jd.required_skills or [])
            ),
            preferred_skills=_dedupe_preserve_order(
                list(scraped_jd.preferred_skills or [])
            ),
            experience_required=scraped_jd.experience_required,
            match_score=match_score,
        )
        for scraped_jd, match_score in (by_id[jd_id] for jd_id in requested_ids)
    ]

    common_skills, unique_skills = _build_common_and_unique(items)

    return CompareResponse(
        items=items,
        common_skills=common_skills,
        unique_skills=unique_skills,
        highest_match_jd_id=_highest_match_jd_id(items),
    )
