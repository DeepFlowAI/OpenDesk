"""
Security utilities: JWT token and password hashing
"""
import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.configs.settings import settings

VISITOR_IDENTITY_SECRET_PREFIX = "vs_"


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def _visitor_identity_message(
    tenant_id: int,
    channel_id: int,
    channel_key_version: int,
    visitor_external_id: str,
) -> bytes:
    return f"{tenant_id}:{channel_id}:{channel_key_version}:{visitor_external_id}".encode("utf-8")


def create_visitor_identity_secret(
    *,
    tenant_id: int,
    channel_id: int,
    channel_key_version: int,
    visitor_external_id: str,
) -> str:
    """Create a server-minted anonymous visitor secret for token renewal."""
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        _visitor_identity_message(tenant_id, channel_id, channel_key_version, visitor_external_id),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{VISITOR_IDENTITY_SECRET_PREFIX}{encoded}"


def verify_visitor_identity_secret(
    *,
    tenant_id: int,
    channel_id: int,
    channel_key_version: int,
    visitor_external_id: str,
    visitor_secret: str,
) -> bool:
    """Verify that a visitor secret was minted by this server for the identity."""
    expected = create_visitor_identity_secret(
        tenant_id=tenant_id,
        channel_id=channel_id,
        channel_key_version=channel_key_version,
        visitor_external_id=visitor_external_id,
    )
    return hmac.compare_digest(visitor_secret, expected)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=settings.JWT_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_visitor_session_token(data: dict, expires_seconds: int | None = None) -> str:
    """Create a signed visitor session JWT."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        seconds=expires_seconds or settings.VISITOR_SESSION_EXPIRE_SECONDS
    )
    to_encode.update({"typ": "visitor_session", "exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_context_token(data: dict, expires_seconds: int | None = None) -> str:
    """Create a signed Web SDK context JWT."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        seconds=expires_seconds or settings.API_CONTEXT_TOKEN_EXPIRE_SECONDS
    )
    to_encode.update({
        "typ": "context_token",
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token. Returns payload or None."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def decode_visitor_session_token(token: str) -> dict | None:
    """Decode and validate a visitor session JWT."""
    payload = decode_access_token(token)
    if not payload or payload.get("typ") != "visitor_session":
        return None
    return payload


def decode_context_token(token: str) -> dict | None:
    """Decode and validate a Web SDK context token."""
    payload = decode_access_token(token)
    if not payload or payload.get("typ") != "context_token":
        return None
    return payload
