"""Internal Training Content Search Assistant — Streamlit entry point.

Chat-style search interface that loads a persisted vector index and metadata
store on startup, accepts user queries, keeps conversation history, runs
retrieval + answer drafting, and renders the full result payload including
text references, screenshot matches, confidence indicator, suggested next
step, query category, and answer sources.

Requirements: 7.4, 8.2, 10.1, 10.2, 10.3, 10.4, 11.1, 12.3
"""

from __future__ import annotations

import logging
import os
import re
import time

# Suppress the noisy transformers image-processor warnings that flood the
# Streamlit file watcher. This app only uses sentence-transformers for text
# embeddings — none of the vision model modules are needed.
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import streamlit as st

import config
from src.index.embedder import Embedder
from src.index.metadata_store import MetadataStore, MetadataStoreNotFoundError
from src.index.vector_index import ChromaVectorIndex, IndexCorruptError, IndexNotBuiltError
from src.models import RetrievalConfig
from src.retrieval.drafter import (
    ExtractiveDrafter,
    OllamaDrafter,
    OpenAIDrafter,
    draft_answer,
)
from src.retrieval.query_guard import check_query
from src.retrieval.render_helpers import render_full_result
from src.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Page configuration
# ------------------------------------------------------------------ #
st.set_page_config(
    page_title="Training Content Search",
    page_icon="🔍",
    layout="wide",
)

_CONFIDENCE_COLORS = {"High": "green", "Medium": "orange", "Low": "red"}


# ------------------------------------------------------------------ #
# Resource loading (cached across reruns)
# ------------------------------------------------------------------ #
@st.cache_resource
def load_resources():
    """Load the index, metadata store, embedder, retriever, and drafter."""
    try:
        embedder = Embedder()
        index = ChromaVectorIndex.load(str(config.CHROMA_STORE_DIR))
        store = MetadataStore.load(str(config.METADATA_DB_PATH))

        retrieval_config = RetrievalConfig(
            top_k=config.TOP_K,
            min_similarity=config.MIN_SIMILARITY,
            medium_confidence_threshold=config.MEDIUM_CONFIDENCE_THRESHOLD,
            high_confidence_threshold=config.HIGH_CONFIDENCE_THRESHOLD,
        )
        retriever = Retriever(
            index=index, store=store, embedder=embedder, config=retrieval_config
        )
        primary_drafter = _create_drafter(config.ANSWER_MODEL)
        return retriever, primary_drafter, None

    except (IndexNotBuiltError, MetadataStoreNotFoundError) as exc:
        return None, None, (
            "⚠️ The search index has not been built yet.\n\n"
            "Run:\n\n```\npython scripts/build.py\n```\n\n"
            f"Details: {exc}"
        )
    except IndexCorruptError as exc:
        return None, None, (
            "⚠️ The search index appears to be corrupt.\n\n"
            "Rebuild it by running:\n\n```\npython scripts/build.py\n```\n\n"
            f"Details: {exc}"
        )
    except Exception as exc:
        logger.exception("Failed to load search resources")
        return None, None, (
            "⚠️ Failed to load the search index or metadata store.\n\n"
            "Make sure you have built the index first:\n\n"
            "```\npython scripts/build.py\n```\n\n"
            f"Details: {exc}"
        )


def _create_drafter(answer_model: str):
    """Return the appropriate drafter instance based on config."""
    model = answer_model.strip().lower()
    if model == "ollama":
        return OllamaDrafter()
    if model == "openai":
        return OpenAIDrafter()
    return ExtractiveDrafter()


# ------------------------------------------------------------------ #
# Formatting helpers
# ------------------------------------------------------------------ #
def _format_answer_as_markdown(raw_text: str) -> str:
    """Convert raw extractive answer text into clean, readable markdown.

    Adapts to content structure: headers, bullet lists, and paragraphs.
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    text = raw_text.strip()
    raw_lines = re.split(r"\n+", text)
    parts = []

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue

        header_match = re.match(r"^([A-Z][A-Za-z0-9 /\-]+):(.*)$", line)
        if header_match and len(header_match.group(1)) < 50:
            header = header_match.group(1).strip()
            rest = header_match.group(2).strip()
            parts.append(f"\n**{header}**")
            if rest:
                if "•" in rest:
                    for item in (i.strip() for i in rest.split("•") if i.strip()):
                        parts.append(f"- {item}")
                else:
                    parts.append(rest)
            continue

        bullet_match = re.match(r"^[•\-\*]\s*(.+)$", line)
        if bullet_match:
            parts.append(f"- {bullet_match.group(1).strip()}")
            continue

        numbered_match = re.match(r"^\d+\.\s*(.+)$", line)
        if numbered_match:
            parts.append(f"- {numbered_match.group(1).strip()}")
            continue

        if "•" in line and line.count("•") >= 2:
            for item in (i.strip() for i in line.split("•") if i.strip()):
                parts.append(f"- {item}")
            continue

        parts.append(line)

    result = "\n".join(parts).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def _stream_text(text: str, delay: float = 0.015):
    """Generator that yields text word-by-word for st.write_stream."""
    words = text.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        time.sleep(delay)


# Phrases that strongly signal a vague follow-up referring to prior context.
# Kept intentionally specific so normal standalone questions are NOT stitched.
_FOLLOWUP_PHRASES = (
    "above", "previous query", "previous question", "more details",
    "any other", "anything else", "tell me more", "what else",
    "elaborate", "explain more", "go on", "continue", "related to above",
    "more info", "more information", "same topic",
)


def _get_last_user_query() -> str:
    """Return the most recent prior user query from history, or empty string."""
    for msg in reversed(st.session_state.get("messages", [])):
        if msg["role"] == "user":
            return msg["content"]
    return ""


def _looks_like_followup(q_lower: str) -> bool:
    """Decide if a query is a vague follow-up needing prior context.

    Only very short queries (<= 3 words) or queries containing an explicit
    follow-up phrase qualify. Normal standalone questions (which often contain
    common words like "it" or "that") are treated as independent.
    """
    word_count = len(q_lower.split())
    # A proper question starting with an interrogative is standalone.
    starts_as_question = q_lower.split()[0] in (
        "what", "which", "when", "where", "who", "why", "how", "can", "does",
        "do", "is", "are", "should", "list", "show", "find", "give",
    ) if q_lower.split() else False

    if starts_as_question and word_count >= 4:
        return False

    is_very_short = word_count <= 3
    has_phrase = any(p in q_lower for p in _FOLLOWUP_PHRASES)
    return is_very_short or has_phrase


def _build_search_query(current_query: str) -> str:
    """Stitch context into vague follow-up queries only.

    Standalone, substantive questions are used as-is so they aren't polluted
    by an unrelated previous query.
    """
    q = current_query.strip()
    q_lower = q.lower()

    if _looks_like_followup(q_lower):
        prev = _get_last_user_query()
        if prev and prev.strip().lower() != q_lower:
            return f"{prev} {q}"
    return q


_NO_MATCH_GUIDANCE = """🔍 **No matching content found for your query.**

### What you can try next

1. **Rephrase your query** — try keywords from the training documents.
2. **Check available topics** — the corpus covers:
   - 📋 Access request routing — roles, supervisor review, temporary access
   - ✅ Approval escalation — L1/L2 review, manual freeze, escalation notes
   - 💰 Refund exceptions — categories, required fields, routing rules
   - 📊 Dashboard filters — saved filters, naming format, required fields
   - 📝 Quality review — monthly sampling, review dimensions, escalation
3. **Escalate to your operations lead** — if the topic isn't covered here.
4. **Request content addition** — ask your team lead to add relevant documents.

💡 _This assistant searches only within the indexed training documents._
"""


def _render_result(payload: dict, no_match: bool, stream: bool = False) -> None:
    """Render a single assistant response (answer + metadata + sources)."""
    if no_match:
        st.markdown(_NO_MATCH_GUIDANCE)
        return

    formatted = _format_answer_as_markdown(payload["answer_text"])
    if stream:
        st.write_stream(_stream_text(formatted))
    else:
        st.markdown(formatted)

    if payload["low_confidence_note"]:
        st.warning("⚠️ Confidence is low — the answer may not be directly relevant.")
        st.markdown(
            "**Next steps:** review the sources below, rephrase your query, "
            "or escalate to your operations lead."
        )

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        conf = payload["confidence"]
        color = _CONFIDENCE_COLORS.get(conf, "gray")
        st.markdown(f"**Confidence:** :{color}[{conf}]")
    with c2:
        st.markdown(f"**Next step:** {payload['suggested_next_step']}")
    with c3:
        st.markdown(f"**Category:** {payload['category_label']}")

    text_refs = payload.get("text_references", [])
    if text_refs:
        st.markdown("**📄 Text References**")
        for ref in text_refs:
            with st.expander(ref["title"]):
                if ref.get("page_or_section"):
                    st.markdown(f"**Page/Section:** {ref['page_or_section']}")
                st.markdown(f"**Source:** `{ref['source_file']}`")
                st.markdown(f"**Excerpt:** {ref['excerpt'][:300]}")

    screenshot_matches = payload.get("screenshot_matches", [])
    if screenshot_matches:
        st.markdown("**🖼️ Screenshot Matches**")
        for sm in screenshot_matches:
            with st.expander(sm["file_name"]):
                if sm.get("topic_tag"):
                    st.markdown(f"**Topic:** {sm['topic_tag']}")
                st.markdown(f"**Details:** {sm['metadata_or_ocr_text']}")

    sources = payload.get("answer_sources", [])
    if sources:
        st.markdown("**📚 Answer Sources**")
        for src in sources:
            ref_part = f" — {src['reference']}" if src.get("reference") else ""
            st.markdown(f"- `{src['source_file']}`{ref_part}")


# ------------------------------------------------------------------ #
# Main UI
# ------------------------------------------------------------------ #
st.title("🔍 Training Content Search Assistant")

with st.spinner("Loading search index and embedding model — this may take a minute on first launch..."):
    retriever, primary_drafter, load_error = load_resources()

if load_error is not None:
    st.error(load_error)
    st.stop()

# Warm up the embedding model so the first query doesn't time out.
if "model_warmed" not in st.session_state:
    with st.spinner("Warming up embedding model..."):
        try:
            retriever._embedder.embed_query("warmup")
        except Exception:
            pass
    st.session_state["model_warmed"] = True

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Sidebar: clear history control
with st.sidebar:
    st.header("Conversation")
    st.caption("Ask questions about the training content. Follow-up questions are supported.")
    if st.button("🗑️ Clear history", use_container_width=True):
        st.session_state["messages"] = []
        st.rerun()

# Replay existing conversation history
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            _render_result(msg["payload"], msg["no_match"], stream=False)

# Chat input for new queries (and follow-ups)
query = st.chat_input("Ask a question about the training content...")

if query:
    # Build the effective search query BEFORE appending the current message
    # to history, so follow-ups can borrow context from the prior query.
    search_query = _build_search_query(query)

    # Show user message
    with st.chat_message("user"):
        st.markdown(query)
    st.session_state["messages"].append({"role": "user", "content": query})

    # Empty-query guard (Req 7.4) — validate the raw user query
    guard_result = check_query(query)
    if not guard_result.is_valid:
        with st.chat_message("assistant"):
            st.info(guard_result.prompt_message)
        st.session_state["messages"].append({
            "role": "assistant",
            "payload": {"answer_text": guard_result.prompt_message, "confidence": "Low",
                        "suggested_next_step": "", "category_label": "",
                        "low_confidence_note": False, "text_references": [],
                        "screenshot_matches": [], "answer_sources": []},
            "no_match": True,
        })
        st.stop()

    # Retrieval + drafting — use the context-stitched search query
    with st.chat_message("assistant"):
        with st.spinner("Searching..."):
            outcome = retriever.retrieve(search_query)
            answer = draft_answer(outcome, primary_drafter)
            payload = render_full_result(
                outcome, answer,
                medium_threshold=config.MEDIUM_CONFIDENCE_THRESHOLD,
                high_threshold=config.HIGH_CONFIDENCE_THRESHOLD,
            )
        _render_result(payload, outcome.no_match, stream=True)

    # Save assistant response to history
    st.session_state["messages"].append({
        "role": "assistant",
        "payload": payload,
        "no_match": outcome.no_match,
    })
