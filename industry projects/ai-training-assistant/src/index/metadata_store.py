"""Metadata_Store: SQLite-backed persistence for chunks and screenshots.

Records per-item metadata (topic tag, document type, source file, page/section
reference) for every ``TextChunk`` and ``ScreenshotItem`` and persists it to a
local SQLite file plus a human-readable JSON export (Req 5.1, 5.2). A previously
built store can be reloaded without re-ingestion (Req 5.3).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.models import DocType, ScreenshotItem, TextChunk

# Schema exactly as defined in the design's *Metadata Store Schema* section.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    source_file TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    page_reference INTEGER,
    section_reference TEXT,
    topic_tag TEXT,
    title TEXT
);
CREATE TABLE IF NOT EXISTS screenshots (
    item_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    topic_tag TEXT,
    description TEXT,
    ocr_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_file);
"""


class MetadataStoreError(RuntimeError):
    """Base error for metadata-store problems."""


class MetadataStoreNotFoundError(MetadataStoreError):
    """Raised when a persisted metadata database is missing."""


def _row_to_chunk(row: sqlite3.Row) -> TextChunk:
    """Reconstruct a ``TextChunk`` from a database row.

    Converts the stored ``doc_type`` string back into a ``DocType`` enum and
    preserves ``None`` for optional fields.

    Args:
        row: A ``sqlite3.Row`` from the ``chunks`` table.

    Returns:
        The reconstructed ``TextChunk``.
    """
    return TextChunk(
        chunk_id=row["chunk_id"],
        text=row["text"],
        source_file=row["source_file"],
        doc_type=DocType(row["doc_type"]),
        page_reference=row["page_reference"],
        section_reference=row["section_reference"],
        topic_tag=row["topic_tag"],
        title=row["title"],
    )


def _row_to_screenshot(row: sqlite3.Row) -> ScreenshotItem:
    """Reconstruct a ``ScreenshotItem`` from a database row.

    Args:
        row: A ``sqlite3.Row`` from the ``screenshots`` table.

    Returns:
        The reconstructed ``ScreenshotItem`` (always ``DocType.SCREENSHOT``).
    """
    return ScreenshotItem(
        item_id=row["item_id"],
        file_name=row["file_name"],
        file_path=row["file_path"],
        topic_tag=row["topic_tag"],
        description=row["description"],
        ocr_text=row["ocr_text"],
    )


class MetadataStore:
    """In-memory metadata collection with SQLite + JSON persistence.

    Chunks and screenshots are held in insertion-keyed dicts (keyed by their id)
    so lookups by id are O(1) and later saves for the same id overwrite earlier
    ones, mirroring the SQLite primary-key semantics.
    """

    def __init__(self) -> None:
        """Create an empty metadata store."""
        self._chunks: dict[str, TextChunk] = {}
        self._screenshots: dict[str, ScreenshotItem] = {}

    def save_chunks(self, chunks: list[TextChunk]) -> None:
        """Record text chunks in the store (Req 5.1).

        Args:
            chunks: The chunks to record; later ids overwrite earlier ones.
        """
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk

    def save_screenshots(self, items: list[ScreenshotItem]) -> None:
        """Record screenshot items in the store (Req 5.1).

        Args:
            items: The screenshots to record; later ids overwrite earlier ones.
        """
        for item in items:
            self._screenshots[item.item_id] = item

    def get_chunk(self, chunk_id: str) -> TextChunk | None:
        """Return the chunk with the given id, or ``None`` if absent."""
        return self._chunks.get(chunk_id)

    def get_screenshot(self, item_id: str) -> ScreenshotItem | None:
        """Return the screenshot with the given id, or ``None`` if absent."""
        return self._screenshots.get(item_id)

    def persist(self, db_path: str, json_path: str) -> None:
        """Persist all recorded metadata to SQLite and a JSON export (Req 5.2).

        The SQLite database is rewritten from scratch so that a persist call
        reflects exactly the current in-memory contents. A human-readable JSON
        export is written alongside for inspection and portability.

        Args:
            db_path: Path to the SQLite database file to write.
            json_path: Path to the JSON export file to write.
        """
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(db_file)
        try:
            connection.executescript(_SCHEMA)
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM screenshots")
            connection.executemany(
                "INSERT INTO chunks (chunk_id, text, source_file, doc_type, "
                "page_reference, section_reference, topic_tag, title) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        chunk.chunk_id,
                        chunk.text,
                        chunk.source_file,
                        chunk.doc_type.value,
                        chunk.page_reference,
                        chunk.section_reference,
                        chunk.topic_tag,
                        chunk.title,
                    )
                    for chunk in self._chunks.values()
                ],
            )
            connection.executemany(
                "INSERT INTO screenshots (item_id, file_name, file_path, "
                "topic_tag, description, ocr_text) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        item.item_id,
                        item.file_name,
                        item.file_path,
                        item.topic_tag,
                        item.description,
                        item.ocr_text,
                    )
                    for item in self._screenshots.values()
                ],
            )
            connection.commit()
        finally:
            connection.close()

        self._write_json_export(Path(json_path))

    def _write_json_export(self, json_file: Path) -> None:
        """Write a human-readable JSON export of the current metadata.

        Args:
            json_file: Path to the JSON file to write.
        """
        json_file.parent.mkdir(parents=True, exist_ok=True)
        export = {
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "source_file": chunk.source_file,
                    "doc_type": chunk.doc_type.value,
                    "page_reference": chunk.page_reference,
                    "section_reference": chunk.section_reference,
                    "topic_tag": chunk.topic_tag,
                    "title": chunk.title,
                }
                for chunk in self._chunks.values()
            ],
            "screenshots": [
                {
                    "item_id": item.item_id,
                    "file_name": item.file_name,
                    "file_path": item.file_path,
                    "topic_tag": item.topic_tag,
                    "description": item.description,
                    "ocr_text": item.ocr_text,
                }
                for item in self._screenshots.values()
            ],
        }
        json_file.write_text(
            json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, db_path: str) -> "MetadataStore":
        """Load a previously persisted store from a SQLite file (Req 5.3).

        Args:
            db_path: Path to the SQLite database file to read.

        Returns:
            A ``MetadataStore`` populated with the persisted chunks and
            screenshots.

        Raises:
            MetadataStoreNotFoundError: If ``db_path`` does not exist.
        """
        db_file = Path(db_path)
        if not db_file.exists():
            raise MetadataStoreNotFoundError(
                f"No metadata store found at '{db_file}'. Build it first by "
                "running 'python scripts/build.py'."
            )

        store = cls()
        connection = sqlite3.connect(db_file)
        connection.row_factory = sqlite3.Row
        try:
            for row in connection.execute("SELECT * FROM chunks"):
                chunk = _row_to_chunk(row)
                store._chunks[chunk.chunk_id] = chunk
            for row in connection.execute("SELECT * FROM screenshots"):
                item = _row_to_screenshot(row)
                store._screenshots[item.item_id] = item
        finally:
            connection.close()

        return store
