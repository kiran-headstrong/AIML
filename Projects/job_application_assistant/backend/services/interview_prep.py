"""
Interview Prep Service.

Generate interview preparation material from a scraped job description: a ranked
list of interview topics (Requirement 7) and categorized question-and-answer
sets per topic (Requirement 8).

The service produces two kinds of output:

* :meth:`InterviewPrepService.generate_topics` asks a LangChain chat model for a
  set of interview topics, each categorised as ``"technical"``, ``"domain"``, or
  ``"behavioral"`` (Requirement 7.2) and ranked by relevance to the job, with
  ``relevance_rank`` starting at ``1`` for the most critical topic
  (Requirement 7.3).
* :meth:`InterviewPrepService.generate_qa` asks the model for question/answer
  sets per topic, spanning the three difficulty tiers ``"easy"``/``"medium"``/
  ``"difficult"`` (Requirement 8.2), including scenario-based questions
  (Requirement 8.3), key points per answer (Requirement 8.6), and aiming for a
  minimum of five questions per difficulty per major topic (Requirement 8.5).
  Question depth and complexity are tailored to the user's
  ``experience_level`` (Requirement 8.4).

The heavy lifting is delegated to a LangChain chat model
(see :func:`services.llm.get_chat_model`), which is asked to return a strict JSON
structure. The service is deliberately defensive: malformed LLM output, missing
fields, or invalid category/difficulty values are coerced or dropped safely
rather than raising, and any LLM/transport failure degrades gracefully to an
empty result instead of surfacing an error.

The LLM invocation is isolated in :meth:`InterviewPrepService._invoke_llm` so
that the parsing/normalisation logic can be exercised independently in tests
without a live model.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

import json
import re
from typing import Any, get_args

from schemas import (
    Difficulty,
    InterviewQA,
    InterviewTopic,
    ScrapedJD,
    TopicCategory,
)
from services.llm import get_chat_model

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Allowed topic category values (derived from the schema Literal so the two
#: stay in sync). e.g. {"technical", "domain", "behavioral"}.
_VALID_CATEGORIES: frozenset[str] = frozenset(get_args(TopicCategory))

#: Allowed difficulty values (derived from the schema Literal).
#: e.g. {"easy", "medium", "difficult"}.
_VALID_DIFFICULTIES: frozenset[str] = frozenset(get_args(Difficulty))

#: Difficulty tiers in canonical order (used for backfill / iteration).
_DIFFICULTY_ORDER: tuple[Difficulty, ...] = ("easy", "medium", "difficult")

#: Default category used when the LLM returns an unrecognised/empty category.
_DEFAULT_CATEGORY: TopicCategory = "technical"

#: Default difficulty used when the LLM returns an unrecognised/empty value.
_DEFAULT_DIFFICULTY: Difficulty = "medium"

#: Minimum questions per difficulty per major topic (Requirement 8.5).
_MIN_QUESTIONS_PER_DIFFICULTY = 5

#: Synonyms / phrasings mapped onto a canonical topic category, used when
#: normalising free-form category labels the LLM may return.
_CATEGORY_ALIASES: dict[str, TopicCategory] = {
    "technical": "technical",
    "technical topics": "technical",
    "technical topic": "technical",
    "tech": "technical",
    "technology": "technical",
    "engineering": "technical",
    "coding": "technical",
    "domain": "domain",
    "domain knowledge": "domain",
    "domain knowledge topics": "domain",
    "domain topics": "domain",
    "business": "domain",
    "industry": "domain",
    "functional": "domain",
    "behavioral": "behavioral",
    "behavioural": "behavioral",
    "behavioral topics": "behavioral",
    "behavioral/soft skill": "behavioral",
    "behavioral/soft skill topics": "behavioral",
    "soft skill": "behavioral",
    "soft skills": "behavioral",
    "soft-skill": "behavioral",
    "culture": "behavioral",
    "cultural": "behavioral",
    "hr": "behavioral",
}

#: Synonyms / phrasings mapped onto a canonical difficulty.
_DIFFICULTY_ALIASES: dict[str, Difficulty] = {
    "easy": "easy",
    "beginner": "easy",
    "basic": "easy",
    "simple": "easy",
    "entry": "easy",
    "entry-level": "easy",
    "entry level": "easy",
    "medium": "medium",
    "intermediate": "medium",
    "moderate": "medium",
    "mid": "medium",
    "mid-level": "medium",
    "mid level": "medium",
    "difficult": "difficult",
    "hard": "difficult",
    "advanced": "difficult",
    "expert": "difficult",
    "challenging": "difficult",
    "complex": "difficult",
    "senior": "difficult",
}

#: System prompt instructing the model to return strict JSON for topics.
_TOPICS_SYSTEM_PROMPT = (
    "You are an expert technical interviewer and career coach who prepares "
    "candidates for job interviews. You respond ONLY with valid JSON."
)

#: User prompt template for topic generation. ``{jd_text}`` is substituted with
#: the job description summary.
_TOPICS_PROMPT_TEMPLATE = """\
Analyse the following job description and produce a ranked list of interview
preparation topics a candidate should study for this role.

For each topic, provide:
- "name": a concise topic name (e.g. "System Design", "Python Concurrency",
  "Payments Domain Knowledge", "Conflict Resolution").
- "category": EXACTLY one of ["technical", "domain", "behavioral"].
    - "technical": programming, tools, frameworks, architecture, algorithms.
    - "domain": business/industry domain knowledge relevant to the role.
    - "behavioral": soft skills, teamwork, communication, leadership, culture.

Rank the topics by relevance to THIS job, most critical first. Provide a good
spread across all three categories where the job description justifies it.

Respond with ONLY a JSON object of the form:
{{"topics": [{{"name": "...", "category": "..."}}]}}

List the topics in ranked order (most important first). Do not include any
prose, explanation, numbering, or markdown fences.

Job description:
\"\"\"
{jd_text}
\"\"\"
"""

#: System prompt instructing the model to return strict JSON for Q&A.
_QA_SYSTEM_PROMPT = (
    "You are an expert technical interviewer who writes realistic interview "
    "questions and high-quality model answers tailored to a candidate's "
    "experience level. You respond ONLY with valid JSON."
)

#: User prompt template for Q&A generation. ``{jd_text}``, ``{topics}``,
#: ``{experience_level}``, and ``{min_count}`` are substituted.
_QA_PROMPT_TEMPLATE = """\
You are preparing a candidate with experience level "{experience_level}" for an
interview for the role described below. Generate interview questions with model
answers for the provided topics.

Topics (JSON array of objects with "name" and "category"):
{topics}

Requirements for the questions and answers:
- Generate AT LEAST {min_count} questions for EACH difficulty level
  ("easy", "medium", "difficult") for EACH topic listed above.
- "difficulty": EXACTLY one of ["easy", "medium", "difficult"].
- Include some scenario-based questions that present a realistic workplace
  situation relevant to the role; mark these with "is_scenario_based": true.
  Non-scenario questions use "is_scenario_based": false.
- Tailor the depth, complexity, and expected answer quality to the candidate's
  experience level "{experience_level}". More senior levels warrant deeper,
  more nuanced questions and answers.
- "answer": a concise model answer.
- "key_points": a list of 2-5 short strings highlighting the key points an
  interviewer looks for (for quick review).
- "topic": the exact topic name this question belongs to.

Respond with ONLY a JSON object of the form:
{{"qa": [{{"question": "...", "answer": "...", "key_points": ["...", "..."],
"difficulty": "...", "is_scenario_based": false, "topic": "..."}}]}}

Do not include any prose, explanation, or markdown fences.

Job description:
\"\"\"
{jd_text}
\"\"\"
"""


class InterviewPrepService:
    """Generate ranked interview topics and categorized Q&A sets via an LLM."""

    # -- Topic generation ---------------------------------------------------

    async def generate_topics(self, jd: ScrapedJD) -> list[InterviewTopic]:
        """Generate ranked interview topics from a scraped job description.

        Uses an LLM to identify interview topics relevant to ``jd``
        (Requirement 7.1), categorising each as ``"technical"``, ``"domain"``,
        or ``"behavioral"`` (Requirement 7.2). Topics are returned ranked by
        relevance with ``relevance_rank`` starting at ``1`` for the most
        critical topic (Requirement 7.3); the rank reflects the order the LLM
        returns them in.

        Any LLM/transport failure, or unusable output, degrades gracefully to an
        empty list rather than raising.

        Args:
            jd: The structured job description to generate topics for.

        Returns:
            A list of validated, de-duplicated :class:`InterviewTopic` objects
            in ranked order (possibly empty).
        """
        jd_text = self._jd_to_text(jd)
        if not jd_text.strip():
            return []

        try:
            raw_response = await self._invoke_llm(
                _TOPICS_SYSTEM_PROMPT,
                _TOPICS_PROMPT_TEMPLATE.format(jd_text=jd_text),
            )
        except Exception:
            # Any LLM/transport failure degrades gracefully to "no topics".
            return []

        return self._parse_topics_response(raw_response)

    # -- Q&A generation -----------------------------------------------------

    async def generate_qa(
        self,
        topics: list[InterviewTopic],
        jd: ScrapedJD,
        experience_level: str,
    ) -> list[InterviewQA]:
        """Generate Q&A sets per topic, tailored to the experience level.

        Asks an LLM to produce questions and model answers for each provided
        topic (Requirement 8.1), spanning the three difficulty tiers
        (Requirement 8.2), including scenario-based questions (Requirement 8.3)
        and key points per answer (Requirement 8.6). The prompt requests a
        minimum of five questions per difficulty per topic (Requirement 8.5) and
        tailors depth/complexity to ``experience_level`` (Requirement 8.4).

        The service is pragmatic: it keeps every structurally-valid entry the
        LLM returns and does not fabricate filler to reach the minimum count —
        if the model returns fewer, the valid questions are preserved. Entries
        referencing an unknown topic are retained with their stated topic name.

        Any LLM/transport failure, or unusable output, degrades gracefully to an
        empty list rather than raising.

        Args:
            topics: The ranked topics to generate questions for.
            jd: The structured job description (for additional context).
            experience_level: The candidate's experience level used to tailor
                question depth and complexity.

        Returns:
            A list of validated :class:`InterviewQA` objects (possibly empty).
        """
        if not topics:
            return []

        jd_text = self._jd_to_text(jd)
        topics_json = json.dumps(
            [{"name": topic.name, "category": topic.category} for topic in topics]
        )
        level = (experience_level or "").strip() or "unspecified"

        try:
            raw_response = await self._invoke_llm(
                _QA_SYSTEM_PROMPT,
                _QA_PROMPT_TEMPLATE.format(
                    jd_text=jd_text,
                    topics=topics_json,
                    experience_level=level,
                    min_count=_MIN_QUESTIONS_PER_DIFFICULTY,
                ),
            )
        except Exception:
            return []

        valid_topic_names = {topic.name for topic in topics}
        return self._parse_qa_response(raw_response, valid_topic_names)

    # -- LLM invocation (isolated for testability) --------------------------

    async def _invoke_llm(self, system_prompt: str, human_prompt: str) -> str:
        """Invoke the configured chat model and return its raw text content.

        Isolated from parsing so that the parsing/normalisation logic can be
        tested with canned responses and no live model.

        Args:
            system_prompt: The system message content.
            human_prompt: The human message content.

        Returns:
            The model's response content as a string.
        """
        model = get_chat_model()
        messages = [
            ("system", system_prompt),
            ("human", human_prompt),
        ]
        response = await model.ainvoke(messages)
        return self._content_to_text(getattr(response, "content", response))

    # -- Parsing / normalisation: topics ------------------------------------

    def _parse_topics_response(self, raw_response: str) -> list[InterviewTopic]:
        """Parse and normalise the LLM response into ranked topics.

        Extracts the JSON payload (tolerating surrounding prose or markdown
        code fences), then normalises each entry's category to the schema's
        allowed values, dropping unnamed or structurally-invalid entries.
        Duplicate topic names (case-insensitive) are removed while preserving
        order. ``relevance_rank`` is assigned from the order of surviving
        entries, starting at ``1`` (Requirement 7.3).

        Args:
            raw_response: The raw string returned by the LLM.

        Returns:
            A list of validated, de-duplicated :class:`InterviewTopic` objects
            in ranked order (possibly empty).
        """
        payload = self._extract_json(raw_response)
        if not isinstance(payload, dict):
            return []

        raw_topics = payload.get("topics")
        if not isinstance(raw_topics, list):
            return []

        topics: list[InterviewTopic] = []
        seen: set[str] = set()
        rank = 1
        for entry in raw_topics:
            parsed = self._coerce_topic(entry, rank)
            if parsed is None:
                continue
            key = parsed.name.lower()
            if key in seen:
                continue
            seen.add(key)
            topics.append(parsed)
            rank += 1
        return topics

    def _coerce_topic(self, entry: Any, rank: int) -> InterviewTopic | None:
        """Coerce a single raw LLM entry into a valid :class:`InterviewTopic`.

        Returns ``None`` when the entry is not a mapping or has no usable name.
        An invalid/empty category is coerced to a safe default rather than
        causing the entry to be dropped. ``rank`` is used as the
        ``relevance_rank`` for this topic.
        """
        if not isinstance(entry, dict):
            return None

        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            return None

        category = self._normalise_category(entry.get("category"))
        return InterviewTopic(
            name=name.strip(),
            category=category,
            relevance_rank=rank,
        )

    # -- Parsing / normalisation: Q&A ---------------------------------------

    def _parse_qa_response(
        self, raw_response: str, valid_topic_names: set[str]
    ) -> list[InterviewQA]:
        """Parse and normalise the LLM response into Q&A entries.

        Extracts the JSON payload (tolerating surrounding prose or markdown
        code fences), then normalises each entry's difficulty to the schema's
        allowed values, coercing the ``key_points`` list and the
        ``is_scenario_based`` flag, and dropping entries missing a question or
        answer. Duplicate ``(question, topic, difficulty)`` combinations are
        removed while preserving order.

        Args:
            raw_response: The raw string returned by the LLM.
            valid_topic_names: The set of known topic names; used only to
                normalise the ``topic`` field casing, not to drop entries.

        Returns:
            A list of validated :class:`InterviewQA` objects (possibly empty).
        """
        payload = self._extract_json(raw_response)
        if not isinstance(payload, dict):
            return []

        raw_qa = payload.get("qa")
        if not isinstance(raw_qa, list):
            return []

        # Case-insensitive lookup to canonicalise topic names.
        topic_lookup = {name.lower(): name for name in valid_topic_names}

        qa_items: list[InterviewQA] = []
        seen: set[tuple[str, str, str]] = set()
        for entry in raw_qa:
            item = self._coerce_qa(entry, topic_lookup)
            if item is None:
                continue
            key = (item.question.lower(), item.topic.lower(), item.difficulty)
            if key in seen:
                continue
            seen.add(key)
            qa_items.append(item)
        return qa_items

    def _coerce_qa(
        self, entry: Any, topic_lookup: dict[str, str]
    ) -> InterviewQA | None:
        """Coerce a single raw LLM entry into a valid :class:`InterviewQA`.

        Returns ``None`` when the entry is not a mapping or lacks a usable
        question or answer. An invalid/empty difficulty is coerced to a safe
        default; ``is_scenario_based`` and ``key_points`` are coerced to safe
        types. The ``topic`` field is canonicalised against known topic names
        when possible, otherwise kept as returned.
        """
        if not isinstance(entry, dict):
            return None

        question = entry.get("question")
        if not isinstance(question, str) or not question.strip():
            return None

        answer = entry.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return None

        difficulty = self._normalise_difficulty(entry.get("difficulty"))
        key_points = self._coerce_string_list(entry.get("key_points"))
        is_scenario = self._coerce_bool(entry.get("is_scenario_based"))

        raw_topic = entry.get("topic")
        topic_name = raw_topic.strip() if isinstance(raw_topic, str) else ""
        if topic_name:
            topic_name = topic_lookup.get(topic_name.lower(), topic_name)

        return InterviewQA(
            question=question.strip(),
            answer=answer.strip(),
            key_points=key_points,
            difficulty=difficulty,
            is_scenario_based=is_scenario,
            topic=topic_name,
        )

    # -- Value normalisation helpers ----------------------------------------

    @staticmethod
    def _normalise_category(value: Any) -> TopicCategory:
        """Map a free-form category value onto an allowed category Literal."""
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in _VALID_CATEGORIES:
                return cleaned  # type: ignore[return-value]
            if cleaned in _CATEGORY_ALIASES:
                return _CATEGORY_ALIASES[cleaned]
        return _DEFAULT_CATEGORY

    @staticmethod
    def _normalise_difficulty(value: Any) -> Difficulty:
        """Map a free-form difficulty value onto an allowed difficulty Literal."""
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in _VALID_DIFFICULTIES:
                return cleaned  # type: ignore[return-value]
            if cleaned in _DIFFICULTY_ALIASES:
                return _DIFFICULTY_ALIASES[cleaned]
        return _DEFAULT_DIFFICULTY

    @staticmethod
    def _coerce_string_list(value: Any) -> list[str]:
        """Coerce a raw value into a list of non-empty, trimmed strings.

        Accepts a list (non-string / empty entries dropped) or a single string
        (wrapped in a one-element list). Any other type yields an empty list.
        """
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
        if isinstance(value, list):
            result: list[str] = []
            for entry in value:
                if isinstance(entry, str) and entry.strip():
                    result.append(entry.strip())
            return result
        return []

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        """Coerce a raw value into a boolean.

        Accepts native booleans and common truthy string spellings
        ("true", "yes", "1"); everything else is treated as ``False``.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1", "y"}
        return False

    # -- JD text assembly ---------------------------------------------------

    @staticmethod
    def _jd_to_text(jd: ScrapedJD) -> str:
        """Assemble a compact textual summary of a :class:`ScrapedJD`.

        Combines the salient fields (title, company, location, experience,
        description body, required/preferred skills) into a single string
        suitable for embedding in an LLM prompt. Missing/empty fields are
        omitted.
        """
        if jd is None:
            return ""

        parts: list[str] = []
        if jd.job_title:
            parts.append(f"Job Title: {jd.job_title}")
        if jd.company_name:
            parts.append(f"Company: {jd.company_name}")
        if jd.location:
            parts.append(f"Location: {jd.location}")
        if jd.experience_required:
            parts.append(f"Experience Required: {jd.experience_required}")
        if jd.required_skills:
            parts.append("Required Skills: " + ", ".join(jd.required_skills))
        if jd.preferred_skills:
            parts.append("Preferred Skills: " + ", ".join(jd.preferred_skills))
        if jd.description_body:
            parts.append("Description:\n" + jd.description_body)
        return "\n".join(parts)

    # -- JSON extraction / content normalisation ----------------------------

    @staticmethod
    def _extract_json(raw_response: str) -> dict[str, Any] | None:
        """Best-effort extraction of a JSON object from an LLM response.

        Handles responses that are pure JSON, wrapped in markdown code fences,
        or embedded in surrounding prose. Returns ``None`` when no JSON object
        can be parsed.
        """
        if not raw_response or not raw_response.strip():
            return None

        text = raw_response.strip()

        # Strip markdown code fences such as ```json ... ``` if present.
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()

        # First, try to parse the whole thing as JSON.
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError):
            pass

        # Otherwise, locate the first balanced {...} object in the text.
        start = text.find("{")
        while start != -1:
            depth = 0
            for idx in range(start, len(text)):
                char = text[idx]
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : idx + 1]
                        try:
                            parsed = json.loads(candidate)
                            return parsed if isinstance(parsed, dict) else None
                        except (ValueError, TypeError):
                            break
            start = text.find("{", start + 1)
        return None

    @staticmethod
    def _content_to_text(content: Any) -> str:
        """Normalise LangChain message content into a plain string.

        LangChain chat models may return a string or a list of content blocks
        (e.g. ``[{"type": "text", "text": "..."}]``). This flattens either form
        into a single string.
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return str(content) if content is not None else ""
