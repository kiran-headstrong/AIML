"""Ingestion orchestrator that assembles a searchable corpus from a folder.

The :class:`IngestionComponent` walks a corpus folder (and its subfolders),
dispatches each file to the appropriate handler by extension, enriches the
results with optional manual metadata, chunks extracted text into bounded
:class:`~src.models.TextChunk` objects, indexes screenshots into
:class:`~src.models.ScreenshotItem` objects, and reports ingested/skipped
counts as an :class:`IngestionResult`.

Resilience is central to the design: a single unreadable or malformed file
never aborts the run. Each per-file parse is wrapped in ``try/except`` and a
descriptive :class:`~src.models.SkippedEntry` is recorded instead (Req 1.4).
Unsupported extensions are skipped with the fixed reason
``"unsupported_extension"`` (Req 1.3). The optional ``metadata.csv`` /
``metadata.json`` inputs are metadata sources, not corpus content, and are
neither ingested nor skipped.

Design references: Req 1.1 (walk folder + subfolders), Req 1.2 (load and apply
optional metadata), Req 1.3 (skip unsupported extensions + log), Req 1.4
(per-file resilience + log), Req 1.5 (report counts), Req 2.3 / 3.2 (chunk
provenance), Req 2.4 (PDFs with no extractable text produce zero chunks and are
not an error).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import config
from src.ingestion.chunker import Chunker
from src.ingestion.metadata_loader import MetadataLoader
from src.ingestion.note_reader import NoteReader
from src.ingestion.pdf_extractor import PdfExtractor
from src.ingestion.screenshot_indexer import ScreenshotIndexer
from src.models import (
    DocType,
    ItemMeta,
    ScreenshotItem,
    SkippedEntry,
    TextChunk,
    make_chunk_id,
)

logger = logging.getLogger(__name__)

# The fixed skip reason for files with an unsupported extension (Req 1.3).
UNSUPPORTED_EXTENSION_REASON = "unsupported_extension"

# Supported extensions grouped by handler (all compared lower-case).
_PDF_EXTENSIONS = frozenset({".pdf"})
_NOTE_EXTENSIONS = frozenset({".txt", ".md", ".markdown"})
_SCREENSHOT_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})

# Optional metadata inputs that are excluded from ingestion entirely (Req 1.2).
_METADATA_FILE_NAMES = frozenset({"metadata.csv", "metadata.json"})


@dataclass
class IngestionResult:
    """The outcome of ingesting a corpus folder.

    Attributes:
        text_chunks: All :class:`~src.models.TextChunk` objects produced from
            PDFs and notes, in walk order.
        screenshot_items: All indexed :class:`~src.models.ScreenshotItem`
            objects, in walk order.
        ingested_doc_count: Number of supported text files (PDF/TXT/MD) that
            were successfully processed, including files that yielded zero
            chunks because they had no extractable text (Req 1.5, 2.4).
        ingested_screenshot_count: Number of screenshots successfully indexed
            (Req 1.5).
        skipped: Files skipped for an unsupported extension or a parse failure
            (Req 1.3, 1.4).
    """

    text_chunks: list[TextChunk]
    screenshot_items: list[ScreenshotItem]
    ingested_doc_count: int
    ingested_screenshot_count: int
    skipped: list[SkippedEntry]


class IngestionComponent:
    """Orchestrate extraction, chunking, and screenshot indexing for a folder.

    Dependencies are injected to keep the orchestrator testable: tests can pass
    fake extractors/readers/indexers to force failures or avoid real PDF/image
    parsing. When omitted, real instances are constructed from ``config`` values.

    Attributes:
        chunker: Splits extracted text into size-bounded chunks.
        pdf_extractor: Extracts per-page text from PDFs.
        note_reader: Reads TXT/Markdown notes into section segments.
        screenshot_indexer: Indexes screenshot images into items.
        metadata_loader: Loads optional manual metadata for the folder.
    """

    def __init__(
        self,
        chunker: Chunker | None = None,
        pdf_extractor: PdfExtractor | None = None,
        note_reader: NoteReader | None = None,
        screenshot_indexer: ScreenshotIndexer | None = None,
        metadata_loader: MetadataLoader | None = None,
    ) -> None:
        """Initialize the orchestrator with real or injected dependencies.

        Args:
            chunker: Optional :class:`~src.ingestion.chunker.Chunker`; defaults
                to one built from ``config.MAX_CHUNK_SIZE`` and
                ``config.CHUNK_OVERLAP``.
            pdf_extractor: Optional :class:`~src.ingestion.pdf_extractor.PdfExtractor`.
            note_reader: Optional :class:`~src.ingestion.note_reader.NoteReader`.
            screenshot_indexer: Optional
                :class:`~src.ingestion.screenshot_indexer.ScreenshotIndexer`;
                defaults to one built from ``config.OCR_ENABLED``.
            metadata_loader: Optional
                :class:`~src.ingestion.metadata_loader.MetadataLoader`.
        """
        self.chunker = chunker or Chunker(
            max_chunk_size=config.MAX_CHUNK_SIZE, overlap=config.CHUNK_OVERLAP
        )
        self.pdf_extractor = pdf_extractor or PdfExtractor()
        self.note_reader = note_reader or NoteReader()
        self.screenshot_indexer = screenshot_indexer or ScreenshotIndexer(
            ocr_enabled=config.OCR_ENABLED
        )
        self.metadata_loader = metadata_loader or MetadataLoader()

        self._configure_logging()

    def ingest_folder(self, folder_path: str) -> IngestionResult:
        """Walk ``folder_path`` and its subfolders and ingest supported files.

        Files are dispatched by extension: PDFs and notes become
        :class:`~src.models.TextChunk` objects, screenshots become
        :class:`~src.models.ScreenshotItem` objects, and everything else is
        skipped with reason ``"unsupported_extension"``. Optional
        ``metadata.csv`` / ``metadata.json`` inputs are excluded from processing
        and used only to enrich items. Each per-file parse is isolated so a
        single failure records a descriptive :class:`~src.models.SkippedEntry`
        and never aborts the walk (Req 1.4).

        For a folder tree containing only supported and unsupported files (no
        metadata inputs), ``ingested_doc_count + ingested_screenshot_count +
        len(skipped)`` equals the total number of files walked (Property 1).

        Args:
            folder_path: Path to the corpus folder to ingest.

        Returns:
            An :class:`IngestionResult` with the produced chunks, screenshot
            items, ingested/skipped counts, and skipped entries.
        """
        metadata = self._load_metadata(folder_path)

        text_chunks: list[TextChunk] = []
        screenshot_items: list[ScreenshotItem] = []
        skipped: list[SkippedEntry] = []
        ingested_doc_count = 0
        ingested_screenshot_count = 0

        for file_path in self._walk_files(folder_path):
            name = file_path.name
            if name.lower() in _METADATA_FILE_NAMES:
                # Metadata inputs are enrichment sources, not corpus content.
                continue

            extension = file_path.suffix.lower()
            item_meta = metadata.get(name)

            if extension in _PDF_EXTENSIONS:
                if self._ingest_pdf(file_path, item_meta, text_chunks, skipped):
                    ingested_doc_count += 1
            elif extension in _NOTE_EXTENSIONS:
                if self._ingest_note(file_path, item_meta, text_chunks, skipped):
                    ingested_doc_count += 1
            elif extension in _SCREENSHOT_EXTENSIONS:
                if self._ingest_screenshot(file_path, item_meta, screenshot_items, skipped):
                    ingested_screenshot_count += 1
            else:
                logger.info("Skipping unsupported file: %s", name)
                skipped.append(SkippedEntry(name=name, reason=UNSUPPORTED_EXTENSION_REASON))

        return IngestionResult(
            text_chunks=text_chunks,
            screenshot_items=screenshot_items,
            ingested_doc_count=ingested_doc_count,
            ingested_screenshot_count=ingested_screenshot_count,
            skipped=skipped,
        )

    # ------------------------------------------------------------------ #
    # Per-file handlers
    # ------------------------------------------------------------------ #
    def _ingest_pdf(
        self,
        file_path: Path,
        item_meta: ItemMeta | None,
        text_chunks: list[TextChunk],
        skipped: list[SkippedEntry],
    ) -> bool:
        """Extract, chunk, and enrich a single PDF file.

        A PDF with no extractable text is logged and produces zero chunks; this
        is a successful ingestion, not a skip (Req 2.4). Any parse error records
        a descriptive :class:`~src.models.SkippedEntry` and returns ``False``.

        Args:
            file_path: Path to the PDF file.
            item_meta: Optional manual metadata for this file.
            text_chunks: Accumulator extended in place with produced chunks.
            skipped: Accumulator extended in place on failure.

        Returns:
            ``True`` when the file was successfully processed (counts as an
            ingested doc), ``False`` when it was skipped due to an error.
        """
        name = file_path.name
        try:
            pages = self.pdf_extractor.extract(str(file_path))
        except Exception as error:  # noqa: BLE001 - resilience is required (Req 1.4)
            logger.warning("Failed to parse PDF %s: %s", name, error)
            skipped.append(SkippedEntry(name=name, reason=str(error)))
            return False

        if not pages:
            logger.info("PDF has no extractable text: %s", name)
            return True

        ordinal = 0
        for page in pages:
            for chunk_text in self.chunker.chunk(page.text):
                text_chunks.append(
                    TextChunk(
                        chunk_id=make_chunk_id(name, page.page_number, ordinal),
                        text=chunk_text,
                        source_file=name,
                        doc_type=DocType.PDF,
                        page_reference=page.page_number,
                        section_reference=None,
                        topic_tag=item_meta.topic_tag if item_meta else None,
                        title=item_meta.title if item_meta else None,
                    )
                )
                ordinal += 1
        return True

    def _ingest_note(
        self,
        file_path: Path,
        item_meta: ItemMeta | None,
        text_chunks: list[TextChunk],
        skipped: list[SkippedEntry],
    ) -> bool:
        """Read, chunk, and enrich a single TXT/Markdown note.

        Each note segment's text is chunked, and each resulting chunk inherits
        the segment's ``section_reference``. A note with no content produces
        zero chunks and still counts as ingested. Any parse error records a
        descriptive :class:`~src.models.SkippedEntry` and returns ``False``.

        Args:
            file_path: Path to the note file.
            item_meta: Optional manual metadata for this file.
            text_chunks: Accumulator extended in place with produced chunks.
            skipped: Accumulator extended in place on failure.

        Returns:
            ``True`` when the file was successfully processed, ``False`` when it
            was skipped due to an error.
        """
        name = file_path.name
        try:
            segments = self.note_reader.read(str(file_path))
        except Exception as error:  # noqa: BLE001 - resilience is required (Req 1.4)
            logger.warning("Failed to parse note %s: %s", name, error)
            skipped.append(SkippedEntry(name=name, reason=str(error)))
            return False

        ordinal = 0
        for position, segment in enumerate(segments):
            # Use the heading where available; otherwise a stable positional key.
            page_or_section = (
                segment.section_reference
                if segment.section_reference
                else f"segment-{position}"
            )
            for chunk_text in self.chunker.chunk(segment.text):
                text_chunks.append(
                    TextChunk(
                        chunk_id=make_chunk_id(name, page_or_section, ordinal),
                        text=chunk_text,
                        source_file=name,
                        doc_type=DocType.NOTE,
                        page_reference=None,
                        section_reference=segment.section_reference,
                        topic_tag=item_meta.topic_tag if item_meta else None,
                        title=item_meta.title if item_meta else None,
                    )
                )
                ordinal += 1
        return True

    def _ingest_screenshot(
        self,
        file_path: Path,
        item_meta: ItemMeta | None,
        screenshot_items: list[ScreenshotItem],
        skipped: list[SkippedEntry],
    ) -> bool:
        """Index a single screenshot image, applying manual metadata.

        Any indexing error records a descriptive
        :class:`~src.models.SkippedEntry` and returns ``False``.

        Args:
            file_path: Path to the screenshot image.
            item_meta: Optional manual metadata for this file.
            screenshot_items: Accumulator extended in place with the indexed item.
            skipped: Accumulator extended in place on failure.

        Returns:
            ``True`` when the screenshot was indexed, ``False`` when it was
            skipped due to an error.
        """
        name = file_path.name
        try:
            item = self.screenshot_indexer.index(str(file_path), item_meta)
        except Exception as error:  # noqa: BLE001 - resilience is required (Req 1.4)
            logger.warning("Failed to index screenshot %s: %s", name, error)
            skipped.append(SkippedEntry(name=name, reason=str(error)))
            return False

        screenshot_items.append(item)
        return True

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _load_metadata(self, folder_path: str) -> dict[str, ItemMeta]:
        """Load optional manual metadata, degrading to an empty map on failure.

        Args:
            folder_path: Path to the corpus folder.

        Returns:
            A map from source file name to :class:`~src.models.ItemMeta`.
        """
        try:
            return self.metadata_loader.load(folder_path)
        except Exception as error:  # noqa: BLE001 - metadata is optional (Req 1.2)
            logger.warning("Failed to load metadata for %s: %s", folder_path, error)
            return {}

    @staticmethod
    def _walk_files(folder_path: str) -> list[Path]:
        """Return every file under ``folder_path`` and its subfolders in order.

        Args:
            folder_path: Path to the corpus folder to walk.

        Returns:
            A sorted list of file paths (directories excluded). Empty when the
            folder does not exist.
        """
        root = Path(folder_path)
        if not root.is_dir():
            logger.warning("Ingestion folder does not exist: %s", folder_path)
            return []
        return sorted(path for path in root.rglob("*") if path.is_file())

    @staticmethod
    def _configure_logging() -> None:
        """Attach a file handler for the ingestion log, best-effort.

        Ensures the log directory exists and adds a
        :class:`logging.FileHandler` writing to ``config.INGESTION_LOG_PATH``
        to this module's logger once. Any failure during setup is swallowed so
        logging never crashes ingestion (Req 1.3, 1.4, 2.4).
        """
        try:
            log_path = Path(config.INGESTION_LOG_PATH)
            already_attached = any(
                isinstance(handler, logging.FileHandler)
                and getattr(handler, "_ingestion_log", False)
                for handler in logger.handlers
            )
            if already_attached:
                return

            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            # Tag the handler so we don't attach duplicates across instances.
            handler._ingestion_log = True  # type: ignore[attr-defined]
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        except OSError as error:  # pragma: no cover - logging setup edge case
            logger.warning("Could not configure ingestion log file: %s", error)
