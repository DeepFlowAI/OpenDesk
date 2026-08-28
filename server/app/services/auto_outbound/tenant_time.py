"""
Resolve per-tenant timezone for auto-outbound calendar-day / window checks.

Business timestamps stay UTC; "today", daily windows, and frequency day-buckets
are evaluated in the tenant's configured timezone.
"""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_settings import SystemSettings

logger = logging.getLogger(__name__)

DEFAULT_TENANT_TIMEZONE = "Asia/Shanghai"

# Process-local cache: tenant_id → ZoneInfo. Timezone changes are rare;
# restart or clear_tenant_timezone_cache() refreshes.
_tz_cache: dict[int, ZoneInfo] = {}


def clear_tenant_timezone_cache(tenant_id: int | None = None) -> None:
    """Clear cached timezone(s). Useful in unit tests."""
    if tenant_id is None:
        _tz_cache.clear()
    else:
        _tz_cache.pop(tenant_id, None)


def _zoneinfo_or_default(name: str | None) -> ZoneInfo:
    raw = (name or "").strip() or DEFAULT_TENANT_TIMEZONE
    try:
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        logger.warning(
            "invalid tenant timezone %r — falling back to %s",
            name,
            DEFAULT_TENANT_TIMEZONE,
        )
        return ZoneInfo(DEFAULT_TENANT_TIMEZONE)


async def resolve_tenant_timezone(db: AsyncSession, tenant_id: int) -> ZoneInfo:
    """
    Load ``system_settings.default_timezone`` for the tenant.

    Falls back to Asia/Shanghai when the row is missing or the value is invalid.
    Results are cached in-process per tenant_id.
    """
    cached = _tz_cache.get(tenant_id)
    if cached is not None:
        return cached

    raw: str | None = None
    try:
        result = await db.execute(
            select(SystemSettings.default_timezone).where(
                SystemSettings.tenant_id == tenant_id
            )
        )
        raw = result.scalar_one_or_none()
    except Exception:  # noqa: BLE001
        logger.exception(
            "resolve_tenant_timezone query failed tenant_id=%s — using default",
            tenant_id,
        )
        raw = None

    tz = _zoneinfo_or_default(raw if isinstance(raw, str) else None)
    _tz_cache[tenant_id] = tz
    return tz
