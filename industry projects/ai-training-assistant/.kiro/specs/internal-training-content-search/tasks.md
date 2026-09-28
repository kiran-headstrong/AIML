# Implementation Plan: Internal Training Content Search Assistant

## Overview

This plan converts the approved design into an incremental, test-driven implementation. Work
proceeds bottom-up: data models and config first, then the extraction layer (chunking, PDF,
notes, screenshots, metadata), then the index layer (embedder, vector index, metadata store),
then the retrieval layer (retriever, categorizer, confidence, drafter), then the build script,
the Streamlit app, and finally the evaluation harness. Each step builds on the previous ones and
ends by wiring components into a runnable whole.

The implementation language is **Python** (as specified in the design). Property-based tests use
`hypothesis`; example/integration/smoke tests use `pytest`. The retrieval, chunking,
categorization, confidence, and drafting logic are tested against an in-memory fake `VectorIndex`
and a deterministic fake `Embedder` so tests run fast on CPU without loading the real model.

Sub-tasks marked with `*` are optional test tasks and can be skipped for a faster MVP; core
implementation sub-tasks are never optional.

## Tasks

- [x] 1. Project setup, configuration, and core data models
  - [x] 1.1 Set up package layout, dependencies, and configuration
    - Create the `src/ingestion/`, `src/index/`, `src/retrieval/`, `scripts/`, and `tests/`
      package directories with `__init__.py` files
    - Add `config.py` with the configuration defaults from the design table
      (`EMBEDDING_MODEL`, `MAX_CHUNK_SIZE=800`, `CHUNK_OVERLAP=100`, `TOP_K=5`,
      `MIN_SIMILARITY=0.30`, `MEDIUM_CONFIDENCE_THRESHOLD=0.45`,
      `HIGH_CONFIDENCE_THRESHOLD=0.65`, `OCR_ENABLED=False`, `ANSWER_MODEL=extractive`,
      `ANSWER_MAX_LINES=6`) plus resolved data paths (corpus, chroma_store, metadata.db,
      metadata.json, logs, model cache), overridable via `.env`
    - Update `requirements.txt` to include streamlit, sentence-transformers, chromadb, pymupdf,
      hypothesis, and pytest (pytesseract optional/commented)
    - _Requirements: 2.2, 3.1, 7.2, 7.5, 10.3, 11.1, 4.4, 9.1, 12.2_

  - [x] 1.2 Implement core dataclasses and enums in `src/models.py`
    - Define `DocType`, `QueryCategory`, `Confidence` enums and the `TextChunk`,
      `ScreenshotItem`, `TextMatch`, `ScreenshotMatch`, `SourceRef`, `SkippedEntry`,
      `ItemMeta` dataclasses exactly as in the design's Data Models section
    - Include a stable `chunk_id` construction helper (`{source_file}::{page_or_section}::{ordinal}`)
    - _Requirements: 2.3, 3.2, 4.1, 4.3, 5.1_

- [-] 2. Chunking utility
  - [x] 2.1 Implement `Chunker` in `src/ingestion/chunker.py`
    - Split text into size-bounded segments (`<= max_chunk_size`), preferring paragraph/sentence
      boundaries and hard-splitting only when a single unit exceeds the limit; support `overlap`
    - Handle empty and whitespace-only input by producing no chunks
    - _Requirements: 2.2, 3.1_

  - [x] 2.2 Write property test for chunk size bounds
    - **Property 3: Chunk size is bounded** — every chunk length `<= N`, and the concatenation of
      chunks (ignoring overlap) covers the non-whitespace content of the original text
    - **Validates: Requirements 2.2, 3.1**

- [x] 3. Extraction layer: PDF, notes, screenshots, and metadata loader
  - [x] 3.1 Implement `PdfExtractor` in `src/ingestion/pdf_extractor.py`
    - Use PyMuPDF (`fitz`) to return per-page `PageText` (1-based page numbers); return an empty
      list when a PDF yields no extractable text
    - _Requirements: 2.1, 2.4_

  - [x] 3.2 Write example unit tests for PDF extraction
    - Assert correct page-number association against 2–3 small fixture PDFs (Req 2.1) and the
      empty-PDF path returning zero pages/chunks (Req 2.4)
    - _Requirements: 2.1, 2.4_

  - [x] 3.3 Implement note reader for TXT/MD
    - Read TXT and Markdown text and derive a `section_reference` from headings/file structure
      where available, ready for chunking
    - _Requirements: 3.1, 3.2_

  - [x] 3.4 Implement `MetadataLoader` in `src/ingestion/metadata_loader.py`
    - Locate optional `metadata.csv`/`metadata.json` in the folder and return an `ItemMeta` map
      keyed by source file name; return `{}` when absent and log a warning (proceed) when malformed
    - _Requirements: 1.2_

  - [x] 3.5 Implement `ScreenshotIndexer` in `src/ingestion/screenshot_indexer.py`
    - Always record `file_name` and `file_path`; apply `topic_tag`/`description` from manual
      metadata when provided; set `ocr_text=None` when OCR is disabled/unavailable (OCR via
      `pytesseract` behind the `ocr_enabled` flag, degrading gracefully)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 3.6 Write property test for screenshot indexing identity and metadata
    - **Property 5: Screenshot indexing preserves identity and applies metadata**
    - **Validates: Requirements 1.2, 4.1, 4.3, 4.4**

- [x] 4. Ingestion orchestrator
  - [x] 4.1 Implement `IngestionComponent` in `src/ingestion/ingest.py`
    - Walk the folder and subfolders, dispatch by extension to PDF/note/screenshot handlers,
      enrich with loaded metadata, chunk text, and assemble `IngestionResult`
    - Skip unsupported extensions with `SkippedEntry(name, "unsupported_extension")`; wrap each
      per-file parse in try/except so one failure records `SkippedEntry(name, error)` and never
      aborts the run; write skips/errors to `data/logs/ingestion.log`
    - Report `ingested_doc_count`, `ingested_screenshot_count`, and skipped count
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.3, 3.2_

  - [x] 4.2 Write property test for ingestion partitioning
    - **Property 1: Ingestion partitions input files** — supported text → doc count, screenshots →
      screenshot count, unsupported → skipped with `unsupported_extension`, and counts+skipped sum
      to total files walked
    - **Validates: Requirements 1.1, 1.3, 1.5**

  - [x] 4.3 Write property test for ingestion resilience
    - **Property 2: Ingestion is resilient to per-file failures** — arbitrary failing subset never
      raises, each failing file is in `skipped` with a reason, each good file still produces items
    - **Validates: Requirements 1.4**

  - [x] 4.4 Write property test for chunk provenance
    - **Property 4: Every chunk carries provenance** — non-empty `source_file`, plus a
      `page_reference` for PDF-origin chunks or a `section_reference` when a note heading is available
    - **Validates: Requirements 2.3, 3.2**

- [ ] 5. Checkpoint - extraction layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Index layer: embedder, vector index, metadata store
  - [x] 6.1 Implement `Embedder` in `src/index/embedder.py`
    - Wrap sentence-transformers (`all-MiniLM-L6-v2`) with CPU-only batch `embed` and
      `embed_query`, caching the model under `data/model/`; fail fast with a clear message if the
      model is missing from cache while offline
    - _Requirements: 6.1, 6.2, 7.1_

  - [x] 6.2 Write example unit test for embedding shape/determinism
    - Assert a 384-dim vector and stable output for identical input against the real model
      (mark `@pytest.mark.slow`, skip gracefully if unavailable)
    - _Requirements: 6.1_

  - [x] 6.3 Implement `VectorIndex` interface and Chroma implementation in `src/index/vector_index.py`
    - Define the `VectorIndex` Protocol (`upsert`, `search`, `persist`, `load`) with `IndexEntry`
      and `Match`; implement a persistent Chroma backend; normalize cosine similarity into `[0,1]`
    - Report "index not built" guidance on missing store; instruct rebuild on corrupt/partial index
    - _Requirements: 6.3, 6.4, 7.2_

  - [x] 6.4 Implement `MetadataStore` in `src/index/metadata_store.py`
    - Create the SQLite schema (`chunks`, `screenshots`, `idx_chunks_source`); implement
      `save_chunks`, `save_screenshots`, `persist` (SQLite + JSON export), `load`, `get_chunk`,
      `get_screenshot`
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 6.5 Write property test for metadata store round-trip
    - **Property 6: Metadata store round-trip** — persist then reload from disk yields items equal
      across all recorded fields (topic tag, doc type, source file, page/section reference)
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [x] 7. Retrieval layer: retriever, categorizer, confidence, drafter
  - [x] 7.1 Add test doubles for the retrieval layer in `tests/conftest.py`
    - Implement an in-memory fake `VectorIndex` and a deterministic fake `Embedder`, plus
      Hypothesis strategies for text bodies, chunk/screenshot collections, scored index entries,
      query strings (including whitespace-only), and `RetrievalOutcome`s
    - _Requirements: 7.1, 7.2, 7.5_

  - [x] 7.2 Implement `Categorizer` in `src/retrieval/categorizer.py`
    - Rule-based keyword classifier over the fixed 5 categories with an embedding-similarity
      tie-breaker against category prototype phrases; always return exactly one `QueryCategory`
    - _Requirements: 8.1_

  - [x] 7.3 Write property test for categorization totality
    - **Property 9: Query categorization is total and single-valued** — returns exactly one member
      of the fixed category set for any query string
    - **Validates: Requirements 8.1**

  - [x] 7.4 Implement confidence and next-step logic in `src/retrieval/confidence.py`
    - Map top similarity `s` to High/Medium/Low using the configured thresholds and select the
      next step from the fixed set; force "escalate to the operations lead if unclear" when Low
    - _Requirements: 10.3, 10.4, 11.1_

  - [x] 7.5 Write property test for confidence and next-step mapping
    - **Property 11: Confidence and next-step mapping** — exactly one confidence label, monotonic
      in `s` per thresholds, next step in the fixed set, and Low ⇒ escalate next step
    - **Validates: Requirements 10.3, 10.4, 11.1**

  - [x] 7.6 Implement `Retriever` in `src/retrieval/retriever.py`
    - Embed query, search the index, apply `min_similarity` threshold, rank text and screenshot
      matches by descending score limited to `top_k`, resolve match ids to stored items, attach
      category and confidence, and set `no_match` when nothing clears the threshold
    - _Requirements: 6.3, 7.1, 7.2, 7.3, 7.5, 8.1_

  - [x] 7.7 Write property test for retrieval ranking, limit, and reference consistency
    - **Property 7: Retrieval ranking, limit, and reference consistency** — matches ordered by
      descending score, at most `top_k`, every returned id resolves to a stored item
    - **Validates: Requirements 6.3, 7.1, 7.2, 7.3**

  - [x] 7.8 Write property test for below-threshold no-match
    - **Property 8: Below-threshold retrieval yields a no-match result** — empty match sets and
      `no_match=true` when nothing reaches `min_similarity`
    - **Validates: Requirements 7.5**

  - [x] 7.9 Implement `AnswerDrafter` strategies in `src/retrieval/drafter.py`
    - Implement the `AnswerDrafter` Protocol with `ExtractiveDrafter` (default, `<= 6` lines,
      grounded only in retrieved items, sources attached, `low_confidence_note` when Low, and a
      "no supporting content found" statement with no guidance/sources on no-match), plus
      `OllamaDrafter` and `OpenAIDrafter` that catch availability/connection errors so the caller
      falls back to `ExtractiveDrafter`
    - _Requirements: 9.1, 9.2, 9.3, 11.2, 12.3_

  - [x] 7.10 Write property test for grounded answer drafts
    - **Property 12: Answer drafts are grounded** — `<= 6` lines; matches ⇒ non-empty sources
      referencing actual items and text drawn only from retrieved content; no-match ⇒ "no
      supporting content" with no sources/guidance; Low ⇒ `low_confidence_note` true
    - **Validates: Requirements 9.1, 9.2, 9.3, 11.2**

  - [x] 7.11 Write property test for drafter fallback
    - **Property 13: Answer drafting falls back to grounded extraction** — when the primary drafter
      is unavailable/raises, a valid grounded extractive draft is returned instead of an error
    - **Validates: Requirements 12.3**

- [x] 8. Checkpoint - index and retrieval layers
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Build script (offline ingestion + indexing pipeline)
  - [x] 9.1 Implement `scripts/build.py`
    - Wire ingestion → embedding → vector index upsert/persist and metadata store persist into a
      CLI that builds `data/chroma_store/`, `data/metadata.db`, and `data/metadata.json` from the
      corpus folder, printing the ingested/skipped counts
    - _Requirements: 1.5, 5.2, 6.3_

  - [x] 9.2 Write integration test for build → persist → reload → query
    - Build a small fixture corpus, persist, reload a fresh index/store, and assert identical
      top-k results before and after reload
    - _Requirements: 6.4_

- [x] 10. Streamlit search interface and result presentation
  - [x] 10.1 Implement render helpers for result payloads
    - Pure functions that build the display payload for a text reference (title, page/section,
      source file, excerpt) and a screenshot match (preview/filename, topic tag, metadata/OCR
      text), and that include the assigned category label
    - _Requirements: 8.2, 10.1, 10.2_

  - [x] 10.2 Write example unit tests for render helpers
    - Assert all required fields are present in the text-reference and screenshot payloads and
      that the category label appears in the rendered payload
    - _Requirements: 8.2, 10.1, 10.2_

  - [x] 10.3 Implement empty-query guard used by the interface
    - A pure predicate/handler that, for whitespace-only or empty input, returns an empty-query
      prompt and does not invoke the retriever
    - _Requirements: 7.4_

  - [x] 10.4 Write property test for empty-query rejection
    - **Property 10: Empty queries are rejected without retrieval** — whitespace-only/empty queries
      return the prompt and never call the Retrieval_Component
    - **Validates: Requirements 7.4**

  - [x] 10.5 Implement the Streamlit app in `app.py`
    - Capture query input, apply the empty-query guard, load index/metadata once via
      `@st.cache_resource`, invoke retrieval + drafting (with extractive fallback), and render
      text references, screenshot matches, the query category, the confidence indicator, and the
      suggested next step; show a friendly banner when the index is not built or load fails
    - _Requirements: 7.4, 8.2, 10.1, 10.2, 10.3, 10.4, 11.1, 12.3_

- [x] 11. Evaluation harness
  - [x] 11.1 Bundle the sample query set
    - Create `data/sample_queries.csv` with at least 20 predefined queries seeded from the dataset
      pack's `evaluation_set.csv`
    - _Requirements: 13.1_

  - [x] 11.2 Implement `scripts/evaluate.py`
    - Load the sample queries, run each through the retriever, and write one record per query
      (retrieved text references, screenshot matches, assigned category, confidence) to
      `data/evaluation_output.csv` plus a Markdown summary
    - _Requirements: 13.1, 13.2, 13.3_

  - [x] 11.3 Write property test for evaluation completeness
    - **Property 14: Evaluation output is complete** — exactly one output record per query, each
      containing text references, screenshot matches, category, and confidence (driven by a fake
      retriever)
    - **Validates: Requirements 13.2**

  - [x] 11.4 Write integration and smoke tests
    - Integration: run the bundled sample queries end-to-end and assert an output file is written
      with the expected number of rows (Req 13.3)
    - Smoke: CPU-only build/query with no GPU (Req 6.2, 12.1); default `ANSWER_MODEL=extractive`
      with no network for core retrieval (Req 12.2); sample-query set has at least 20 queries (Req 13.1)
    - _Requirements: 6.2, 12.1, 12.2, 13.1, 13.3_

- [x] 12. Final checkpoint - full pipeline
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test tasks and can be skipped for a faster MVP.
- Each task references specific requirements (and, for test tasks, specific design properties) for
  traceability.
- Property-based tests (Properties 1–14) validate universal correctness; example, integration, and
  smoke tests cover external-library behavior, UI rendering, and environment constraints.
- Property tests use an in-memory fake `VectorIndex` and deterministic fake `Embedder`; configure
  `@settings(max_examples=100, deadline=None)`. Run once with `pytest -q` (no watch mode).
- Real-model and OCR tests are marked (`@pytest.mark.slow`, `@pytest.mark.ocr`) and skip gracefully
  when resources are unavailable.
