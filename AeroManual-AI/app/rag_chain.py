from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.config import GROQ_API_KEY, GROQ_MODEL
from app.vector_store import search

_llm = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0.3)

_prompt = ChatPromptTemplate.from_template(
    """You are a helpful assistant. Answer the question thoroughly and in detail 
using the provided context. Include all relevant information from the context.
If the context doesn't contain enough information, say so and answer what you can.

Context:
{context}

Question: {question}

Answer:"""
)

_chain = _prompt | _llm | StrOutputParser()


def ask(question: str) -> dict:
    docs = search(question)
    context = "\n\n---\n\n".join(d.page_content for d in docs)
    answer = _chain.invoke({"context": context, "question": question})
    sources = list({d.metadata.get("source", "unknown") for d in docs})
    return {"answer": answer, "sources": sources}
