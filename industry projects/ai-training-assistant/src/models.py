"""Core data models for the Internal Training Content Search Assistant.

Defines the shared enums and dataclasses used across the ingestion, index, and
retrieval layers, matching the design's *Data Models* section exactly. All enums
subclass ``(str, Enum)`` so their values serialize cleanly to metadata stores and
JSON exports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class DocType(str, Enum):
    """The type of an indexed source item."""

    PDF = "pdf"
    NOTE = "note"  # txt / md
    SCREENSHOT = "screenshot"


class QueryCategory(str, Enum):
    """The fixed set of query classification labels (Req 8.1)."""

    ONBOARDING = "onboarding"
    SOP_LOOKUP = "sop_lookup"
    SCREENSHOT_LOOKUP = "screenshot_lookup"
    POLICY_REFERENCE = "policy_reference"
    TROUBLESHOOTING = "troubleshooting_support"


class Confidence(str, Enum):
    """Qualitative confidence indicator for a set of results (Req 10.3, 11.1)."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# --------------------------------------------------------------------------- #
# Chunk id helper
# --------------------------------------------------------------------------- #
def make_chunk_id(source_file: str, page_or_section: object, ordinal: int) -> str:
    """Construct a stable chunk id of the form ``{source_file}::{page_or_section}::{ordinal}``.

    ``page_or_section`` may be a page number (int), a section reference (str), or
    ``None`` when neither is available; it is stringified into the id. This mirrors
    the ``TextChunk.chunk_id`` convention documented in the design.
    """
    return f"{source_file}::{page_or_section}::{ordinal}"


# --------------------------------------------------------------------------- #
# Dataclasses (design: Data Models)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PageText:
    """A single PDF page's extracted text with its 1-based page number."""

    page_number: int  # 1-based (Req 2.1)
    text: str


@dataclass(frozen=True)
class TextChunk:
    """A bounded segment of extracted text with source/section provenance."""

    chunk_id: str  # stable id: f"{source_file}::{page_or_section}::{ordinal}"
    text: str
    source_file: str  # Req 2.3, 3.2, 5.1
    doc_type: DocType  # Req 5.1
    page_reference: Optional[int]  # Req 2.1, 2.3 (PDF page)
    section_reference: Optional[str]  # Req 3.2 (heading/section for notes)
    topic_tag: Optional[str]  # Req 5.1 (from metadata if available)
    title: Optional[str]  # display title (Req 10.1)


@dataclass(frozen=True)
class ScreenshotItem:
    """An indexed screenshot image with identity and optional metadata/OCR text."""

    item_id: str  # stable id from file path
    file_name: str  # Req 4.1, 5.1
    file_path: str  # Req 4.1
    topic_tag: Optional[str]  # Req 4.3, 5.1
    description: Optional[str]  # Req 4.3
    ocr_text: Optional[str]  # Req 4.2 (None when OCR disabled/unavailable)
    doc_type: DocType = DocType.SCREENSHOT


@dataclass
class TextMatch:
    """A retrieved text chunk with its normalized similarity score."""

    chunk: TextChunk
    score: float  # normalized [0,1]


@dataclass
class ScreenshotMatch:
    """A retrieved screenshot item with its normalized similarity score."""

    item: ScreenshotItem
    score: float


@dataclass(frozen=True)
class SourceRef:
    """A source reference attached to a drafted answer."""

    source_file: str
    reference: Optional[str]  # page or section
    excerpt: str


@dataclass(frozen=True)
class SkippedEntry:
    """A file that was skipped during ingestion, with a reason."""

    name: str
    reason: str  # "unsupported_extension" | descriptive parse error


@dataclass(frozen=True)
class ItemMeta:
    """Optional manual metadata loaded for a source item."""

    topic_tag: Optional[str]
    description: Optional[str]
    title: Optional[str]


# --------------------------------------------------------------------------- #
# Retrieval layer models (design: Retrieval_Component)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetrievalConfig:
    """Configuration knobs for the retrieval layer."""

    top_k: int  # Req 7.2
    min_similarity: float  # Req 7.5 no-match threshold
    medium_confidence_threshold: float  # Req 11.1
    high_confidence_threshold: float  # Req 10.3


@dataclass
class RetrievalOutcome:
    """The full result of a single retrieval pass (Req 7.1-7.5, 8.1)."""

    query: str
    category: QueryCategory  # Req 8.1
    text_matches: list[TextMatch]  # ranked, above threshold
    screenshot_matches: list[ScreenshotMatch]
    confidence: Confidence  # High | Medium | Low (Req 10.3, 11.1)
    no_match: bool  # Req 7.5
