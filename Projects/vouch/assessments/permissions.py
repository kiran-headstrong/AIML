"""
Role-based + per-assessment access control helpers.

Core rule from the synopsis: an assessor cannot approve their own work, and
users only see assessments they are assigned to (business sees only their own).
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Role


def get_role(user):
    if user.is_superuser:
        return Role.ADMIN
    profile = getattr(user, "profile", None)
    return profile.role if profile else None


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            role = get_role(request.user)
            if role not in allowed_roles:
                raise PermissionDenied("Your role cannot access this page.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def is_staff_role(user):
    return get_role(user) in (Role.ADMIN, Role.ASSESSOR, Role.REVIEWER)


def can_view_assessment(user, assessment):
    """Per-assessment assignment check."""
    role = get_role(user)
    if role == Role.ADMIN:
        return True
    if role == Role.ASSESSOR:
        return assessment.assessor_id == user.id
    if role == Role.REVIEWER:
        return assessment.reviewer_id == user.id
    if role == Role.BUSINESS:
        return assessment.business_user_id == user.id
    return False


def ensure_can_view(user, assessment):
    if not can_view_assessment(user, assessment):
        raise PermissionDenied("You are not assigned to this assessment.")
