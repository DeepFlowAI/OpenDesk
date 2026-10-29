"""X-API-Key authentication for the Tenant Platform APIs.

The tenants, telephony, SMS platform and verify-file routers all trust the
same ``TENANT_API_KEY``. Empty values and the placeholders shipped in the
example configs count as "not configured": the APIs then refuse every
request instead of accepting a publicly known key.
"""
import hmac

from fastapi import Header

from app.configs.settings import settings
from app.core.exceptions import ServiceUnavailableError, UnauthorizedError

PLACEHOLDER_TENANT_API_KEYS = frozenset({"change-me-tenant-api-key", "sk-change-me"})


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
