"""Property-based test for the Metadata_Store round-trip.

# Feature: internal-training-content-search, Property 6: Metadata store round-trip

Persisting a set of TextChunks and ScreenshotItems to the MetadataStore and then
loading a fresh store from disk must yield items equal to the originals across
every recorded field.

**Validates: Requirements 5.1, 5.2, 5.3**
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.index.metadata_store import MetadataStore
from src.models import DocType, ScreenshotItem, TextChunk

# Doc types that a text chunk can originate from (screenshots are separate).
_TEXT_DOC_TYPES = [DocType.PDF, DocType.NOTE]

# Reusable optional-string strategy (exercises the None-preserving paths).
_optional_text = st.one_of(st.none(), st.text(max_size=40))


@st.composite
def _text_chunks(draw: st.DrawFn) -> list[TextChunk]:
    """Generate a list of TextChunks with unique chunk_ids."""
    ids = draw(
        st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=8, unique=True)
    )
    chunks: list[TextChunk] = []
    for chunk_id in ids:
        chunks.append(
            TextChunk(
                chunk_id=chunk_id,
                text=draw(st.text(max_size=200)),
                source_file=draw(st.text(min_size=1, max_size=40)),
                doc_type=draw(st.sampled_from(_TEXT_DOC_TYPES)),
                page_reference=draw(st.one_of(st.none(), st.integers(1, 500))),
                section_reference=draw(_optional_text),
                topic_tag=draw(_optional_text),
                title=draw(_optional_text),
            )
        )
    return chunks


@st.composite
def _screenshot_items(draw: st.DrawFn) -> list[ScreenshotItem]:
    """Generate a list of ScreenshotItems with unique item_ids."""
    ids = draw(
        st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=8, unique=True)
    )
    items: list[ScreenshotItem] = []
    for item_id in ids:
        items.append(
            ScreenshotItem(
                item_id=item_id,
                file_name=draw(st.text(min_size=1, max_size=40)),
                file_path=draw(st.text(min_size=1, max_size=80)),
                topic_tag=draw(_optional_text),
                description=draw(_optional_text),
                ocr_text=draw(_optional_text),
            )
        )
    return items


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(chunks=_text_chunks(), screenshots=_screenshot_items())
def test_metadata_store_roundtrip(
    chunks: list[TextChunk],
    screenshots: list[ScreenshotItem],
    tmp_path_factory,
) -> None:
    """Persist then reload yields items equal to the originals (Property 6)."""
    tmp_dir: Path = tmp_path_factory.mktemp("metadata")
    db_path = tmp_dir / "metadata.db"
    json_path = tmp_dir / "metadata.json"

    store = MetadataStore()
    store.save_chunks(chunks)
    store.save_screenshots(screenshots)
    store.persist(str(db_path), str(json_path))

    # SQLite and the human-readable JSON export must both be written (Req 5.2).
    assert db_path.exists()
    assert json_path.exists()

    reloaded = MetadataStore.load(str(db_path))

    for original in chunks:
        restored = reloaded.get_chunk(original.chunk_id)
        assert restored is not None
        assert restored == original
        # Explicitly exercise the recorded fields called out in Property 6.
        assert restored.topic_tag == original.topic_tag
        assert restored.doc_type == original.doc_type
        assert restored.source_file == original.source_file
        assert restored.page_reference == original.page_reference
        assert restored.section_reference == original.section_reference

    for original_item in screenshots:
        restored_item = reloaded.get_screenshot(original_item.item_id)
        assert restored_item is not None
        assert restored_item == original_item
