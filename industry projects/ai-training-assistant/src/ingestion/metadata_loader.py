"""Loader for optional per-item manual metadata (CSV or JSON).

The :class:`MetadataLoader` looks for an optional ``metadata.csv`` or
``metadata.json`` file inside a corpus folder and returns a mapping from source
file name to :class:`~src.models.ItemMeta`. The metadata file is entirely
optional: when it is absent an empty map is returned, and when it is present but
malformed a warning is logged and loading proceeds without raising (falling back
to an empty or best-effort partial map).

Both formats key entries by a source file name and carry optional ``topic_tag``,
``description``, and ``title`` fields.

Expected CSV columns (header row, extra columns ignored)::

    file_name,topic_tag,description,title

Expected JSON shapes (either is accepted)::

    {"onboarding.pdf": {"topic_tag": "hr", "title": "Onboarding"}, ...}

    [{"file_name": "onboarding.pdf", "topic_tag": "hr"}, ...]

Design references: Req 1.2 (load optional metadata and associate it with source
files; absent is fine, malformed logs a warning and proceeds).
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from src.models import ItemMeta

logger = logging.getLogger(__name__)

# Candidate metadata file names searched (in order) within the folder.
_CSV_NAME = "metadata.csv"
_JSON_NAME = "metadata.json"

# The metadata field consumed as the map key.
_FILE_NAME_FIELD = "file_name"


class MetadataLoader:
    """Locate and parse optional manual metadata for a corpus folder."""

    def load(self, folder_path: str) -> dict[str, ItemMeta]:
        """Load manual metadata from a folder, keyed by source file name.

        Searches ``folder_path`` for ``metadata.csv`` first, then
        ``metadata.json``. The first file found is parsed. A missing file yields
        an empty map. A present-but-malformed file logs a warning and yields an
        empty (or best-effort partial) map rather than raising.

        Args:
            folder_path: Path to the corpus folder that may contain a metadata
                file.

        Returns:
            A mapping from source file name to :class:`~src.models.ItemMeta`.
            Empty when no metadata file is present or it cannot be parsed.
        """
        folder = Path(folder_path)

        csv_path = folder / _CSV_NAME
        if csv_path.is_file():
            return self._load_csv(csv_path)

        json_path = folder / _JSON_NAME
        if json_path.is_file():
            return self._load_json(json_path)

        logger.debug("No metadata file found in %s", folder_path)
        return {}

    @classmethod
    def _load_csv(cls, path: Path) -> dict[str, ItemMeta]:
        """Parse a ``metadata.csv`` file into an :class:`ItemMeta` map.

        Args:
            path: Path to the CSV file.

        Returns:
            The parsed metadata map, or ``{}`` if the file cannot be read/parsed.
        """
        result: dict[str, ItemMeta] = {}
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    file_name = (row.get(_FILE_NAME_FIELD) or "").strip()
                    if not file_name:
                        continue
                    result[file_name] = cls._build_meta(row)
        except (OSError, csv.Error, UnicodeDecodeError) as error:
            logger.warning(
                "Failed to parse metadata CSV %s (%s); proceeding without it.",
                path,
                error,
            )
            return {}
        return result

    @classmethod
    def _load_json(cls, path: Path) -> dict[str, ItemMeta]:
        """Parse a ``metadata.json`` file into an :class:`ItemMeta` map.

        Accepts either an object keyed by file name or a list of objects each
        carrying a ``file_name`` field.

        Args:
            path: Path to the JSON file.

        Returns:
            The parsed metadata map, or ``{}`` if the file cannot be
            read/parsed or has an unexpected top-level shape.
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            logger.warning(
                "Failed to parse metadata JSON %s (%s); proceeding without it.",
                path,
                error,
            )
            return {}

        result: dict[str, ItemMeta] = {}
        if isinstance(raw, dict):
            for file_name, entry in raw.items():
                if isinstance(entry, dict) and str(file_name).strip():
                    result[str(file_name).strip()] = cls._build_meta(entry)
        elif isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                file_name = str(entry.get(_FILE_NAME_FIELD, "")).strip()
                if file_name:
                    result[file_name] = cls._build_meta(entry)
        else:
            logger.warning(
                "Unexpected metadata JSON shape in %s; proceeding without it.",
                path,
            )
            return {}
        return result

    @staticmethod
    def _build_meta(entry: dict[str, Any]) -> ItemMeta:
        """Build an :class:`ItemMeta` from a raw metadata record.

        Missing or empty fields become ``None``.

        Args:
            entry: A mapping of metadata fields for a single source file.

        Returns:
            The corresponding :class:`~src.models.ItemMeta`.
        """

        def clean(key: str) -> str | None:
            value = entry.get(key)
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        return ItemMeta(
            topic_tag=clean("topic_tag"),
            description=clean("description"),
            title=clean("title"),
        )
