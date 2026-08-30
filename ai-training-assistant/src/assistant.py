"""Main assistant: orchestrates routing, retrieval, and generation."""

import logging
import os
import re
import time
import uuid

from dotenv import load_dotenv
from groq import Groq

from src.knowledge_base import get_retriever, retrieve
from src.observability import log_event, metrics, trace_span
from src.router import classify_query


load_dotenv()

MODEL = "qwen/qwen3.6-27b"

# Routing categories that correspond to real document metadata categories.
# Used to scope vector retrieval via the store's metadata filter. The router's
# fourth category, "general", is not a document category, so it is excluded
# here and results in an unfiltered search.
DOCUMENT_CATEGORIES = {"company", "policy", "onboarding"}

SYSTEM_PROMPT = """You are a helpful AI Training Assistant for TechNova Solutions.
Your role is to help new employees find answers about company policies, onboarding,
and general company information.

Guidelines:
- Be friendly, professional, and concise
- Answer ONLY based on the provided context
- If the context doesn't contain the answer, say so honestly
- Cite which document the information comes from
- For policy questions, be precise about numbers and dates
- If unsure, suggest who the employee should contact
- Do NOT include any thinking or reasoning tags in your response

Context from company documents:
{context}

Source documents used: {sources}"""

FALLBACK_RESPONSE = """I don't have specific information about that in our company \
documents. Here's what you can do:
- For HR queries: Contact hr.helpdesk@technova.com
- For IT issues: Reach out on Slack #it-helpdesk
- For policy clarifications: Ask your manager or People & Culture team
- For anything else: Your onboarding buddy can help!"""


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks from model output."""
    if not text:
        return ""
    # Handle properly closed tags
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Handle unclosed <think> tag (model outputs thinking without closing tag)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL).strip()
    return cleaned


class TrainingAssistant:
    """AI Training Assistant with RAG and query routing."""

    def __init__(self) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Copy .env.sample to .env and add your key."
            )
        self.groq = Groq(api_key=api_key)
        self.store, self.embeddings = get_retriever()
        self.chat_history: list[dict] = []

    def answer(self, question: str, username: str = "anonymous") -> dict:
        """Process a user question and return an answer with metadata.

        Args:
            question: The user's question.
            username: The authenticated user issuing the query (for audit
                logging and per-user admin analytics).

        Returns:
            A dict with ``answer``, ``category``, ``sources``, and
            ``confidence`` keys.
        """
        # One correlation id ties routing, retrieval, and generation spans of
        # this request together in the event log.
        trace_id = uuid.uuid4().hex[:12]
        start_time = time.perf_counter()
        log_event(
            logging.INFO,
            "query received",
            span="query",
            status="start",
            trace_id=trace_id,
            username=username,
            question_len=len(question),
        )

        with trace_span("query", trace_id=trace_id) as q_attrs:
            # Step 1: Classify the query.
            with trace_span("routing", trace_id=trace_id) as r_attrs:
                category = classify_query(question, self.groq)
                r_attrs["category"] = category

            # Step 2: Retrieve relevant context.
            with trace_span("retrieval", trace_id=trace_id) as ret_attrs:
                # Scope the search to the routed category when it maps to a
                # real document category. "general" is not a document category,
                # so it triggers an unfiltered search.
                filter_category = (
                    category if category in DOCUMENT_CATEGORIES else None
                )
                retrieved = retrieve(
                    question,
                    self.store,
                    self.embeddings,
                    top_k=5,
                    category=filter_category,
                )
                relevant = [r for r in retrieved if r["score"] > 0.3]

                # Safe fallback: if the category-scoped search found nothing
                # relevant, retry unfiltered. This keeps recall for questions
                # whose best answer lives in a different category than routed.
                used_fallback_search = False
                if filter_category is not None and not relevant:
                    used_fallback_search = True
                    retrieved = retrieve(
                        question, self.store, self.embeddings, top_k=5
                    )
                    relevant = [r for r in retrieved if r["score"] > 0.3]

                top_score = retrieved[0]["score"] if retrieved else None
                ret_attrs["filter_category"] = filter_category
                ret_attrs["unfiltered_retry"] = used_fallback_search
                ret_attrs["retrieved"] = len(retrieved)
                ret_attrs["relevant"] = len(relevant)
                ret_attrs["top_score"] = round(top_score, 4) if top_score else None

            # Fallback path: no sufficiently relevant context found.
            if not relevant:
                q_attrs["category"] = category
                q_attrs["is_fallback"] = True
                metrics.record_query(
                    category=category,
                    confidence="low",
                    is_fallback=True,
                    top_score=top_score,
                    filter_category=filter_category,
                    unfiltered_retry=used_fallback_search,
                    username=username,
                    latency_ms=(time.perf_counter() - start_time) * 1000.0,
                )
                return {
                    "answer": FALLBACK_RESPONSE,
                    "category": category,
                    "sources": [],
                    "confidence": "low",
                    "filter_category": filter_category,
                    "unfiltered_retry": used_fallback_search,
                }

            # Step 3: Build context.
            context = "\n\n---\n\n".join([r["text"] for r in relevant])
            sources = list(set(r["source"] for r in relevant))

            # Step 4: Generate answer.
            system_msg = SYSTEM_PROMPT.format(
                context=context, sources=", ".join(sources)
            )

            messages: list[dict] = [
                {"role": "system", "content": system_msg},
            ]
            # Add recent chat history for context.
            for msg in self.chat_history[-4:]:
                messages.append(msg)
            messages.append({"role": "user", "content": question})

            with trace_span("generation", trace_id=trace_id, model=MODEL) as g_attrs:
                response = self.groq.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=800,
                    # Qwen is a reasoning model: without this it spends the
                    # token budget emitting <think> blocks and can return an
                    # empty answer. "none" disables reasoning so it responds
                    # directly.
                    reasoning_effort="none",
                )
                # Record token usage for cost/throughput observability.
                usage = getattr(response, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                    metrics.record_tokens(prompt_tokens, completion_tokens)
                    g_attrs["prompt_tokens"] = prompt_tokens
                    g_attrs["completion_tokens"] = completion_tokens

            answer_text = strip_thinking(response.choices[0].message.content)

            # Update chat history.
            self.chat_history.append({"role": "user", "content": question})
            self.chat_history.append({"role": "assistant", "content": answer_text})

            # Determine confidence.
            avg_score = sum(r["score"] for r in relevant) / len(relevant)
            if avg_score > 0.6:
                confidence = "high"
            elif avg_score > 0.4:
                confidence = "medium"
            else:
                confidence = "low"

            q_attrs["category"] = category
            q_attrs["confidence"] = confidence
            q_attrs["sources"] = sources
            q_attrs["is_fallback"] = False

            metrics.record_query(
                category=category,
                confidence=confidence,
                is_fallback=False,
                top_score=top_score,
                filter_category=filter_category,
                unfiltered_retry=used_fallback_search,
                username=username,
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
            )

            return {
                "answer": answer_text,
                "category": category,
                "sources": sources,
                "confidence": confidence,
                "filter_category": filter_category,
                "unfiltered_retry": used_fallback_search,
            }

    def reset_history(self) -> None:
        """Clear conversation history."""
        self.chat_history = []
