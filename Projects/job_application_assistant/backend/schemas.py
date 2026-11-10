"""
Pydantic v2 request/response schemas for the Job Application Assistant API.

These schemas provide validation and serialization for all API endpoints
described in the design document's "API Routes" table, and mirror the
service-layer component interfaces (ScrapedJD, TechStackResult, ParsedResume,
MatchBreakdown, EditSuggestion, InterviewTopic, InterviewQA, cover letter,
skill gaps, etc.).

Conventions
-----------
* Request bodies are plain ``BaseModel`` subclasses.
* Response schemas that are read from SQLAlchemy ORM objects set
  ``model_config = ConfigDict(from_attributes=True)`` so they can be built via
  ``Schema.model_validate(orm_obj)``.
* ``Literal`` types are used for constrained string fields (status, priority,
  category, difficulty, ...) so invalid values are rejected at the boundary.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared literal / enum-style types
# ---------------------------------------------------------------------------

#: Valid values for a job application's status (mirrors JOB_ENTRY_STATUSES).
JobStatus = Literal[
    "not_applied",
    "applied",
    "interview_scheduled",
    "interview_completed",
    "offered",
    "rejected",
]

#: Tech-stack categories.
TechCategory = Literal["language", "framework", "database", "cloud", "tool"]

#: Tech-stack / skill priority.
TechPriority = Literal["required", "nice_to_have"]

#: Match category label.
MatchCategory = Literal["Strong Match", "Moderate Match", "Weak Match"]

#: Edit-suggestion category.
SuggestionCategory = Literal[
    "skills_to_add",
    "experience_rephrase",
    "keywords_to_include",
    "sections_reorder",
]

#: Edit-suggestion impact.
Impact = Literal["high", "medium", "low"]

#: Interview topic category.
TopicCategory = Literal["technical", "domain", "behavioral"]

#: Interview question difficulty.
Difficulty = Literal["easy", "medium", "difficult"]

#: Skill-gap priority label.
GapPriority = Literal["Critical", "Recommended"]


# ===========================================================================
# Authentication
# ===========================================================================


class UserRegister(BaseModel):
    """Request body for ``POST /api/auth/register``."""

    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=1, max_length=255)
    experience_level: str | None = Field(default=None, max_length=50)


class UserLogin(BaseModel):
    """Request body for ``POST /api/auth/login``."""

    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """Public representation of a user (``GET /api/auth/me``)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    experience_level: str | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT token response returned from login/register."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ===========================================================================
# Scraped Job Description
# ===========================================================================


class JDScrapeRequest(BaseModel):
    """Request body for ``POST /api/jd/scrape``."""

    url: str = Field(..., min_length=1, description="LinkedIn or Naukri job URL.")


class ScrapedJD(BaseModel):
    """Structured job-description data (service output + scrape response)."""

    job_title: str
    company_name: str
    location: str | None = None
    experience_required: str | None = None
    description_body: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    raw_html: str = ""  # preserved for re-parsing


class ScrapedJDResponse(BaseModel):
    """Persisted scraped JD (``GET /api/jd/{id}``)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_title: str
    company_name: str
    location: str | None = None
    experience_required: str | None = None
    description_body: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    scraped_at: datetime


class JDScrapeResponse(BaseModel):
    """Response for ``POST /api/jd/scrape`` — JD plus the created job entry."""

    jd: ScrapedJDResponse
    job_entry_id: UUID
    pretty: str = Field(
        default="",
        description="Clean, human-readable rendering of the scraped JD.",
    )
    tech_stack: "TechStackResult | None" = None


# ===========================================================================
# Tech Stack
# ===========================================================================


class TechStackItem(BaseModel):
    """A single categorized technology requirement."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    category: TechCategory
    priority: TechPriority


class TechStackResult(BaseModel):
    """Categorized tech-stack result (``GET /api/jd/{id}/tech-stack``)."""

    items: list[TechStackItem] = Field(default_factory=list)
    required: list[TechStackItem] = Field(default_factory=list)
    nice_to_have: list[TechStackItem] = Field(default_factory=list)
    message: str | None = Field(
        default=None,
        description="Informational message, e.g. when no technologies found.",
    )


# ===========================================================================
# Resume parsing
# ===========================================================================


class ContactInfo(BaseModel):
    """Contact details extracted from a resume."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class WorkExperience(BaseModel):
    """A single work-experience entry extracted from a resume."""

    title: str | None = None
    company: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)


class Education(BaseModel):
    """A single education entry extracted from a resume."""

    degree: str | None = None
    institution: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class ParsedResume(BaseModel):
    """Structured resume data produced by the parser service."""

    contact: ContactInfo = Field(default_factory=ContactInfo)
    skills: list[str] = Field(default_factory=list)
    experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    raw_text: str = ""
    warning: str | None = Field(
        default=None,
        description=(
            "Human-readable notice when parsing could not fully extract "
            "structured sections (e.g. no text layer in the PDF, or the LLM "
            "was unreachable). Null when parsing succeeded normally."
        ),
    )


class ResumeDetailResponse(BaseModel):
    """Stored base-resume details (``GET /api/resume``)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_name: str
    file_type: str
    uploaded_at: datetime
    skills: list[str] = Field(
        default_factory=list,
        description="Summary of extracted skills for display.",
    )
    warning: str | None = Field(
        default=None,
        description="Notice when no skills/sections could be extracted.",
    )


class ResumeUploadResponse(BaseModel):
    """Response for ``POST /api/resume/upload``."""

    id: UUID
    file_name: str
    file_type: str
    uploaded_at: datetime
    parsed: ParsedResume


# ===========================================================================
# Match / scoring
# ===========================================================================


class MatchBreakdown(BaseModel):
    """Weighted match score with detailed breakdown."""

    overall_score: float = Field(..., ge=0, le=100)
    skills_score: float = Field(..., ge=0, le=100)
    experience_score: float = Field(..., ge=0, le=100)
    education_score: float = Field(..., ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    matched_experience_keywords: list[str] = Field(default_factory=list)
    missing_experience_keywords: list[str] = Field(default_factory=list)
    category: MatchCategory


class MatchRequest(BaseModel):
    """Optional request body for ``POST /api/match/{jd_id}``."""

    recompute: bool = Field(
        default=False,
        description="Force recomputation even if a result already exists.",
    )


class MatchResponse(BaseModel):
    """Persisted match result (``GET /api/match/{jd_id}``)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    job_entry_id: UUID
    overall_score: float
    skills_score: float
    experience_score: float
    education_score: float
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    matched_experience_keywords: list[str] = Field(
        default_factory=list, alias="matched_experience_kw"
    )
    missing_experience_keywords: list[str] = Field(
        default_factory=list, alias="missing_experience_kw"
    )
    category: str
    computed_at: datetime


# ===========================================================================
# Resume edit suggestions / tailored resume
# ===========================================================================


class EditSuggestion(BaseModel):
    """A single prioritized resume edit suggestion."""

    category: SuggestionCategory
    description: str
    impact: Impact
    original_text: str | None = None
    suggested_text: str | None = None


class SuggestionsResponse(BaseModel):
    """Response for ``GET /api/match/{jd_id}/suggestions``."""

    suggestions: list[EditSuggestion] = Field(default_factory=list)


class TailoredResumeResponse(BaseModel):
    """Response for ``POST /api/match/{jd_id}/generate-resume``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_entry_id: UUID
    file_path: str
    applied_suggestions: list[EditSuggestion] = Field(default_factory=list)
    generated_at: datetime


# ===========================================================================
# Skill gap analysis
# ===========================================================================


class SkillGap(BaseModel):
    """A single missing skill with a priority and learning resources."""

    skill: str
    priority: GapPriority
    learning_resources: list[str] = Field(default_factory=list)


class SkillGapResult(BaseModel):
    """Skill-gap analysis (``GET /api/match/{jd_id}/skill-gaps``)."""

    gaps: list[SkillGap] = Field(default_factory=list)
    critical: list[SkillGap] = Field(default_factory=list)
    recommended: list[SkillGap] = Field(default_factory=list)


# ===========================================================================
# Interview preparation
# ===========================================================================


class InterviewTopic(BaseModel):
    """A ranked interview topic."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    category: TopicCategory
    relevance_rank: int


class InterviewQA(BaseModel):
    """A single interview question-and-answer."""

    model_config = ConfigDict(from_attributes=True)

    question: str
    answer: str
    key_points: list[str] = Field(default_factory=list)
    difficulty: Difficulty
    is_scenario_based: bool = False
    topic: str


class InterviewTopicsResponse(BaseModel):
    """Response for ``POST /api/interview/{jd_id}/topics``."""

    topics: list[InterviewTopic] = Field(default_factory=list)


class InterviewQARequest(BaseModel):
    """Request body for ``POST /api/interview/{jd_id}/qa``."""

    experience_level: str | None = Field(
        default=None,
        description="Override the user's experience level for tailoring.",
    )


class InterviewQAResponse(BaseModel):
    """Response for ``POST /api/interview/{jd_id}/qa``."""

    topics: list[InterviewTopic] = Field(default_factory=list)
    qa: list[InterviewQA] = Field(default_factory=list)


# ===========================================================================
# Cover letter
# ===========================================================================


class CoverLetterRequest(BaseModel):
    """Request body for ``POST /api/cover-letter/{jd_id}``."""

    experience_level: str | None = Field(
        default=None,
        description="Override the user's experience level for tailoring.",
    )


class CoverLetter(BaseModel):
    """Generated cover letter (content + optional persisted file path)."""

    model_config = ConfigDict(from_attributes=True)

    content: str
    file_path: str | None = None


class CoverLetterResponse(BaseModel):
    """Response for ``POST /api/cover-letter/{jd_id}``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    job_entry_id: UUID | None = None
    content: str
    file_path: str | None = None
    generated_at: datetime | None = None


# ===========================================================================
# Dashboard
# ===========================================================================


class DashboardEntry(BaseModel):
    """A single job entry row for the tracking dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    jd_id: UUID
    job_title: str
    company_name: str
    status: JobStatus
    match_score: float | None = None
    notes: str | None = None
    deadline: date | None = None
    tailored_resume_id: UUID | None = None
    cover_letter_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    days_remaining: int | None = Field(
        default=None,
        description="Days until deadline (for not_applied entries with a deadline).",
    )
    is_urgent: bool = Field(
        default=False,
        description="True when the deadline is within 2 days.",
    )


class DashboardResponse(BaseModel):
    """Response for ``GET /api/dashboard``."""

    entries: list[DashboardEntry] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    """Request body for ``PATCH /api/dashboard/{entry_id}``."""

    status: JobStatus | None = None
    notes: str | None = None
    deadline: date | None = None


class DashboardSummary(BaseModel):
    """Response for ``GET /api/dashboard/summary``."""

    total_analyzed: int = 0
    total_applied: int = 0
    interviews_scheduled: int = 0
    offers_received: int = 0


# ===========================================================================
# JD comparison
# ===========================================================================


class CompareRequest(BaseModel):
    """Request body for ``POST /api/compare``."""

    jd_ids: list[UUID] = Field(..., min_length=1)


class CompareItem(BaseModel):
    """A single JD's data within a comparison."""

    jd_id: UUID
    job_title: str
    company_name: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_required: str | None = None
    match_score: float | None = None


class CompareResponse(BaseModel):
    """Response for ``POST /api/compare``."""

    items: list[CompareItem] = Field(default_factory=list)
    common_skills: list[str] = Field(default_factory=list)
    unique_skills: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map of jd_id (str) -> skills unique to that JD.",
    )
    highest_match_jd_id: UUID | None = None


# ---------------------------------------------------------------------------
# Resolve forward references (JDScrapeResponse -> TechStackResult)
# ---------------------------------------------------------------------------

JDScrapeResponse.model_rebuild()
