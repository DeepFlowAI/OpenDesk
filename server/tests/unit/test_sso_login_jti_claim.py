"""Unit tests for one-time SSO token (jti) consumption."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import UnauthorizedError
from app.schemas.auth import SsoLoginRequest
from app.services.auth_service import AuthService


def _sso_fixtures():
    tenant = SimpleNamespace(id=1, is_active=True)
    employee = SimpleNamespace(
        id=42,
        tenant_id=1,
        username="admin",
        name="Admin",
        display_name="Admin",
        avatar=None,
        roles=["admin"],
        is_active=True,
        preferences={},
        current_session_id=None,
    )
    principal = SimpleNamespace(
        role_ids=[],
        permissions=["chat.workspace.use"],
        data_scopes={},
        is_super_admin=True,
        group_ids=[],
    )
    return tenant, employee, principal


def _patch_sso_login_deps(monkeypatch, *, employee, tenant, principal):
    async def fake_update_login_session(_db, emp, session_id):
        emp.current_session_id = session_id
        return emp

    monkeypatch.setattr(
        "app.services.auth_service.TenantRepository.resolve_by_identifier",
        AsyncMock(return_value=tenant),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeRepository.get_sso_admin",
        AsyncMock(return_value=employee),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeRepository.update_login_session",
        AsyncMock(side_effect=fake_update_login_session),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeSessionService.disconnect_current_socket",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeSessionService.generate_session_id",
        lambda: "sso-session-001",
    )
    monkeypatch.setattr(
        "app.services.auth_service.PermissionService.get_current_principal",
        AsyncMock(return_value=principal),
    )
    monkeypatch.setattr(
        "app.services.auth_service.create_access_token",
        lambda data: "signed-token",
    )


@pytest.mark.asyncio
async def test_sso_login_rejects_replayed_jti(monkeypatch):
    tenant, employee, principal = _sso_fixtures()
    _patch_sso_login_deps(monkeypatch, employee=employee, tenant=tenant, principal=principal)

    payload = {
        "tenant_id": "1",
        "jti": "jti-once-only",
        "exp": 4_000_000_000,
    }
    monkeypatch.setattr(
        AuthService,
        "_decode_sso_token",
        staticmethod(lambda _token: payload),
    )
    monkeypatch.setattr(
        "app.services.auth_service.settings.REDIS_URL",
        "redis://localhost:6379/0",
    )

    claimed: set[str] = set()

    async def fake_set(key, _value, *, ex=None, nx=False):
        if nx and key in claimed:
            return False
        claimed.add(key)
        return True

    redis_mock = MagicMock()
    redis_mock.client = SimpleNamespace(set=fake_set)
    monkeypatch.setattr("app.db.redis.redis_client", redis_mock)

    first = await AuthService.sso_login(AsyncMock(), SsoLoginRequest(token="sso-token"))
    assert first.access_token == "signed-token"

    with pytest.raises(UnauthorizedError, match="SSO token already used"):
        await AuthService.sso_login(AsyncMock(), SsoLoginRequest(token="sso-token"))


@pytest.mark.asyncio
async def test_sso_login_skips_jti_claim_without_redis(monkeypatch):
    tenant, employee, principal = _sso_fixtures()
    _patch_sso_login_deps(monkeypatch, employee=employee, tenant=tenant, principal=principal)

    payload = {
        "tenant_id": "1",
        "jti": "jti-no-redis",
        "exp": 4_000_000_000,
    }
    monkeypatch.setattr(
        AuthService,
        "_decode_sso_token",
        staticmethod(lambda _token: payload),
    )
    monkeypatch.setattr("app.services.auth_service.settings.REDIS_URL", None)

    claim_calls: list[str] = []

    async def unexpected_set(*_args, **_kwargs):
        claim_calls.append("set")
        return True

    redis_mock = MagicMock()
    redis_mock.client = SimpleNamespace(set=unexpected_set)
    monkeypatch.setattr("app.db.redis.redis_client", redis_mock)

    first = await AuthService.sso_login(AsyncMock(), SsoLoginRequest(token="sso-token"))
    second = await AuthService.sso_login(AsyncMock(), SsoLoginRequest(token="sso-token"))

    assert first.access_token == "signed-token"
    assert second.access_token == "signed-token"
    assert claim_calls == []
