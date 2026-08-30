"""Authentication, roles, and per-user rate limiting.

This module provides a lightweight, local authentication layer intended as a
demo-safe stand-in for enterprise SSO (OIDC/SAML). It supports:

- Password hashing and verification with bcrypt.
- A JSON-backed user store with roles (``employee`` / ``admin``).
- First-run seeding of default users from environment variables so no
  credentials are ever hardcoded.
- Simple per-user, sliding-window rate limiting.

Production note:
    In a real MNC deployment this should be replaced by the corporate identity
    provider (Okta / Azure AD / Google Workspace) via OIDC or SAML, with
    sessions issued as signed, expiring tokens and secrets stored in a vault.
    The role model and rate limiter here map cleanly onto that design.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import bcrypt

from src.observability import log_event


USERS_FILE = Path(__file__).resolve().parents[1] / "data" / "users.json"

# Valid roles. ``admin`` unlocks the observability/admin portal.
ROLE_EMPLOYEE = "employee"
ROLE_ADMIN = "admin"
VALID_ROLES = {ROLE_EMPLOYEE, ROLE_ADMIN}

# Per-user rate limit: max requests within the rolling window (seconds).
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


@dataclass(frozen=True)
class User:
    """An authenticated user.

    Attributes:
        username: The unique login name.
        role: The user's role (``"employee"`` or ``"admin"``).
    """

    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        """Return whether this user has the admin role.

        Returns:
            True if the user's role is ``"admin"``.
        """
        return self.role == ROLE_ADMIN


def _hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        plain: The plaintext password.

    Returns:
        The bcrypt hash as a UTF-8 string.
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain: The plaintext password to check.
        hashed: The stored bcrypt hash.

    Returns:
        True if the password matches the hash.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _seed_users() -> dict[str, dict]:
    """Build the initial user store from environment variables.

    Reads optional ``ADMIN_USERNAME`` / ``ADMIN_PASSWORD`` and
    ``EMPLOYEE_USERNAME`` / ``EMPLOYEE_PASSWORD`` env vars. Falls back to safe
    defaults (with a logged warning) if they are not set, so the demo remains
    runnable while never hardcoding real secrets.

    Returns:
        A mapping of ``username -> {"password_hash", "role"}``.
    """
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD")
    emp_user = os.getenv("EMPLOYEE_USERNAME", "employee")
    emp_pass = os.getenv("EMPLOYEE_PASSWORD")

    if not admin_pass:
        admin_pass = "admin123"
        log_event(
            logging.WARNING,
            "ADMIN_PASSWORD not set; seeding default admin password. "
            "Set ADMIN_PASSWORD in .env for anything beyond local demo.",
            span="auth_seed",
        )
    if not emp_pass:
        emp_pass = "employee123"
        log_event(
            logging.WARNING,
            "EMPLOYEE_PASSWORD not set; seeding default employee password. "
            "Set EMPLOYEE_PASSWORD in .env for anything beyond local demo.",
            span="auth_seed",
        )

    return {
        admin_user: {"password_hash": _hash_password(admin_pass), "role": ROLE_ADMIN},
        emp_user: {"password_hash": _hash_password(emp_pass), "role": ROLE_EMPLOYEE},
    }


class UserStore:
    """A JSON-backed store of users with hashed passwords and roles.

    On first use the store is seeded from environment variables and persisted
    to ``data/users.json`` (which is gitignored). Passwords are never stored in
    plaintext.
    """

    def __init__(self, path: Path = USERS_FILE) -> None:
        """Initialize (and seed, if needed) the user store.

        Args:
            path: Path to the JSON user store file.
        """
        self._path = path
        self._lock = Lock()
        self._users: dict[str, dict] = {}
        self._load_or_seed()

    def _load_or_seed(self) -> None:
        """Load users from disk, seeding a fresh store if none exists."""
        if self._path.exists():
            with self._path.open("r", encoding="utf-8") as fh:
                self._users = json.load(fh)
            return

        self._users = _seed_users()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(self._users, fh, indent=2)
        log_event(
            logging.INFO,
            f"seeded user store with {len(self._users)} users",
            span="auth_seed",
        )

    def authenticate(self, username: str, password: str) -> User | None:
        """Verify credentials and return the matching user.

        Args:
            username: The submitted username.
            password: The submitted plaintext password.

        Returns:
            A :class:`User` on success, or ``None`` if authentication fails.
        """
        username = (username or "").strip()
        record = self._users.get(username)
        if record is None:
            return None
        if not _verify_password(password or "", record["password_hash"]):
            return None
        return User(username=username, role=record.get("role", ROLE_EMPLOYEE))


class RateLimiter:
    """Thread-safe sliding-window rate limiter keyed by username.

    Allows at most ``max_requests`` actions per ``window_seconds`` per user.
    """

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        """Initialize the limiter.

        Args:
            max_requests: Maximum requests allowed within the window.
            window_seconds: Rolling window length in seconds.
        """
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = Lock()

    def allow(self, username: str) -> bool:
        """Record a request and report whether it is within the limit.

        Args:
            username: The user making the request.

        Returns:
            True if the request is allowed, False if the user is rate-limited.
        """
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            hits = [t for t in self._hits.get(username, []) if t > cutoff]
            if len(hits) >= self._max:
                self._hits[username] = hits
                return False
            hits.append(now)
            self._hits[username] = hits
            return True
