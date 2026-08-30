"""Query router: classifies user questions and routes to appropriate handler."""

import re

from groq import Groq


CATEGORIES = {
    "company": "Questions about company overview, mission, products, culture, departments",
    "policy": "Questions about leave, expenses, code of conduct, compliance, performance reviews",
    "onboarding": "Questions about first week, IT setup, accounts, probation, benefits, contacts",
    "general": "General greetings, unclear questions, or topics not covered in documents",
}

ROUTER_PROMPT = """You are a query classifier. Classify the question into ONE category.
Categories: company, policy, onboarding, general
Respond with ONLY the category name. One word. No explanation.

Question: {question}
Category:"""


def classify_query(question: str, groq_client: Groq) -> str:
    """Classify a user question into a category."""
    response = groq_client.chat.completions.create(
        model="qwen/qwen3.6-27b",
        messages=[{"role": "user", "content": ROUTER_PROMPT.format(question=question)}],
        temperature=0,
        max_tokens=200,
        # Disable Qwen reasoning so it returns the category directly instead
        # of consuming the token budget on <think> blocks.
        reasoning_effort="none",
    )
    raw = response.choices[0].message.content or ""

    # Strip thinking tags (closed or unclosed)
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip().lower()

    # Extract just the category word
    for cat in CATEGORIES:
        if cat in cleaned:
            return cat
    return "general"
