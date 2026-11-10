"""
Tech Stack Extractor Service.

Analyse a job description and extract the technologies it mentions, categorising
each into one of the supported categories (language, framework, database, cloud,
tool) and assigning a priority (required vs. nice-to-have) based on the language
used in the posting (Requirements 2.1, 2.2).

The heavy lifting of identification/categorisation is delegated to a LangChain
chat model (see :func:`services.llm.get_chat_model`), which is asked to return a
strict JSON structure. The service is deliberately defensive: malformed LLM
output, missing fields, or invalid category/priority values are coerced or
dropped safely rather than raising, and a job description with no identifiable
technologies yields an empty :class:`~schemas.TechStackResult` carrying an
informational message suggesting manual review (Requirement 2.3).

The LLM invocation is isolated in :meth:`TechStackExtractorService._invoke_llm`
so that the parsing/normalisation logic (:meth:`_parse_llm_response`) can be
exercised independently in tests without a live model.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

import json
import re
from typing import Any, get_args

from schemas import (
    GapPriority,
    SkillGap,
    SkillGapResult,
    TechCategory,
    TechPriority,
    TechStackItem,
    TechStackResult,
)
from services.llm import get_chat_model

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Allowed category values (derived from the schema Literal so the two stay in
#: sync). e.g. {"language", "framework", "database", "cloud", "tool"}.
_VALID_CATEGORIES: frozenset[str] = frozenset(get_args(TechCategory))

#: Allowed priority values (derived from the schema Literal).
#: e.g. {"required", "nice_to_have"}.
_VALID_PRIORITIES: frozenset[str] = frozenset(get_args(TechPriority))

#: Default category used when the LLM returns an unrecognised/empty category.
_DEFAULT_CATEGORY: TechCategory = "tool"

#: Default priority used when the LLM returns an unrecognised/empty priority.
_DEFAULT_PRIORITY: TechPriority = "required"

#: Message returned when no technologies could be identified (Requirement 2.3).
_NO_TECH_MESSAGE = (
    "No specific tech stack could be identified in this job description. "
    "Please review the posting manually to determine the required technologies."
)

#: Common synonyms / phrasings mapped onto a canonical category, used when
#: normalising free-form category labels the LLM may return.
_CATEGORY_ALIASES: dict[str, TechCategory] = {
    "language": "language",
    "languages": "language",
    "programming language": "language",
    "programming languages": "language",
    "framework": "framework",
    "frameworks": "framework",
    "library": "framework",
    "libraries": "framework",
    "database": "database",
    "databases": "database",
    "data store": "database",
    "datastore": "database",
    "cloud": "cloud",
    "cloud platform": "cloud",
    "cloud platforms": "cloud",
    "platform": "cloud",
    "tool": "tool",
    "tools": "tool",
    "tooling": "tool",
    "technology": "tool",
}

#: Synonyms / phrasings mapped onto a canonical priority.
_PRIORITY_ALIASES: dict[str, TechPriority] = {
    "required": "required",
    "require": "required",
    "must have": "required",
    "must-have": "required",
    "must": "required",
    "mandatory": "required",
    "essential": "required",
    "nice_to_have": "nice_to_have",
    "nice-to-have": "nice_to_have",
    "nice to have": "nice_to_have",
    "nice": "nice_to_have",
    "preferred": "nice_to_have",
    "good to have": "nice_to_have",
    "good-to-have": "nice_to_have",
    "optional": "nice_to_have",
    "bonus": "nice_to_have",
    "plus": "nice_to_have",
    "desired": "nice_to_have",
}

#: System prompt instructing the model to return strict JSON.
_SYSTEM_PROMPT = (
    "You are an expert technical recruiter who extracts technology "
    "requirements from job descriptions. You respond ONLY with valid JSON."
)

#: User prompt template. ``{jd_text}`` is substituted with the job description.
_PROMPT_TEMPLATE = """\
Analyse the following job description and extract every technology it mentions:
programming languages, frameworks, libraries, tools, databases, and cloud
platforms.

For each technology, provide:
- "name": the technology name (e.g. "Python", "React", "PostgreSQL", "AWS").
- "category": EXACTLY one of ["language", "framework", "database", "cloud", "tool"].
    - "language": programming languages (Python, Java, Go, ...).
    - "framework": frameworks AND libraries (React, Django, Spring, ...).
    - "database": databases and data stores (PostgreSQL, MongoDB, Redis, ...).
    - "cloud": cloud platforms/providers (AWS, Azure, GCP, ...).
    - "tool": everything else (Docker, Git, Jira, Kubernetes, CI/CD tools, ...).
- "priority": EXACTLY one of ["required", "nice_to_have"].
    - "required": technologies phrased as required/must-have/mandatory, or
      listed under requirements.
    - "nice_to_have": technologies phrased as preferred/good-to-have/
      nice-to-have/bonus/optional.

Respond with ONLY a JSON object of the form:
{{"items": [{{"name": "...", "category": "...", "priority": "..."}}]}}

If no technologies are mentioned, respond with {{"items": []}}.
Do not include any prose, explanation, or markdown fences.

Job description:
\"\"\"
{jd_text}
\"\"\"
"""

#: System prompt for learning-resource suggestions.
_RESOURCES_SYSTEM_PROMPT = (
    "You are a helpful technical mentor who recommends concise, high-quality "
    "learning resources for specific technologies. You respond ONLY with valid "
    "JSON."
)

#: User prompt template for learning resources. ``{skills}`` is a JSON array of
#: the skill names the user is missing.
_RESOURCES_PROMPT_TEMPLATE = """\
A job seeker is missing the following technical skills:
{skills}

For EACH skill, suggest 2-3 concrete learning resources: official documentation
links, reputable online courses, or well-known tutorials. Prefer stable,
widely-recognised resources (official docs, MDN, freeCodeCamp, Coursera, etc.).

Respond with ONLY a JSON object mapping each skill name to a list of resource
strings, of the form:
{{"resources": {{"<skill name>": ["resource 1", "resource 2"], ...}}}}

Use the exact skill names provided as keys. Do not include any prose,
explanation, or markdown fences.
"""

#: Generic fallback resource template used when the LLM is unavailable or omits
#: a skill. ``{skill}`` is substituted with the skill name.
_FALLBACK_RESOURCE_TEMPLATE = (
    "Search official documentation and reputable tutorials for '{skill}' "
    "(e.g. the project's docs site, freeCodeCamp, or a Coursera/Udemy course)."
)


class TechStackExtractorService:
    """Extract and categorise technologies from job-description text."""

    async def extract(self, jd_text: str) -> TechStackResult:
        """Extract and categorise technologies from ``jd_text`` using an LLM.

        Identifies programming languages, frameworks/libraries, databases,
        cloud platforms, and tools, categorising each and assigning a
        required/nice-to-have priority (Requirements 2.1, 2.2). The resulting
        items are also split into ``required`` and ``nice_to_have`` lists.

        When the job description contains no identifiable technologies — or when
        the LLM cannot be reached / returns unusable output — an empty
        :class:`TechStackResult` is returned with an informational ``message``
        suggesting manual review (Requirement 2.3).

        Args:
            jd_text: The raw job-description text to analyse.

        Returns:
            A :class:`TechStackResult` with ``items`` plus the ``required`` and
            ``nice_to_have`` splits, and an optional informational ``message``.
        """
        if not jd_text or not jd_text.strip():
            return self._empty_result()

        try:
            raw_response = await self._invoke_llm(jd_text)
        except Exception:
            # Any LLM/transport failure degrades gracefully to "no tech found"
            # with a manual-review suggestion rather than surfacing an error.
            return self._empty_result()

        items = self._parse_llm_response(raw_response)
        return self._build_result(items)

    # -- Skill gap analysis -------------------------------------------------

    async def identify_skill_gaps(
        self, tech_stack: TechStackResult, resume_skills: list[str]
    ) -> SkillGapResult:
        """Identify skills the JD requires that are absent from the resume.

        Compares each technology in ``tech_stack`` against the user's
        ``resume_skills`` (Requirement 11.1), categorising every gap by priority
        — ``"Critical"`` for required technologies and ``"Recommended"`` for
        nice-to-have ones (Requirement 11.2). For each identified gap, learning
        resources (documentation links, course/tutorial recommendations) are
        suggested via the LLM, with a safe generic fallback when the model is
        unavailable or omits a skill (Requirement 11.3).

        The comparison is case-insensitive and token-aware so that, e.g., a
        resume skill ``"Amazon Web Services (AWS)"`` is treated as covering a
        tech-stack item ``"AWS"``.

        Args:
            tech_stack: The categorised tech stack extracted from the JD.
            resume_skills: The skills extracted from the user's base resume.

        Returns:
            A :class:`SkillGapResult` with the full ``gaps`` list plus the
            ``critical`` and ``recommended`` splits. When there are no gaps, all
            lists are empty.
        """
        resume_norm = self._normalise_skill_list(resume_skills)

        # Collect missing items, de-duplicated by name, preserving the stronger
        # (Critical) priority when a name appears as both required and
        # nice-to-have.
        gaps_by_name: dict[str, GapPriority] = {}
        display_name: dict[str, str] = {}
        for item in tech_stack.items:
            if self._skill_present(item.name, resume_norm):
                continue
            key = item.name.strip().lower()
            if not key:
                continue
            priority: GapPriority = (
                "Critical" if item.priority == "required" else "Recommended"
            )
            # Critical wins over Recommended if the same name appears twice.
            if key not in gaps_by_name or priority == "Critical":
                gaps_by_name[key] = priority
            display_name.setdefault(key, item.name.strip())

        if not gaps_by_name:
            return SkillGapResult(gaps=[], critical=[], recommended=[])

        missing_names = [display_name[key] for key in gaps_by_name]
        resources = await self._suggest_learning_resources(missing_names)

        gaps: list[SkillGap] = []
        for key, priority in gaps_by_name.items():
            name = display_name[key]
            gaps.append(
                SkillGap(
                    skill=name,
                    priority=priority,
                    learning_resources=resources.get(
                        name,
                        [_FALLBACK_RESOURCE_TEMPLATE.format(skill=name)],
                    ),
                )
            )

        critical = [gap for gap in gaps if gap.priority == "Critical"]
        recommended = [gap for gap in gaps if gap.priority == "Recommended"]
        return SkillGapResult(gaps=gaps, critical=critical, recommended=recommended)

    async def _suggest_learning_resources(
        self, skills: list[str]
    ) -> dict[str, list[str]]:
        """Suggest learning resources for each missing skill via the LLM.

        Returns a mapping of skill name -> list of resource strings. Any
        LLM/transport failure or unusable output degrades gracefully to an empty
        mapping (callers then apply a generic per-skill fallback).

        Args:
            skills: The missing skill names to find resources for.

        Returns:
            A mapping from skill name to a list of resource strings. May be
            empty or omit some skills.
        """
        if not skills:
            return {}

        try:
            raw_response = await self._invoke_resources_llm(skills)
        except Exception:
            return {}

        payload = self._extract_json(raw_response)
        if not isinstance(payload, dict):
            return {}

        raw_resources = payload.get("resources")
        if not isinstance(raw_resources, dict):
            return {}

        result: dict[str, list[str]] = {}
        for skill in skills:
            value = raw_resources.get(skill)
            cleaned = self._coerce_resource_list(value)
            if cleaned:
                result[skill] = cleaned
        return result

    async def _invoke_resources_llm(self, skills: list[str]) -> str:
        """Invoke the chat model for learning-resource suggestions.

        Isolated from parsing so the normalisation logic can be exercised with
        canned responses and no live model.
        """
        model = get_chat_model()
        skills_json = json.dumps(skills)
        messages = [
            ("system", _RESOURCES_SYSTEM_PROMPT),
            ("human", _RESOURCES_PROMPT_TEMPLATE.format(skills=skills_json)),
        ]
        response = await model.ainvoke(messages)
        return self._content_to_text(getattr(response, "content", response))

    @staticmethod
    def _coerce_resource_list(value: Any) -> list[str]:
        """Coerce a raw resource value into a list of non-empty strings.

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
    def _normalise_skill_list(skills: list[str]) -> list[str]:
        """Trim, lower-case, and drop empty resume-skill strings."""
        result: list[str] = []
        for skill in skills or []:
            if isinstance(skill, str) and skill.strip():
                result.append(skill.strip().lower())
        return result

    @classmethod
    def _skill_present(cls, tech_name: str, resume_skills: list[str]) -> bool:
        """Whether a tech-stack item is covered by any resume skill.

        Matches when a resume skill equals the tech name, or when either string
        contains the other as a whole-word/phrase (case-insensitive), tolerating
        parenthetical expansions and extra descriptors.
        """
        name = (tech_name or "").strip().lower()
        if not name:
            return True  # Nothing to look for — treat as covered (skip it).
        for resume_skill in resume_skills:
            if resume_skill == name:
                return True
            if cls._whole_word_contains(resume_skill, name):
                return True
            if cls._whole_word_contains(name, resume_skill):
                return True
        return False

    @staticmethod
    def _whole_word_contains(haystack: str, needle: str) -> bool:
        """Whole-word / phrase containment check (both already lower-cased)."""
        if not haystack or not needle:
            return False
        pattern = r"\b" + re.escape(needle) + r"\b"
        return re.search(pattern, haystack) is not None

    # -- LLM invocation (isolated for testability) --------------------------

    async def _invoke_llm(self, jd_text: str) -> str:
        """Invoke the configured chat model and return its raw text content.

        Isolated from parsing so that :meth:`_parse_llm_response` can be tested
        with canned responses and no live model.

        Args:
            jd_text: The job-description text to embed in the prompt.

        Returns:
            The model's response content as a string.
        """
        model = get_chat_model()
        messages = [
            ("system", _SYSTEM_PROMPT),
            ("human", _PROMPT_TEMPLATE.format(jd_text=jd_text)),
        ]
        response = await model.ainvoke(messages)
        return self._content_to_text(getattr(response, "content", response))

    # -- Parsing / normalisation --------------------------------------------

    def _parse_llm_response(self, raw_response: str) -> list[TechStackItem]:
        """Parse and normalise the LLM response into valid tech-stack items.

        Extracts the JSON payload (tolerating surrounding prose or markdown
        code fences), then normalises each entry's category and priority to the
        schema's allowed values, dropping unnamed or structurally-invalid
        entries. Duplicate ``(name, category, priority)`` combinations are
        removed while preserving order.

        Args:
            raw_response: The raw string returned by the LLM.

        Returns:
            A list of validated, de-duplicated :class:`TechStackItem` objects
            (possibly empty).
        """
        payload = self._extract_json(raw_response)
        if payload is None:
            return []

        raw_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            return []

        items: list[TechStackItem] = []
        seen: set[tuple[str, str, str]] = set()
        for entry in raw_items:
            item = self._coerce_item(entry)
            if item is None:
                continue
            key = (item.name.lower(), item.category, item.priority)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        return items

    def _coerce_item(self, entry: Any) -> TechStackItem | None:
        """Coerce a single raw LLM entry into a valid :class:`TechStackItem`.

        Returns ``None`` when the entry is not a mapping or has no usable name.
        Invalid/empty category and priority values are coerced to safe defaults
        rather than causing the entry to be dropped.
        """
        if not isinstance(entry, dict):
            return None

        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            return None

        category = self._normalise_category(entry.get("category"))
        priority = self._normalise_priority(entry.get("priority"))

        return TechStackItem(
            name=name.strip(),
            category=category,
            priority=priority,
        )

    @staticmethod
    def _normalise_category(value: Any) -> TechCategory:
        """Map a free-form category value onto an allowed category Literal."""
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in _VALID_CATEGORIES:
                return cleaned  # type: ignore[return-value]
            if cleaned in _CATEGORY_ALIASES:
                return _CATEGORY_ALIASES[cleaned]
        return _DEFAULT_CATEGORY

    @staticmethod
    def _normalise_priority(value: Any) -> TechPriority:
        """Map a free-form priority value onto an allowed priority Literal."""
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in _VALID_PRIORITIES:
                return cleaned  # type: ignore[return-value]
            # Normalise separators (spaces/hyphens) before alias lookup.
            if cleaned in _PRIORITY_ALIASES:
                return _PRIORITY_ALIASES[cleaned]
            collapsed = re.sub(r"[\s\-]+", "_", cleaned)
            if collapsed in _VALID_PRIORITIES:
                return collapsed  # type: ignore[return-value]
        return _DEFAULT_PRIORITY

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

    # -- Result assembly ----------------------------------------------------

    def _build_result(self, items: list[TechStackItem]) -> TechStackResult:
        """Assemble a :class:`TechStackResult` from validated items.

        Splits items into ``required`` and ``nice_to_have`` lists. When no items
        were found, returns the informational empty result (Requirement 2.3).
        """
        if not items:
            return self._empty_result()

        required = [item for item in items if item.priority == "required"]
        nice_to_have = [item for item in items if item.priority == "nice_to_have"]

        return TechStackResult(
            items=items,
            required=required,
            nice_to_have=nice_to_have,
            message=None,
        )

    @staticmethod
    def _empty_result() -> TechStackResult:
        """Return an empty result with the manual-review message (Req 2.3)."""
        return TechStackResult(
            items=[],
            required=[],
            nice_to_have=[],
            message=_NO_TECH_MESSAGE,
        )
