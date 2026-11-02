"""Authentication for the Tenant Platform APIs.

The tenants, telephony, SMS platform and verify-file routers all trust the
same ``TENANT_API_KEY``. Empty values and the placeholders shipped in the
example configs count as "not configured": the APIs then refuse every
request instead of accepting a publicly known key.

The tenants and telephony routers also accept a Bearer token issued by the
built-in tenant console login (``TENANT_CONSOLE_USERNAME`` /
``TENANT_CONSOLE_PASSWORD``), so the console UI never needs the API key.
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import Header
from jose import JWTError, jwt

from app.configs.settings import settings
from app.core.exceptions import ServiceUnavailableError, UnauthorizedError

PLACEHOLDER_TENANT_API_KEYS = frozenset({"change-me-tenant-api-key", "sk-change-me"})

TENANT_CONSOLE_TOKEN_TYPE = "tenant_console"


def tenant_api_key_configured() -> bool:
    key = (settings.TENANT_API_KEY or "").strip()
    return bool(key) and key not in PLACEHOLDER_TENANT_API_KEYS


async def verify_tenant_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if not tenant_api_key_configured():
        raise ServiceUnavailableError(
            "Tenant Platform API is disabled: set TENANT_API_KEY to a generated secret",
            code="TENANT_API_KEY_NOT_CONFIGURED",
        )
    expected = settings.TENANT_API_KEY.strip()
    if not hmac.compare_digest(x_api_key.strip().encode(), expected.encode()):
        raise UnauthorizedError("Invalid or missing API Key")
    return x_api_key


def tenant_console_configured() -> bool:
    return bool((settings.TENANT_CONSOLE_USERNAME or "").strip()) and bool(
        settings.TENANT_CONSOLE_PASSWORD or ""
    )


def _console_signing_key() -> str:
    # Derived from SECRET_KEY plus the console credentials: console tokens can
    # never pass as employee access tokens (and vice versa), and rotating the
    # console password invalidates every issued console token.
    material = (
        f"{TENANT_CONSOLE_TOKEN_TYPE}:{settings.TENANT_CONSOLE_USERNAME.strip()}:"
        f"{settings.TENANT_CONSOLE_PASSWORD}"
    )
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), material.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def tenant_console_credentials_match(username: str, password: str) -> bool:
    if not tenant_console_configured():
        return False
    expected_user = settings.TENANT_CONSOLE_USERNAME.strip().encode("utf-8")
    expected_pwd = settings.TENANT_CONSOLE_PASSWORD.encode("utf-8")
    user_ok = hmac.compare_digest(username.strip().encode("utf-8"), expected_user)
    pwd_ok = hmac.compare_digest(password.encode("utf-8"), expected_pwd)
    return user_ok and pwd_ok


def create_tenant_console_token() -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)`` for the console admin."""
    expires_in = settings.TENANT_CONSOLE_TOKEN_EXPIRE_HOURS * 3600
    now = datetime.now(timezone.utc)
    payload = {
        "typ": TENANT_CONSOLE_TOKEN_TYPE,
        "username": settings.TENANT_CONSOLE_USERNAME.strip(),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, _console_signing_key(), algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


def decode_tenant_console_token(token: str) -> dict | None:
    if not tenant_console_configured():
        return None
    try:
        payload = jwt.decode(token, _console_signing_key(), algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("typ") != TENANT_CONSOLE_TOKEN_TYPE:
        return None
    return payload


def _ensure_console_enabled() -> None:
    if not tenant_console_configured():
        raise ServiceUnavailableError(
            "Tenant console is disabled: set TENANT_CONSOLE_PASSWORD",
            code="TENANT_CONSOLE_NOT_CONFIGURED",
        )


async def verify_tenant_console_token(
    authorization: str | None = Header(None),
) -> str:
    """Accept only a console Bearer token. Returns the console username."""
    _ensure_console_enabled()
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")
    payload = decode_tenant_console_token(authorization[len("Bearer "):])
    if not payload:
        raise UnauthorizedError("Invalid or expired console token")
    return str(payload.get("username") or "")


async def verify_tenant_platform_access(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
) -> str:
    """Accept either the Tenant Platform API key or a console Bearer token."""
    if x_api_key is not None:
        return await verify_tenant_api_key(x_api_key)
    if authorization and authorization.startswith("Bearer "):
        return await verify_tenant_console_token(authorization)
    raise UnauthorizedError("Invalid or missing API Key")
