"""Unit tests for auth-related diagnostic logging."""
from __future__ import annotations

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.core.client_info import get_client_ip, get_user_agent
from app.core.exceptions import (
    NotFoundError,
    SessionReplacedError,
    UnauthorizedError,
    register_exception_handlers,
)
from app.core.security import create_access_token, hash_password
from app.schemas.auth import LoginRequest
from app.services.auth_service import AuthService
from app.services.employee_session_service import EmployeeSessionService


def _build_unauthorized_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/protected")
    async def protected():
        raise UnauthorizedError("Invalid or expired token")

    @app.get("/replaced")
    async def replaced():
        raise SessionReplacedError()

    return app


def _request_with_headers(
    headers: dict[str, str] | None = None,
    *,
    client_host: str | None = "127.0.0.1",
) -> Request:
    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.3", "version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": Headers(headers or {}).raw,
        "client": (client_host, 12345) if client_host else None,
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_get_client_ip_prefers_cf_connecting_ip():
    request = _request_with_headers(
        {
            "cf-connecting-ip": "203.0.113.9",
            "x-forwarded-for": "198.51.100.1, 10.0.0.1",
            "x-real-ip": "192.0.2.1",
        },
        client_host="172.27.0.2",
    )
    assert get_client_ip(request) == "203.0.113.9"


def test_get_client_ip_x_forwarded_for_takes_first():
    request = _request_with_headers(
        {"x-forwarded-for": "198.51.100.1, 10.0.0.1"},
        client_host="172.27.0.2",
    )
    assert get_client_ip(request) == "198.51.100.1"


def test_get_client_ip_falls_back_to_x_real_ip():
    request = _request_with_headers(
        {"x-real-ip": "192.0.2.55"},
        client_host="172.27.0.2",
    )
    assert get_client_ip(request) == "192.0.2.55"


def test_get_client_ip_falls_back_to_request_client_host():
    request = _request_with_headers({}, client_host="172.27.0.2")
    assert get_client_ip(request) == "172.27.0.2"


def test_get_client_ip_returns_dash_when_unavailable():
    request = _request_with_headers({}, client_host=None)
    assert get_client_ip(request) == "-"


def test_get_user_agent_truncates():
    long_ua = "A" * 250
    request = _request_with_headers({"user-agent": long_ua})
    assert get_user_agent(request) == "A" * 200


def test_unauthorized_handler_logs_expired_token_claims(caplog):
    token = create_access_token(
        {
            "sub": "42",
            "tenant_id": 7,
            "session_id": "abcdef1234567890",
            "roles": ["agent"],
        },
        expires_delta=timedelta(seconds=-30),
    )
    client = TestClient(_build_unauthorized_app(), raise_server_exceptions=False)

    with caplog.at_level(logging.WARNING, logger="app.core.exceptions"):
        response = client.get(
            "/protected",
            headers={
                "Authorization": f"Bearer {token}",
                "x-forwarded-for": "203.0.113.10",
                "user-agent": "OpenDeskAgent/1.0",
            },
        )

    assert response.status_code == 401
    record = next(r for r in caplog.records if r.name == "app.core.exceptions")
    message = record.getMessage()
    assert "error_code=UNAUTHORIZED" in message
    assert "user_id=42" in message
    assert "tenant_id=7" in message
    assert "session_id=abcdef12" in message
    assert "abcdef1234567890" not in message
    assert record.error_code == "UNAUTHORIZED"
    assert record.user_id == "42"
    assert record.tenant_id == "7"
    assert record.session_id == "abcdef12"
    assert record.client_ip == "203.0.113.10"
    assert int(record.token_expired_for_s) > 0
    assert "token_expired_for_s=-" not in message


def test_unauthorized_handler_logs_session_replaced_error_code(caplog):
    token = create_access_token(
        {
            "sub": "9",
            "tenant_id": 3,
            "session_id": "oldsession99",
        }
    )
    client = TestClient(_build_unauthorized_app(), raise_server_exceptions=False)

    with caplog.at_level(logging.WARNING, logger="app.core.exceptions"):
        response = client.get(
            "/replaced",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_REPLACED"
    record = next(r for r in caplog.records if r.name == "app.core.exceptions")
    assert record.error_code == "SESSION_REPLACED"
    assert "error_code=SESSION_REPLACED" in record.getMessage()


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Basic abc"},
    ],
)
def test_unauthorized_handler_degrades_when_token_missing_or_garbage(headers, caplog):
    client = TestClient(_build_unauthorized_app(), raise_server_exceptions=False)

    with caplog.at_level(logging.WARNING, logger="app.core.exceptions"):
        response = client.get("/protected", headers=headers)

    assert response.status_code == 401
    record = next(r for r in caplog.records if r.name == "app.core.exceptions")
    assert record.error_code == "UNAUTHORIZED"
    assert record.user_id == "-"
    assert record.tenant_id == "-"
    assert record.session_id == "-"
    assert record.token_expired_for_s == "-"


def _login_fixtures(*, current_session_id: str | None):
    tenant = SimpleNamespace(id=1, is_active=True)
    employee = SimpleNamespace(
        id=42,
        tenant_id=1,
        username="agent",
        name="Agent",
        display_name="Agent",
        avatar=None,
        roles=["agent"],
        password_hash=hash_password("Test1234"),
        is_active=True,
        preferences={},
        current_session_id=current_session_id,
    )
    principal = SimpleNamespace(
        role_ids=[],
        permissions=["chat.workspace.use"],
        data_scopes={},
        is_super_admin=False,
        group_ids=[],
    )
    return tenant, employee, principal


async def _run_login(monkeypatch, *, current_session_id: str | None, caplog):
    tenant, employee, principal = _login_fixtures(current_session_id=current_session_id)

    async def fake_update_login_session(_db, emp, session_id):
        emp.current_session_id = session_id
        return emp

    monkeypatch.setattr(
        "app.services.auth_service.TenantRepository.resolve_by_identifier",
        AsyncMock(return_value=tenant),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeRepository.get_by_username_or_email",
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
        lambda: "newsess00112233",
    )
    monkeypatch.setattr(
        "app.services.auth_service.PermissionService.get_current_principal",
        AsyncMock(return_value=principal),
    )
    monkeypatch.setattr(
        "app.services.auth_service.create_access_token",
        lambda data: "signed-token",
    )

    with caplog.at_level(logging.INFO, logger="app.services.auth_service"):
        await AuthService.login(
            AsyncMock(),
            LoginRequest(tenant="test", username="agent", password="Test1234"),
            client_ip="198.51.100.20",
            user_agent="pytest-agent",
        )


@pytest.mark.asyncio
async def test_login_success_logs_replaced_previous_false(monkeypatch, caplog):
    await _run_login(monkeypatch, current_session_id=None, caplog=caplog)

    record = next(r for r in caplog.records if "Login success" in r.getMessage())
    assert record.replaced_previous == "false"
    assert "replaced_previous=False" in record.getMessage()
    assert record.user_id == "42"
    assert record.tenant_id == "1"
    assert record.session_id == "newsess0"
    assert record.client_ip == "198.51.100.20"
    assert record.auth_method == "password"


@pytest.mark.asyncio
async def test_login_success_logs_replaced_previous_true(monkeypatch, caplog):
    await _run_login(monkeypatch, current_session_id="oldsessionaabbcc", caplog=caplog)

    record = next(r for r in caplog.records if "Login success" in r.getMessage())
    assert record.replaced_previous == "true"
    assert "replaced_previous=True" in record.getMessage()
    assert record.session_id == "newsess0"
    assert "oldsessionaabbcc" not in record.getMessage()


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("", "(empty)"),
        ("a", "* (len=1)"),
        ("ab", "** (len=2)"),
        ("Test1234", "T******4 (len=8)"),
    ],
)
def test_mask_password_redacts_middle(password, expected):
    assert AuthService._mask_password(password) == expected


@pytest.mark.asyncio
async def test_login_failure_logs_invalid_password_with_account_fields(monkeypatch, caplog):
    tenant, employee, _principal = _login_fixtures(current_session_id=None)
    monkeypatch.setattr(
        "app.services.auth_service.TenantRepository.resolve_by_identifier",
        AsyncMock(return_value=tenant),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeRepository.get_by_username_or_email",
        AsyncMock(return_value=employee),
    )

    with caplog.at_level(logging.WARNING, logger="app.services.auth_service"):
        with pytest.raises(UnauthorizedError, match="Invalid credentials"):
            await AuthService.login(
                AsyncMock(),
                LoginRequest(tenant="membrane", username="8001", password="WrongPass"),
                client_ip="203.0.113.50",
                user_agent="pytest-login-fail",
            )

    record = next(r for r in caplog.records if "Login failed" in r.getMessage())
    message = record.getMessage()
    assert "reason=invalid_password" in message
    assert "tenant=membrane" in message
    assert "tenant_id=1" in message
    assert "username=8001" in message
    assert "password=W*******s (len=9)" in message
    assert "WrongPass" not in message
    assert record.reason == "invalid_password"
    assert record.tenant == "membrane"
    assert record.username == "8001"
    assert record.password_masked == "W*******s (len=9)"
    assert record.user_id == "42"
    assert record.client_ip == "203.0.113.50"


@pytest.mark.asyncio
async def test_login_failure_logs_user_not_found(monkeypatch, caplog):
    tenant = SimpleNamespace(id=7, is_active=True)
    monkeypatch.setattr(
        "app.services.auth_service.TenantRepository.resolve_by_identifier",
        AsyncMock(return_value=tenant),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeRepository.get_by_username_or_email",
        AsyncMock(return_value=None),
    )

    with caplog.at_level(logging.WARNING, logger="app.services.auth_service"):
        with pytest.raises(UnauthorizedError, match="Invalid credentials"):
            await AuthService.login(
                AsyncMock(),
                LoginRequest(tenant="membrane", username="missing", password="Secret1"),
                client_ip="198.51.100.9",
            )

    record = next(r for r in caplog.records if "Login failed" in r.getMessage())
    assert record.reason == "user_not_found"
    assert record.tenant_id == "7"
    assert record.username == "missing"
    assert record.user_id == "-"
    assert "password=S*****1 (len=7)" in record.getMessage()


@pytest.mark.asyncio
async def test_login_failure_logs_tenant_not_found(monkeypatch, caplog):
    monkeypatch.setattr(
        "app.services.auth_service.TenantRepository.resolve_by_identifier",
        AsyncMock(return_value=None),
    )

    with caplog.at_level(logging.WARNING, logger="app.services.auth_service"):
        with pytest.raises(NotFoundError, match="Tenant not found"):
            await AuthService.login(
                AsyncMock(),
                LoginRequest(tenant="no-such-tenant", username="8001", password="Abcd1234"),
            )

    record = next(r for r in caplog.records if "Login failed" in r.getMessage())
    assert record.reason == "tenant_not_found"
    assert record.tenant == "no-such-tenant"
    assert record.username == "8001"
    assert record.tenant_id == "-"


def test_validate_employee_session_logs_both_session_prefixes(caplog):
    employee = SimpleNamespace(
        id=55,
        tenant_id=2,
        is_active=True,
        current_session_id="xyz98765deadbeef",
    )

    with caplog.at_level(logging.WARNING, logger="app.services.employee_session_service"):
        with pytest.raises(SessionReplacedError):
            EmployeeSessionService.validate_employee_session(
                employee,
                tenant_id=2,
                token_session_id="abc12345cafebabe",
            )

    record = next(
        r for r in caplog.records if "Employee session replaced" in r.getMessage()
    )
    message = record.getMessage()
    assert "user_id=55" in message
    assert "tenant_id=2" in message
    assert "current_session_id=xyz98765" in message
    assert "token_session_id=abc12345" in message
    assert "xyz98765deadbeef" not in message
    assert "abc12345cafebabe" not in message
    assert record.current_session_id == "xyz98765"
    assert record.token_session_id == "abc12345"
