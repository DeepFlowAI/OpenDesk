"""
Unit tests for runtime permission resolution.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ValidationError
from app.services.employee_service import EmployeeService
from app.services.permission_catalog import ALL_PERMISSION_KEYS
from app.services.permission_service import PermissionService
from app.services.role_service import RoleService


def _role(
    role_id: int,
    permissions: list[str],
    data_scopes: dict[str, str] | None = None,
    key: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=role_id,
        key=key,
        permissions=permissions,
        data_scopes=data_scopes or {},
    )


def test_merge_role_permissions_filters_missing_switches():
    roles = [
        _role(1, ["org.employee.view", "chat.session_record.view"]),
        _role(2, ["chat.workspace.use", "chat.session_record.export"]),
    ]

    permissions = PermissionService.merge_role_permissions(roles)

    assert "chat.workspace.use" in permissions
    assert "chat.session_record.view" in permissions
    assert "chat.session_record.export" in permissions
    assert "org.employee.view" not in permissions


def test_merge_role_data_scopes_uses_widest_scope():
    roles = [
        _role(1, ["ticket.workspace.view"], {"ticket": "self"}),
        _role(2, ["ticket.workspace.view"], {"ticket": "group"}),
        _role(3, ["call.workspace.use", "call.record.view"], {"call_record": "all"}),
    ]
    permissions = [
        "ticket.workspace.view",
        "call.workspace.use",
        "call.record.view",
    ]

    data_scopes = PermissionService.merge_role_data_scopes(roles, permissions)

    assert data_scopes["ticket"] == "group"
    assert data_scopes["call_record"] == "all"


def test_merge_role_data_scopes_defaults_to_self_for_view_permission():
    roles = [_role(1, ["ticket.workspace.view"])]

    data_scopes = PermissionService.merge_role_data_scopes(roles, ["ticket.workspace.view"])

    assert data_scopes == {"ticket": "self"}


@pytest.mark.asyncio
async def test_get_current_principal_resolves_active_roles_and_groups():
    employee = SimpleNamespace(
        id=7,
        tenant_id=3,
        is_active=True,
        is_super_admin=False,
        roles=["agent"],
    )
    roles = [
        _role(11, ["admin.access", "org.employee.view"]),
        _role(12, ["ticket.workspace.view"], {"ticket": "group"}),
    ]

    with (
        patch(
            "app.services.permission_service.EmployeeRepository.get_by_id",
            AsyncMock(return_value=employee),
        ),
        patch(
            "app.services.permission_service.EmployeeRepository.get_group_ids_by_employee_ids",
            AsyncMock(return_value={7: [101, 102]}),
        ),
        patch(
            "app.services.permission_service.RoleRepository.get_active_roles_by_employee_id",
            AsyncMock(return_value=roles),
        ),
    ):
        principal = await PermissionService.get_current_principal(
            AsyncMock(),
            {"user_id": 7, "tenant_id": 3},
        )

    assert principal.user_id == 7
    assert principal.tenant_id == 3
    assert principal.role_ids == [11, 12]
    assert principal.group_ids == [101, 102]
    assert principal.permissions == ["admin.access", "org.employee.view", "ticket.workspace.view"]
    assert principal.data_scopes == {"ticket": "group"}


@pytest.mark.asyncio
async def test_get_current_principal_falls_back_to_legacy_system_roles():
    employee = SimpleNamespace(
        id=7,
        tenant_id=3,
        is_active=True,
        is_super_admin=False,
        roles=["admin"],
    )
    admin_role = _role(11, ["admin.access", "org.employee.view"], key="admin")
    admin_role.is_active = True

    with (
        patch(
            "app.services.permission_service.EmployeeRepository.get_by_id",
            AsyncMock(return_value=employee),
        ),
        patch(
            "app.services.permission_service.EmployeeRepository.get_group_ids_by_employee_ids",
            AsyncMock(return_value={7: []}),
        ),
        patch(
            "app.services.permission_service.RoleRepository.get_active_roles_by_employee_id",
            AsyncMock(return_value=[]),
        ),
        patch("app.services.permission_service.RoleService.ensure_system_roles", AsyncMock()),
        patch(
            "app.services.permission_service.RoleRepository.get_by_keys",
            AsyncMock(return_value=[admin_role]),
        ),
    ):
        principal = await PermissionService.get_current_principal(
            AsyncMock(),
            {"user_id": 7, "tenant_id": 3},
        )

    assert principal.role_ids == [11]
    assert principal.permissions == ["admin.access", "org.employee.view"]


@pytest.mark.asyncio
async def test_get_current_principal_super_admin_has_all_permissions():
    employee = SimpleNamespace(
        id=1,
        tenant_id=2,
        is_active=True,
        is_super_admin=True,
        roles=[],
    )

    with (
        patch(
            "app.services.permission_service.EmployeeRepository.get_by_id",
            AsyncMock(return_value=employee),
        ),
        patch(
            "app.services.permission_service.EmployeeRepository.get_group_ids_by_employee_ids",
            AsyncMock(return_value={1: []}),
        ),
    ):
        principal = await PermissionService.get_current_principal(
            AsyncMock(),
            {"user_id": 1, "tenant_id": 2},
        )

    assert principal.is_super_admin is True
    assert set(principal.permissions) == ALL_PERMISSION_KEYS
    assert principal.data_scopes == {
        "call_record": "all",
        "session_record": "all",
        "ticket": "all",
    }


def test_role_config_requires_parent_permission():
    with pytest.raises(ValidationError) as exc_info:
        RoleService._normalize_config(["org.employee.view"], {})

    assert exc_info.value.details == {"missing_requirements": {"org.employee.view": "admin.access"}}


def test_role_config_adds_default_data_scope():
    permissions, data_scopes = RoleService._normalize_config(["ticket.workspace.view"], {})

    assert permissions == ["ticket.workspace.view"]
    assert data_scopes == {"ticket": "self"}


@pytest.mark.asyncio
async def test_custom_role_assignment_does_not_fallback_to_agent_legacy_role():
    custom_role = SimpleNamespace(id=42, key=None)

    with (
        patch("app.services.employee_service.RoleService.ensure_system_roles", AsyncMock()),
        patch(
            "app.services.employee_service.RoleRepository.get_active_by_ids",
            AsyncMock(return_value=[custom_role]),
        ),
    ):
        role_ids, legacy_roles = await EmployeeService._validate_role_ids(AsyncMock(), 1, [42])

    assert role_ids == [42]
    assert legacy_roles == []


@pytest.mark.asyncio
async def test_backfill_skips_employees_with_existing_role_assignments():
    employees = [
        SimpleNamespace(id=1, roles=[]),
        SimpleNamespace(id=2, roles=[]),
    ]
    agent_role = SimpleNamespace(id=10, key="agent")

    class EmployeeResult:
        @staticmethod
        def scalars():
            class Scalars:
                @staticmethod
                def all():
                    return employees

            return Scalars()

    class ExistingAssignmentResult:
        @staticmethod
        def all():
            return [(1, 42)]

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[EmployeeResult(), ExistingAssignmentResult()]),
        add=MagicMock(),
        commit=AsyncMock(),
    )

    with (
        patch("app.services.role_service.RoleService.ensure_system_roles", AsyncMock()),
        patch(
            "app.services.role_service.RoleRepository.get_by_keys",
            AsyncMock(return_value=[agent_role]),
        ),
    ):
        await RoleService.backfill_employee_roles(db, 1)

    db.add.assert_called_once()
    new_assignment = db.add.call_args.args[0]
    assert new_assignment.employee_id == 2
    assert new_assignment.role_id == agent_role.id
