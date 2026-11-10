"""
Resume Parser Service.

Parse an uploaded Base_Resume (PDF or DOCX) into structured sections — contact
information, skills, work experience, education, and certifications — for reuse
across the application lifecycle (Requirements 3.1, 3.2).

The pipeline has two stages:

1. **Raw text extraction** (synchronous, library-backed):
   * :meth:`ResumeParserService._parse_pdf` uses ``pypdf`` to concatenate the
     text of every page of a PDF file.
   * :meth:`ResumeParserService._parse_docx` uses ``python-docx`` to read the
     text of every paragraph (and table cell) of a Word document.

2. **Structured section extraction** (asynchronous, LLM-backed):
   * :meth:`ResumeParserService._extract_sections` asks a LangChain chat model
     (see :func:`services.llm.get_chat_model`) to return a strict JSON object
     describing the contact info, skills, experience, education, and
     certifications found in the raw text, then validates/coerces that payload
     defensively into a :class:`~schemas.ParsedResume`.

The service is deliberately robust:

* Unsupported file types raise :class:`UnsupportedResumeFormatError`
  (Requirement 3.7) with a message naming the supported formats.
* Corrupted / unreadable files raise :class:`ResumeParseError` (Requirement 3.8)
  wrapping the underlying library error with a descriptive message.
* If the LLM is unreachable or returns unusable output, section extraction
  degrades gracefully to an (otherwise empty) :class:`ParsedResume` that still
  carries the extracted ``raw_text`` — mirroring how the tech-stack extractor
  tolerates LLM failures — rather than raising.

Note on the public interface: the design sketches ``parse`` as synchronous, but
structured section extraction depends on an asynchronous LLM call. ``parse`` is
therefore implemented as ``async def`` — it performs the synchronous raw-text
extraction, then awaits :meth:`_extract_sections`.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pypdf import PdfReader
from docx import Document

from schemas import ContactInfo, Education, ParsedResume, WorkExperience
from services.llm import get_chat_model

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

#: Supported resume file types (normalised, lower-case, no leading dot).
_SUPPORTED_FILE_TYPES: frozenset[str] = frozenset({"pdf", "docx"})

#: User-facing warnings surfaced on the upload response when structured
#: extraction could not populate the sections (skills, experience, ...).
_WARN_NO_TEXT = (
    "We couldn't read any text from this file. If it's a scanned or "
    "image-based PDF, please upload a text-based PDF (e.g. 'Save as PDF' from "
    "Word) or the .docx version instead."
)
_WARN_LLM_FAILED = (
    "The resume was uploaded, but the AI service couldn't be reached to "
    "extract skills and other details. Check the LLM settings "
    "(LLM_API_KEY, LLM_MODEL, LLM_API_BASE), then re-upload to try again."
)
_WARN_LLM_UNPARSEABLE = (
    "The resume was uploaded, but the AI service returned an unexpected "
    "response, so skills and other details couldn't be extracted. "
    "Please re-upload to try again."
)
_WARN_NO_SKILLS = (
    "The resume was uploaded, but no skills were detected in it. If your "
    "resume lists skills, consider adding a clearly labelled 'Skills' section."
)

#: Known technologies/skills used as a deterministic fallback when the LLM
#: returns no skills (e.g. skills embedded in DOCX tables, or model variance).
#: Matched case-insensitively as whole words/phrases against the raw text.
_KNOWN_SKILLS: tuple[str, ...] = (
    # Languages
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "C",
    "Go", "Golang", "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala",
    "R", "MATLAB", "Perl", "Shell Scripting", "Bash", "SQL", "PL/SQL",
    "VBA", "Groovy", "Dart", "Objective-C",
    # Frameworks / libraries
    "Spring Boot", "Spring", "Spring Data", "Hibernate", "JPA", "Django",
    "Flask", "FastAPI", "React", "ReactJS", "Angular", "AngularJS", "Vue",
    "Vue.js", "Node.js", "NodeJS", "Express", "Express.js", "Next.js",
    "Backbone.js", "Backbone js", "Require js", "jQuery", "Bootstrap",
    "Tailwind", "Redux", ".NET", "ASP.NET", "Laravel", "Rails",
    "TensorFlow", "PyTorch", "Keras", "scikit-learn", "Pandas", "NumPy",
    "LangChain", "Spark", "Hadoop", "Kafka",
    # Web / markup
    "HTML", "HTML5", "CSS", "CSS3", "SASS", "LESS", "REST", "GraphQL",
    "SOAP", "gRPC", "Microservices", "Micro services",
    # Databases
    "PostgreSQL", "MySQL", "Oracle", "SQL Server", "SQLite", "MongoDB",
    "Redis", "Cassandra", "DynamoDB", "Elasticsearch", "Elastic Search",
    "Neo4j", "MariaDB",
    # Cloud / devops
    "AWS", "Azure", "GCP", "Google Cloud", "Docker", "Kubernetes", "K8s",
    "Terraform", "Ansible", "Jenkins", "GitLab", "GitHub", "Git", "SVN",
    "Subversion", "CI/CD", "Maven", "Gradle", "Apache Tomcat", "Tomcat",
    "JBoss", "Wildfly", "Nginx", "Linux", "Unix", "Windows", "ELK",
    "Logstash", "Kibana", "Prometheus", "Grafana",
    # Tools / methodologies
    "Jira", "Confluence", "Postman", "Eclipse", "IntelliJ", "VS Code",
    "Putty", "Agile", "Scrum", "Kanban", "Waterfall", "TDD", "Pair Programming",
    "Data Structures", "Algorithms", "Object Oriented Programming", "OOP",
    "SDLC", "Alfresco", "Documentum",
)

#: System prompt instructing the model to return strict JSON.
_SYSTEM_PROMPT = (
    "You are an expert resume parser. You read raw resume text and extract its "
    "structured sections. You respond ONLY with valid JSON."
)

#: User prompt template. ``{resume_text}`` is substituted with the raw text.
_PROMPT_TEMPLATE = """\
Parse the following resume text into structured sections.

Extract:
- "contact": an object with "name", "email", "phone", "location" (all strings or
  null) and "links" (a list of URLs/handles such as LinkedIn/GitHub/portfolio).
- "skills": a flat list of distinct technical and professional skills (strings).
- "experience": a list of work-experience objects, each with "title",
  "company", "start_date", "end_date" (strings or null; use "Present" for
  current roles) and "description" (string or null) and "highlights" (a list of
  bullet-point strings).
- "education": a list of education objects, each with "degree", "institution",
  "field_of_study", "start_date", "end_date" (strings or null).
- "certifications": a flat list of certification names (strings).

Respond with ONLY a JSON object of the form:
{{"contact": {{"name": "...", "email": "...", "phone": "...", "location": "...", "links": ["..."]}},
  "skills": ["..."],
  "experience": [{{"title": "...", "company": "...", "start_date": "...", "end_date": "...", "description": "...", "highlights": ["..."]}}],
  "education": [{{"degree": "...", "institution": "...", "field_of_study": "...", "start_date": "...", "end_date": "..."}}],
  "certifications": ["..."]}}

Use null for any field you cannot find. Use empty lists for missing list
sections. Do not invent information that is not present in the resume text.
Do not include any prose, explanation, or markdown fences.

Resume text:
\"\"\"
{resume_text}
\"\"\"
"""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class UnsupportedResumeFormatError(ValueError):
    """Raised when the supplied file type is not a supported resume format.

    Supported formats are PDF (``.pdf``) and Word (``.docx``) — see
    Requirement 3.7.
    """


class ResumeParseError(RuntimeError):
    """Raised when a resume file cannot be read/parsed.

    This typically indicates corrupted content or unreadable formatting — see
    Requirement 3.8. The underlying library error is chained as ``__cause__``.
    """


class ResumeParserService:
    """Parse uploaded resume files (PDF/DOCX) into structured data."""

    async def parse(self, file_path: str, file_type: str) -> ParsedResume:
        """Parse a resume file into a structured :class:`ParsedResume`.

        Validates the file type (Requirement 3.7), extracts the raw text with
        the appropriate library (Requirement 3.1), then uses an LLM to extract
        structured sections — contact info, skills, experience, education, and
        certifications (Requirement 3.2).

        Note: structured extraction depends on an asynchronous LLM call, so this
        method is ``async`` even though the design sketches it as synchronous.
        The raw-text extraction helpers (:meth:`_parse_pdf` / :meth:`_parse_docx`)
        remain synchronous.

        Args:
            file_path: Filesystem path to the uploaded resume file.
            file_type: The file's type/extension — "pdf" or "docx"
                (case-insensitive; a leading dot is tolerated).

        Returns:
            A :class:`ParsedResume`. ``raw_text`` is always populated with the
            extracted text; the structured sections are best-effort and may be
            empty if the LLM could not be reached or returned unusable output.

        Raises:
            UnsupportedResumeFormatError: If ``file_type`` is not "pdf"/"docx".
            ResumeParseError: If the file cannot be read/parsed (corrupted or
                unreadable content).
        """
        normalised = self._normalise_file_type(file_type)

        if normalised == "pdf":
            raw_text = self._parse_pdf(file_path)
        else:  # "docx"
            raw_text = self._parse_docx(file_path)

        return await self._extract_sections(raw_text)

    # -- File type validation ----------------------------------------------

    @staticmethod
    def _normalise_file_type(file_type: str) -> str:
        """Normalise and validate a file type to "pdf" or "docx".

        Lower-cases the value and strips surrounding whitespace and any leading
        dot (so ".PDF", "pdf", and " .docx " are all accepted).

        Raises:
            UnsupportedResumeFormatError: If the normalised type is unsupported.
        """
        cleaned = (file_type or "").strip().lower().lstrip(".")
        if cleaned not in _SUPPORTED_FILE_TYPES:
            raise UnsupportedResumeFormatError(
                f"Unsupported resume format '{file_type}'. "
                "Supported formats are PDF (.pdf) and Word (.docx)."
            )
        return cleaned

    # -- Raw text extraction (synchronous, library-backed) -----------------

    def _parse_pdf(self, file_path: str) -> str:
        """Extract text from a PDF file using ``pypdf``.

        Concatenates the extracted text of every page, separated by newlines.

        Args:
            file_path: Filesystem path to the PDF file.

        Returns:
            The extracted text (possibly empty if the PDF has no text layer).

        Raises:
            ResumeParseError: If the PDF cannot be opened or read (corrupted or
                unreadable content — Requirement 3.8).
        """
        try:
            reader = PdfReader(file_path)
            pages: list[str] = []
            for page in reader.pages:
                extracted = page.extract_text() or ""
                if extracted:
                    pages.append(extracted)
            return "\n".join(pages).strip()
        except ResumeParseError:
            raise
        except Exception as exc:  # noqa: BLE001 - wrap any library/IO failure
            raise ResumeParseError(
                f"Failed to parse PDF resume '{file_path}': the file may be "
                "corrupted or in an unreadable format."
            ) from exc

    def _parse_docx(self, file_path: str) -> str:
        """Extract text from a Word document using ``python-docx``.

        Concatenates the text of every paragraph and every table cell, each on
        its own line, preserving the document's top-to-bottom reading order for
        paragraphs followed by tables.

        Args:
            file_path: Filesystem path to the ``.docx`` file.

        Returns:
            The extracted text (possibly empty for an empty document).

        Raises:
            ResumeParseError: If the document cannot be opened or read
                (corrupted or unreadable content — Requirement 3.8).
        """
        try:
            document = Document(file_path)

            lines: list[str] = []
            for paragraph in document.paragraphs:
                text = paragraph.text.strip()
                if text:
                    lines.append(text)

            # Tables often hold skills/contact details in resume templates.
            for table in document.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    row_text = " | ".join(c for c in cells if c)
                    if row_text:
                        lines.append(row_text)

            return "\n".join(lines).strip()
        except ResumeParseError:
            raise
        except Exception as exc:  # noqa: BLE001 - wrap any library/IO failure
            raise ResumeParseError(
                f"Failed to parse Word resume '{file_path}': the file may be "
                "corrupted or in an unreadable format."
            ) from exc

    # -- Structured section extraction (asynchronous, LLM-backed) ----------

    async def _extract_sections(self, text: str) -> ParsedResume:
        """Use an LLM to extract structured sections from raw resume text.

        Produces a :class:`ParsedResume` with contact info, skills, experience,
        education, and certifications (Requirement 3.2). ``raw_text`` is always
        set to ``text``.

        If ``text`` is empty, or the LLM cannot be reached / returns unusable
        output, this degrades gracefully to a :class:`ParsedResume` with empty
        structured sections (but ``raw_text`` populated) rather than raising.

        Args:
            text: The raw resume text to analyse.

        Returns:
            A best-effort :class:`ParsedResume`.
        """
        raw_text = text or ""

        if not raw_text.strip():
            # No text layer was extracted from the file (e.g. a scanned/image
            # PDF). The LLM has nothing to work with, so every section is empty.
            logger.warning(
                "Resume raw-text extraction produced no text; skills and other "
                "sections will be empty. The file may be a scanned/image PDF "
                "with no selectable text."
            )
            return ParsedResume(raw_text=raw_text, warning=_WARN_NO_TEXT)

        try:
            raw_response = await self._invoke_llm(raw_text)
        except Exception:
            # Any LLM/transport failure degrades gracefully: return the raw text
            # with empty structured sections rather than surfacing an error.
            logger.exception(
                "LLM invocation failed during resume section extraction; "
                "returning empty structured sections. Check LLM_API_KEY, "
                "LLM_MODEL, and LLM_API_BASE in your .env."
            )
            return ParsedResume(raw_text=raw_text, warning=_WARN_LLM_FAILED)

        payload = self._extract_json(raw_response)
        if not isinstance(payload, dict):
            logger.warning(
                "LLM response could not be parsed as a JSON object during "
                "resume section extraction; returning empty sections. "
                "First 200 chars of response: %r",
                (raw_response or "")[:200],
            )
            return ParsedResume(raw_text=raw_text, warning=_WARN_LLM_UNPARSEABLE)

        parsed = ParsedResume(
            contact=self._coerce_contact(payload.get("contact")),
            skills=self._coerce_str_list(payload.get("skills")),
            experience=self._coerce_experience(payload.get("experience")),
            education=self._coerce_education(payload.get("education")),
            certifications=self._coerce_str_list(payload.get("certifications")),
            raw_text=raw_text,
        )
        if not parsed.skills:
            # The LLM returned no skills. Fall back to deterministic keyword
            # matching against the raw text so skills still populate when the
            # model misses them (e.g. skills embedded in DOCX tables).
            fallback = self._keyword_skills(raw_text)
            if fallback:
                logger.info(
                    "LLM returned no skills; keyword fallback matched %d skills.",
                    len(fallback),
                )
                parsed.skills = fallback
            else:
                logger.info(
                    "Resume parsed but no skills were extracted (LLM and keyword "
                    "fallback). Raw text length=%d.",
                    len(raw_text),
                )
                parsed.warning = _WARN_NO_SKILLS
        return parsed

    @staticmethod
    def _keyword_skills(raw_text: str) -> list[str]:
        """Scan raw resume text for known skills (deterministic fallback).

        Matches each entry in :data:`_KNOWN_SKILLS` as a whole word/phrase,
        case-insensitively, preserving the canonical casing and de-duplicating
        overlapping synonyms (e.g. "ReactJS" vs "React").

        Args:
            raw_text: The raw extracted resume text.

        Returns:
            A list of detected skill names (canonical casing), possibly empty.
        """
        if not raw_text:
            return []
        found: list[str] = []
        seen: set[str] = set()
        for skill in _KNOWN_SKILLS:
            key = skill.lower()
            if key in seen:
                continue
            # Word-boundary match; escape regex metacharacters in the skill.
            pattern = r"(?<![\w])" + re.escape(skill) + r"(?![\w])"
            if re.search(pattern, raw_text, re.IGNORECASE):
                seen.add(key)
                found.append(skill)
        return found

    # -- LLM invocation (isolated for testability) --------------------------

    async def _invoke_llm(self, resume_text: str) -> str:
        """Invoke the configured chat model and return its raw text content.

        Isolated from parsing so the normalisation logic can be exercised with
        canned responses and no live model.

        Args:
            resume_text: The raw resume text to embed in the prompt.

        Returns:
            The model's response content as a string.
        """
        model = get_chat_model()
        messages = [
            ("system", _SYSTEM_PROMPT),
            ("human", _PROMPT_TEMPLATE.format(resume_text=resume_text)),
        ]
        response = await model.ainvoke(messages)
        return self._content_to_text(getattr(response, "content", response))

    # -- Defensive coercion helpers -----------------------------------------

    def _coerce_contact(self, value: Any) -> ContactInfo:
        """Coerce a raw contact mapping into a :class:`ContactInfo`.

        Non-mapping input yields an empty :class:`ContactInfo`.
        """
        if not isinstance(value, dict):
            return ContactInfo()
        return ContactInfo(
            name=self._coerce_optional_str(value.get("name")),
            email=self._coerce_optional_str(value.get("email")),
            phone=self._coerce_optional_str(value.get("phone")),
            location=self._coerce_optional_str(value.get("location")),
            links=self._coerce_str_list(value.get("links")),
        )

    def _coerce_experience(self, value: Any) -> list[WorkExperience]:
        """Coerce a raw experience list into :class:`WorkExperience` entries.

        Non-list input yields an empty list; entries that are not mappings or
        carry no usable content are dropped.
        """
        if not isinstance(value, list):
            return []
        entries: list[WorkExperience] = []
        for raw in value:
            if not isinstance(raw, dict):
                continue
            entry = WorkExperience(
                title=self._coerce_optional_str(raw.get("title")),
                company=self._coerce_optional_str(raw.get("company")),
                start_date=self._coerce_optional_str(raw.get("start_date")),
                end_date=self._coerce_optional_str(raw.get("end_date")),
                description=self._coerce_optional_str(raw.get("description")),
                highlights=self._coerce_str_list(raw.get("highlights")),
            )
            if self._work_experience_is_empty(entry):
                continue
            entries.append(entry)
        return entries

    def _coerce_education(self, value: Any) -> list[Education]:
        """Coerce a raw education list into :class:`Education` entries.

        Non-list input yields an empty list; entries that are not mappings or
        carry no usable content are dropped.
        """
        if not isinstance(value, list):
            return []
        entries: list[Education] = []
        for raw in value:
            if not isinstance(raw, dict):
                continue
            entry = Education(
                degree=self._coerce_optional_str(raw.get("degree")),
                institution=self._coerce_optional_str(raw.get("institution")),
                field_of_study=self._coerce_optional_str(raw.get("field_of_study")),
                start_date=self._coerce_optional_str(raw.get("start_date")),
                end_date=self._coerce_optional_str(raw.get("end_date")),
            )
            if self._education_is_empty(entry):
                continue
            entries.append(entry)
        return entries

    @staticmethod
    def _work_experience_is_empty(entry: WorkExperience) -> bool:
        """Return True when a work-experience entry carries no usable content."""
        return not any(
            [
                entry.title,
                entry.company,
                entry.start_date,
                entry.end_date,
                entry.description,
                entry.highlights,
            ]
        )

    @staticmethod
    def _education_is_empty(entry: Education) -> bool:
        """Return True when an education entry carries no usable content."""
        return not any(
            [
                entry.degree,
                entry.institution,
                entry.field_of_study,
                entry.start_date,
                entry.end_date,
            ]
        )

    @staticmethod
    def _coerce_optional_str(value: Any) -> str | None:
        """Coerce a scalar value into a trimmed string, or ``None``.

        Empty / whitespace-only strings and JSON ``null`` become ``None``.
        """
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return None

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        """Coerce a raw value into a de-duplicated list of non-empty strings.

        Accepts a list (non-string / empty entries dropped) or a single string
        (returned as a one-element list). Any other type yields an empty list.
        Order is preserved; case-insensitive duplicates are removed.
        """
        raw_items: list[Any]
        if isinstance(value, list):
            raw_items = value
        elif isinstance(value, str):
            raw_items = [value]
        else:
            return []

        result: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
        return result

    # -- JSON / content extraction (shared pattern) -------------------------

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
