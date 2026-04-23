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
    """You are a precise document assistant. Answer the question using ONLY the provided context.

CRITICAL RULES:
1. Each context chunk is labeled with [Source: filename]. Use these labels to attribute information correctly.
2. If the question asks about a SPECIFIC person or topic, answer ONLY from chunks relevant to that person/topic. Ignore unrelated chunks entirely.
3. If the question is GENERIC (e.g. "list all", "summarize all docs"), group your answer by source document using ## headings.
4. NEVER mix information from different people or documents without clearly labeling which source it came from.
5. If a person or topic is not found in the context, explicitly say so.

FORMATTING RULES:
- Use **## Document/Person name** as heading when showing results from multiple sources.
- Use bullet points (- ) for lists and details.
- Use numbered lists (1. 2. 3.) for steps or sequences.
- Bold (**text**) key terms and important values.
- Use tables (| col | col |) when comparing across sources.
- Maximum 2 sentences per paragraph — prefer bullet points.

Chat History:
{chat_history}

Context:
{context}

Question: {question}

Answer (strictly attribute information to its source, never mix across sources):"""
)

# LangChain chain: prompt → LLM → parse output as string
_chain = _prompt | _llm | StrOutputParser()


def _build_context(docs: list) -> str:
    """
    Combine retrieved document chunks into a single context string,
    each labeled with its source filename so the LLM can attribute
    information correctly and segregate answers by document.
    """
    parts = []
    for d in docs:
        source = d.metadata.get("source", "unknown")
        filename = source.split("/")[-1].split("\\")[-1]
        parts.append(f"[Source: {filename}]\n{d.page_content}")
    return "\n\n---\n\n".join(parts)


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
