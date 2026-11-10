"""
Cover Letter Service.

Generate a tailored cover letter for a specific job from the user's parsed
resume and a scraped job description, and export it as a downloadable Word
document.

The service produces two artifacts:

* :meth:`CoverLetterService.generate` asks a LangChain chat model to write a
  structured cover letter — an opening paragraph, one or more body paragraphs
  highlighting relevant qualifications drawn from the resume, and a closing
  paragraph (Requirements 10.1, 10.2). The tone and content depth are tailored
  to the candidate's ``experience_level`` (Requirement 10.3). The model is
  instructed to draw ONLY from the provided resume content and to never
  fabricate qualifications the candidate does not have, mirroring the
  factual-accuracy constraint used by the resume editor.
* :meth:`CoverLetterService.export_docx` renders the generated plain-text
  cover letter into a new ``.docx`` using ``python-docx`` and saves it to the
  configured ``generated`` directory, returning the filesystem path.

Design notes
------------
* The LLM invocation is isolated in :meth:`CoverLetterService._invoke_llm` so
  the surrounding logic can be exercised in tests without a live model,
  mirroring :class:`InterviewPrepService` and :class:`ResumeEditorService`.
* :meth:`generate` degrades gracefully: any LLM/transport failure or empty
  output falls back to a deterministic cover letter assembled from the resume
  and JD fields rather than raising.
* Document export is deterministic and LLM-free so output is stable and
  testable.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from docx import Document

from config import settings
from schemas import ParsedResume, ScrapedJD
from services.llm import get_chat_model

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: System prompt instructing the model to write a structured, factual cover
#: letter. As with the resume editor, the model must never invent
#: qualifications the candidate does not already have (Requirement 10.1).
_SYSTEM_PROMPT = (
    "You are an expert career coach who writes compelling, professional cover "
    "letters tailored to a specific job description. You NEVER invent skills, "
    "experience, employers, dates, achievements, or credentials the candidate "
    "does not already have — you only draw from the resume content provided. "
    "You respond with ONLY the cover letter body text, in plain prose, with "
    "paragraphs separated by a single blank line, and no markdown, headers, "
    "addresses, dates, or salutation/signature placeholders beyond the letter "
    "itself."
)

#: User prompt template for cover-letter generation. ``{job_title}``,
#: ``{company}``, ``{experience_level}``, ``{jd_block}`` and ``{resume_block}``
#: are substituted with the relevant context.
_PROMPT_TEMPLATE = """\
Write a tailored cover letter for the candidate described below applying to the
following role. The candidate's self-reported experience level is
"{experience_level}".

STRUCTURE (Requirement 10.2):
- An opening paragraph that states the role being applied for and expresses
  genuine interest in the company.
- One or more body paragraphs that highlight the candidate's most relevant
  qualifications, skills, and experience for THIS job, drawing specific
  evidence from the resume content provided.
- A closing paragraph that reiterates interest, adds a call to action, and
  thanks the reader.

STRICT RULES:
- Do NOT fabricate skills, experience, employers, dates, achievements, or
  credentials. Only reference qualifications evidenced by the resume below.
- Tailor the tone and depth to the experience level "{experience_level}": more
  junior levels should emphasise enthusiasm, learning, and transferable
  skills, while more senior levels should emphasise leadership, impact, and
  strategic contributions (Requirement 10.3).
- Keep it concise and professional (roughly 3-5 paragraphs).
- Output ONLY the cover letter text itself, with paragraphs separated by a
  single blank line. Do not include a date, mailing address, or markdown.

TARGET ROLE: {job_title} at {company}

JOB DESCRIPTION:
{jd_block}

CANDIDATE RESUME:
{resume_block}
"""


class CoverLetterService:
    """Generate tailored cover letters and export them as Word documents."""

    # -- Public API: generation --------------------------------------------

    async def generate(
        self,
        resume: ParsedResume,
        jd: ScrapedJD,
        experience_level: str,
    ) -> str:
        """Generate a cover letter tailored to the job and resume.

        Uses an LLM to write a structured cover letter — opening paragraph,
        body paragraph(s) highlighting relevant qualifications drawn from the
        resume, and a closing paragraph (Requirements 10.1, 10.2) — with the
        tone and content depth tailored to ``experience_level``
        (Requirement 10.3). The prompt constrains the model to draw only from
        the provided resume content and to never fabricate qualifications.

        Any LLM/transport failure, or empty/unusable output, degrades
        gracefully to a deterministically-generated cover letter assembled from
        the resume and JD fields rather than raising.

        Args:
            resume: The user's parsed base resume.
            jd: The scraped, structured job description.
            experience_level: The candidate's experience level used to tailor
                the tone and depth of the letter.

        Returns:
            The cover letter as plain text, with paragraphs separated by blank
            lines.
        """
        level = (experience_level or "").strip() or "unspecified"

        try:
            raw_response = await self._invoke_llm(
                _SYSTEM_PROMPT,
                _PROMPT_TEMPLATE.format(
                    job_title=jd.job_title or "the role",
                    company=jd.company_name or "the company",
                    experience_level=level,
                    jd_block=self._jd_to_text(jd),
                    resume_block=self._resume_to_text(resume),
                ),
            )
        except Exception:
            # Any LLM/transport failure degrades gracefully to a deterministic
            # fallback letter, mirroring the other services.
            return self._fallback_letter(resume, jd, level)

        content = (raw_response or "").strip()
        if not content:
            return self._fallback_letter(resume, jd, level)
        return content

    # -- Public API: export -------------------------------------------------

    def export_docx(self, content: str, job_title: str, company: str) -> str:
        """Render a cover letter into a new ``.docx`` and return its path.

        Splits ``content`` into paragraphs on blank lines/newlines and writes
        each as a ``python-docx`` paragraph, producing a downloadable Word
        document (Requirement 10 download support). The file is saved to the
        configured ``generated`` directory (``settings.generated_dir``) under a
        unique filename; no existing file is overwritten.

        Args:
            content: The cover letter text (paragraphs separated by blank
                lines).
            job_title: The target job title (included as light context).
            company: The target company name (included as light context).

        Returns:
            The filesystem path to the generated ``.docx`` file.
        """
        document = Document()

        title = (job_title or "").strip()
        org = (company or "").strip()
        if title or org:
            context = " — ".join(bit for bit in (title, org) if bit)
            heading = document.add_paragraph()
            run = heading.add_run(f"Cover Letter: {context}")
            run.bold = True

        for paragraph_text in self._split_paragraphs(content):
            document.add_paragraph(paragraph_text)

        out_dir = Path(settings.generated_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"cover_letter_{uuid.uuid4().hex}.docx"
        document.save(str(out_path))
        return str(out_path)

    # -- LLM invocation (isolated for testability) --------------------------

    async def _invoke_llm(self, system_prompt: str, human_prompt: str) -> str:
        """Invoke the configured chat model and return its raw text content.

        Isolated from the surrounding logic so the generation/fallback and
        export behaviour can be tested with canned responses and no live model,
        mirroring :meth:`InterviewPrepService._invoke_llm` and
        :meth:`ResumeEditorService._invoke_llm`.

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

    # -- Deterministic fallback --------------------------------------------

    def _fallback_letter(
        self, resume: ParsedResume, jd: ScrapedJD, experience_level: str
    ) -> str:
        """Assemble a reasonable cover letter from resume + JD fields.

        Used when the LLM is unavailable or returns nothing. The letter keeps
        the required opening/body/closing structure (Requirement 10.2), tailors
        the opening framing to ``experience_level`` (Requirement 10.3), and only
        references qualifications present in the resume (Requirement 10.1).
        """
        name = (resume.contact.name or "").strip()
        job_title = (jd.job_title or "the role").strip() or "the role"
        company = (jd.company_name or "your organization").strip() or (
            "your organization"
        )

        # Opening paragraph, framed by experience level.
        level = experience_level.strip().lower()
        if level in {"fresher", "junior", "entry", "entry-level", "entry level"}:
            framing = (
                "As an early-career professional, I am eager to bring my "
                "enthusiasm and growing skill set to your team."
            )
        elif level in {"senior", "lead", "lead/architect", "architect", "principal"}:
            framing = (
                "As a seasoned professional, I am excited to bring my "
                "leadership experience and proven track record to this role."
            )
        else:
            framing = (
                "I am confident that my background aligns well with what this "
                "role requires."
            )
        opening = (
            f"I am writing to express my strong interest in the {job_title} "
            f"position at {company}. {framing}"
        )

        # Body paragraph, drawing only from resume content.
        body_sentences: list[str] = []
        if resume.skills:
            relevant = self._relevant_skills(resume.skills, jd)
            skills_shown = relevant or resume.skills
            body_sentences.append(
                "My skills include "
                + ", ".join(skills_shown[:10])
                + ", which I believe are directly applicable to this role."
            )
        if resume.experience:
            top = resume.experience[0]
            role_bits = [b for b in (top.title, top.company) if b]
            if role_bits:
                body_sentences.append(
                    "In my role as "
                    + " at ".join(role_bits)
                    + ", I developed experience relevant to your team's needs."
                )
            elif top.description:
                body_sentences.append(top.description.strip())
        if resume.certifications:
            body_sentences.append(
                "I also hold the following credentials: "
                + ", ".join(resume.certifications[:5])
                + "."
            )
        if not body_sentences:
            body_sentences.append(
                "My background has prepared me to contribute effectively in "
                "this position."
            )
        body = " ".join(body_sentences)

        # Closing paragraph.
        signoff = f"\n\nSincerely,\n{name}" if name else ""
        closing = (
            f"I would welcome the opportunity to discuss how my background can "
            f"contribute to {company}. Thank you for your time and "
            f"consideration.{signoff}"
        )

        return "\n\n".join([opening, body, closing])

    @staticmethod
    def _relevant_skills(skills: list[str], jd: ScrapedJD) -> list[str]:
        """Return resume skills that overlap the JD's required/preferred skills.

        Matching is case-insensitive. Preserves the resume's ordering and does
        not invent any skill not already present on the resume.
        """
        wanted = {
            s.strip().lower()
            for s in (jd.required_skills or []) + (jd.preferred_skills or [])
            if s and s.strip()
        }
        if not wanted:
            return []
        return [s for s in skills if s and s.strip().lower() in wanted]

    # -- Prompt context formatting -----------------------------------------

    @staticmethod
    def _jd_to_text(jd: ScrapedJD) -> str:
        """Assemble a compact textual summary of a :class:`ScrapedJD`.

        Combines the salient fields (title, company, location, experience,
        required/preferred skills, description body) into a single string
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

    @staticmethod
    def _resume_to_text(resume: ParsedResume) -> str:
        """Render the parsed resume into a compact prompt block.

        Prefers the structured sections (contact, skills, experience,
        education, certifications); falls back to raw text when the structured
        sections are empty. Missing/empty fields are omitted.
        """
        parts: list[str] = []

        contact = resume.contact
        if contact.name:
            parts.append(f"Name: {contact.name}")
        contact_bits = [b for b in (contact.email, contact.phone, contact.location) if b]
        if contact_bits:
            parts.append("Contact: " + " | ".join(contact_bits))

        if resume.skills:
            parts.append("Skills: " + ", ".join(resume.skills))

        if resume.experience:
            parts.append("Experience:")
            for entry in resume.experience:
                header = " — ".join(b for b in (entry.title, entry.company) if b)
                date_bits = [b for b in (entry.start_date, entry.end_date) if b]
                if date_bits:
                    header = (
                        f"{header} ({' - '.join(date_bits)})"
                        if header
                        else " - ".join(date_bits)
                    )
                if header:
                    parts.append(f"- {header}")
                if entry.description:
                    parts.append(f"  {entry.description}")
                for highlight in entry.highlights:
                    parts.append(f"  * {highlight}")

        if resume.education:
            parts.append("Education:")
            for edu in resume.education:
                line = ", ".join(
                    b
                    for b in (edu.degree, edu.field_of_study, edu.institution)
                    if b
                )
                if line:
                    parts.append(f"- {line}")

        if resume.certifications:
            parts.append("Certifications: " + ", ".join(resume.certifications))

        if not parts:
            return resume.raw_text or "(no resume content available)"
        return "\n".join(parts)

    # -- Text / docx helpers ------------------------------------------------

    @staticmethod
    def _split_paragraphs(content: str) -> list[str]:
        """Split cover-letter text into clean paragraphs for the document.

        Paragraphs are separated by blank lines; a single newline within a
        paragraph is collapsed into a space so that soft-wrapped lines render as
        one paragraph. Empty paragraphs are dropped. When ``content`` has no
        blank-line separators, each non-empty line becomes its own paragraph.
        """
        if not content or not content.strip():
            return []

        normalised = content.replace("\r\n", "\n").replace("\r", "\n").strip()

        # Prefer splitting on blank lines (paragraph breaks).
        if re.search(r"\n\s*\n", normalised):
            blocks = re.split(r"\n\s*\n", normalised)
        else:
            blocks = normalised.split("\n")

        paragraphs: list[str] = []
        for block in blocks:
            # Collapse internal single newlines/whitespace into single spaces.
            cleaned = re.sub(r"\s*\n\s*", " ", block).strip()
            cleaned = re.sub(r"[ \t]+", " ", cleaned)
            if cleaned:
                paragraphs.append(cleaned)
        return paragraphs

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
