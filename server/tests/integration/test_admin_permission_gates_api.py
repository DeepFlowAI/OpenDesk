"""
Integration tests for admin API permission gates.
"""
import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal


_PERMISSION_GATE_CONTEXT: dict | None = None


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _auth_headers(employee_id: int, tenant_id: int, roles: list[str] | None = None) -> dict:
    token = create_access_token(
        {
            "sub": str(employee_id),
            "tenant_id": tenant_id,
            "roles": roles or [],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _employee_payload(prefix: str) -> dict:
    value = _unique(prefix)
    return {
        "name": f"Permission Gate {prefix}",
        "username": value,
        "email": f"{value}@example.com",
        "password": "Test1234abc",
        "roles": ["agent"],
    }


@pytest_asyncio.fixture
async def permission_gate_context():
    global _PERMISSION_GATE_CONTEXT
    if _PERMISSION_GATE_CONTEXT is not None:
        return _PERMISSION_GATE_CONTEXT

    suffix = uuid.uuid4().hex[:10]
    password_hash = hash_password("Test1234abc")

    async with AsyncSessionLocal() as db:
        tenant_result = await db.execute(
            text(
                """
                INSERT INTO tenants (tenant_id, slug, name, is_active)
                VALUES (:tenant_key, :slug, :name, true)
                RETURNING id
                """
            ),
            {
                "tenant_key": f"perm-gate-{suffix}",
                "slug": f"perm-gate-{suffix}",
                "name": f"Permission Gate {suffix}",
            },
        )
        tenant_id = tenant_result.scalar_one()

        async def create_employee(username: str, legacy_roles: list[str]) -> int:
            result = await db.execute(
                text(
                    """
                    INSERT INTO employees (
                        tenant_id, username, email, password_hash, display_name,
                        name, roles, is_active
                    )
                    VALUES (
                        :tenant_id, :username, :email, :password_hash, :display_name,
                        :name, CAST(:roles AS JSON), true
                    )
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "username": username,
                    "email": f"{username}@example.com",
                    "password_hash": password_hash,
                    "display_name": username,
                    "name": username,
                    "roles": json.dumps(legacy_roles),
                },
            )
            return result.scalar_one()

        async def create_role(name: str, permissions: list[str]) -> int:
            result = await db.execute(
                text(
                    """
                    INSERT INTO roles (
                        tenant_id, name, description, is_system, is_active,
                        permissions, data_scopes
                    )
                    VALUES (
                        :tenant_id, :name, :description, false, true,
                        CAST(:permissions AS JSON), CAST(:data_scopes AS JSON)
                    )
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "name": name,
                    "description": name,
                    "permissions": json.dumps(permissions),
                    "data_scopes": json.dumps({}),
                },
            )
            return result.scalar_one()

        async def assign_role(employee_id: int, role_id: int) -> None:
            await db.execute(
                text(
                    """
                    INSERT INTO employee_roles (employee_id, role_id)
                    VALUES (:employee_id, :role_id)
                    """
                ),
                {"employee_id": employee_id, "role_id": role_id},
            )

        admin_id = await create_employee(f"admin_{suffix}", ["admin"])

        view_role_id = await create_role(
            f"employee-view-{suffix}",
            ["admin.access", "org.employee.view"],
        )
        create_role_id = await create_role(
            f"employee-create-{suffix}",
            ["admin.access", "org.employee.view", "org.employee.create"],
        )
        edit_role_id = await create_role(
            f"employee-edit-{suffix}",
            ["admin.access", "org.employee.view", "org.employee.edit"],
        )
        group_role_id = await create_role(
            f"group-manage-{suffix}",
            ["admin.access", "org.group.manage"],
        )

        view_employee_id = await create_employee(f"view_{suffix}", [])
        create_employee_id = await create_employee(f"create_{suffix}", [])
        edit_employee_id = await create_employee(f"edit_{suffix}", [])
        group_employee_id = await create_employee(f"group_{suffix}", [])
        plain_employee_id = await create_employee(f"field_option_{suffix}", [])

        await assign_role(view_employee_id, view_role_id)
        await assign_role(create_employee_id, create_role_id)
        await assign_role(edit_employee_id, edit_role_id)
        await assign_role(group_employee_id, group_role_id)
        await db.commit()

    _PERMISSION_GATE_CONTEXT = {
        "tenant_id": tenant_id,
        "admin": _auth_headers(admin_id, tenant_id, ["admin"]),
        "employee_view": _auth_headers(view_employee_id, tenant_id),
        "employee_create": _auth_headers(create_employee_id, tenant_id),
        "employee_edit": _auth_headers(edit_employee_id, tenant_id),
        "group_manage": _auth_headers(group_employee_id, tenant_id),
        "plain": _auth_headers(plain_employee_id, tenant_id),
        "plain_id": plain_employee_id,
    }
    return _PERMISSION_GATE_CONTEXT


@pytest.mark.asyncio
async def test_employee_create_requires_create_permission(
    client: AsyncClient,
    permission_gate_context: dict,
):
    list_resp = await client.get(
        "/api/v1/employees",
        headers=permission_gate_context["employee_view"],
    )
    assert list_resp.status_code == 200

    denied_resp = await client.post(
        "/api/v1/employees",
        json=_employee_payload("denied"),
        headers=permission_gate_context["employee_view"],
    )
    assert denied_resp.status_code == 403

    allowed_resp = await client.post(
        "/api/v1/employees",
        json=_employee_payload("allowed"),
        headers=permission_gate_context["employee_create"],
    )
    assert allowed_resp.status_code == 201


@pytest.mark.asyncio
async def test_role_management_requires_role_manage_permission(
    client: AsyncClient,
    permission_gate_context: dict,
):
    denied_resp = await client.get(
        "/api/v1/roles",
        headers=permission_gate_context["employee_view"],
    )
    assert denied_resp.status_code == 403

    allowed_resp = await client.get(
        "/api/v1/roles",
        headers=permission_gate_context["admin"],
    )
    assert allowed_resp.status_code == 200


@pytest.mark.asyncio
async def test_role_options_are_available_to_employee_edit_permission(
    client: AsyncClient,
    permission_gate_context: dict,
):
    options_resp = await client.get(
        "/api/v1/roles/options",
        headers=permission_gate_context["employee_edit"],
    )
    assert options_resp.status_code == 200

    tree_resp = await client.get(
        "/api/v1/roles/permission-tree",
        headers=permission_gate_context["employee_edit"],
    )
    assert tree_resp.status_code == 403


@pytest.mark.asyncio
async def test_employee_groups_require_group_manage_permission(
    client: AsyncClient,
    permission_gate_context: dict,
):
    denied_resp = await client.get(
        "/api/v1/employee-groups",
        headers=permission_gate_context["employee_view"],
    )
    assert denied_resp.status_code == 403

    allowed_resp = await client.get(
        "/api/v1/employee-groups",
        headers=permission_gate_context["group_manage"],
    )
    assert allowed_resp.status_code == 200


@pytest.mark.asyncio
async def test_field_reference_options_do_not_require_org_permissions(
    client: AsyncClient,
    permission_gate_context: dict,
):
    group_resp = await client.post(
        "/api/v1/employee-groups",
        json={"name": _unique("Field Option Group")},
        headers=permission_gate_context["group_manage"],
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    employees_denied = await client.get(
        "/api/v1/employees",
        headers=permission_gate_context["plain"],
    )
    assert employees_denied.status_code == 403

    groups_denied = await client.get(
        "/api/v1/employee-groups",
        headers=permission_gate_context["plain"],
    )
    assert groups_denied.status_code == 403

    employees_resp = await client.get(
        "/api/v1/field-definitions/reference-options/employees",
        headers=permission_gate_context["plain"],
    )
    assert employees_resp.status_code == 200

    employee_detail_resp = await client.get(
        f"/api/v1/field-definitions/reference-options/employees/{permission_gate_context['plain_id']}",
        headers=permission_gate_context["plain"],
    )
    assert employee_detail_resp.status_code == 200

    groups_resp = await client.get(
        "/api/v1/field-definitions/reference-options/employee-groups",
        headers=permission_gate_context["plain"],
    )
    assert groups_resp.status_code == 200

    group_detail_resp = await client.get(
        f"/api/v1/field-definitions/reference-options/employee-groups/{group_id}",
        headers=permission_gate_context["plain"],
    )
    assert group_detail_resp.status_code == 200
