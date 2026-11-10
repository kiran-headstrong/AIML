import hashlib
import datetime

from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    Assessment, Category, Criterion, Score, Evidence,
    PublishedReport, AuditLog, Role, Stage,
)
from .forms import AssessmentCreateForm, EvidenceForm, BusinessInfoForm, SummaryForm
from .permissions import (
    get_role, role_required, is_staff_role, ensure_can_view, can_view_assessment,
)


def log(request, action, assessment=None, detail=""):
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action, assessment=assessment, detail=detail,
    )


# ---------------------------------------------------------------- Auth

def login_view(request):
    if request.method == "POST":
        user = authenticate(
            request, username=request.POST.get("username"),
            password=request.POST.get("password"),
        )
        if user:
            login(request, user)
            log(request, "login")
            if get_role(user) == Role.BUSINESS:
                return redirect("business_home")
            return redirect("dashboard")
        messages.error(request, "Invalid credentials.")
    return render(request, "auth/login.html")


def logout_view(request):
    log(request, "logout")
    logout(request)
    return redirect("public_home")


# ---------------------------------------------------------------- Public site
# Reads ONLY from PublishedReport. Never touches internal records.

def public_home(request):
    reports = PublishedReport.objects.all()
    return render(request, "public/home.html", {"reports": reports})


def public_report(request, slug):
    report = get_object_or_404(PublishedReport, slug=slug)
    valid = report.valid_until >= timezone.now().date()
    return render(request, "public/report.html", {"report": report, "valid": valid})


# ---------------------------------------------------------------- Internal dashboard

@role_required(Role.ADMIN, Role.ASSESSOR, Role.REVIEWER)
def dashboard(request):
    role = get_role(request.user)
    qs = Assessment.objects.select_related("category").all()
    if role == Role.ASSESSOR:
        qs = qs.filter(assessor=request.user)
    elif role == Role.REVIEWER:
        qs = qs.filter(reviewer=request.user)

    stage_filter = request.GET.get("stage")
    if stage_filter:
        qs = qs.filter(stage=stage_filter)

    return render(request, "internal/dashboard.html", {
        "assessments": qs,
        "stages": Stage.choices,
        "role": role,
        "active_stage": stage_filter,
    })


@role_required(Role.ADMIN)
def assessment_create(request):
    if request.method == "POST":
        form = AssessmentCreateForm(request.POST)
        if form.is_valid():
            a = form.save()
            log(request, "create_assessment", a, f"Created {a.business_name}")
            messages.success(request, "Assessment created.")
            return redirect("assessment_detail", pk=a.pk)
    else:
        form = AssessmentCreateForm()
    return render(request, "internal/assessment_form.html", {"form": form})


@login_required
def assessment_detail(request, pk):
    a = get_object_or_404(Assessment, pk=pk)
    ensure_can_view(request.user, a)
    log(request, "view_assessment", a)

    criteria = Criterion.objects.filter(category=a.category)
    existing = {s.criterion_id: s for s in a.scores.all()}
    scoring_rows = [(c, existing.get(c.id)) for c in criteria]

    role = get_role(request.user)
    # Assessor cannot approve their own work.
    can_senior_approve = (
        role in (Role.ADMIN, Role.REVIEWER)
        and a.reviewer_id == request.user.id
        and a.assessor_id != request.user.id
    ) or (role == Role.ADMIN)

    return render(request, "internal/assessment_detail.html", {
        "a": a,
        "scoring_rows": scoring_rows,
        "evidence_form": EvidenceForm(),
        "summary_form": SummaryForm(instance=a),
        "role": role,
        "stages": Stage,
        "can_senior_approve": can_senior_approve,
    })


@role_required(Role.ADMIN, Role.ASSESSOR)
def add_evidence(request, pk):
    a = get_object_or_404(Assessment, pk=pk)
    ensure_can_view(request.user, a)
    if request.method == "POST":
        form = EvidenceForm(request.POST, request.FILES)
        if form.is_valid():
            ev = form.save(commit=False)
            ev.assessment = a
            ev.collected_by = request.user
            f = request.FILES["file"]
            h = hashlib.sha256()
            for chunk in f.chunks():
                h.update(chunk)
            ev.file_hash = h.hexdigest()
            ev.save()
            log(request, "add_evidence", a, f"{ev.evidence_type} hash={ev.file_hash[:12]}")
            messages.success(request, "Evidence uploaded with integrity hash.")
    return redirect("assessment_detail", pk=pk)


@login_required
def evidence_download(request, pk):
    """Serve private evidence via a controlled view (stand-in for signed URL)."""
    ev = get_object_or_404(Evidence, pk=pk)
    if not can_view_assessment(request.user, ev.assessment) or get_role(request.user) == Role.BUSINESS:
        raise PermissionDenied("No access to this evidence.")
    log(request, "download_evidence", ev.assessment, ev.evidence_type)
    try:
        return FileResponse(ev.file.open("rb"), as_attachment=True)
    except FileNotFoundError:
        raise Http404


@role_required(Role.ADMIN, Role.ASSESSOR)
def save_scores(request, pk):
    a = get_object_or_404(Assessment, pk=pk)
    ensure_can_view(request.user, a)
    if request.method == "POST":
        for c in Criterion.objects.filter(category=a.category):
            raw = request.POST.get(f"score_{c.id}")
            note = request.POST.get(f"note_{c.id}", "")
            if raw is not None and raw != "":
                value = max(0, min(int(raw), c.max_score))
                Score.objects.update_or_create(
                    assessment=a, criterion=c,
                    defaults={"value": value, "note": note},
                )
        log(request, "save_scores", a)
        messages.success(request, "Scores saved.")
    return redirect("assessment_detail", pk=pk)


@role_required(Role.ADMIN, Role.ASSESSOR)
def save_summary(request, pk):
    a = get_object_or_404(Assessment, pk=pk)
    ensure_can_view(request.user, a)
    if request.method == "POST":
        form = SummaryForm(request.POST, instance=a)
        if form.is_valid():
            form.save()
            log(request, "save_summary", a)
            messages.success(request, "Summary saved.")
    return redirect("assessment_detail", pk=pk)


# Permission-controlled stage transitions.
STAGE_FLOW = {
    Stage.INTAKE: Stage.INFO_REQUESTED,
    Stage.INFO_REQUESTED: Stage.EVIDENCE,
    Stage.EVIDENCE: Stage.SCORING,
    Stage.SCORING: Stage.PEER_REVIEW,
    Stage.PEER_REVIEW: Stage.SENIOR_APPROVAL,
    Stage.SENIOR_APPROVAL: Stage.BUSINESS_REVIEW,
}


@login_required
def advance_stage(request, pk):
    a = get_object_or_404(Assessment, pk=pk)
    ensure_can_view(request.user, a)
    role = get_role(request.user)
    current = a.stage
    nxt = STAGE_FLOW.get(current)
    if not nxt:
        messages.error(request, "No forward transition from this stage here.")
        return redirect("assessment_detail", pk=pk)

    # Senior approval requires reviewer/admin and not the assessor.
    if current == Stage.PEER_REVIEW or current == Stage.SENIOR_APPROVAL:
        if role == Role.ASSESSOR or a.assessor_id == request.user.id:
            raise PermissionDenied("An assessor cannot approve their own work.")
        if role not in (Role.ADMIN, Role.REVIEWER):
            raise PermissionDenied("Only reviewers or admins can approve.")

    a.stage = nxt
    a.save(update_fields=["stage"])
    log(request, "advance_stage", a, f"{current} -> {nxt}")
    messages.success(request, f"Moved to {a.get_stage_display()}.")
    return redirect("assessment_detail", pk=pk)


@role_required(Role.ADMIN, Role.REVIEWER)
def publish(request, pk):
    """Freeze a read-only PublishedReport snapshot after consent."""
    a = get_object_or_404(Assessment, pk=pk)
    ensure_can_view(request.user, a)
    if not a.consent_given:
        messages.error(request, "Cannot publish without business consent.")
        return redirect("assessment_detail", pk=pk)
    if a.stage != Stage.BUSINESS_REVIEW:
        messages.error(request, "Assessment must be in Business review to publish.")
        return redirect("assessment_detail", pk=pk)
    if a.total_score is None:
        messages.error(request, "Cannot publish without scores.")
        return redirect("assessment_detail", pk=pk)

    findings = [
        {"criterion": s.criterion.name, "value": s.value,
         "max": s.criterion.max_score, "note": s.note}
        for s in a.scores.select_related("criterion")
    ]
    today = timezone.now().date()
    version = PublishedReport.objects.filter(
        business_name=a.business_name).count() + 1
    report = PublishedReport.objects.create(
        business_name=a.business_name,
        category_name=a.category.name,
        rating=a.rating,
        score=a.total_score,
        summary=a.summary or "Assessment summary not provided.",
        findings=findings,
        assessment_date=today,
        valid_until=today + datetime.timedelta(days=365),
        version=version,
        slug=slugify(f"{a.business_name}-v{version}"),
    )
    a.stage = Stage.PUBLISHED
    a.save(update_fields=["stage"])
    log(request, "publish", a, f"Published v{version}")
    messages.success(request, "Approved report published to the public site.")
    return redirect("public_report", slug=report.slug)


# ---------------------------------------------------------------- Business portal

@role_required(Role.BUSINESS)
def business_home(request):
    assessments = Assessment.objects.filter(business_user=request.user)
    return render(request, "business/home.html", {"assessments": assessments})


# Stages the business is allowed to see (business-visible updates only).
BUSINESS_VISIBLE_STAGES = {
    Stage.INTAKE: "Assessment opened",
    Stage.INFO_REQUESTED: "Information requested from you",
    Stage.EVIDENCE: "Under assessment",
    Stage.SCORING: "Under assessment",
    Stage.PEER_REVIEW: "In review",
    Stage.SENIOR_APPROVAL: "In review",
    Stage.BUSINESS_REVIEW: "Ready for your review and consent",
    Stage.PUBLISHED: "Published",
}


@role_required(Role.BUSINESS)
def business_assessment(request, pk):
    a = get_object_or_404(Assessment, pk=pk)
    ensure_can_view(request.user, a)
    log(request, "business_view", a)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "submit_info":
            form = BusinessInfoForm(request.POST, instance=a)
            if form.is_valid():
                form.save()
                log(request, "business_submit_info", a)
                messages.success(request, "Information submitted.")
            return redirect("business_assessment", pk=pk)
        if action == "consent" and a.stage == Stage.BUSINESS_REVIEW:
            a.consent_given = True
            a.consent_at = timezone.now()
            a.save(update_fields=["consent_given", "consent_at"])
            log(request, "business_consent", a, "Consent given")
            messages.success(request, "Thank you. Publishing consent recorded.")
            return redirect("business_assessment", pk=pk)

    status_label = BUSINESS_VISIBLE_STAGES.get(a.stage, "In progress")
    return render(request, "business/assessment.html", {
        "a": a,
        "info_form": BusinessInfoForm(instance=a),
        "status_label": status_label,
    })


# ---------------------------------------------------------------- Audit trail

@role_required(Role.ADMIN)
def audit_trail(request):
    entries = AuditLog.objects.select_related("actor", "assessment")[:300]
    return render(request, "internal/audit.html", {"entries": entries})
