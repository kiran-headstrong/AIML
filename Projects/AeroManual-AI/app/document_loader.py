"""
document_loader.py — Loads documents from various file formats and splits
them into chunks for embedding and indexing.

Supported formats: PDF, DOCX, DOC, TXT.
Falls back to UnstructuredFileLoader for unknown extensions.
"""

import logging
from pathlib import Path
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    UnstructuredFileLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)

# Maps file extensions to their corresponding LangChain document loaders
LOADER_MAP = {
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".doc": Docx2txtLoader,
    ".txt": TextLoader,
}


def load_and_split(file_path: str) -> list:
    """
    Load a document from disk and split it into overlapping text chunks.

    Steps:
        1. Detect file type by extension
        2. Select the appropriate LangChain loader
        3. Load raw document pages/sections
        4. Split into chunks of CHUNK_SIZE chars with CHUNK_OVERLAP overlap

    Args:
        file_path: Absolute path to the uploaded document.

    Returns:
        List of LangChain Document objects (chunks with metadata).

    Raises:
        Exception: If the file cannot be loaded or parsed.
    """
    ext = Path(file_path).suffix.lower()
    loader_cls = LOADER_MAP.get(ext, UnstructuredFileLoader)
    logger.info("Loading file=%s with loader=%s", file_path, loader_cls.__name__)

    loader = loader_cls(file_path)
    docs = loader.load()
    logger.info("Loaded %d raw pages/sections from %s", len(docs), file_path)

    # Split documents into smaller chunks for embedding
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)
    logger.info(
        "Split into %d chunks (size=%d, overlap=%d)",
        len(chunks), CHUNK_SIZE, CHUNK_OVERLAP,
    )
    return chunks
