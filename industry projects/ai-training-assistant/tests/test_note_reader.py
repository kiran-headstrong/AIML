"""Example unit tests for :class:`~src.ingestion.note_reader.NoteReader`.

Covers TXT and Markdown reading and section-reference derivation (Req 3.1, 3.2).
"""

from __future__ import annotations

from pathlib import Path

from src.ingestion.note_reader import NoteReader, NoteSegment


def test_plain_txt_single_untagged_segment(tmp_path: Path) -> None:
    """A TXT file yields one segment with no section reference (Req 3.1)."""
    path = tmp_path / "sop.txt"
    path.write_text("Step one.\nStep two.", encoding="utf-8")

    segments = NoteReader().read(str(path))

    assert segments == [NoteSegment(section_reference=None, text="Step one.\nStep two.")]


def test_markdown_headings_become_section_references(tmp_path: Path) -> None:
    """Markdown headings drive the section reference for their content (Req 3.2)."""
    path = tmp_path / "guide.md"
    path.write_text(
        "# Onboarding\nWelcome text.\n\n## Access\nRequest access here.",
        encoding="utf-8",
    )

    segments = NoteReader().read(str(path))

    refs = [s.section_reference for s in segments]
    assert refs == ["Onboarding", "Access"]
    assert "Welcome text." in segments[0].text
    assert "Request access here." in segments[1].text


def test_markdown_preamble_before_first_heading_is_untagged(tmp_path: Path) -> None:
    """Content before the first heading is tagged with ``None``."""
    path = tmp_path / "notes.md"
    path.write_text("Intro line.\n\n# Section\nBody.", encoding="utf-8")

    segments = NoteReader().read(str(path))

    assert segments[0].section_reference is None
    assert "Intro line." in segments[0].text
    assert segments[1].section_reference == "Section"


def test_empty_file_yields_no_segments(tmp_path: Path) -> None:
    """An empty or whitespace-only note produces no segments."""
    path = tmp_path / "blank.md"
    path.write_text("   \n\n\t", encoding="utf-8")

    assert NoteReader().read(str(path)) == []
