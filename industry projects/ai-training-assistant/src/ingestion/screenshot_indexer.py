"""Screenshot indexing with optional OCR and manual metadata.

The :class:`ScreenshotIndexer` turns a screenshot image file into a
:class:`~src.models.ScreenshotItem`. It always records the file name and a
stable ``item_id`` derived from the file path, and applies ``topic_tag`` /
``description`` from any provided manual metadata. OCR is optional and feature
-flagged off by default: when disabled (or when ``pytesseract`` / the Tesseract
binary is unavailable) ``ocr_text`` is set to ``None`` and the item is still
indexed by file name and manual metadata.

Design references: Req 4.1 (record file name + path), Req 4.2 (OCR text where
enabled and available), Req 4.3 (apply manual topic/description), Req 4.4 (index
by file name + manual metadata when OCR is disabled/unavailable).
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.models import ItemMeta, ScreenshotItem

logger = logging.getLogger(__name__)


class ScreenshotIndexer:
    """Index screenshot images into :class:`~src.models.ScreenshotItem` objects.

    Attributes:
        ocr_enabled: When ``True``, OCR is attempted via ``pytesseract``; failures
            degrade gracefully to ``ocr_text=None``.
    """

    def __init__(self, ocr_enabled: bool = False) -> None:
        """Initialize the indexer.

        Args:
            ocr_enabled: Whether to attempt OCR text extraction. Defaults to
                ``False`` (Req 4.4); requires ``pytesseract`` and a system
                Tesseract binary when enabled.
        """
        self.ocr_enabled = ocr_enabled
        # Guard so an unavailable OCR backend is logged only once per instance.
        self._ocr_warning_emitted = False

    def index(self, path: str, manual_meta: ItemMeta | None) -> ScreenshotItem:
        """Index the screenshot at ``path`` into a :class:`ScreenshotItem`.

        The file name and file path are always recorded, and a stable
        ``item_id`` is derived from the resolved file path. When ``manual_meta``
        is provided, its ``topic_tag`` and ``description`` are applied. OCR text
        is attached only when OCR is enabled and available; otherwise
        ``ocr_text`` is ``None``.

        Args:
            path: Filesystem path to the screenshot image file.
            manual_meta: Optional manual metadata for this screenshot; when
                provided its topic tag and description are applied (Req 4.3).

        Returns:
            The indexed :class:`~src.models.ScreenshotItem`.
        """
        image_path = Path(path)
        item_id = self._build_item_id(image_path)

        topic_tag = manual_meta.topic_tag if manual_meta is not None else None
        description = manual_meta.description if manual_meta is not None else None

        ocr_text = self._extract_ocr_text(image_path) if self.ocr_enabled else None

        return ScreenshotItem(
            item_id=item_id,
            file_name=image_path.name,
            file_path=str(image_path),
            topic_tag=topic_tag,
            description=description,
            ocr_text=ocr_text,
        )

    @staticmethod
    def _build_item_id(image_path: Path) -> str:
        """Build a stable ``item_id`` from the screenshot's file path.

        Uses the resolved absolute path where possible so the id is stable across
        equivalent relative references; falls back to the raw path string when
        resolution is not possible (e.g. the file does not exist).

        Args:
            image_path: The screenshot's path.

        Returns:
            A stable string identifier for the screenshot.
        """
        try:
            return str(image_path.resolve())
        except OSError:  # pragma: no cover - filesystem edge case
            return str(image_path)

    def _extract_ocr_text(self, image_path: Path) -> str | None:
        """Attempt to extract OCR text, degrading gracefully on failure.

        Any missing dependency (``pytesseract`` / Pillow), missing Tesseract
        binary, or read error results in ``None`` with a single warning logged
        per indexer instance (Req 4.4).

        Args:
            image_path: The screenshot's path.

        Returns:
            The extracted text (stripped), or ``None`` when OCR is unavailable or
            yields no text.
        """
        try:
            import pytesseract  # type: ignore[import-not-found]
            from PIL import Image  # type: ignore[import-not-found]

            with Image.open(image_path) as image:
                text = pytesseract.image_to_string(image)
        except ImportError as error:
            self._warn_ocr_unavailable(f"OCR dependency missing: {error}")
            return None
        except (OSError, RuntimeError) as error:
            # pytesseract raises TesseractNotFoundError (a RuntimeError subclass)
            # when the binary is absent, and OSError on unreadable images.
            self._warn_ocr_unavailable(f"OCR failed for {image_path}: {error}")
            return None

        cleaned = text.strip()
        return cleaned or None

    def _warn_ocr_unavailable(self, message: str) -> None:
        """Log an OCR-unavailable warning at most once per indexer instance.

        Args:
            message: Context describing why OCR was unavailable.
        """
        if not self._ocr_warning_emitted:
            logger.warning("%s; indexing screenshots without OCR text.", message)
            self._ocr_warning_emitted = True
