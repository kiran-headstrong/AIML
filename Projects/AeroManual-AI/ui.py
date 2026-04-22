"""
ui.py — Streamlit chat UI for AeroManual AI.

Features:
    - Document upload with progress feedback
    - Streaming Q&A with real-time token display
    - Conversation history sent to API for multi-turn context
    - Graceful error handling with user-friendly messages
"""

import os
import json
import logging
import streamlit as st
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
)
logger = logging.getLogger(__name__)

# API base URL — configurable via environment variable for container deployments
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="AeroManual AI", layout="wide")
st.title("✈️ AeroManual AI")

# ---------------------------------------------------------------------------
# Sidebar: Document Upload
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Upload Documents")
    uploaded_files = st.file_uploader(
        "Upload PDF, DOCX, TXT, or other documents",
        accept_multiple_files=True,
        type=["pdf", "docx", "doc", "txt", "md", "csv"],
    )
    if st.button("Process & Index", disabled=not uploaded_files):
        for f in uploaded_files:
            with st.spinner(f"Processing {f.name}..."):
                try:
                    resp = requests.post(
                        f"{API_URL}/upload",
                        files={"file": (f.name, f.getvalue())},
                        timeout=120,
                    )
                    if resp.ok:
                        data = resp.json()
                        if data.get("status") == "duplicate":
                            st.warning(f"⚠️ {f.name} — already indexed, skipped")
                        else:
                            st.success(
                                f"✅ {f.name} — {data['chunks_indexed']} chunks indexed"
                            )
                    elif resp.status_code == 429:
                        st.error("⏳ Rate limit exceeded. Please wait and try again.")
                    else:
                        detail = resp.json().get("detail", "Unknown error")
                        st.error(f"❌ {f.name} — {detail}")
                except requests.ConnectionError:
                    st.error("❌ Cannot connect to API. Is the server running?")
                    logger.error("Connection failed to %s", API_URL)
                except requests.Timeout:
                    st.error("❌ Upload timed out. The file may be too large.")
                    logger.error("Upload timeout for %s", f.name)

# ---------------------------------------------------------------------------
# Main: Chat Q&A with streaming
# ---------------------------------------------------------------------------
st.header("Ask a Question")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display existing chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle new user input
if question := st.chat_input("Ask something about your documents..."):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Build chat history string from previous messages for multi-turn context
    history_lines = []
    for msg in st.session_state.messages[:-1]:  # exclude current question
        role = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role}: {msg['content']}")
    chat_history = "\n".join(history_lines[-10:])  # last 10 messages for context

    # Stream the assistant's response
    with st.chat_message("assistant"):
        try:
            # Try streaming endpoint first for real-time token display
            resp = requests.post(
                f"{API_URL}/query/stream",
                json={"question": question, "chat_history": chat_history},
                stream=True,
                timeout=60,
            )

            if resp.ok:
                placeholder = st.empty()
                full_answer = ""

                # Read SSE tokens as they arrive
                for line in resp.iter_lines(decode_unicode=True):
                    if line and line.startswith("data: "):
                        token = line[6:]  # strip "data: " prefix
                        if token == "[DONE]":
                            break
                        try:
                            token = json.loads(token)
                        except json.JSONDecodeError:
                            pass
                        full_answer += token
                        placeholder.markdown(full_answer + "▌")

                placeholder.markdown(full_answer)

                # Fetch sources from the non-streaming endpoint
                source_resp = requests.post(
                    f"{API_URL}/query",
                    json={"question": question, "chat_history": chat_history},
                    timeout=60,
                )
                if source_resp.ok:
                    sources = source_resp.json().get("sources", [])
                    if sources:
                        st.caption(f"📚 Sources: {', '.join(sources)}")

                st.session_state.messages.append(
                    {"role": "assistant", "content": full_answer}
                )
            elif resp.status_code == 429:
                st.error("⏳ Rate limit exceeded. Please wait and try again.")
            else:
                # Fallback to non-streaming endpoint
                logger.warning("Streaming failed (status=%d), falling back", resp.status_code)
                with st.spinner("Searching documents..."):
                    resp = requests.post(
                        f"{API_URL}/query",
                        json={"question": question, "chat_history": chat_history},
                        timeout=60,
                    )
                    if resp.ok:
                        data = resp.json()
                        answer = data["answer"]
                        sources = data.get("sources", [])
                        st.markdown(answer)
                        if sources:
                            st.caption(f"📚 Sources: {', '.join(sources)}")
                        st.session_state.messages.append(
                            {"role": "assistant", "content": answer}
                        )
                    else:
                        st.error("Failed to get response from API.")

        except requests.ConnectionError:
            st.error("❌ Cannot connect to API. Is the server running?")
            logger.error("Connection failed to %s", API_URL)
        except requests.Timeout:
            st.error("❌ Request timed out. Please try again.")
            logger.error("Query timeout for question: %s", question[:80])
