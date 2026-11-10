"""
Data model for the VOUCH by Vectis prototype.

Key confidentiality principle from the synopsis:
  - Internal working data (Assessment, Evidence, Score, reviews) stays private.
  - On senior approval + business consent, a frozen read-only PublishedReport
    snapshot is created. The public site reads ONLY from PublishedReport.
"""
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    ADMIN = "admin", "Admin"
    ASSESSOR = "assessor", "Assessor"
    REVIEWER = "reviewer", "Reviewer / Senior approver"
    BUSINESS = "business", "Business"


class Profile(models.Model):
    """Extends the built-in User with a VOUCH role."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class Category(models.Model):
    """Assessment category, e.g. Restaurants. Prototype uses one."""
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Criterion(models.Model):
    """A scored criterion belonging to a category."""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="criteria")
    name = models.CharField(max_length=200)
    weight = models.PositiveIntegerField(default=1)
    max_score = models.PositiveIntegerField(default=10)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class Stage(models.TextChoices):
    INTAKE = "intake", "Intake"
    INFO_REQUESTED = "info_requested", "Information requested"
    EVIDENCE = "evidence", "Evidence gathering"
    SCORING = "scoring", "Analysis and scoring"
    PEER_REVIEW = "peer_review", "Peer review"
    SENIOR_APPROVAL = "senior_approval", "Senior approval"
    BUSINESS_REVIEW = "business_review", "Business review and consent"
    PUBLISHED = "published", "Published"
    REASSESS_DUE = "reassess_due", "Re-assessment due"


class Assessment(models.Model):
    """Internal working record for one business assessment."""
    business_name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="assessments")
    stage = models.CharField(max_length=30, choices=Stage.choices, default=Stage.INTAKE)

    # Participants
    business_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="business_assessments"
    )
    assessor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assessor_assessments"
    )
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewer_assessments"
    )

    # Business-submitted information (business-visible)
    business_info = models.TextField(blank=True)

    # Internal analysis summary (private)
    summary = models.TextField(blank=True)

    # Consent
    consent_given = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.business_name} [{self.get_stage_display()}]"

    @property
    def total_score(self):
        scores = self.scores.select_related("criterion")
        if not scores:
            return None
        got = sum(s.value * s.criterion.weight for s in scores)
        possible = sum(s.criterion.max_score * s.criterion.weight for s in scores)
        if possible == 0:
            return None
        return round(got / possible * 100, 1)

    @property
    def rating(self):
        score = self.total_score
        if score is None:
            return None
        if score >= 85:
            return "Excellent"
        if score >= 70:
            return "Good"
        if score >= 50:
            return "Fair"
        return "Poor"


class Score(models.Model):
    """Assessor's score for a single criterion (private working data)."""
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="scores")
    criterion = models.ForeignKey(Criterion, on_delete=models.CASCADE)
    value = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True)

    class Meta:
        unique_together = ("assessment", "criterion")

    def __str__(self):
        return f"{self.criterion.name}: {self.value}"


def evidence_upload_path(instance, filename):
    return f"evidence/assessment_{instance.assessment_id}/{filename}"


class Evidence(models.Model):
    """Private evidence file with integrity metadata."""
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="evidence")
    evidence_type = models.CharField(max_length=120)
    source = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to=evidence_upload_path)
    file_hash = models.CharField(max_length=64, blank=True)  # sha256
    collected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    collected_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.evidence_type} ({self.assessment.business_name})"


class PublishedReport(models.Model):
    """
    Frozen, read-only snapshot created on approval + consent.
    This is the ONLY data the public site reads. No link back to internal records.
    """
    business_name = models.CharField(max_length=200)
    category_name = models.CharField(max_length=120)
    rating = models.CharField(max_length=40)
    score = models.FloatField()
    summary = models.TextField()
    findings = models.JSONField(default=list)  # list of {criterion, value, max, note}
    assessment_date = models.DateField()
    valid_until = models.DateField()
    version = models.PositiveIntegerField(default=1)
    published_at = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(max_length=220)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return f"{self.business_name} v{self.version} ({self.rating})"


class AuditLog(models.Model):
    """Append-only log of views, edits and approvals."""
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=200)
    assessment = models.ForeignKey(
        Assessment, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_entries"
    )
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
