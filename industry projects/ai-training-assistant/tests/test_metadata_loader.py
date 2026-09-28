"""Example unit tests for :class:`~src.ingestion.metadata_loader.MetadataLoader`.

Covers CSV/JSON loading, the absent-file case, and malformed-file resilience
(Req 1.2).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.ingestion.metadata_loader import MetadataLoader
from src.models import ItemMeta


def test_absent_metadata_returns_empty_map(tmp_path: Path) -> None:
    """A folder with no metadata file yields an empty map (Req 1.2)."""
    assert MetadataLoader().load(str(tmp_path)) == {}


def test_loads_csv_keyed_by_file_name(tmp_path: Path) -> None:
    """A ``metadata.csv`` is parsed into an ItemMeta map (Req 1.2)."""
    (tmp_path / "metadata.csv").write_text(
        "file_name,topic_tag,description,title\n"
        "onboarding.pdf,hr,New hire deck,Onboarding\n"
        "sop.md,ops,,\n",
        encoding="utf-8",
    )

    result = MetadataLoader().load(str(tmp_path))

    assert result["onboarding.pdf"] == ItemMeta(
        topic_tag="hr", description="New hire deck", title="Onboarding"
    )
    # Empty CSV cells become None.
    assert result["sop.md"] == ItemMeta(topic_tag="ops", description=None, title=None)


def test_loads_json_object_shape(tmp_path: Path) -> None:
    """A ``metadata.json`` object keyed by file name is parsed (Req 1.2)."""
    (tmp_path / "metadata.json").write_text(
        json.dumps({"login.png": {"topic_tag": "auth", "description": "Login screen"}}),
        encoding="utf-8",
    )

    result = MetadataLoader().load(str(tmp_path))

    assert result["login.png"] == ItemMeta(
        topic_tag="auth", description="Login screen", title=None
    )


def test_loads_json_list_shape(tmp_path: Path) -> None:
    """A ``metadata.json`` list of records is parsed by ``file_name`` (Req 1.2)."""
    (tmp_path / "metadata.json").write_text(
        json.dumps([{"file_name": "policy.pdf", "topic_tag": "legal"}]),
        encoding="utf-8",
    )

    result = MetadataLoader().load(str(tmp_path))

    assert result["policy.pdf"].topic_tag == "legal"


def test_malformed_json_logs_and_returns_empty(tmp_path: Path) -> None:
    """A malformed metadata file never raises; it returns an empty map (Req 1.2)."""
    (tmp_path / "metadata.json").write_text("{ not valid json", encoding="utf-8")

    assert MetadataLoader().load(str(tmp_path)) == {}
