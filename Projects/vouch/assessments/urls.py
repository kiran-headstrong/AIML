from django.urls import path
from . import views

urlpatterns = [
    # Public
    path("", views.public_home, name="public_home"),
    path("report/<slug:slug>/", views.public_report, name="public_report"),

    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Internal dashboard
    path("dashboard/", views.dashboard, name="dashboard"),
    path("assessments/new/", views.assessment_create, name="assessment_create"),
    path("assessments/<int:pk>/", views.assessment_detail, name="assessment_detail"),
    path("assessments/<int:pk>/evidence/", views.add_evidence, name="add_evidence"),
    path("evidence/<int:pk>/download/", views.evidence_download, name="evidence_download"),
    path("assessments/<int:pk>/scores/", views.save_scores, name="save_scores"),
    path("assessments/<int:pk>/summary/", views.save_summary, name="save_summary"),
    path("assessments/<int:pk>/advance/", views.advance_stage, name="advance_stage"),
    path("assessments/<int:pk>/publish/", views.publish, name="publish"),
    path("audit/", views.audit_trail, name="audit_trail"),

    # Business portal
    path("portal/", views.business_home, name="business_home"),
    path("portal/<int:pk>/", views.business_assessment, name="business_assessment"),
]
