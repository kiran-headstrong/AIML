import os
import streamlit as st
import requests

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="AeroManual AI", layout="wide")
st.title("✈️ AeroManual AI")

# --- Sidebar: Upload ---
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
                resp = requests.post(
                    f"{API_URL}/upload", files={"file": (f.name, f.getvalue())}
                )
                if resp.ok:
                    data = resp.json()
                    st.success(f"✅ {f.name} — {data['chunks_indexed']} chunks indexed")
                else:
                    st.error(f"❌ {f.name} — {resp.json().get('detail', 'Error')}")

# --- Main: Q&A ---
st.header("Ask a Question")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if question := st.chat_input("Ask something about your documents..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching documents..."):
            resp = requests.post(f"{API_URL}/query", json={"question": question})
            if resp.ok:
                data = resp.json()
                answer = data["answer"]
                sources = data.get("sources", [])
                st.markdown(answer)
                if sources:
                    st.caption(f"📚 Sources: {', '.join(sources)}")
                st.session_state.messages.append({"role": "assistant", "content": answer})
            else:
                st.error("Failed to get response from API.")
