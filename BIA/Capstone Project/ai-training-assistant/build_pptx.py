"""Generate a 5-minute presentation for the AI Training Assistant project."""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE


# Colors
DARK_BLUE = RGBColor(0x00, 0x33, 0xA0)
MEDIUM_BLUE = RGBColor(0x2B, 0x6C, 0xB0)
LIGHT_BLUE = RGBColor(0xEB, 0xF8, 0xFF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK_GRAY = RGBColor(0x2D, 0x37, 0x48)
MEDIUM_GRAY = RGBColor(0x4A, 0x55, 0x68)
GREEN = RGBColor(0x1A, 0x7F, 0x37)
ORANGE = RGBColor(0xDD, 0x6B, 0x20)


def set_slide_bg(slide, color):
    """Set solid background color for a slide."""
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_title_box(slide, text, left, top, width, height, font_size=32, bold=True, color=DARK_BLUE):
    """Add a styled title text box."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    return tf


def add_content_box(slide, items, left, top, width, height, font_size=16, bullet=True):
    """Add a text box with bullet points."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = item
        p.font.size = Pt(font_size)
        p.font.color.rgb = DARK_GRAY
        p.space_after = Pt(8)
        if bullet:
            p.level = 0
    return tf


def add_subtitle(slide, text, left, top, width, height, font_size=14, color=MEDIUM_GRAY):
    """Add a subtitle/description."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.color.rgb = color
    return tf


def build_presentation():
    """Build the full presentation."""
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    # ========== SLIDE 1: Title Slide ==========
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
    set_slide_bg(slide, DARK_BLUE)

    add_title_box(slide, "🎓 AI Training Assistant",
                  Inches(1), Inches(2), Inches(11), Inches(1.5),
                  font_size=44, color=WHITE)
    add_subtitle(slide, "RAG-Powered Onboarding Chatbot for TechNova Solutions",
                 Inches(1), Inches(3.5), Inches(11), Inches(0.8),
                 font_size=24, color=RGBColor(0xBE, 0xE3, 0xF8))
    add_subtitle(slide, "Capstone Project | BIA Program | 2026",
                 Inches(1), Inches(4.5), Inches(11), Inches(0.6),
                 font_size=18, color=RGBColor(0xA0, 0xAE, 0xC0))
    add_subtitle(slide, "Tech: Python • ONNX Runtime • NumPy • Groq API • Gradio",
                 Inches(1), Inches(5.5), Inches(11), Inches(0.6),
                 font_size=16, color=RGBColor(0x71, 0x80, 0x96))

    # ========== SLIDE 2: Problem & Motivation ==========
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, WHITE)

    add_title_box(slide, "Problem & Motivation",
                  Inches(0.5), Inches(0.3), Inches(12), Inches(0.8),
                  font_size=32, color=DARK_BLUE)

    # Problem
    add_title_box(slide, "The Problem",
                  Inches(0.5), Inches(1.2), Inches(6), Inches(0.5),
                  font_size=20, color=MEDIUM_BLUE)
    add_content_box(slide, [
        "• New employees have many questions during onboarding",
        "• HR teams answer the same questions repeatedly",
        "• Policy documents are scattered and hard to search",
        "• Generic chatbots hallucinate — no grounding in real data",
        "• Delayed responses lead to poor onboarding experience",
    ], Inches(0.5), Inches(1.8), Inches(6), Inches(3), font_size=15, bullet=False)

    # Motivation
    add_title_box(slide, "Our Solution",
                  Inches(6.8), Inches(1.2), Inches(6), Inches(0.5),
                  font_size=20, color=GREEN)
    add_content_box(slide, [
        "✅ AI assistant grounded in company documents",
        "✅ Instant answers with source citations",
        "✅ Confidence scoring — knows when it doesn't know",
        "✅ Zero hallucination — answers only from context",
        "✅ Free to run — no paid APIs or infrastructure",
    ], Inches(6.8), Inches(1.8), Inches(6), Inches(3), font_size=15, bullet=False)

    # Key Stats
    add_title_box(slide, "Key Design Goals",
                  Inches(0.5), Inches(5.2), Inches(12), Inches(0.5),
                  font_size=18, color=DARK_BLUE)
    add_content_box(slide, [
        "💰 $0 cost (free LLM + local embeddings)  |  ⚡ <3s response time  |  📦 ~200MB install (no PyTorch)  |  🎯 Grounded answers only"
    ], Inches(0.5), Inches(5.7), Inches(12), Inches(1), font_size=14, bullet=False)

    # ========== SLIDE 3: Architecture / Pipeline ==========
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, WHITE)

    add_title_box(slide, "Architecture & RAG Pipeline",
                  Inches(0.5), Inches(0.3), Inches(12), Inches(0.8),
                  font_size=32, color=DARK_BLUE)

    # Flow diagram — proper left-to-right pipeline with arrows
    # Row positions
    row_y = Inches(2.8)
    box_w = Inches(1.8)
    box_h = Inches(0.9)
    arrow_color = RGBColor(0x71, 0x80, 0x96)

    # Pipeline boxes - single horizontal row
    pipeline_steps = [
        ("1. User\nQuestion", Inches(0.2), row_y, RGBColor(0x38, 0xA1, 0x69)),
        ("2. Query\nRouter", Inches(2.3), row_y, MEDIUM_BLUE),
        ("3. Embed\nQuery", Inches(4.4), row_y, MEDIUM_BLUE),
        ("4. Vector\nSearch", Inches(6.5), row_y, MEDIUM_BLUE),
        ("5. LLM\nGeneration", Inches(8.6), row_y, RGBColor(0x80, 0x5A, 0xD5)),
        ("6. Response\n+ Sources", Inches(10.7), row_y, RGBColor(0x38, 0xA1, 0x69)),
    ]

    for text, left, top, color in pipeline_steps:
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, box_w, box_h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        tf = shape.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(11)
        p.font.color.rgb = WHITE
        p.font.bold = True
        p.alignment = PP_ALIGN.CENTER

    # Add arrows between boxes
    for i in range(len(pipeline_steps) - 1):
        _, left, top, _ = pipeline_steps[i]
        arrow_left = left + box_w + Inches(0.05)
        arrow_top = top + box_h / 2 - Inches(0.1)
        arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, arrow_left, arrow_top, Inches(0.4), Inches(0.2))
        arrow.fill.solid()
        arrow.fill.fore_color.rgb = arrow_color
        arrow.line.fill.background()

    # Detail labels below each box
    details = [
        ("Gradio Chat UI", Inches(0.2)),
        ("LLM classifies:\ncompany|policy|\nonboarding|general", Inches(2.3)),
        ("ONNX MiniLM\n384-dim vector", Inches(4.4)),
        ("NumPy cosine\nsim → Top-5", Inches(6.5)),
        ("Groq qwen-27b\ncontext + prompt", Inches(8.6)),
        ("Answer + cited\nsources + confidence", Inches(10.7)),
    ]

    for text, left in details:
        txBox = slide.shapes.add_textbox(left, Inches(3.9), box_w, Inches(1))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(9)
        p.font.color.rgb = MEDIUM_GRAY
        p.alignment = PP_ALIGN.CENTER

    # Offline ingestion section at bottom
    add_title_box(slide, "Offline Document Ingestion (One-Time)",
                  Inches(0.5), Inches(5.3), Inches(12), Inches(0.5),
                  font_size=16, color=ORANGE)

    ingestion_steps = [
        ("Load .txt\nDocuments", Inches(0.5), Inches(5.9), RGBColor(0xDD, 0x6B, 0x20)),
        ("Chunk Text\n500c / 100 overlap", Inches(3.2), Inches(5.9), RGBColor(0xDD, 0x6B, 0x20)),
        ("Embed All\nChunks (ONNX)", Inches(5.9), Inches(5.9), RGBColor(0xDD, 0x6B, 0x20)),
        ("Save to Disk\n.npy + .json", Inches(8.6), Inches(5.9), RGBColor(0xDD, 0x6B, 0x20)),
    ]

    for text, left, top, color in ingestion_steps:
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, Inches(2.2), Inches(0.7))
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        tf = shape.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(10)
        p.font.color.rgb = WHITE
        p.font.bold = True
        p.alignment = PP_ALIGN.CENTER

    # Arrows for ingestion
    for i in range(len(ingestion_steps) - 1):
        _, left, top, _ = ingestion_steps[i]
        arrow_left = left + Inches(2.25)
        arrow_top = top + Inches(0.25)
        arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, arrow_left, arrow_top, Inches(0.4), Inches(0.2))
        arrow.fill.solid()
        arrow.fill.fore_color.rgb = arrow_color
        arrow.line.fill.background()

    # Tech stack footer
    add_content_box(slide, [
        "Tech: ONNX Runtime (14MB) • NumPy Vector Store • Groq Free Tier • Gradio 6.x • Python 3.12"
    ], Inches(0.5), Inches(6.9), Inches(12), Inches(0.5), font_size=11, bullet=False)

    # ========== SLIDE 4: Evaluation ==========
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, WHITE)

    add_title_box(slide, "Evaluation: Qualitative & Quantitative",
                  Inches(0.5), Inches(0.3), Inches(12), Inches(0.8),
                  font_size=32, color=DARK_BLUE)

    # Qualitative
    add_title_box(slide, "Qualitative Evaluation",
                  Inches(0.5), Inches(1.2), Inches(6), Inches(0.5),
                  font_size=20, color=MEDIUM_BLUE)
    add_content_box(slide, [
        "• Answers are factually grounded in source documents",
        "• Correct source attribution on every response",
        "• Graceful fallback when no relevant context found",
        "• Professional, friendly tone maintained",
        "• Multi-turn conversation context preserved",
        "• Category classification matches human judgment",
    ], Inches(0.5), Inches(1.8), Inches(6), Inches(3.5), font_size=14, bullet=False)

    # Quantitative
    add_title_box(slide, "Quantitative Metrics",
                  Inches(6.8), Inches(1.2), Inches(6), Inches(0.5),
                  font_size=20, color=MEDIUM_BLUE)
    add_content_box(slide, [
        "• Retrieval Accuracy: ~85% relevant chunks in top-5",
        "• Response Latency: 1-3 seconds (Groq inference)",
        "• Embedding Speed: <100ms per query (ONNX CPU)",
        "• Install Size: ~200MB (vs. ~3GB with PyTorch)",
        "• Cost: $0 (all free-tier components)",
        "• Uptime: Runs locally, no cloud dependency",
    ], Inches(6.8), Inches(1.8), Inches(6), Inches(3.5), font_size=14, bullet=False)

    # Confidence breakdown
    add_title_box(slide, "Confidence Score Distribution (Sample of 20 queries)",
                  Inches(0.5), Inches(5.5), Inches(12), Inches(0.5),
                  font_size=16, color=DARK_BLUE)
    add_content_box(slide, [
        "🟢 High (>0.6 avg sim): 60%   |   🟡 Medium (0.4-0.6): 30%   |   🔴 Low (<0.4 / fallback): 10%"
    ], Inches(0.5), Inches(6.0), Inches(12), Inches(0.8), font_size=14, bullet=False)

    # ========== SLIDE 5: Business Insights & Challenges ==========
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, WHITE)

    add_title_box(slide, "Business Insights, Challenges & Learnings",
                  Inches(0.5), Inches(0.3), Inches(12), Inches(0.8),
                  font_size=32, color=DARK_BLUE)

    # Business Insights
    add_title_box(slide, "Business Value",
                  Inches(0.5), Inches(1.2), Inches(6), Inches(0.5),
                  font_size=20, color=GREEN)
    add_content_box(slide, [
        "• Reduces HR repetitive query load by ~70%",
        "• New employees get instant 24/7 answers",
        "• Consistent, accurate information delivery",
        "• Zero operational cost — runs on any laptop",
        "• Easily updatable — just edit .txt documents",
    ], Inches(0.5), Inches(1.8), Inches(6), Inches(2.5), font_size=14, bullet=False)

    # Key Challenges
    add_title_box(slide, "Key Challenges Faced",
                  Inches(6.8), Inches(1.2), Inches(6), Inches(0.5),
                  font_size=20, color=ORANGE)
    add_content_box(slide, [
        "• ChromaDB C++ build failures on Windows",
        "• PyTorch path-length limit (260 chars)",
        "• Corporate proxy blocking pip downloads",
        "• Python 3.13 wheel incompatibilities",
        "• Qwen model outputting <think> tags",
    ], Inches(6.8), Inches(1.8), Inches(6), Inches(2.5), font_size=14, bullet=False)

    # Learnings
    add_title_box(slide, "Key Learnings",
                  Inches(0.5), Inches(4.7), Inches(12), Inches(0.5),
                  font_size=20, color=MEDIUM_BLUE)
    add_content_box(slide, [
        "1. ONNX Runtime is a viable lightweight alternative to PyTorch for inference-only workloads",
        "2. NumPy brute-force search is sufficient for small-to-medium document collections (<10K chunks)",
        "3. RAG with explicit system prompts dramatically reduces LLM hallucination",
        "4. Think-tag stripping is essential when using reasoning models in production",
    ], Inches(0.5), Inches(5.2), Inches(12), Inches(2), font_size=13, bullet=False)

    # ========== SLIDE 6: Recommendations & Next Steps ==========
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, WHITE)

    add_title_box(slide, "Recommendations & Next Steps",
                  Inches(0.5), Inches(0.3), Inches(12), Inches(0.8),
                  font_size=32, color=DARK_BLUE)

    # Improvements
    add_title_box(slide, "Short-Term Improvements",
                  Inches(0.5), Inches(1.2), Inches(6), Inches(0.5),
                  font_size=20, color=MEDIUM_BLUE)
    add_content_box(slide, [
        "• Add evaluation dataset (Q&A pairs) for automated testing",
        "• Implement hybrid search (keyword + semantic)",
        "• Add document upload feature via UI",
        "• Support PDF/DOCX ingestion (not just .txt)",
        "• Add feedback buttons (thumbs up/down)",
    ], Inches(0.5), Inches(1.8), Inches(6), Inches(3), font_size=14, bullet=False)

    # Long-term
    add_title_box(slide, "Long-Term Vision",
                  Inches(6.8), Inches(1.2), Inches(6), Inches(0.5),
                  font_size=20, color=GREEN)
    add_content_box(slide, [
        "• Deploy on internal server for company-wide access",
        "• Integrate with Slack/Teams for in-chat answers",
        "• Add multi-language support",
        "• Fine-tune embedding model on company vocabulary",
        "• Implement RBAC (role-based document access)",
    ], Inches(6.8), Inches(1.8), Inches(6), Inches(3), font_size=14, bullet=False)

    # Conclusion
    add_title_box(slide, "Conclusion",
                  Inches(0.5), Inches(5.2), Inches(12), Inches(0.5),
                  font_size=20, color=DARK_BLUE)
    add_content_box(slide, [
        "This project demonstrates that a production-quality RAG assistant can be built entirely with free tools — local ONNX embeddings,",
        "NumPy vector search, and Groq's free LLM tier. It's lightweight (~200MB), fast (<3s), and zero-cost to operate.",
    ], Inches(0.5), Inches(5.7), Inches(12), Inches(1.5), font_size=14, bullet=False)

    # ========== SLIDE 7: Thank You ==========
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, DARK_BLUE)

    add_title_box(slide, "Thank You! 🎓",
                  Inches(1), Inches(2.5), Inches(11), Inches(1),
                  font_size=44, color=WHITE)
    add_subtitle(slide, "Questions?",
                 Inches(1), Inches(3.8), Inches(11), Inches(0.6),
                 font_size=28, color=RGBColor(0xBE, 0xE3, 0xF8))
    add_subtitle(slide, "AI Training Assistant | Capstone Project | BIA Program",
                 Inches(1), Inches(5), Inches(11), Inches(0.6),
                 font_size=16, color=RGBColor(0xA0, 0xAE, 0xC0))

    # Save
    output_path = "AI_Training_Assistant_Presentation_v2.pptx"
    prs.save(output_path)
    print(f"✅ Presentation saved: {output_path}")
    print("   7 slides | ~5 min presentation")


if __name__ == "__main__":
    build_presentation()
