"""
Shared helpers for integration tests that need a real RBAC principal.
"""
import json

from sqlalchemy import text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal


_ADMIN_EMPLOYEE_IDS: dict[int, int] = {}


async def ensure_admin_principals(tenant_ids: list[int]) -> None:
    missing_tenant_ids = [
        tenant_id
        for tenant_id in tenant_ids
        if tenant_id not in _ADMIN_EMPLOYEE_IDS
    ]
    if not missing_tenant_ids:
        return

    password_hash = hash_password("Test1234abc")
    async with AsyncSessionLocal() as db:
        for tenant_id in missing_tenant_ids:
            tenant_key = f"integration-tenant-{tenant_id}"
            await db.execute(
                text(
                    """
                    INSERT INTO tenants (id, tenant_id, slug, name, is_active)
                    VALUES (:id, :tenant_key, :slug, :name, true)
                    ON CONFLICT (id) DO UPDATE SET is_active = true
                    """
                ),
                {
                    "id": tenant_id,
                    "tenant_key": tenant_key,
                    "slug": tenant_key,
                    "name": f"Integration Tenant {tenant_id}",
                },
            )
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
                    ON CONFLICT ON CONSTRAINT uq_employees_tenant_username
                    DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        roles = EXCLUDED.roles,
                        is_active = true
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "username": f"integration_admin_{tenant_id}",
                    "email": f"integration_admin_{tenant_id}@example.com",
                    "password_hash": password_hash,
                    "display_name": f"Integration Admin {tenant_id}",
                    "name": f"Integration Admin {tenant_id}",
                    "roles": json.dumps(["admin"]),
                },
            )
            employee_id = result.scalar_one()
            await db.execute(
                text("DELETE FROM employee_roles WHERE employee_id = :employee_id"),
                {"employee_id": employee_id},
            )
            _ADMIN_EMPLOYEE_IDS[tenant_id] = employee_id
        await db.commit()


def auth_headers_for_seeded_admin(tenant_id: int, role: str = "admin") -> dict:
    employee_id = _ADMIN_EMPLOYEE_IDS[tenant_id]
    token = create_access_token(
        {
            "sub": str(employee_id),
            "tenant_id": tenant_id,
            "roles": [role],
        }
    )
    return {"Authorization": f"Bearer {token}"}
