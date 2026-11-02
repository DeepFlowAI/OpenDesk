"""Unit tests for tenant console login and the combined Tenant Platform auth."""
import pytest

from app.configs.settings import settings
from app.core.exceptions import RateLimitedError, ServiceUnavailableError, UnauthorizedError
from app.core.security import create_access_token, decode_access_token
from app.core.tenant_platform_auth import (
    create_tenant_console_token,
    decode_tenant_console_token,
    tenant_console_credentials_match,
    verify_tenant_console_token,
    verify_tenant_platform_access,
)
from app.extensions.tenants import console_service
from app.extensions.tenants.console_service import (
    LOGIN_FAIL_LIMIT,
    LOGIN_GLOBAL_FAIL_LIMIT,
    TenantConsoleAuthService,
)
from app.extensions.tenants.schemas import TenantConsoleLoginRequest

API_KEY = "example-tenant-api-key"
USERNAME = "console-admin"
PASSWORD = "example-console-pass"


class FakeRedis:
    """Minimal Redis fake: only commands available before Redis 6.2."""

    def __init__(self) -> None:
        self.data: dict[str, int] = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def incr(self, key: str) -> int:
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def delete(self, *keys: str) -> int:
        return sum(1 for key in keys if self.data.pop(key, None) is not None)


@pytest.fixture
def console_enabled(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_CONSOLE_USERNAME", USERNAME)
    monkeypatch.setattr(settings, "TENANT_CONSOLE_PASSWORD", PASSWORD)
    monkeypatch.setattr(settings, "TENANT_API_KEY", API_KEY)


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(console_service, "_redis", lambda: redis)
    return redis


def _bearer(token: str) -> str:
    return f"Bearer {token}"


async def test_console_disabled_without_password(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_CONSOLE_PASSWORD", "")

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await verify_tenant_console_token(_bearer("any"))
    assert exc_info.value.code == "TENANT_CONSOLE_NOT_CONFIGURED"
    assert tenant_console_credentials_match("admin", "") is False


def test_credentials_match(console_enabled):
    assert tenant_console_credentials_match(USERNAME, PASSWORD) is True
    assert tenant_console_credentials_match(f" {USERNAME} ", PASSWORD) is True
    assert tenant_console_credentials_match(USERNAME, "wrong") is False
    assert tenant_console_credentials_match("other", PASSWORD) is False


async def test_console_token_round_trip(console_enabled):
    token, expires_in = create_tenant_console_token()

    assert expires_in == settings.TENANT_CONSOLE_TOKEN_EXPIRE_HOURS * 3600
    assert await verify_tenant_console_token(_bearer(token)) == USERNAME


async def test_password_change_invalidates_token(console_enabled, monkeypatch):
    token, _ = create_tenant_console_token()
    monkeypatch.setattr(settings, "TENANT_CONSOLE_PASSWORD", "rotated-pass-456")

    assert decode_tenant_console_token(token) is None
    with pytest.raises(UnauthorizedError):
        await verify_tenant_console_token(_bearer(token))


async def test_employee_token_is_not_a_console_token(console_enabled):
    employee_token = create_access_token({"sub": "1", "tenant_id": 1})

    with pytest.raises(UnauthorizedError):
        await verify_tenant_console_token(_bearer(employee_token))


def test_console_token_is_not_an_employee_token(console_enabled):
    token, _ = create_tenant_console_token()

    assert decode_access_token(token) is None


async def test_platform_access_accepts_api_key(console_enabled):
    assert await verify_tenant_platform_access(x_api_key=API_KEY, authorization=None) == API_KEY


async def test_platform_access_rejects_wrong_api_key_even_with_console_token(console_enabled):
    token, _ = create_tenant_console_token()

    with pytest.raises(UnauthorizedError):
        await verify_tenant_platform_access(x_api_key="sk-wrong", authorization=_bearer(token))


async def test_platform_access_accepts_console_token(console_enabled):
    token, _ = create_tenant_console_token()

    assert await verify_tenant_platform_access(x_api_key=None, authorization=_bearer(token)) == USERNAME


async def test_platform_access_requires_credentials(console_enabled):
    with pytest.raises(UnauthorizedError):
        await verify_tenant_platform_access(x_api_key=None, authorization=None)


async def test_login_success_returns_usable_token(console_enabled, fake_redis):
    result = await TenantConsoleAuthService.login(
        TenantConsoleLoginRequest(username=USERNAME, password=PASSWORD), "1.2.3.4"
    )

    assert result.username == USERNAME
    assert await verify_tenant_console_token(_bearer(result.access_token)) == USERNAME


async def test_login_wrong_password_records_failure(console_enabled, fake_redis):
    with pytest.raises(UnauthorizedError):
        await TenantConsoleAuthService.login(
            TenantConsoleLoginRequest(username=USERNAME, password="wrong"), "1.2.3.4"
        )

    assert fake_redis.data == {
        "tenant_console:login_fail:1.2.3.4": 1,
        "tenant_console:login_fail_global": 1,
    }


async def test_login_is_rate_limited_after_repeated_failures(console_enabled, fake_redis):
    fake_redis.data["tenant_console:login_fail:1.2.3.4"] = LOGIN_FAIL_LIMIT

    with pytest.raises(RateLimitedError):
        await TenantConsoleAuthService.login(
            TenantConsoleLoginRequest(username=USERNAME, password=PASSWORD), "1.2.3.4"
        )


async def test_login_global_limit_blocks_rotating_ips(console_enabled, fake_redis):
    fake_redis.data["tenant_console:login_fail_global"] = LOGIN_GLOBAL_FAIL_LIMIT

    with pytest.raises(RateLimitedError):
        await TenantConsoleAuthService.login(
            TenantConsoleLoginRequest(username=USERNAME, password=PASSWORD), "9.9.9.9"
        )


async def test_login_success_clears_failures(console_enabled, fake_redis):
    fake_redis.data["tenant_console:login_fail:1.2.3.4"] = 3
    fake_redis.data["tenant_console:login_fail_global"] = 3

    await TenantConsoleAuthService.login(
        TenantConsoleLoginRequest(username=USERNAME, password=PASSWORD), "1.2.3.4"
    )

    assert fake_redis.data == {}


async def test_login_disabled_without_password(monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "TENANT_CONSOLE_PASSWORD", "")

    with pytest.raises(ServiceUnavailableError):
        await TenantConsoleAuthService.login(
            TenantConsoleLoginRequest(username="admin", password="x"), "1.2.3.4"
        )
