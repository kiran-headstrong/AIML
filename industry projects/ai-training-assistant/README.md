# 🔍 Internal Training Content Search Assistant

A local-first, CPU-only search assistant that lets you query your internal training materials — PDFs, text/markdown notes, and screenshots — using semantic search powered by sentence-transformers and ChromaDB.

## Features

- **Semantic search** over PDFs, TXT, and Markdown files using local embeddings
- **Screenshot indexing** with optional OCR support
- **Confidence scoring** (High / Medium / Low) with suggested next steps
- **Query categorization** across 5 training content categories
- **Extractive answer drafting** grounded only in retrieved content (with optional Ollama/OpenAI backends)
- **Streamlit UI** for an interactive search experience
- **Fully offline** after the initial model download — no paid APIs required

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

The search interface opens in your browser at [http://localhost:8501](http://localhost:8501).

## Configuration

All settings are configured via the `.env` file in the project root. Copy the provided `.env` and edit as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model name |
| `MAX_CHUNK_SIZE` | `800` | Max chunk size in characters |
| `CHUNK_OVERLAP` | `100` | Overlap between adjacent chunks |
| `TOP_K` | `5` | Max results per query |
| `MIN_SIMILARITY` | `0.30` | Minimum similarity threshold |
| `MEDIUM_CONFIDENCE_THRESHOLD` | `0.45` | Score threshold for "Medium" confidence |
| `HIGH_CONFIDENCE_THRESHOLD` | `0.65` | Score threshold for "High" confidence |
| `OCR_ENABLED` | `False` | Enable OCR for screenshots (requires Tesseract) |
| `ANSWER_MODEL` | `extractive` | Drafting strategy: `extractive`, `ollama`, or `openai` |
| `ANSWER_MAX_LINES` | `6` | Max lines in a drafted answer |
| `CORPUS_DIR` | `data/documents/corpus` | Source content directory |
| `CHROMA_STORE_DIR` | `data/chroma_store` | Vector index storage |
| `METADATA_DB_PATH` | `data/metadata.db` | SQLite metadata file |

See `config.py` for the full list of overridable settings.

## Project Structure

```
ai-training-assistant/
├── app.py                  # Streamlit search interface
├── config.py               # Central configuration (reads .env)
├── requirements.txt        # Python dependencies
├── .env                    # Environment overrides (git-ignored)
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
    ├── chroma_store/       # Generated vector index
    ├── metadata.db         # Generated metadata store
    ├── metadata.json       # Generated metadata export
    ├── model/              # Cached embedding model
    ├── logs/               # Ingestion logs
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
