"""Property-based tests for the :class:`ScreenshotIndexer`.

Validates **Correctness Property 5 (Screenshot indexing preserves identity and
applies metadata)**:

    For any screenshot image, the produced Screenshot_Item records its
    ``file_name`` and ``file_path``; when manual metadata is provided the item
    carries that ``topic_tag`` and ``description``; and when OCR is disabled the
    item's ``ocr_text`` is ``None`` while the item is still indexed by file name
    and any manual metadata.

Validates: Requirements 1.2, 4.1, 4.3, 4.4
Feature: internal-training-content-search, Property 5
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from hypothesis import given, settings
from hypothesis import strategies as st

from src.ingestion.screenshot_indexer import ScreenshotIndexer
from src.models import ItemMeta

# Path segments constrained to safe, non-empty, non-separator file/dir names.
_path_segment = st.text(
    alphabet=st.characters(
        min_codepoint=0x21,
        max_codepoint=0x7E,
        blacklist_characters="/\\:*?\"<>|.",
    ),
    min_size=1,
    max_size=20,
)

# An image file name: a base segment plus a common screenshot extension.
_file_name = st.builds(
    lambda base, ext: f"{base}{ext}",
    _path_segment,
    st.sampled_from([".png", ".jpg", ".jpeg", ".PNG", ".JPG"]),
)

# An arbitrary POSIX-style file path with 0-3 parent directories.
_file_path = st.builds(
    lambda parents, name: str(PurePosixPath(*parents, name)) if parents else name,
    st.lists(_path_segment, min_size=0, max_size=3),
    _file_name,
)

# Optional metadata text fields (present or None).
_optional_text = st.one_of(st.none(), st.text(min_size=0, max_size=40))

# Optional ItemMeta: either no metadata at all, or one with optional fields.
_optional_meta = st.one_of(
    st.none(),
    st.builds(ItemMeta, topic_tag=_optional_text, description=_optional_text,
              title=_optional_text),
)


@settings(max_examples=100, deadline=None)
@given(file_path=_file_path, manual_meta=_optional_meta)
def test_property5_identity_and_metadata(
    file_path: str, manual_meta: ItemMeta | None
) -> None:
    """Screenshot indexing preserves identity and applies manual metadata.

    Validates: Requirements 1.2, 4.1, 4.3, 4.4

    Args:
        file_path: An arbitrary screenshot file path.
        manual_meta: Optional manual metadata (may be ``None``).
    """
    indexer = ScreenshotIndexer(ocr_enabled=False)
    item = indexer.index(file_path, manual_meta)

    # Identity is always recorded (Req 4.1). The path is stored via pathlib, so
    # compare against the platform-normalized form to stay OS-independent.
    assert item.file_path == str(Path(file_path))
    assert item.file_name == Path(file_path).name
    assert item.file_name  # non-empty
    assert item.item_id  # stable, non-empty id derived from the path

    # Manual metadata, when provided, is carried through (Req 1.2, 4.3).
    expected_topic = manual_meta.topic_tag if manual_meta is not None else None
    expected_desc = manual_meta.description if manual_meta is not None else None
    assert item.topic_tag == expected_topic
    assert item.description == expected_desc

    # With OCR disabled, ocr_text is None but the item is still indexed (Req 4.4).
    assert item.ocr_text is None


@settings(max_examples=100, deadline=None)
@given(file_path=_file_path, topic=st.text(min_size=1, max_size=30),
       desc=st.text(min_size=1, max_size=30))
def test_property5_present_metadata_is_applied(
    file_path: str, topic: str, desc: str
) -> None:
    """When metadata carries values, they appear verbatim on the item.

    Validates: Requirements 4.3

    Args:
        file_path: An arbitrary screenshot file path.
        topic: A non-empty topic tag.
        desc: A non-empty description.
    """
    meta = ItemMeta(topic_tag=topic, description=desc, title=None)
    item = ScreenshotIndexer(ocr_enabled=False).index(file_path, meta)

    assert item.topic_tag == topic
    assert item.description == desc
    assert item.ocr_text is None
    assert item.file_name == Path(file_path).name


def test_stable_item_id_for_same_path() -> None:
    """Indexing the same path twice yields the same ``item_id``."""
    indexer = ScreenshotIndexer(ocr_enabled=False)
    first = indexer.index("screenshots/login.png", None)
    second = indexer.index("screenshots/login.png", None)

    assert first.item_id == second.item_id
