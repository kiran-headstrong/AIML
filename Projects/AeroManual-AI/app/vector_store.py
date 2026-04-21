from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from app.config import EMBEDDING_MODEL, VECTORSTORE_DIR, TOP_K

_embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
_index_path = str(VECTORSTORE_DIR / "index")


def _load_existing():
    try:
        return FAISS.load_local(_index_path, _embeddings, allow_dangerous_deserialization=True)
    except Exception:
        return None


def add_documents(docs: list) -> int:
    store = _load_existing()
    if store:
        store.add_documents(docs)
    else:
        store = FAISS.from_documents(docs, _embeddings)
    store.save_local(_index_path)
    return len(docs)


def search(query: str, k: int = TOP_K) -> list:
    store = _load_existing()
    if not store:
        return []
    results = store.similarity_search_with_score(query, k=k)
    # Filter out low-relevance chunks (FAISS L2 distance — lower = better)
    return [doc for doc, score in results if score < 1.5]
