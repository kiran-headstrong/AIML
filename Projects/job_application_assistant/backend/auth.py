"""
Authentication utilities: password hashing, JWT creation/validation, and the
FastAPI dependency that resolves the current authenticated user.

Password hashing uses passlib with the bcrypt scheme. JWTs are signed and
verified with python-jose using the secret, algorithm, and expiry configured
in :mod:`config`.

Import style follows the rest of the backend package (direct module imports),
since ``main.py`` inserts the backend directory onto ``sys.path``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import User

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
]


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

#: Password hashing context. ``deprecated="auto"`` lets passlib transparently
#: upgrade hashes to the preferred scheme over time.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

#: bcrypt only considers the first 72 bytes of a password. Longer inputs raise
#: in newer bcrypt releases, so we truncate deterministically at the byte level.
_BCRYPT_MAX_BYTES = 72


def _prepare_password(password: str) -> bytes:
    """Encode and truncate a password to bcrypt's 72-byte input limit."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt and return the hash string."""
    return pwd_context.hash(_prepare_password(password))


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if ``plain`` matches the stored ``hashed`` password."""
    return pwd_context.verify(_prepare_password(plain), hashed)


# ---------------------------------------------------------------------------
# JWT creation / validation
# ---------------------------------------------------------------------------


def create_access_token(
    subject: str | UUID,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    The user identifier is stored in the ``sub`` claim and an ``exp`` claim is
    always included. When ``expires_delta`` is omitted the configured
    ``jwt_expiration_minutes`` value is used.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expiration_minutes)

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"sub": str(subject), "exp": expire}
    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Raises:
        HTTPException: 401 if the token is invalid, malformed, or expired.
    """
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:  # invalid signature, expired, malformed, ...
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI auth dependency
# ---------------------------------------------------------------------------

#: Extracts the ``Authorization: Bearer <token>`` credentials from a request.
bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current authenticated user from a Bearer JWT.

    Decodes the token, extracts the user id from the ``sub`` claim, and loads
    the matching :class:`~models.User`. Raises ``401`` when the token is
    missing/invalid/expired or the referenced user no longer exists.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(credentials.credentials)
    subject = payload.get("sub")
    if not subject:
        raise credentials_exception

    try:
        user_id = UUID(subject)
    except (ValueError, TypeError) as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user
