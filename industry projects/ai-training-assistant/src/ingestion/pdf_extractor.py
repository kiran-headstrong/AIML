"""PDF text extraction using PyMuPDF (``fitz``).

The :class:`PdfExtractor` reads a PDF file and returns per-page text with
1-based page numbers, ready for chunking by the ingestion orchestrator. Pages
that contain only whitespace (or no extractable text) are omitted; when a PDF
yields no extractable text on any page the extractor returns an empty list so
the orchestrator can log "no extractable text" and produce zero chunks.

Design references: Req 2.1 (per-page text with page numbers) and Req 2.4 (empty
PDFs produce zero pages/chunks). The heavy ``fitz`` dependency is imported lazily
so importing this module never fails when PyMuPDF is not installed; a clear error
is raised only when :meth:`PdfExtractor.extract` is actually invoked.
"""

from __future__ import annotations

from pathlib import Path

from src.models import PageText


class PdfExtractor:
    """Extract per-page text from PDF files using PyMuPDF.

    The extractor is stateless; a single instance may be reused across files.
    """

    def extract(self, path: str) -> list[PageText]:
        """Extract per-page text from the PDF at ``path``.

        Iterates over the document's pages in order, extracting each page's text
        and pairing it with a 1-based page number. Pages whose extracted text is
        empty or whitespace-only are skipped. If every page is empty (or the
        document has no pages), an empty list is returned.

        Args:
            path: Filesystem path to the PDF file to read.

        Returns:
            A list of :class:`~src.models.PageText` entries in page order, one
            per page that contains extractable text. Empty when the PDF yields
            no extractable text on any page (Req 2.4).

        Raises:
            RuntimeError: If PyMuPDF (``fitz``) is not installed.
            FileNotFoundError: If ``path`` does not exist.
        """
        fitz = self._import_fitz()

        pdf_path = Path(path)
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF file not found: {path}")

        pages: list[PageText] = []
        with fitz.open(pdf_path) as document:
            for index, page in enumerate(document):
                text = page.get_text()
                if text and text.strip():
                    pages.append(PageText(page_number=index + 1, text=text))
        return pages

    @staticmethod
    def _import_fitz():
        """Import and return the PyMuPDF (``fitz``) module.

        Imported lazily so that importing this module has no hard dependency on
        PyMuPDF; the dependency is only required when extraction is performed.

        Returns:
            The imported ``fitz`` module.

        Raises:
            RuntimeError: If PyMuPDF is not installed.
        """
        try:
            import fitz  # type: ignore[import-not-found]
        except ImportError as error:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "PyMuPDF (pymupdf) is required for PDF extraction. "
                "Install it with 'pip install pymupdf'."
            ) from error
        return fitz
