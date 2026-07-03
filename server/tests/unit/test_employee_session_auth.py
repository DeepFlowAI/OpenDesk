"""
Unit tests for employee login session validation.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import SessionReplacedError, UnauthorizedError
from app.core.security import hash_password
from app.schemas.auth import LoginRequest
from app.services.auth_service import AuthService
from app.services.employee_session_service import EmployeeSessionService


def _employee(current_session_id: str | None, tenant_id: int = 1, active: bool = True):
    return SimpleNamespace(
        current_session_id=current_session_id,
        tenant_id=tenant_id,
        is_active=active,
    )


def test_validate_employee_session_allows_matching_session():
    employee = _employee("session-a")

    result = EmployeeSessionService.validate_employee_session(
        employee,
        tenant_id=1,
        token_session_id="session-a",
    )

    assert result is employee


def test_validate_employee_session_allows_legacy_token_before_session_is_set():
    employee = _employee(None)

    result = EmployeeSessionService.validate_employee_session(
        employee,
        tenant_id=1,
        token_session_id=None,
    )

    assert result is employee


@pytest.mark.parametrize("token_session_id", [None, "session-old"])
def test_validate_employee_session_rejects_replaced_session(token_session_id):
    employee = _employee("session-new")

    with pytest.raises(SessionReplacedError):
        EmployeeSessionService.validate_employee_session(
            employee,
            tenant_id=1,
            token_session_id=token_session_id,
        )


def test_validate_employee_session_rejects_disabled_employee():
    employee = _employee("session-a", active=False)

    with pytest.raises(UnauthorizedError):
        EmployeeSessionService.validate_employee_session(
            employee,
            tenant_id=1,
            token_session_id="session-a",
        )


@pytest.mark.asyncio
async def test_login_updates_current_session_and_signs_token(monkeypatch):
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
        current_session_id=None,
    )
    principal = SimpleNamespace(
        role_ids=[],
        permissions=["chat.workspace.use"],
        data_scopes={},
        is_super_admin=False,
        group_ids=[],
    )
    token_payload = {}

    async def fake_update_login_session(_db, emp, session_id):
        emp.current_session_id = session_id
        return emp

    def fake_create_access_token(data):
        token_payload.update(data)
        return "signed-token"

    monkeypatch.setattr(
        "app.services.auth_service.TenantRepository.resolve_by_identifier",
        AsyncMock(return_value=tenant),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeRepository.get_by_username_or_email",
        AsyncMock(return_value=employee),
    )
    update_login_session = AsyncMock(side_effect=fake_update_login_session)
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeRepository.update_login_session",
        update_login_session,
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeSessionService.disconnect_current_socket",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.auth_service.EmployeeSessionService.generate_session_id",
        lambda: "session-new",
    )
    monkeypatch.setattr(
        "app.services.auth_service.PermissionService.get_current_principal",
        AsyncMock(return_value=principal),
    )
    monkeypatch.setattr("app.services.auth_service.create_access_token", fake_create_access_token)

    db = AsyncMock()
    response = await AuthService.login(
        db,
        LoginRequest(tenant="test", username="agent", password="Test1234"),
    )

    assert response.access_token == "signed-token"
    assert response.user.username == "agent"
    update_login_session.assert_awaited_once_with(db, employee, "session-new")
    assert token_payload["session_id"] == "session-new"
