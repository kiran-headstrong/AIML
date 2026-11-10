"""
SQLAlchemy 2.x ORM models for the Job Application Assistant.

Models map to the PostgreSQL schema described in the design document's
"Table Definitions" section. All primary keys are UUIDs (generated with
``uuid.uuid4``), JSON columns use PostgreSQL ``JSONB``, timestamps use
server-side defaults, and foreign keys declare ``ON DELETE CASCADE`` where
the design requires it.

The declarative base is exposed as ``Base`` so that it can be imported by the
database/session module and Alembic migrations.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


# ---------------------------------------------------------------------------
# Job entry status
# ---------------------------------------------------------------------------

#: Valid values for :attr:`JobEntry.status`.
JOB_ENTRY_STATUSES: tuple[str, ...] = (
    "not_applied",
    "applied",
    "interview_scheduled",
    "interview_completed",
    "offered",
    "rejected",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(Base):
    """Application user. Maps to ``users``."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    base_resume: Mapped[BaseResume | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    job_entries: Mapped[list[JobEntry]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class BaseResume(Base):
    """A user's single uploaded base resume. Maps to ``base_resumes``."""

    __tablename__ = "base_resumes"
    __table_args__ = (
        # One base resume per user.
        UniqueConstraint("user_id", name="uq_base_resumes_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    parsed_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="base_resume")


class ScrapedJD(Base):
    """A scraped job description. Maps to ``scraped_jds``."""

    __tablename__ = "scraped_jds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_title: Mapped[str] = mapped_column(String(500), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    experience_required: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    description_body: Mapped[str] = mapped_column(Text, nullable=False)
    required_skills: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    preferred_skills: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    raw_html: Mapped[str] = mapped_column(Text, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    tech_stack_items: Mapped[list[TechStackItem]] = relationship(
        back_populates="scraped_jd",
        cascade="all, delete-orphan",
    )
    job_entries: Mapped[list[JobEntry]] = relationship(back_populates="scraped_jd")


class TechStackItem(Base):
    """A single technology extracted from a JD. Maps to ``tech_stack_items``."""

    __tablename__ = "tech_stack_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jd_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scraped_jds.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)

    # Relationships
    scraped_jd: Mapped[ScrapedJD] = relationship(back_populates="tech_stack_items")


class JobEntry(Base):
    """A tracked job application for a user. Maps to ``job_entries``."""

    __tablename__ = "job_entries"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'not_applied', 'applied', 'interview_scheduled', "
            "'interview_completed', 'offered', 'rejected')",
            name="ck_job_entries_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    jd_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scraped_jds.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_applied", server_default="not_applied"
    )
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    tailored_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tailored_resumes.id"),
        nullable=True,
    )
    cover_letter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cover_letters.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="job_entries")
    scraped_jd: Mapped[ScrapedJD] = relationship(back_populates="job_entries")

    match_result: Mapped[MatchResult | None] = relationship(
        back_populates="job_entry",
        uselist=False,
        cascade="all, delete-orphan",
    )
    interview_topics: Mapped[list[InterviewTopic]] = relationship(
        back_populates="job_entry",
        cascade="all, delete-orphan",
    )
    interview_qas: Mapped[list[InterviewQA]] = relationship(
        back_populates="job_entry",
        cascade="all, delete-orphan",
    )

    # Document associations (FKs live on this table, pointing at the
    # tailored_resume / cover_letter rows).
    tailored_resume: Mapped[TailoredResume | None] = relationship(
        foreign_keys=[tailored_resume_id],
    )
    cover_letter: Mapped[CoverLetter | None] = relationship(
        foreign_keys=[cover_letter_id],
    )


class MatchResult(Base):
    """Resume-to-JD match breakdown. Maps to ``match_results``."""

    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint("job_entry_id", name="uq_match_results_job_entry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    skills_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    experience_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    education_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    matched_skills: Mapped[list] = mapped_column(JSONB, nullable=False)
    missing_skills: Mapped[list] = mapped_column(JSONB, nullable=False)
    matched_experience_kw: Mapped[list] = mapped_column(JSONB, nullable=False)
    missing_experience_kw: Mapped[list] = mapped_column(JSONB, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    job_entry: Mapped[JobEntry] = relationship(
        back_populates="match_result",
        foreign_keys=[job_entry_id],
    )


class TailoredResume(Base):
    """A generated, tailored resume document. Maps to ``tailored_resumes``."""

    __tablename__ = "tailored_resumes"
    __table_args__ = (
        UniqueConstraint("job_entry_id", name="uq_tailored_resumes_job_entry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    applied_suggestions: Mapped[list] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationship back to the owning job entry (the FK for the association
    # lives on job_entries.tailored_resume_id).
    job_entry: Mapped[JobEntry] = relationship(
        foreign_keys=[job_entry_id],
    )


class CoverLetter(Base):
    """A generated cover letter. Maps to ``cover_letters``."""

    __tablename__ = "cover_letters"
    __table_args__ = (
        UniqueConstraint("job_entry_id", name="uq_cover_letters_job_entry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationship back to the owning job entry (the FK for the association
    # lives on job_entries.cover_letter_id).
    job_entry: Mapped[JobEntry] = relationship(
        foreign_keys=[job_entry_id],
    )


class InterviewTopic(Base):
    """A ranked interview topic. Maps to ``interview_topics``."""

    __tablename__ = "interview_topics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    relevance_rank: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    job_entry: Mapped[JobEntry] = relationship(back_populates="interview_topics")
    qas: Mapped[list[InterviewQA]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )


class InterviewQA(Base):
    """A single interview question and answer. Maps to ``interview_qas``."""

    __tablename__ = "interview_qas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[list] = mapped_column(JSONB, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    is_scenario_based: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Relationships
    job_entry: Mapped[JobEntry] = relationship(back_populates="interview_qas")
    topic: Mapped[InterviewTopic] = relationship(back_populates="qas")
