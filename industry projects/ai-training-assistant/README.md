# 🔍 Internal Training Content Search Assistant

A local-first, CPU-only search assistant that lets you query your internal training materials — PDFs, text/markdown notes, and screenshots — using semantic search powered by sentence-transformers and ChromaDB.

## Features

- **Semantic search** over PDFs, TXT, and Markdown files using local embeddings
- **Screenshot indexing & search** — screenshots are embedded (via metadata/OCR text) so they're semantically searchable, not just listed
- **Conversational chat interface** — keeps history and supports follow-up questions (context stitching for vague follow-ups)
- **Streaming answers** rendered word-by-word, with adaptive markdown formatting (headers, bullets, or prose based on content)
- **Confidence scoring** (High / Medium / Low) with suggested next steps
- **No-match & low-confidence fallback guidance** — actionable next steps when results are weak or absent
- **Query categorization** across 5 training content categories
- **Extractive answer drafting** grounded only in retrieved content (with optional Ollama/OpenAI backends and automatic fallback)
- **Fully offline** after the initial model download — no paid APIs required

Validated against a 20-query evaluation set: **4.5/5 average retrieval relevance, 100% grounded answers, 90% screenshot return.** All 109 tests (property-based + example + integration) pass.

## Prerequisites

- **Python 3.10+**
- **pip** (or your preferred package manager)
- Internet connection for the first run (to download the embedding model)

## Quick Start

### 1. Clone and install dependencies

```bash
cd ai-training-assistant
pip install -r requirements.txt
```

### 2. Add your training content

Place your files into the corpus directory:

```
data/documents/corpus/
```

Supported file types:
| Type | Extensions |
|------|-----------|
| PDFs | `.pdf` |
| Text notes | `.txt`, `.md` |
| Screenshots | `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp` |

You can organize files into subfolders — the ingestion pipeline walks subdirectories recursively.

#### Optional: Add metadata

Place a `metadata.csv` or `metadata.json` in the corpus folder to tag files with topics and descriptions:

**metadata.csv**
```csv
file_name,topic_tag,description
onboarding-guide.pdf,onboarding,New hire onboarding procedures
setup-screenshot.png,setup,IDE setup instructions
```

**metadata.json**
```json
{
  "onboarding-guide.pdf": {"topic_tag": "onboarding", "description": "New hire onboarding procedures"},
  "setup-screenshot.png": {"topic_tag": "setup", "description": "IDE setup instructions"}
}
```

### 3. Build the search index

```bash
python scripts/build.py
```

This step:
- Ingests and chunks your documents
- Generates embeddings using `all-MiniLM-L6-v2`
- Persists the vector index to `data/chroma_store/`
- Saves metadata to `data/metadata.db` and `data/metadata.json`

The first run downloads the embedding model (~80 MB). After that, everything works offline.

### 4. Launch the app

```bash
streamlit run app.py
```

The chat interface opens in your browser at [http://localhost:8501](http://localhost:8501).

Type a question in the chat box at the bottom. Your conversation history is preserved on screen, and you can ask follow-up questions (e.g. "any other details?") — vague follow-ups automatically borrow context from your previous question. Use the sidebar **"Clear history"** button to reset the conversation.

> **First launch note:** the app loads the embedding model on startup (1–2 minutes on CPU the first time), shown with a spinner. Subsequent queries respond in a few seconds.

## Configuration

All settings are configured via the `.env` file in the project root. `config.py` holds the built-in spec defaults; the `.env` values below are the **tuned production settings** shipped with this project and override those defaults.

| Variable | `.env` value | `config.py` default | Description |
|----------|-------------|---------------------|-------------|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | `all-MiniLM-L6-v2` | Sentence-transformers model name |
| `MAX_CHUNK_SIZE` | `800` | `800` | Max chunk size in characters |
| `CHUNK_OVERLAP` | `100` | `100` | Overlap between adjacent chunks |
| `TOP_K` | `5` | `5` | Max results per query |
| `MIN_SIMILARITY` | `0.62` | `0.30` | Below this score → no match returned |
| `MEDIUM_CONFIDENCE_THRESHOLD` | `0.68` | `0.45` | Score threshold for "Medium" confidence |
| `HIGH_CONFIDENCE_THRESHOLD` | `0.75` | `0.65` | Score threshold for "High" confidence |
| `OCR_ENABLED` | `False` | `False` | Enable OCR for screenshots (requires Tesseract) |
| `ANSWER_MODEL` | `extractive` | `extractive` | Drafting strategy: `extractive`, `ollama`, or `openai` |
| `ANSWER_MAX_LINES` | `6` | `6` | Max lines in a drafted answer |
| `EXCLUDE_FILES` | `internal_search_use_cases.md` | `internal_search_use_cases.md` | Comma-separated files to skip during indexing (meta-documents that match queries but aren't real content) |
| `CORPUS_DIR` | `data/documents/corpus` | `data/documents/corpus` | Source content directory |
| `CHROMA_STORE_DIR` | `data/chroma_store` | `data/chroma_store` | Vector index storage |
| `METADATA_DB_PATH` | `data/metadata.db` | `data/metadata.db` | SQLite metadata file |

### Why the thresholds are tuned higher than spec defaults

Empirical scoring on the corpus showed on-topic queries score ~0.62–0.87 while off-topic queries (e.g. "payroll", "weather") score ~0.54–0.67. The tuned thresholds separate these so genuinely irrelevant queries return a no-match instead of confidently wrong results. Adjust in `.env` if your corpus behaves differently.

See `config.py` for the full list of overridable settings (data paths, logs, model cache, etc.).

## Project Structure

```
ai-training-assistant/
├── app.py                  # Streamlit chat interface (entry point)
├── config.py               # Central configuration (reads .env)
├── requirements.txt        # Python dependencies
├── pytest.ini              # Test markers (slow, ocr, smoke)
├── .env                    # Environment overrides (git-ignored)
├── .streamlit/
│   └── config.toml         # Disables file watcher (avoids transformers scan hang)
├── scripts/
│   ├── build.py            # Offline ingestion + indexing pipeline
│   └── evaluate.py         # Evaluation harness for sample queries
├── src/
│   ├── models.py           # Core dataclasses and enums
│   ├── ingestion/
│   │   ├── chunker.py      # Text chunking with overlap
│   │   ├── pdf_extractor.py# PDF per-page text extraction
│   │   ├── note_reader.py  # TXT/Markdown reader
│   │   ├── screenshot_indexer.py  # Screenshot indexing + optional OCR
│   │   ├── metadata_loader.py     # CSV/JSON metadata loader
│   │   └── ingest.py       # Ingestion orchestrator
│   ├── index/
│   │   ├── embedder.py     # Sentence-transformers wrapper
│   │   ├── vector_index.py # ChromaDB vector index
│   │   └── metadata_store.py     # SQLite + JSON metadata store
│   └── retrieval/
│       ├── retriever.py    # Semantic retrieval pipeline
│       ├── categorizer.py  # Query category classifier
│       ├── confidence.py   # Confidence scoring + next-step logic
│       ├── drafter.py      # Answer drafting (extractive/Ollama/OpenAI)
│       ├── query_guard.py  # Empty-query validation
│       └── render_helpers.py  # UI display payload builders
├── tests/                  # pytest + hypothesis test suite
└── data/
    ├── documents/corpus/   # Your training content goes here
    │   ├── notes/          # TXT/MD notes
    │   ├── pdfs/           # PDF documents
    │   ├── screenshots/    # PNG/JPG screenshots
    │   └── metadata.json   # Optional per-file topic tags & descriptions
    ├── chroma_store/       # Generated vector index (git-ignored)
    ├── metadata.db         # Generated metadata store (git-ignored)
    ├── metadata.json       # Generated metadata export (git-ignored)
    ├── model/              # Cached embedding model (git-ignored)
    ├── logs/               # Ingestion logs (git-ignored)
    └── sample_queries.csv  # Evaluation query set
```

## Running Tests

```bash
# Run all tests (excluding slow model-loading and OCR tests)
python -m pytest tests/ -q -m "not slow and not ocr"

# Run all tests including slow ones (requires the embedding model)
python -m pytest tests/ -q -m "not ocr"

# Run a specific test file
python -m pytest tests/test_retriever.py -q
```

## Evaluation

Run the evaluation harness against the bundled sample queries:

```bash
python scripts/evaluate.py
```

This produces `data/evaluation_output.csv` with retrieval results for each query, plus a Markdown summary.

## Optional: OCR for Screenshots

To extract text from screenshots:

1. Install [Tesseract](https://github.com/tesseract-ocr/tesseract) on your system
2. Install the Python binding: `pip install pytesseract`
3. Set `OCR_ENABLED=True` in `.env`
4. Rebuild the index: `python scripts/build.py`

## Optional: LLM-Powered Answer Drafting

By default, answers are drafted using extractive summarization (no network needed). To use an LLM:

**Ollama (local)**
1. Install and run [Ollama](https://ollama.com)
2. Set `ANSWER_MODEL=ollama` in `.env`

**OpenAI**
1. Set `ANSWER_MODEL=openai` in `.env`
2. Set your `OPENAI_API_KEY` environment variable

If the LLM backend is unavailable, the app automatically falls back to extractive drafting.

## Troubleshooting

**The app floods the terminal with `[transformers] Accessing __path__` warnings or hangs on startup**
This happens when Streamlit's file watcher scans every module in a large `transformers` install. The included `.streamlit/config.toml` disables the watcher to prevent it. Also pin transformers to a stable 4.x line if you see this:
```bash
pip install "transformers>=4.38,<4.50"
```
Trade-off: with the watcher disabled, code changes won't auto-reload — restart the app manually after editing.

**A query about a real topic returns "no match"**
The query scored below `MIN_SIMILARITY` (0.62). Try rephrasing with keywords closer to the training documents, or lower `MIN_SIMILARITY` in `.env`.

**Results changed / stale content appears after editing the corpus**
Rebuild the index. ChromaDB persists across runs, so removed files can linger. For a clean rebuild:
```bash
# Windows PowerShell
Remove-Item -Recurse -Force data/chroma_store; Remove-Item -Force data/metadata.db,data/metadata.json
python scripts/build.py
```

**Screenshot queries don't return the screenshot**
Ensure `data/documents/corpus/metadata.json` has a `topic_tag` and `description` for each screenshot — screenshots are embedded using this text. Without it, they fall back to filename-only matching (or enable OCR).

**The server stops when I click in the terminal (Windows)**
Windows terminals have "Quick Edit" mode that pauses a process when you click inside the window. Press Enter to resume, or run the app in a terminal where Quick Edit is disabled.
