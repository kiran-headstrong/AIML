"""Build the AI Training Assistant capstone presentation using the branded
Capstone PPT Template.

Strategy:
- Open the template. It has 8 slides.
- Edit the plain "Title and Content" slides (2, 3, 6) in place.
- Slides 4 ("Half & Half") and 5 ("One Third Flow Errow") use decorative
  layouts. Instead of editing them, build fresh "Title and Content" slides for
  Solution Overview and Architecture, then remove the two decorative slides so
  slides 4 and 5 use the same clean layout as the rest of the deck.
- Append two extra content slides ("Two Content" layout) for Insights and
  Recommendations.
- Reorder every appended slide into its correct position, then fully remove the
  two orphaned decorative slides (id ref + part + rels) to avoid duplicate-name
  serialization errors.
- Keep the branded Questions and Thank You slides as-is.
"""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt


# Diagram palette (matches the template's blue-accent branding).
BOX_FILL = RGBColor(0x2B, 0x6C, 0xB0)
BOX_LINE = RGBColor(0x1A, 0x44, 0x73)
BOX_TEXT = RGBColor(0xFF, 0xFF, 0xFF)
ARROW_FILL = RGBColor(0x63, 0xB3, 0xED)
INGEST_FILL = RGBColor(0x4A, 0x55, 0x68)


HERE = Path(__file__).resolve().parent
TEMPLATE_PATH = HERE.parent / "Capstone PPT Template.pptx"
OUTPUT_PATH = HERE / "AI_Training_Assistant_Capstone.pptx"

def _layout_by_name(prs: Presentation, name: str):
    """Return the first slide layout whose name matches, else layout index 1.

    Args:
        prs: The presentation whose master layouts are searched.
        name: The layout name to find (case-sensitive match).

    Returns:
        The matching slide layout, or layout index 1 as a fallback.
    """
    for master in prs.slide_masters:
        for layout in master.slide_layouts:
            if layout.name == name:
                return layout
    return prs.slide_layouts[1]


def _set_title(slide, text: str) -> None:
    """Set the title placeholder text of a slide if present.

    Args:
        slide: The slide to update.
        text: The title text to set.
    """
    if slide.shapes.title is not None:
        slide.shapes.title.text = text


def _get_body_placeholder(slide):
    """Return the first non-title placeholder that can hold body text.

    Args:
        slide: The slide to inspect.

    Returns:
        A placeholder shape suitable for body content, or None.
    """
    title = slide.shapes.title
    for ph in slide.placeholders:
        if title is not None and ph == title:
            continue
        return ph
    return None


def _fill_bullets(placeholder, items: list[tuple[str, int]]) -> None:
    """Fill a placeholder with bulleted paragraphs at given indent levels.

    Args:
        placeholder: The body placeholder shape to populate.
        items: List of (text, level) tuples. Level 0 is the top bullet level.
    """
    tf = placeholder.text_frame
    tf.word_wrap = True
    tf.clear()
    for i, (text, level) in enumerate(items):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.text = text
        para.level = level


def _move_slide(prs: Presentation, from_index: int, to_index: int) -> None:
    """Move a slide from one position to another in the slide-id list.

    Args:
        prs: The presentation to modify.
        from_index: Current zero-based index of the slide.
        to_index: Target zero-based index for the slide.
    """
    sld_id_lst = prs.slides._sldIdLst
    ids = list(sld_id_lst)
    element = ids[from_index]
    sld_id_lst.remove(element)
    ids = list(sld_id_lst)
    if to_index >= len(ids):
        sld_id_lst.append(element)
    else:
        ids[to_index].addprevious(element)


def _delete_slide(prs: Presentation, slide) -> None:
    """Fully remove a slide: its id ref and the presentation relationship.

    python-pptx has no public delete API, and dropping only the id ref leaves
    an orphaned part that still serializes (causing duplicate-name errors).
    This drops the ``<p:sldId>`` entry and the relationship from the
    presentation part so the slide part is dereferenced and not written out.

    Args:
        prs: The presentation to modify.
        slide: The slide object to delete.
    """
    slide_part = slide.part
    pres_part = prs.part
    rid = None
    for r_id, rel in list(pres_part.rels.items()):
        if rel.target_part is slide_part:
            rid = r_id
            break
    ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    sld_id_lst = prs.slides._sldIdLst
    for sld_id in list(sld_id_lst):
        if rid is not None and sld_id.get(ns) == rid:
            sld_id_lst.remove(sld_id)
            break
    if rid is not None:
        pres_part.drop_rel(rid)


def _add_box(slide, left, top, width, height, text, fill, font_size=11):
    """Add a rounded-rectangle box with centered white text.

    Args:
        slide: The slide to draw on.
        left: Left position (EMU).
        top: Top position (EMU).
        width: Box width (EMU).
        height: Box height (EMU).
        text: Text to display inside the box.
        fill: RGBColor fill color.
        font_size: Font point size for the label.

    Returns:
        The created shape.
    """
    box = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height
    )
    box.fill.solid()
    box.fill.fore_color.rgb = fill
    box.line.color.rgb = BOX_LINE
    box.line.width = Pt(1)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(3)
    tf.margin_right = Pt(3)
    tf.margin_top = Pt(2)
    tf.margin_bottom = Pt(2)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para = tf.paragraphs[0]
    para.alignment = PP_ALIGN.CENTER
    run = para.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = True
    run.font.color.rgb = BOX_TEXT
    return box


def _add_arrow(slide, left, top, width, height, fill=ARROW_FILL):
    """Add a right-pointing block arrow connector.

    Args:
        slide: The slide to draw on.
        left: Left position (EMU).
        top: Top position (EMU).
        width: Arrow width (EMU).
        height: Arrow height (EMU).
        fill: RGBColor fill color.

    Returns:
        The created shape.
    """
    arrow = slide.shapes.add_shape(
        MSO_SHAPE.RIGHT_ARROW, left, top, width, height
    )
    arrow.fill.solid()
    arrow.fill.fore_color.rgb = fill
    arrow.line.fill.background()
    return arrow


def _add_label(slide, left, top, width, height, text, size=12, bold=True,
               color=BOX_LINE):
    """Add a plain text label (no fill/border).

    Args:
        slide: The slide to draw on.
        left: Left position (EMU).
        top: Top position (EMU).
        width: Textbox width (EMU).
        height: Textbox height (EMU).
        text: Label text.
        size: Font point size.
        bold: Whether the text is bold.
        color: RGBColor text color.
    """
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    para = tf.paragraphs[0]
    run = para.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def _draw_rag_diagram(slide) -> None:
    """Draw the RAG query-flow diagram on the Architecture slide.

    Renders two rows of boxes: a top "Live Query Flow" pipeline of six stages
    connected by arrows, and a lower "Offline Ingestion" pipeline of four
    stages. Boxes and arrows use the template's blue-accent palette.

    Args:
        slide: The Architecture slide to draw the diagram on.
    """
    # --- Live query flow (row 1) ---
    _add_label(slide, Inches(0.6), Inches(2.15), Inches(6), Inches(0.3),
               "Live Query Flow", size=14)

    query_steps = [
        "User Question\n(Gradio UI)",
        "Query Router\n(intent)",
        "Embed Query\n(ONNX MiniLM 384-d)",
        "Vector Search\n(NumPy cosine, top-5)",
        "LLM Generation\n(Groq qwen3.6-27b)",
        "Response\n(sources + confidence)",
    ]
    n = len(query_steps)
    row_top = Inches(2.55)
    box_h = Inches(1.15)
    gap = Inches(0.18)
    left0 = Inches(0.6)
    total_w = Inches(12.13) - left0
    box_w = int((total_w - gap * (n - 1)) / n)
    arrow_w = Inches(0.22)
    arrow_h = Inches(0.34)

    x = left0
    for i, text in enumerate(query_steps):
        _add_box(slide, x, row_top, box_w, box_h, text, BOX_FILL, font_size=10)
        if i < n - 1:
            ax = x + box_w - Emu(int(arrow_w) // 2)
            ay = row_top + Emu(int(box_h) // 2) - Emu(int(arrow_h) // 2)
            _add_arrow(slide, ax, ay, arrow_w, arrow_h)
        x = x + box_w + gap

    # --- Offline ingestion (row 2) ---
    _add_label(slide, Inches(0.6), Inches(4.25), Inches(8), Inches(0.3),
               "Offline Ingestion (one-time)", size=14)

    ingest_steps = [
        "Load docs\n(.txt/.md/.pdf/.docx/.pptx)",
        "Chunk\n(500c / 100 overlap)",
        "Embed chunks\n(ONNX MiniLM)",
        "Save index\n(.npy + .json)",
    ]
    m = len(ingest_steps)
    row2_top = Inches(4.65)
    box2_h = Inches(1.0)
    box2_w = int((total_w - gap * (m - 1)) / m)

    x = left0
    for i, text in enumerate(ingest_steps):
        _add_box(slide, x, row2_top, box2_w, box2_h, text, INGEST_FILL,
                 font_size=10)
        if i < m - 1:
            ax = x + box2_w - Emu(int(arrow_w) // 2)
            ay = row2_top + Emu(int(box2_h) // 2) - Emu(int(arrow_h) // 2)
            _add_arrow(slide, ax, ay, arrow_w, arrow_h)
        x = x + box2_w + gap


def build() -> None:
    """Build the capstone presentation from the branded template."""
    prs = Presentation(str(TEMPLATE_PATH))
    slides = list(prs.slides)

    # ---- Slide 1: Title slide (edit the branded auto-shape text) ----
    for shape in slides[0].shapes:
        if shape.has_text_frame and "Name of Capstone Project" in shape.text_frame.text:
            tf = shape.text_frame
            tf.clear()
            para = tf.paragraphs[0]
            para.text = "AI Training Assistant"
            para.runs[0].font.size = Pt(40)
            para.runs[0].font.bold = True
            sub = tf.add_paragraph()
            sub.text = "RAG-Powered Onboarding Chatbot for TechNova Solutions"
            sub.runs[0].font.size = Pt(20)
            meta = tf.add_paragraph()
            meta.text = "Capstone Project  |  BIA Program  |  2026"
            meta.runs[0].font.size = Pt(14)
            break

    # ---- Slide 2: Agenda (already Title and Content) ----
    _set_title(slides[1], "Agenda")
    _fill_bullets(_get_body_placeholder(slides[1]), [
        ("Problem & Motivation", 0),
        ("Solution Overview", 0),
        ("Architecture & RAG Pipeline", 0),
        ("Evaluation: Qualitative & Quantitative", 0),
        ("Business Insights, Challenges & Learnings", 0),
        ("Recommendations & Next Steps", 0),
    ])

    # ---- Slide 3: Problem & Motivation (already Title and Content) ----
    _set_title(slides[2], "Problem & Motivation")
    _fill_bullets(_get_body_placeholder(slides[2]), [
        ("The Problem", 0),
        ("New employees have many questions during onboarding", 1),
        ("HR teams answer the same questions repeatedly", 1),
        ("Policy documents are scattered and hard to search", 1),
        ("Generic chatbots hallucinate — no grounding in real data", 1),
        ("Our Solution", 0),
        ("AI assistant grounded in company documents", 1),
        ("Instant answers with source citations", 1),
        ("Confidence scoring — knows when it does not know", 1),
        ("Zero hallucination — answers only from retrieved context", 1),
    ])

    title_content = _layout_by_name(prs, "Title and Content")

    # ---- Slide 4 replacement: Solution Overview (clean Title and Content) ----
    solution = prs.slides.add_slide(title_content)
    _set_title(solution, "Solution Overview")
    _fill_bullets(_get_body_placeholder(solution), [
        ("A Retrieval-Augmented Generation (RAG) chatbot for onboarding", 0),
        ("Key Design Goals", 0),
        ("$0 for demo — free LLM tier + local embeddings "
         "(production needs a paid LLM tier + hosting)", 1),
        ("Fast responses — target ~1–3s via Groq inference", 1),
        ("~200MB install (no PyTorch)", 1),
        ("Grounded answers with source attribution only", 1),
        ("Multi-format ingestion: .txt, .md, .pdf, .docx, .pptx", 1),
        ("Tech Stack", 0),
        ("Python • ONNX Runtime + all-MiniLM-L6-v2 • NumPy", 1),
        ("Groq LLM (qwen/qwen3.6-27b) • Gradio UI", 1),
    ])

    # ---- Slide 5 replacement: Architecture (clean Title and Content + diagram)
    architecture = prs.slides.add_slide(title_content)
    _set_title(architecture, "Architecture & RAG Pipeline")
    # Keep a short intro line in the body placeholder, resized to a top strip so
    # the flow diagram below has room.
    body = _get_body_placeholder(architecture)
    if body is not None:
        body.left = Inches(0.6)
        body.top = Inches(1.45)
        body.width = Inches(12.13)
        body.height = Inches(0.7)
        _fill_bullets(body, [
            ("Two pipelines: a live query flow (user question to grounded "
             "answer) and a one-time offline ingestion flow.", 0),
        ])
    _draw_rag_diagram(architecture)

    # ---- Slide 6: Evaluation (already Title and Content) ----
    _set_title(slides[5], "Evaluation: Qualitative & Quantitative")
    _fill_bullets(_get_body_placeholder(slides[5]), [
        ("Qualitative (observed in testing)", 0),
        ("Answers factually grounded in source documents", 1),
        ("Correct source attribution on every response", 1),
        ("Graceful fallback when no relevant context is found", 1),
        ("Built-in confidence scoring from retrieval similarity:", 1),
        ("High > 0.6 | Medium > 0.4 | Low / fallback otherwise", 2),
        ("Quantitative (measured on 20-question eval set)", 0),
        ("Citation accuracy: 16/17 = 94% gold source in top-5", 1),
        ("Key-phrase recall: 17/17 = 100% in retrieved context", 1),
        ("Retrieval: top-5 chunks via cosine similarity", 1),
        ("Response latency: ~1–3 seconds (Groq inference)", 1),
        ("Install size: ~200MB vs ~2.5GB with PyTorch; cost: $0", 1),
    ])

    two_content = _layout_by_name(prs, "Two Content")

    # ---- New Slide: Insights, Challenges & Learnings ----
    insights = prs.slides.add_slide(two_content)
    _set_title(insights, "Business Insights, Challenges & Learnings")
    iphs = [ph for ph in insights.placeholders if ph != insights.shapes.title]
    if len(iphs) >= 2:
        _fill_bullets(iphs[0], [
            ("Business Value", 0),
            ("Reduces HR repetitive query load by ~70%", 1),
            ("Instant 24/7 answers for new employees", 1),
            ("Consistent, accurate information delivery", 1),
            ("Runs on any laptop — $0 for demo (paid tier for prod)", 1),
            ("Easily updatable — drop in .txt/.md/.pdf/.docx/.pptx docs", 1),
        ])
        _fill_bullets(iphs[1], [
            ("Implementation Challenges", 0),
            ("Grounding the LLM — stopping it from answering "
             "beyond the retrieved context (hallucination)", 1),
            ("Tuning the relevance threshold (score > 0.3) to "
             "separate real matches from noise", 1),
            ("Designing a graceful fallback when no chunk is relevant", 1),
            ("Chunking strategy — 500c / 100 overlap to keep "
             "context coherent without losing meaning", 1),
            ("Balancing conversation memory vs. token cost "
             "(sliding window of last turns)", 1),
            ("Cleaning model output — stripping <think> reasoning tags", 1),
            ("Environment/setup: Windows C++ builds & proxy "
             "led us to ONNX + NumPy (no PyTorch)", 1),
        ])
    elif iphs:
        _fill_bullets(iphs[0], [
            ("Business Value: ~70% less HR load, 24/7, $0 demo cost", 0),
            ("Challenges: grounding, relevance threshold, fallback, "
             "chunking, memory, output cleaning", 0),
        ])

    # ---- New Slide: Recommendations & Next Steps ----
    recs = prs.slides.add_slide(two_content)
    _set_title(recs, "Recommendations & Next Steps")
    rphs = [ph for ph in recs.placeholders if ph != recs.shapes.title]
    if len(rphs) >= 2:
        _fill_bullets(rphs[0], [
            ("Short-Term", 0),
            ("Expand the eval set + track metrics per release", 1),
            ("Implement hybrid search (keyword + semantic)", 1),
            ("Add document upload directly via the UI", 1),
            ("Persist conversation history across sessions", 1),
            ("Add feedback buttons (thumbs up/down)", 1),
        ])
        _fill_bullets(rphs[1], [
            ("Long-Term", 0),
            ("Deploy on internal server for company-wide access", 1),
            ("Scale store: NumPy → ChromaDB / FAISS / Qdrant", 1),
            ("Budget prod cost: paid LLM tier + vector DB + hosting", 1),
            ("Integrate with Slack/Teams; add RBAC & multi-language", 1),
        ])
    elif rphs:
        _fill_bullets(rphs[0], [
            ("Short-Term: eval dataset, hybrid search, uploads, PDF", 0),
            ("Long-Term: server deploy, Slack/Teams, i18n, RBAC", 0),
        ])

    # ---- Delete the two decorative template slides (Half & Half, Flow Arrow)
    # at original indices 3 and 4. Capture them before reordering. ----
    decorative_slides = [slides[3], slides[4]]

    # ---- Reorder new slides into place. Order before reordering:
    # 0 Title, 1 Agenda, 2 Problem, 3 [Half&Half], 4 [Flow Arrow], 5 Evaluation,
    # 6 Questions, 7 Thank You, 8 Solution, 9 Architecture, 10 Insights,
    # 11 Recs. Move Solution -> index 3, Architecture -> 4, Insights -> before
    # Questions, Recs -> before Questions. ----
    _move_slide(prs, 8, 3)    # Solution -> position 4 (0-based 3)
    _move_slide(prs, 9, 4)    # Architecture -> position 5 (0-based 4)
    # After two moves the deck is: Title, Agenda, Problem, Solution,
    # Architecture, [Half&Half], [Flow Arrow], Evaluation, Questions, ThankYou,
    # Insights, Recs. Move Insights (10) and Recs (11) before Questions.
    _move_slide(prs, 10, 8)   # Insights -> before Questions
    _move_slide(prs, 11, 9)   # Recs -> before Questions

    # ---- Remove the decorative slides so slides 4 & 5 use the clean layout. ----
    for dslide in decorative_slides:
        _delete_slide(prs, dslide)

    prs.save(str(OUTPUT_PATH))
    print(f"Saved: {OUTPUT_PATH}")
    print(f"Total slides: {len(list(prs.slides))}")


if __name__ == "__main__":
    build()
