"""Example unit tests for :class:`~src.ingestion.pdf_extractor.PdfExtractor`.

These tests generate small fixture PDFs at runtime with PyMuPDF into a
``tmp_path`` so no binary fixtures are committed. They assert that:

* text is extracted with correct 1-based page-number association (Req 2.1), and
* a PDF with no extractable text yields zero pages/chunks (Req 2.4).

If PyMuPDF is not installed the whole module is skipped gracefully.
"""

from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")  # skip module if PyMuPDF is unavailable

from src.ingestion.pdf_extractor import PdfExtractor


def _make_pdf(path: Path, pages: list[str]) -> Path:
    """Create a PDF at ``path`` with one text block per entry in ``pages``.

    Args:
        path: Destination file path for the generated PDF.
        pages: The text to write onto each page, in order. An empty string
            produces a blank page with no extractable text.

    Returns:
        The path to the written PDF.
    """
    document = fitz.open()
    try:
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text, fontsize=12)
        document.save(str(path))
    finally:
        document.close()
    return path


def test_extract_associates_text_with_1based_page_numbers(tmp_path: Path) -> None:
    """Each page's text is returned with its correct 1-based page number.

    Validates: Requirement 2.1
    """
    pdf_path = _make_pdf(
        tmp_path / "guide.pdf",
        ["Onboarding overview", "SOP steps section", "Policy reference notes"],
    )

    pages = PdfExtractor().extract(str(pdf_path))

    assert [p.page_number for p in pages] == [1, 2, 3]
    assert "Onboarding overview" in pages[0].text
    assert "SOP steps section" in pages[1].text
    assert "Policy reference notes" in pages[2].text


def test_extract_two_page_document_page_number_order(tmp_path: Path) -> None:
    """A two-page PDF preserves page order and content association.

    Validates: Requirement 2.1
    """
    pdf_path = _make_pdf(tmp_path / "notes.pdf", ["First page body", "Second page body"])

    pages = PdfExtractor().extract(str(pdf_path))

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2
    assert "First page body" in pages[0].text
    assert "Second page body" in pages[1].text


def test_extract_skips_whitespace_only_pages(tmp_path: Path) -> None:
    """Blank pages are omitted while text pages keep their true page numbers.

    Validates: Requirements 2.1, 2.4
    """
    pdf_path = _make_pdf(tmp_path / "mixed.pdf", ["", "Real content here", ""])

    pages = PdfExtractor().extract(str(pdf_path))

    assert len(pages) == 1
    assert pages[0].page_number == 2
    assert "Real content here" in pages[0].text


def test_extract_empty_pdf_returns_no_pages(tmp_path: Path) -> None:
    """A PDF with no extractable text on any page returns an empty list.

    Validates: Requirement 2.4
    """
    pdf_path = _make_pdf(tmp_path / "blank.pdf", ["", ""])

    pages = PdfExtractor().extract(str(pdf_path))

    assert pages == []


def test_extract_missing_file_raises(tmp_path: Path) -> None:
    """Extracting a non-existent path raises ``FileNotFoundError``."""
    with pytest.raises(FileNotFoundError):
        PdfExtractor().extract(str(tmp_path / "does_not_exist.pdf"))
