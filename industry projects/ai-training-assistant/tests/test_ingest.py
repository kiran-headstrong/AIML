"""Property-based tests for the ingestion orchestrator (``IngestionComponent``).

Covers three design correctness properties:

- Property 1 (partitioning): every walked file lands in exactly one of the
  ingested-doc / ingested-screenshot / skipped buckets, and their counts sum to
  the total number of files walked.
- Property 2 (resilience): an arbitrary subset of failing files never aborts the
  run; each failing file is skipped with a descriptive reason and every good
  file still produces its items.
- Property 4 (provenance): every produced ``TextChunk`` has a non-empty
  ``source_file`` and carries a ``page_reference`` (PDF) or ``section_reference``
  (note heading) as appropriate.

Real PDF/image parsing is avoided by injecting fake handlers via the
``IngestionComponent`` constructor; notes use trivially-parseable real files.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.ingestion.chunker import Chunker
from src.ingestion.ingest import UNSUPPORTED_EXTENSION_REASON, IngestionComponent
from src.ingestion.note_reader import NoteSegment
from src.models import DocType, ItemMeta, PageText, ScreenshotItem

# --------------------------------------------------------------------------- #
# Fakes used to avoid real PDF/image parsing and to force controlled failures.
# --------------------------------------------------------------------------- #


class FakePdfExtractor:
    """Return a fixed single page of text (or raise for configured names)."""

    def __init__(self, fail_names: frozenset[str] = frozenset()) -> None:
        self.fail_names = fail_names

    def extract(self, path: str) -> list[PageText]:
        if Path(path).name in self.fail_names:
            raise ValueError("simulated pdf parse failure")
        return [PageText(page_number=1, text="Fixed PDF page body text.")]


class FakeNoteReader:
    """Return one untagged segment (or raise for configured names)."""

    def __init__(self, fail_names: frozenset[str] = frozenset()) -> None:
        self.fail_names = fail_names

    def read(self, path: str) -> list[NoteSegment]:
        if Path(path).name in self.fail_names:
            raise ValueError("simulated note parse failure")
        return [NoteSegment(section_reference=None, text="Fixed note body text.")]


class FakeScreenshotIndexer:
    """Return a minimal ScreenshotItem (or raise for configured names)."""

    def __init__(self, fail_names: frozenset[str] = frozenset()) -> None:
        self.fail_names = fail_names

    def index(self, path: str, manual_meta: ItemMeta | None) -> ScreenshotItem:
        name = Path(path).name
        if name in self.fail_names:
            raise ValueError("simulated screenshot index failure")
        return ScreenshotItem(
            item_id=path,
            file_name=name,
            file_path=path,
            topic_tag=manual_meta.topic_tag if manual_meta else None,
            description=manual_meta.description if manual_meta else None,
            ocr_text=None,
        )


class FakeMetadataLoader:
    """Return an empty metadata map so tests need no metadata files."""

    def load(self, folder_path: str) -> dict[str, ItemMeta]:
        return {}


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #

_SUPPORTED_DOC_EXTS = [".pdf", ".txt", ".md", ".markdown"]
_SUPPORTED_SCREENSHOT_EXTS = [".png", ".jpg", ".jpeg"]
_UNSUPPORTED_EXTS = [".zip", ".docx", ".exe", ".csv2", ".xyz", ".bin"]

# File name stems: safe, non-empty, no separators or dots.
_stems = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_", min_size=1, max_size=8
)


@dataclass(frozen=True)
class PlannedFile:
    """A file to materialize in the temp corpus tree."""

    rel_path: str
    extension: str
    kind: str  # "doc" | "screenshot" | "unsupported"


def _extension_strategy() -> st.SearchStrategy[tuple[str, str]]:
    """Yield ``(extension, kind)`` pairs across all three buckets."""
    return st.one_of(
        st.sampled_from([(ext, "doc") for ext in _SUPPORTED_DOC_EXTS]),
        st.sampled_from([(ext, "screenshot") for ext in _SUPPORTED_SCREENSHOT_EXTS]),
        st.sampled_from([(ext, "unsupported") for ext in _UNSUPPORTED_EXTS]),
    )


@st.composite
def _file_trees(draw: st.DrawFn) -> list[PlannedFile]:
    """Generate a list of files with unique relative paths across subfolders."""
    count = draw(st.integers(min_value=0, max_value=8))
    used: set[str] = set()
    planned: list[PlannedFile] = []
    for _ in range(count):
        extension, kind = draw(_extension_strategy())
        stem = draw(_stems)
        # Optionally nest inside subfolders to exercise recursive walking.
        depth = draw(st.integers(min_value=0, max_value=2))
        subdirs = [draw(_stems) for _ in range(depth)]
        rel = "/".join([*subdirs, f"{stem}{extension}"])
        if rel in used:
            continue  # skip accidental collisions; keeps names unique
        used.add(rel)
        planned.append(PlannedFile(rel_path=rel, extension=extension, kind=kind))
    return planned


def _fresh_dir(tmp_path: Path) -> Path:
    """Return a unique empty subdirectory.

    Hypothesis reuses the function-scoped ``tmp_path`` across generated
    examples, so each example must isolate its files in its own subfolder to
    avoid accumulation across runs.
    """
    target = tmp_path / uuid.uuid4().hex
    target.mkdir(parents=True, exist_ok=True)
    return target


def _materialize(tmp_root: Path, planned: list[PlannedFile]) -> None:
    """Create the planned files under ``tmp_root`` with trivial contents."""
    for spec in planned:
        target = tmp_root / spec.rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("content", encoding="utf-8")


def _make_component(
    pdf_fail: frozenset[str] = frozenset(),
    note_fail: frozenset[str] = frozenset(),
    screenshot_fail: frozenset[str] = frozenset(),
) -> IngestionComponent:
    """Build an IngestionComponent wired with fakes for fast, controlled tests."""
    return IngestionComponent(
        chunker=Chunker(max_chunk_size=800, overlap=0),
        pdf_extractor=FakePdfExtractor(fail_names=pdf_fail),
        note_reader=FakeNoteReader(fail_names=note_fail),
        screenshot_indexer=FakeScreenshotIndexer(fail_names=screenshot_fail),
        metadata_loader=FakeMetadataLoader(),
    )


# --------------------------------------------------------------------------- #
# Property 1: Ingestion partitions input files
# --------------------------------------------------------------------------- #
# Feature: internal-training-content-search, Property 1: For any folder tree
# containing a mix of supported and unsupported files, every supported text file
# contributes to the ingested-document count, every screenshot to the
# ingested-screenshot count, every unsupported file appears in skipped with
# reason "unsupported_extension", and doc+screenshot+skipped == total files walked.
# Validates: Requirements 1.1, 1.3, 1.5
@given(planned=_file_trees())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_ingestion_partitions_input_files(tmp_path: Path, planned: list[PlannedFile]) -> None:
    """doc + screenshot + skipped counts sum to the total files walked."""
    corpus = _fresh_dir(tmp_path)
    _materialize(corpus, planned)
    component = _make_component()

    result = component.ingest_folder(str(corpus))

    total_files = len(planned)
    expected_docs = sum(1 for f in planned if f.kind == "doc")
    expected_screenshots = sum(1 for f in planned if f.kind == "screenshot")
    expected_unsupported = sum(1 for f in planned if f.kind == "unsupported")

    assert result.ingested_doc_count == expected_docs
    assert result.ingested_screenshot_count == expected_screenshots

    unsupported_skips = [
        s for s in result.skipped if s.reason == UNSUPPORTED_EXTENSION_REASON
    ]
    assert len(unsupported_skips) == expected_unsupported
    assert len(result.skipped) == expected_unsupported

    # Every unsupported file name is present in the skipped list.
    unsupported_names = {Path(f.rel_path).name for f in planned if f.kind == "unsupported"}
    assert {s.name for s in unsupported_skips} == unsupported_names

    # Partitioning invariant.
    assert (
        result.ingested_doc_count
        + result.ingested_screenshot_count
        + len(result.skipped)
        == total_files
    )


# --------------------------------------------------------------------------- #
# Property 2: Ingestion is resilient to per-file failures
# --------------------------------------------------------------------------- #
# Feature: internal-training-content-search, Property 2: For any set of supported
# files in which an arbitrary subset fails to parse, ingestion completes without
# raising, every failing file appears in skipped with a descriptive reason (not
# "unsupported_extension"), and every successfully-parsed file still produces items.
# Validates: Requirements 1.4
@given(
    good_stems=st.lists(_stems, min_size=0, max_size=6, unique=True),
    bad_stems=st.lists(_stems, min_size=0, max_size=6, unique=True),
    kind=st.sampled_from(["pdf", "note", "screenshot"]),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_ingestion_is_resilient_to_per_file_failures(
    tmp_path: Path,
    good_stems: list[str],
    bad_stems: list[str],
    kind: str,
) -> None:
    """A failing subset is skipped with a reason; good files still yield items."""
    # Ensure disjoint names so a stem is unambiguously good or bad.
    bad_only = [s for s in bad_stems if s not in set(good_stems)]

    ext = {"pdf": ".pdf", "note": ".txt", "screenshot": ".png"}[kind]
    good_names = {f"{s}{ext}" for s in good_stems}
    bad_names = {f"{s}{ext}" for s in bad_only}

    corpus = _fresh_dir(tmp_path)
    for name in good_names | bad_names:
        (corpus / name).write_text("content", encoding="utf-8")

    fail = frozenset(bad_names)
    component = _make_component(
        pdf_fail=fail if kind == "pdf" else frozenset(),
        note_fail=fail if kind == "note" else frozenset(),
        screenshot_fail=fail if kind == "screenshot" else frozenset(),
    )

    # Must not raise despite failures.
    result = component.ingest_folder(str(corpus))

    # Every failing file is skipped with a descriptive (non-unsupported) reason.
    skipped_names = {s.name for s in result.skipped}
    assert bad_names <= skipped_names
    for entry in result.skipped:
        if entry.name in bad_names:
            assert entry.reason != UNSUPPORTED_EXTENSION_REASON
            assert entry.reason  # non-empty descriptive reason

    # Every good file still produced its output items.
    if kind == "screenshot":
        produced = {item.file_name for item in result.screenshot_items}
        assert good_names <= produced
        assert result.ingested_screenshot_count == len(good_names)
    else:
        produced = {chunk.source_file for chunk in result.text_chunks}
        assert good_names <= produced
        assert result.ingested_doc_count == len(good_names)


# --------------------------------------------------------------------------- #
# Property 4: Every chunk carries provenance
# --------------------------------------------------------------------------- #
# Feature: internal-training-content-search, Property 4: Every TextChunk produced
# by ingestion has a non-empty source_file, and has a page_reference when it
# originates from a PDF or a section_reference when a heading/section is available
# for a note.
# Validates: Requirements 2.3, 3.2
@given(
    pdf_stems=st.lists(_stems, min_size=0, max_size=4, unique=True),
    md_stems=st.lists(_stems, min_size=0, max_size=4, unique=True),
    headings=st.lists(
        st.text(alphabet="ABCDEFGHIJ ", min_size=1, max_size=10), min_size=1, max_size=3
    ),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_every_chunk_carries_provenance(
    tmp_path: Path,
    pdf_stems: list[str],
    md_stems: list[str],
    headings: list[str],
) -> None:
    """PDF chunks carry a page_reference; heading-tagged note chunks a section."""
    md_only = [s for s in md_stems if s not in set(pdf_stems)]

    corpus = _fresh_dir(tmp_path)

    # PDF files handled by the fake extractor (fixed single page).
    for stem in pdf_stems:
        (corpus / f"{stem}.pdf").write_text("content", encoding="utf-8")

    # Real Markdown files with headings so the real NoteReader derives sections.
    md_body = "\n".join(f"# {h.strip() or 'Section'}\n\nBody text for {h}." for h in headings)
    for stem in md_only:
        (corpus / f"{stem}.md").write_text(md_body, encoding="utf-8")

    # Use a real NoteReader (headings drive section_reference) + fake PDF extractor.
    component = IngestionComponent(
        chunker=Chunker(max_chunk_size=800, overlap=0),
        pdf_extractor=FakePdfExtractor(),
        note_reader=None,  # real NoteReader
        screenshot_indexer=FakeScreenshotIndexer(),
        metadata_loader=FakeMetadataLoader(),
    )

    result = component.ingest_folder(str(corpus))

    for chunk in result.text_chunks:
        assert chunk.source_file  # non-empty provenance
        if chunk.doc_type == DocType.PDF:
            assert chunk.page_reference is not None
        elif chunk.doc_type == DocType.NOTE:
            # These markdown notes always have headings, so a section is present.
            assert chunk.section_reference is not None and chunk.section_reference != ""
