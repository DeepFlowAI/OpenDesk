"""System-level idempotent seed.

Runs once on app startup after Alembic migrations. Use this for data that is
**system-wide** (not tenant-bound) — e.g. enum reference rows, built-in roles,
global feature flags.

For tenant-scoped defaults that should accompany every tenant (form layouts,
field definitions, etc.), see ``app/services/tenant_init_service.py``.

Every operation here MUST be idempotent — ``INSERT ... ON CONFLICT DO NOTHING``
or "SELECT then INSERT" — because this function runs on every startup.
"""
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.security import hash_password
from app.models.employee import Employee
from app.models.tenant import Tenant
from app.services.role_service import RoleService
from app.services.tenant_init_service import init_tenant_data

logger = logging.getLogger(__name__)


async def seed_system_defaults(db: AsyncSession) -> None:
    """Seed system-level default data. Idempotent.

    Call site: ``app.main.lifespan`` after ``run_migrations()``.
    """
    await _ensure_default_tenant(db)
    tenant_ids = (await db.execute(select(Tenant.id))).scalars().all()
    for tenant_id in tenant_ids:
        await RoleService.ensure_system_roles(db, tenant_id)
        await RoleService.backfill_employee_roles(db, tenant_id)


async def _ensure_default_tenant(db: AsyncSession) -> None:
    """Auto-provision a default tenant + super-admin employee on first boot.

    Fires only when the ``tenants`` table is empty. This makes the default
    distribution usable out of the box (no separate tenant-provisioning step
    needed). Once any tenant exists — whether created here, by a tenant-
    management extension, or directly via SQL — this function becomes a no-op
    forever.
    """
    count = (await db.execute(select(func.count()).select_from(Tenant))).scalar_one()
    if count > 0:
        return

    tenant = Tenant(
        tenant_id=settings.DEFAULT_TENANT_ID,
        name=settings.DEFAULT_TENANT_NAME,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    admin = Employee(
        tenant_id=tenant.id,
        username=settings.DEFAULT_ADMIN_USERNAME,
        name=settings.DEFAULT_ADMIN_USERNAME,
        password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        roles=["admin"],
        is_super_admin=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    await init_tenant_data(db, tenant.id)

    logger.warning(
        "First-run init: created default tenant '%s' (id=%s) with super-admin "
        "'%s'. CHANGE THE PASSWORD ON FIRST LOGIN.",
        settings.DEFAULT_TENANT_ID,
        tenant.id,
        settings.DEFAULT_ADMIN_USERNAME,
    )
