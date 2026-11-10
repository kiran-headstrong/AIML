"""
Export Service.

Render prepared interview material (ranked topics and categorized Q&A) into a
formatted, downloadable PDF using WeasyPrint.

:meth:`ExportService.export_interview_prep_pdf` builds a self-contained HTML
document and renders it to a PDF saved under the configured ``generated``
directory (``settings.generated_dir``), returning the filesystem path — the
same save-then-return-path convention used by
:class:`CoverLetterService.export_docx` and
:class:`ResumeEditorService.generate_tailored_docx` (Requirement 14.1). The PDF
is laid out with clear section headings per topic, a difficulty label on every
question, and readable answer/key-point formatting (Requirement 14.2), and it
carries the job title and company name as a header for reference
(Requirement 14.3). The returned path lets the router stream the file as a
download (Requirement 14.4).

Design notes
------------
* The HTML is assembled deterministically (no LLM involvement) so output is
  stable and testable; all user/LLM-sourced text is HTML-escaped to keep the
  generated markup well-formed.
* Topics are rendered in the order supplied (the router fetches them ordered by
  ``relevance_rank``); each topic's Q&A is grouped under its heading by a
  case-insensitive topic-name match, with any ungrouped Q&A rendered under a
  trailing "Additional Questions" section so nothing is dropped.

Import style follows the backend package convention (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

import html
import uuid
from pathlib import Path

from config import settings
from schemas import InterviewQA, InterviewTopic

# NOTE: WeasyPrint depends on native GTK/Pango libraries (e.g.
# ``libgobject-2.0``) that may not be present in every environment. Importing
# it at module load time would crash the whole application (and every router
# that transitively imports this module) on such systems. We therefore import
# it lazily inside ``export_interview_prep_pdf`` so the API boots normally and
# only PDF export — the single feature that needs it — fails, with a clear,
# actionable error message, when the native libraries are missing.

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Human-readable labels for the topic categories (schemas.TopicCategory).
_CATEGORY_LABELS: dict[str, str] = {
    "technical": "Technical",
    "domain": "Domain",
    "behavioral": "Behavioral",
}

#: Human-readable labels for the question difficulties (schemas.Difficulty).
_DIFFICULTY_LABELS: dict[str, str] = {
    "easy": "Easy",
    "medium": "Medium",
    "difficult": "Difficult",
}

#: Document stylesheet. Kept inline so the rendered PDF is self-contained and
#: the layout (headings, difficulty badges, readable answers) is deterministic.
_STYLESHEET = """
@page { size: A4; margin: 2cm; }
body {
    font-family: "Helvetica", "Arial", sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #1a1a1a;
}
h1.doc-title { font-size: 22pt; margin: 0 0 4px 0; color: #111; }
p.doc-subtitle { font-size: 13pt; margin: 0 0 4px 0; color: #444; }
p.doc-meta { font-size: 10pt; margin: 0 0 18px 0; color: #777; }
hr.rule { border: none; border-top: 2px solid #333; margin: 0 0 18px 0; }
h2.topic {
    font-size: 15pt;
    margin: 22px 0 2px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid #ccc;
    color: #0b3d66;
}
p.topic-category { font-size: 9pt; margin: 0 0 10px 0; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
div.qa { margin: 0 0 14px 0; page-break-inside: avoid; }
p.question { font-weight: bold; margin: 0 0 4px 0; color: #1a1a1a; }
span.difficulty {
    display: inline-block;
    font-size: 8pt;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 1px 6px;
    margin-right: 6px;
    border-radius: 3px;
    color: #fff;
    vertical-align: middle;
}
span.difficulty-easy { background: #2e7d32; }
span.difficulty-medium { background: #ef6c00; }
span.difficulty-difficult { background: #c62828; }
span.scenario-tag {
    display: inline-block;
    font-size: 8pt;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 1px 6px;
    margin-right: 6px;
    border-radius: 3px;
    color: #fff;
    background: #5e35b1;
    vertical-align: middle;
}
p.answer { margin: 0 0 6px 0; color: #222; }
p.key-points-label { font-size: 9.5pt; font-weight: bold; margin: 0 0 2px 0; color: #555; }
ul.key-points { margin: 0 0 4px 18px; padding: 0; }
ul.key-points li { margin: 0 0 2px 0; }
p.empty { font-style: italic; color: #888; }
"""


class ExportService:
    """Render interview preparation material to a downloadable PDF."""

    def export_interview_prep_pdf(
        self,
        topics: list[InterviewTopic],
        qa: list[InterviewQA],
        job_title: str,
        company_name: str,
    ) -> str:
        """Generate a formatted PDF of interview prep and return its file path.

        Builds a self-contained HTML document — a header carrying the job title
        and company name (Requirement 14.3), a section per topic with its
        category, and the topic's questions each labelled with a difficulty
        badge and readable answer/key-point formatting (Requirement 14.2) — and
        renders it to a PDF via WeasyPrint. The file is saved under the
        configured ``generated`` directory (``settings.generated_dir``) with a
        unique name and the path is returned so the caller can stream it as a
        download (Requirements 14.1, 14.4).

        Q&A entries are grouped under their topic by case-insensitive name
        match; any entries whose topic is not among ``topics`` are rendered in a
        trailing "Additional Questions" section so none are dropped.

        Args:
            topics: Ranked interview topics (rendered in the order supplied).
            qa: The generated question-and-answer entries.
            job_title: The target job title, shown in the header.
            company_name: The target company name, shown in the header.

        Returns:
            The filesystem path to the generated ``.pdf`` file.
        """
        try:
            from weasyprint import HTML
        except OSError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "PDF export is unavailable because WeasyPrint's native "
                "dependencies (GTK/Pango, e.g. libgobject-2.0) are not "
                "installed. See "
                "https://doc.courtbouillon.org/weasyprint/stable/first_steps.html"
                "#installation for setup instructions."
            ) from exc

        document_html = self._build_html(topics, qa, job_title, company_name)

        out_dir = Path(settings.generated_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"interview_prep_{uuid.uuid4().hex}.pdf"

        HTML(string=document_html).write_pdf(str(out_path))
        return str(out_path)

    # -- HTML assembly ------------------------------------------------------

    def _build_html(
        self,
        topics: list[InterviewTopic],
        qa: list[InterviewQA],
        job_title: str,
        company_name: str,
    ) -> str:
        """Assemble the full, self-contained HTML document for rendering."""
        title = (job_title or "").strip() or "Interview Preparation"
        company = (company_name or "").strip()

        parts: list[str] = [
            "<!DOCTYPE html>",
            '<html lang="en"><head><meta charset="utf-8">',
            f"<style>{_STYLESHEET}</style>",
            "</head><body>",
            self._render_header(title, company),
            self._render_body(topics, qa),
            "</body></html>",
        ]
        return "".join(parts)

    def _render_header(self, title: str, company: str) -> str:
        """Render the document header carrying job title and company name."""
        parts = [f'<h1 class="doc-title">{html.escape(title)}</h1>']
        if company:
            parts.append(
                f'<p class="doc-subtitle">{html.escape(company)}</p>'
            )
        parts.append('<p class="doc-meta">Interview Preparation</p>')
        parts.append('<hr class="rule">')
        return "".join(parts)

    def _render_body(
        self, topics: list[InterviewTopic], qa: list[InterviewQA]
    ) -> str:
        """Render all topic sections plus any ungrouped questions."""
        # Group Q&A by topic name (case-insensitive), preserving input order.
        grouped: dict[str, list[InterviewQA]] = {}
        for entry in qa:
            grouped.setdefault((entry.topic or "").strip().lower(), []).append(
                entry
            )

        parts: list[str] = []
        rendered_keys: set[str] = set()

        for topic in topics:
            key = (topic.name or "").strip().lower()
            rendered_keys.add(key)
            parts.append(self._render_topic_section(topic, grouped.get(key, [])))

        # Any Q&A whose topic did not match a supplied topic is still included.
        leftover: list[InterviewQA] = [
            entry
            for key, entries in grouped.items()
            if key not in rendered_keys
            for entry in entries
        ]
        if leftover:
            parts.append('<h2 class="topic">Additional Questions</h2>')
            for entry in leftover:
                parts.append(self._render_qa(entry))

        if not topics and not qa:
            parts.append(
                '<p class="empty">No interview preparation content '
                "available.</p>"
            )
        return "".join(parts)

    def _render_topic_section(
        self, topic: InterviewTopic, entries: list[InterviewQA]
    ) -> str:
        """Render a single topic heading, its category, and its Q&A."""
        name = (topic.name or "").strip() or "Untitled Topic"
        category = _CATEGORY_LABELS.get(topic.category, topic.category.title())

        parts = [
            f'<h2 class="topic">{html.escape(name)}</h2>',
            f'<p class="topic-category">{html.escape(category)}</p>',
        ]
        if entries:
            for entry in entries:
                parts.append(self._render_qa(entry))
        else:
            parts.append(
                '<p class="empty">No questions generated for this topic.</p>'
            )
        return "".join(parts)

    def _render_qa(self, entry: InterviewQA) -> str:
        """Render one question/answer block with a difficulty label."""
        difficulty_label = _DIFFICULTY_LABELS.get(
            entry.difficulty, entry.difficulty.title()
        )
        difficulty_badge = (
            f'<span class="difficulty difficulty-{html.escape(entry.difficulty)}">'
            f"{html.escape(difficulty_label)}</span>"
        )
        scenario_badge = (
            '<span class="scenario-tag">Scenario</span>'
            if entry.is_scenario_based
            else ""
        )

        parts = [
            '<div class="qa">',
            (
                '<p class="question">'
                f"{difficulty_badge}{scenario_badge}"
                f"{html.escape(entry.question or '')}</p>"
            ),
        ]

        answer = (entry.answer or "").strip()
        if answer:
            parts.append(f'<p class="answer">{html.escape(answer)}</p>')

        if entry.key_points:
            parts.append('<p class="key-points-label">Key points:</p>')
            parts.append('<ul class="key-points">')
            for point in entry.key_points:
                parts.append(f"<li>{html.escape(str(point))}</li>")
            parts.append("</ul>")

        parts.append("</div>")
        return "".join(parts)
