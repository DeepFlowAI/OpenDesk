"""Tenant timezone resolution.

Single entry point for any reports code that needs the tenant's display timezone.
The tenant model does not currently store a timezone column, so this falls back
to a project-wide default. When a per-tenant timezone column is added, only this
function needs to change — callers will pick it up automatically.
"""
from zoneinfo import ZoneInfo

_DEFAULT_TIMEZONE = ZoneInfo("Asia/Shanghai")


def get_tenant_timezone(tenant_id: int) -> ZoneInfo:
    return _DEFAULT_TIMEZONE
