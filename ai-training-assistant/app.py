"""Gradio web app for the AI Training Assistant (production-shaped).

Provides a branded chat UI for TechNova Solutions employees plus an admin
portal, gated by login:

- **Authentication**: username/password (bcrypt) via Gradio's native auth,
  a demo-safe stand-in for enterprise SSO (OIDC/SAML).
- **Roles**: ``employee`` (chat only) and ``admin`` (chat + observability
  portal with charts and downloadable CSV reports).
- **Per-user sessions**: each logged-in user gets an isolated assistant and
  conversation history (no shared global state).
- **Rate limiting**: per-user sliding-window limit.
- **Audit logging**: every query is attributed to its user in the event log.

Answers are grounded in company documents with source attribution, routing
category, a confidence badge, and the vector-DB filter scope.
"""

import logging

import gradio as gr

from src.assistant import TrainingAssistant
from src.auth import ROLE_ADMIN, RateLimiter, UserStore
from src.knowledge_base import rebuild_index, save_uploaded_document
from src.observability import (
    export_metrics_summary_csv,
    export_query_records_csv,
    format_metrics_markdown,
    log_event,
    metrics,
)


# Shared auth + rate-limit singletons (thread-safe).
user_store = UserStore()
rate_limiter = RateLimiter()

# Per-username assistant instances so conversations are isolated per user.
_assistants: dict[str, TrainingAssistant] = {}

# Confidence level -> (emoji, accent color) for the response badge.
CONFIDENCE_STYLES = {
    "high": ("🟢", "#22c55e"),
    "medium": ("🟡", "#eab308"),
    "low": ("🔴", "#ef4444"),
}

# Example questions curated from the labeled evaluation set.
EXAMPLE_QUESTIONS = [
    "What are standard work hours and the core collaboration window?",
    "As a Data Analyst, what are the first 30 days expectations?",
    "How do I submit an expense claim and by when?",
    "How do I request PTO and what notice is expected for planned leave?",
    "What should I do if I can't access a tool on Day 1?",
    "What are the steps to take if I suspect a security incident?",
    "What is my exact salary breakup and tax deductions?",
    "Can you approve my leave request right now?",
]

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

.gradio-container {
    font-family: 'Inter', system-ui, sans-serif !important;
    background: linear-gradient(135deg, #f5f7fb 0%, #eef2f9 100%) !important;
    max-width: 1100px !important;
    margin: auto !important;
}
#app-header {
    background: linear-gradient(120deg, #4f46e5 0%, #7c3aed 45%, #2563eb 100%);
    border-radius: 18px;
    padding: 28px 32px;
    margin-bottom: 18px;
    color: #ffffff;
    box-shadow: 0 10px 30px rgba(79, 70, 229, 0.28);
}
#app-header h1 { font-size: 1.9rem; font-weight: 700; margin: 0 0 6px 0; color: #fff; }
#app-header p { font-size: 1rem; margin: 0; color: #e0e7ff; line-height: 1.5; }
#app-header .pill {
    display: inline-block;
    background: rgba(255, 255, 255, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.35);
    padding: 4px 12px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 600;
    margin-top: 12px; margin-right: 6px;
}
.chatbot, #chatbot {
    border-radius: 16px !important;
    border: 1px solid #e2e8f0 !important;
    box-shadow: 0 4px 18px rgba(30, 41, 59, 0.06) !important;
    background: #ffffff !important;
}
.meta-badge {
    display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 0.75rem; font-weight: 600; margin: 2px 4px 2px 0;
}
button.primary, .primary {
    background: linear-gradient(120deg, #4f46e5, #7c3aed) !important;
    border: none !important; color: #fff !important;
    border-radius: 12px !important; font-weight: 600 !important;
}
footer { display: none !important; }
"""

HEADER_HTML = """
<div id="app-header">
    <h1>🎓 AI Training Assistant</h1>
    <p>Your smart onboarding buddy at <strong>TechNova Solutions</strong>.
    Ask about policies, expenses, leave, IT access, roles, and more — every
    answer is grounded in our company documents with sources cited.</p>
    <span class="pill">📚 Document-grounded</span>
    <span class="pill">🔎 Source-cited</span>
    <span class="pill">🛡️ Safe refusals</span>
    <span class="pill">🗄️ ChromaDB vector search</span>
    <span class="pill">🔐 Login + roles</span>
    <span class="pill">⚡ RAG + Groq</span>
</div>
"""


def auth_fn(username: str, password: str) -> bool:
    """Gradio auth callback: verify credentials against the user store.

    Args:
        username: Submitted username.
        password: Submitted password.

    Returns:
        True if the credentials are valid, else False.
    """
    user = user_store.authenticate(username, password)
    ok = user is not None
    log_event(
        logging.INFO,
        f"login {'success' if ok else 'failure'} for '{username}'",
        span="auth_login",
        status="ok" if ok else "denied",
        username=username,
    )
    return ok


def _get_assistant(username: str) -> TrainingAssistant:
    """Return the per-user assistant instance, creating it on first use.

    Args:
        username: The authenticated username.

    Returns:
        The user's :class:`TrainingAssistant` (isolated conversation history).
    """
    assistant = _assistants.get(username)
    if assistant is None:
        assistant = TrainingAssistant()
        _assistants[username] = assistant
    return assistant


def _current_username(request: gr.Request | None) -> str:
    """Resolve the logged-in username from the Gradio request.

    Args:
        request: The incoming Gradio request (carries the auth session).

    Returns:
        The username, or ``"anonymous"`` if it cannot be resolved.
    """
    if request is not None and getattr(request, "username", None):
        return request.username
    return "anonymous"


def _format_response(result: dict) -> str:
    """Format the assistant result into a colorful markdown/HTML string.

    Args:
        result: The dict returned by ``TrainingAssistant.answer``.

    Returns:
        A markdown string with the answer plus styled source and metadata
        badges (category, confidence, and vector-DB filter scope).
    """
    response = result["answer"]
    parts = ["\n\n---"]
    if result["sources"]:
        sources_str = " · ".join(
            s.replace(".md", "").split("/")[-1] for s in result["sources"]
        )
        parts.append(f"📚 **Sources:** {sources_str}")

    emoji, color = CONFIDENCE_STYLES.get(result["confidence"], ("⚪", "#64748b"))
    badges = [
        f"<span class='meta-badge' style='background:#eef2ff;color:#4338ca;'>"
        f"🏷️ {result['category']}</span>",
        f"<span class='meta-badge' style='background:{color}22;color:{color};'>"
        f"{emoji} confidence: {result['confidence']}</span>",
    ]
    filter_category = result.get("filter_category")
    unfiltered_retry = result.get("unfiltered_retry", False)
    if unfiltered_retry:
        badges.append(
            "<span class='meta-badge' style='background:#fef3c7;color:#92400e;'>"
            "🔁 retry: unfiltered</span>"
        )
    elif filter_category:
        badges.append(
            "<span class='meta-badge' style='background:#dcfce7;color:#166534;'>"
            f"🔎 filter: {filter_category}</span>"
        )
    else:
        badges.append(
            "<span class='meta-badge' style='background:#e2e8f0;color:#475569;'>"
            "🌐 filter: all</span>"
        )
    parts.append("".join(badges))
    return response + "\n\n" + "  \n".join(parts)


def chat(message: str, history: list, request: gr.Request) -> str:
    """Handle a chat message for the logged-in user and return the response.

    Args:
        message: The user's chat message.
        history: Prior conversation turns (managed by Gradio).
        request: The Gradio request (used to resolve the authenticated user).

    Returns:
        The assistant's formatted response, a rate-limit notice, or an error.
    """
    username = _current_username(request)

    if not rate_limiter.allow(username):
        log_event(
            logging.WARNING,
            f"rate limit exceeded for '{username}'",
            span="rate_limit",
            status="blocked",
            username=username,
        )
        return (
            "⏳ **You're sending requests too quickly.** Please wait a moment "
            "and try again."
        )

    try:
        assistant = _get_assistant(username)
    except (FileNotFoundError, ValueError) as e:
        metrics.record_error(type(e).__name__)
        log_event(logging.ERROR, f"init failed: {e}", span="ui_init", username=username)
        return f"⚠️ **Setup required:** {e}"
    except Exception as e:  # noqa: BLE001 - surface any init error in the UI
        metrics.record_error(type(e).__name__)
        log_event(logging.ERROR, f"init failed: {e}", span="ui_init", username=username)
        return f"⚠️ **Failed to initialize:** {e}"

    try:
        result = assistant.answer(message, username=username)
    except Exception as e:  # noqa: BLE001 - surface any runtime error in the UI
        log_event(
            logging.ERROR,
            f"response generation failed: {e}",
            span="ui_chat",
            username=username,
        )
        return f"⚠️ **Error generating response:** {e}"

    return _format_response(result)


def on_feedback(like_data: gr.LikeData, request: gr.Request) -> None:
    """Record a user's thumbs up/down on an answer.

    Wired to the chatbot's native like/dislike event.

    Args:
        like_data: Gradio like event payload (``liked`` is True for thumbs-up).
        request: The Gradio request (used to attribute feedback to the user).
    """
    username = _current_username(request)
    positive = bool(like_data.liked)
    metrics.record_feedback(positive)
    log_event(
        logging.INFO,
        f"feedback {'up' if positive else 'down'} from '{username}'",
        span="feedback",
        status="ok",
        username=username,
        positive=positive,
    )


# ── Admin portal helpers ────────────────────────────────────────────────────


def admin_upload_and_reindex(files: list, request: gr.Request) -> str:
    """Save uploaded documents and rebuild the vector index (admin only).

    Args:
        files: List of uploaded file paths from the Gradio File component.
        request: The Gradio request (checked for admin role).

    Returns:
        A markdown status message describing the result.
    """
    if not _is_admin(request):
        return "🔒 **Admin access required** to upload documents."
    if not files:
        return "⚠️ No files selected. Choose one or more documents to upload."

    saved: list[str] = []
    errors: list[str] = []
    for f in files:
        # Gradio may pass file paths (str) or objects with a ``.name`` path.
        path = f if isinstance(f, str) else getattr(f, "name", None)
        if not path:
            continue
        original = getattr(f, "orig_name", None)
        try:
            label = save_uploaded_document(path, original_name=original)
            saved.append(label)
        except ValueError as e:
            errors.append(str(e))
        except Exception as e:  # noqa: BLE001 - surface unexpected save errors
            errors.append(f"Failed to save a file: {e}")

    if not saved:
        detail = " ".join(errors) if errors else "No valid documents saved."
        return f"⚠️ **Upload failed.** {detail}"

    username = _current_username(request)
    log_event(
        logging.INFO,
        f"admin '{username}' uploaded {len(saved)} document(s)",
        span="admin_upload",
        status="ok",
        username=username,
        files=saved,
    )

    try:
        summary = rebuild_index()
    except Exception as e:  # noqa: BLE001 - surface reindex failure in the UI
        log_event(
            logging.ERROR, f"reindex failed: {e}", span="reindex", status="error"
        )
        return (
            f"✅ Saved {len(saved)} file(s), but **re-indexing failed:** {e}"
        )

    # New documents changed the corpus: reset per-user assistants so their next
    # query loads the rebuilt index.
    _assistants.clear()

    lines = [
        f"✅ **Uploaded {len(saved)} document(s) and rebuilt the index.**",
        f"- Saved: {', '.join(saved)}",
        f"- Index: {summary['documents']} documents · {summary['chunks']} "
        f"chunks · backend `{summary['backend']}`",
    ]
    if errors:
        lines.append(f"- ⚠️ Skipped: {' '.join(errors)}")
    return "\n".join(lines)


def feedback_df():
    """Build a feedback distribution for the admin bar chart.

    Returns:
        A DataFrame with ``feedback`` and ``count`` columns.
    """
    import pandas as pd

    snap = metrics.snapshot()
    fb = snap.get("feedback", {})
    if not fb or fb.get("total", 0) == 0:
        return _empty_df(["feedback", "count"])
    return pd.DataFrame(
        {"feedback": ["👍 up", "👎 down"], "count": [fb["up"], fb["down"]]}
    )


def _is_admin(request: gr.Request | None) -> bool:
    """Return whether the current request belongs to an admin user.

    Args:
        request: The Gradio request.

    Returns:
        True if the resolved user has the admin role.
    """
    username = _current_username(request)
    record = user_store.authenticate  # noqa: F841 - store lookup below
    user = user_store._users.get(username)  # role lookup (read-only)
    return bool(user and user.get("role") == ROLE_ADMIN)


def _empty_df(columns: list[str]):
    """Return an empty pandas DataFrame with the given columns.

    Args:
        columns: Column names for the empty frame.

    Returns:
        An empty ``pandas.DataFrame``.
    """
    import pandas as pd

    return pd.DataFrame({c: [] for c in columns})


def latency_over_time_df():
    """Build a per-query latency time-series for the admin chart.

    Returns:
        A DataFrame with ``query`` (sequence index) and ``latency_ms`` columns.
    """
    import pandas as pd

    records = [r for r in metrics.query_records() if r.get("latency_ms") is not None]
    if not records:
        return _empty_df(["query", "latency_ms"])
    return pd.DataFrame(
        {
            "query": list(range(1, len(records) + 1)),
            "latency_ms": [r["latency_ms"] for r in records],
        }
    )


def routes_df():
    """Build a routing-category distribution for the admin bar chart.

    Returns:
        A DataFrame with ``category`` and ``count`` columns.
    """
    import pandas as pd

    snap = metrics.snapshot()
    cats = snap.get("categories", {})
    if not cats:
        return _empty_df(["category", "count"])
    return pd.DataFrame({"category": list(cats), "count": list(cats.values())})


def confidence_df():
    """Build a confidence distribution for the admin bar chart.

    Returns:
        A DataFrame with ``confidence`` and ``count`` columns.
    """
    import pandas as pd

    snap = metrics.snapshot()
    conf = snap.get("confidence", {})
    if not conf:
        return _empty_df(["confidence", "count"])
    return pd.DataFrame(
        {"confidence": list(conf), "count": list(conf.values())}
    )


def filter_scope_df():
    """Build a vector-DB filter-scope distribution for the admin bar chart.

    Returns:
        A DataFrame with ``scope`` and ``count`` columns.
    """
    import pandas as pd

    snap = metrics.snapshot()
    scopes = dict(snap.get("filter_categories", {}))
    unfiltered = snap["total_queries"] - snap["total_category_filtered"]
    if unfiltered > 0:
        scopes["all (unfiltered)"] = unfiltered
    if not scopes:
        return _empty_df(["scope", "count"])
    return pd.DataFrame({"scope": list(scopes), "count": list(scopes.values())})


def refresh_admin() -> tuple:
    """Recompute all admin-portal outputs.

    Returns:
        A tuple of ``(metrics_markdown, latency_df, routes_df, confidence_df,
        filter_scope_df, feedback_df)`` for the admin components.
    """
    return (
        format_metrics_markdown(),
        latency_over_time_df(),
        routes_df(),
        confidence_df(),
        filter_scope_df(),
        feedback_df(),
    )


def download_query_report() -> str | None:
    """Export the per-query records to a CSV file for download.

    Returns:
        The path to the generated CSV, or ``None`` if there is no data yet.
    """
    path = export_query_records_csv()
    return str(path) if path else None


def download_metrics_report() -> str | None:
    """Export the aggregated metrics summary to a CSV file for download.

    Returns:
        The path to the generated CSV, or ``None`` if there is no data yet.
    """
    path = export_metrics_summary_csv()
    return str(path) if path else None


def _theme() -> gr.themes.Base:
    """Return the branded Soft theme used by the app.

    Returns:
        A configured Gradio Soft theme (indigo/violet/slate + Inter font).
    """
    return gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="violet",
        neutral_hue="slate",
        font=gr.themes.GoogleFont("Inter"),
    )


def build_demo() -> gr.Blocks:
    """Build the branded, login-gated Gradio Blocks app with an admin portal.

    Returns:
        The configured Gradio Blocks demo.
    """
    with gr.Blocks(title="AI Training Assistant") as demo:
        gr.HTML(HEADER_HTML)

        with gr.Tabs():
            with gr.Tab("💬 Assistant"):
                gr.Markdown(
                    "_Tip: use 👍 / 👎 on any answer to send feedback — it "
                    "feeds the admin quality dashboard._"
                )
                feedback_chatbot = gr.Chatbot(
                    elem_id="chatbot",
                    height=460,
                    show_label=False,
                    avatar_images=(
                        None,
                        "https://api.dicebear.com/7.x/bottts/svg?seed=techNova",
                    ),
                )
                gr.ChatInterface(
                    fn=chat,
                    examples=EXAMPLE_QUESTIONS,
                    chatbot=feedback_chatbot,
                )
                # Native thumbs up/down feedback on answers.
                feedback_chatbot.like(fn=on_feedback)

            with gr.Tab("📊 Admin Portal"):
                admin_gate = gr.Markdown()
                with gr.Column(visible=False) as admin_panel:
                    gr.Markdown("## 📊 Observability Dashboard")
                    admin_metrics = gr.Markdown()
                    with gr.Row():
                        latency_plot = gr.LinePlot(
                            x="query", y="latency_ms",
                            title="Query latency over time (ms)",
                            height=260,
                        )
                        routes_plot = gr.BarPlot(
                            x="category", y="count",
                            title="Routing categories", height=260,
                        )
                    with gr.Row():
                        confidence_plot = gr.BarPlot(
                            x="confidence", y="count",
                            title="Confidence distribution", height=260,
                        )
                        filter_plot = gr.BarPlot(
                            x="scope", y="count",
                            title="Vector-DB filter scope", height=260,
                        )
                    with gr.Row():
                        feedback_plot = gr.BarPlot(
                            x="feedback", y="count",
                            title="User feedback (👍 / 👎)", height=260,
                        )
                    with gr.Row():
                        refresh_admin_btn = gr.Button(
                            "🔄 Refresh dashboard", variant="primary"
                        )
                        query_report_btn = gr.Button("⬇️ Export query report (CSV)")
                        metrics_report_btn = gr.Button("⬇️ Export metrics report (CSV)")
                    query_report_file = gr.File(
                        label="Query report", interactive=False
                    )
                    metrics_report_file = gr.File(
                        label="Metrics summary report", interactive=False
                    )

                    admin_outputs = [
                        admin_metrics, latency_plot, routes_plot,
                        confidence_plot, filter_plot, feedback_plot,
                    ]
                    refresh_admin_btn.click(fn=refresh_admin, outputs=admin_outputs)
                    query_report_btn.click(
                        fn=download_query_report, outputs=query_report_file
                    )
                    metrics_report_btn.click(
                        fn=download_metrics_report, outputs=metrics_report_file
                    )

                    gr.Markdown("---\n### 📄 Document Management")
                    gr.Markdown(
                        "Upload company documents (.txt .md .pdf .docx .pptx) "
                        "and rebuild the knowledge base — no redeploy needed. "
                        "New docs are indexed immediately for all users."
                    )
                    upload_files = gr.File(
                        label="Upload documents",
                        file_count="multiple",
                        file_types=[".txt", ".md", ".pdf", ".docx", ".pptx"],
                    )
                    upload_btn = gr.Button(
                        "📤 Upload & rebuild index", variant="primary"
                    )
                    upload_status = gr.Markdown()
                    upload_btn.click(
                        fn=admin_upload_and_reindex,
                        inputs=upload_files,
                        outputs=upload_status,
                    )

                def _load_admin(request: gr.Request):
                    """Gate the admin panel by role and populate it on load.

                    Args:
                        request: The Gradio request (resolves the user + role).

                    Returns:
                        Updates for the gate message, the panel visibility, and
                        all dashboard outputs.
                    """
                    if not _is_admin(request):
                        return (
                            "🔒 **Admin access required.** You are signed in as a "
                            "standard user. Contact IT to request admin access.",
                            gr.update(visible=False),
                            *refresh_admin(),
                        )
                    return (
                        f"✅ Signed in as admin **{_current_username(request)}**.",
                        gr.update(visible=True),
                        *refresh_admin(),
                    )

                demo.load(
                    fn=_load_admin,
                    outputs=[admin_gate, admin_panel, *admin_outputs],
                )

        gr.HTML(
            "<p style='text-align:center;color:#94a3b8;font-size:0.8rem;"
            "margin-top:14px;'>TechNova Solutions · Capstone Project · "
            "Answers are grounded in internal documents only.</p>"
        )
    return demo


demo = build_demo()


if __name__ == "__main__":
    # Login gate: Gradio's native auth calls auth_fn to verify credentials.
    # share=False keeps the app local (no public tunnel).
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        auth=auth_fn,
        auth_message="Sign in with your TechNova credentials to continue.",
        theme=_theme(),
        css=CUSTOM_CSS,
    )
