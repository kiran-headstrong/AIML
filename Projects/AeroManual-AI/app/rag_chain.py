"""
rag_chain.py — RAG (Retrieval-Augmented Generation) chain that combines
vector search results with an LLM to generate context-aware answers.

Features:
    - Conversation memory: Chat history is included in the prompt so the
      LLM can handle follow-up questions like "tell me more about that".
    - Streaming: async generator yields tokens as they arrive from Groq,
      enabling real-time token-by-token display in the UI.
    - Source tracking: Returns the list of source files used to generate
      each answer for transparency.
"""

import logging
import re
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.config import GROQ_API_KEY, GROQ_MODEL
from app.vector_store import search

logger = logging.getLogger(__name__)

MAX_QUESTION_LEN = 2000
MAX_HISTORY_LEN = 10000


def _sanitize_input(text: str, max_len: int) -> str:
    """Strip control characters and truncate user input before use."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text[:max_len]

# Initialize the Groq LLM with low temperature for factual answers
_llm = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0.3)

# Prompt template with formatting instructions and chat history support
_prompt = ChatPromptTemplate.from_template(
    """You are a helpful technical assistant. Answer the question using ONLY the provided context.

STRICT FORMATTING RULES (you MUST follow these):
1. NEVER write long paragraphs. Every answer MUST use structured formatting.
2. Start with a 1-2 sentence **summary** of the answer.
3. Then organize details using:
   - **## Headings** for major sections
   - **Bullet points** (- ) for lists, features, components, or details
   - **Numbered lists** (1. 2. 3.) for steps, procedures, or sequences
   - **Bold** (**text**) for key terms, names, acronyms, and important values
   - **Tables** (| col1 | col2 |) when comparing items or showing structured data
4. Maximum 2 sentences per paragraph. Break longer text into bullet points.
5. If the answer involves multiple topics, use a separate heading for each.
6. If the context doesn't contain enough information, say so clearly.

Chat History:
{chat_history}

Context:
{context}

Question: {question}

Answer (use structured Markdown formatting):"""
)

# LangChain chain: prompt → LLM → parse output as string
_chain = _prompt | _llm | StrOutputParser()


def _build_context(docs: list) -> str:
    """
    Combine retrieved document chunks into a single context string.

    Each chunk is separated by a horizontal rule for clarity in the prompt.

    Args:
        docs: List of LangChain Document objects from vector search.

    Returns:
        Concatenated text of all chunks.
    """
    return "\n\n---\n\n".join(d.page_content for d in docs)


def _extract_sources(docs: list) -> list:
    """
    Extract unique source file paths from retrieved documents.

    Args:
        docs: List of LangChain Document objects.

    Returns:
        Deduplicated list of source file paths.
    """
    return list({d.metadata.get("source", "unknown") for d in docs})


def ask(question: str, chat_history: str = "") -> dict:
    """
    Answer a question using the RAG pipeline (synchronous).

    Steps:
        1. Search FAISS index for relevant document chunks
        2. Build context from retrieved chunks
        3. Send context + question + chat history to Groq LLM
        4. Return the generated answer with source references

    Args:
        question: User's natural language question.
        chat_history: Formatted string of previous Q&A turns.

    Returns:
        Dict with 'answer' (str) and 'sources' (list of file paths).
    """
    logger.info("Processing query: '%s'", question[:100])

    question = _sanitize_input(question, MAX_QUESTION_LEN)
    chat_history = _sanitize_input(chat_history, MAX_HISTORY_LEN)

    docs = search(question)
    if not docs:
        logger.warning("No relevant documents found for query")
        return {
            "answer": "No relevant documents found. Please upload documents first.",
            "sources": [],
        }

    context = _build_context(docs)
    sources = _extract_sources(docs)
    logger.info("Retrieved %d chunks from %d sources", len(docs), len(sources))

    answer = _chain.invoke({
        "context": context,
        "question": question,
        "chat_history": chat_history or "No previous conversation.",
    })
    logger.info("Answer generated (length=%d chars)", len(answer))
    return {"answer": answer, "sources": sources}


async def ask_stream(question: str, chat_history: str = ""):
    """
    Answer a question using the RAG pipeline (async streaming).

    Yields tokens as they arrive from the Groq LLM, enabling real-time
    display in the UI via Server-Sent Events (SSE).

    Args:
        question: User's natural language question.
        chat_history: Formatted string of previous Q&A turns.

    Yields:
        String tokens as they are generated by the LLM.
    """
    logger.info("Streaming query: '%s'", question[:100])

    question = _sanitize_input(question, MAX_QUESTION_LEN)
    chat_history = _sanitize_input(chat_history, MAX_HISTORY_LEN)

    docs = search(question)
    if not docs:
        logger.warning("No relevant documents found for streaming query")
        yield "No relevant documents found. Please upload documents first."
        return

    context = _build_context(docs)
    sources = _extract_sources(docs)
    logger.info("Streaming: %d chunks from %d sources", len(docs), len(sources))

    async for chunk in _chain.astream({
        "context": context,
        "question": question,
        "chat_history": chat_history or "No previous conversation.",
    }):
        if isinstance(chunk, str):
            yield chunk
