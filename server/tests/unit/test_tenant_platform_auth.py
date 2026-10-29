"""Unit tests for Tenant Platform X-API-Key auth and the SSO secret fallback."""
import pytest

from app.configs.settings import settings
from app.core.exceptions import ServiceUnavailableError, UnauthorizedError
from app.core.tenant_platform_auth import tenant_api_key_configured, verify_tenant_api_key
from app.services.auth_service import AuthService

REAL_KEY = "unit-test-tenant-api-key"


@pytest.mark.parametrize("value", ["", "   ", "change-me-tenant-api-key", "sk-change-me"])
async def test_unconfigured_key_disables_api(monkeypatch, value):
    monkeypatch.setattr(settings, "TENANT_API_KEY", value)

    assert tenant_api_key_configured() is False
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await verify_tenant_api_key(value)
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "TENANT_API_KEY_NOT_CONFIGURED"


async def test_wrong_key_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_API_KEY", REAL_KEY)

    with pytest.raises(UnauthorizedError):
        await verify_tenant_api_key("sk-wrong")


async def test_empty_header_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_API_KEY", REAL_KEY)

    with pytest.raises(UnauthorizedError):
        await verify_tenant_api_key("")


async def test_matching_key_passes(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_API_KEY", REAL_KEY)

    assert await verify_tenant_api_key(f" {REAL_KEY} ") == f" {REAL_KEY} "


async def test_non_ascii_header_is_rejected_not_crashing(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_API_KEY", REAL_KEY)

    with pytest.raises(UnauthorizedError):
        await verify_tenant_api_key("密钥")


@pytest.mark.parametrize("value", ["", "change-me-tenant-api-key", "sk-change-me"])
def test_sso_secret_never_uses_placeholder_key(monkeypatch, value):
    monkeypatch.setattr(settings, "TENANT_PLATFORM_SSO_SECRET", "")
    monkeypatch.setattr(settings, "TENANT_API_KEY", value)

    assert AuthService._sso_secret() == ""
    with pytest.raises(UnauthorizedError, match="SSO is not configured"):
        AuthService._decode_sso_token("any.token.value")


def test_sso_secret_falls_back_to_configured_api_key(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_PLATFORM_SSO_SECRET", "")
    monkeypatch.setattr(settings, "TENANT_API_KEY", REAL_KEY)

    assert AuthService._sso_secret() == REAL_KEY


def test_dedicated_sso_secret_wins(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_PLATFORM_SSO_SECRET", "dedicated-sso-secret")
    monkeypatch.setattr(settings, "TENANT_API_KEY", "sk-change-me")

    assert AuthService._sso_secret() == "dedicated-sso-secret"
