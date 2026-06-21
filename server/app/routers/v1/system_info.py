"""Public system info — UX hints for the frontend.

This endpoint is intentionally **not** an authorisation gate. It tells the
frontend whether to render multi-tenant UI (login form's tenant field, tenant
admin pages, etc.). The actual authority over multi-tenant features comes
from whether an optional ``tenants`` extension is loaded — controlled by
file-system presence of the extension package, not by any config flag.

Single-tenant deployments do not load this extension, so ``single_tenant_mode``
is always ``true`` for them.
"""
from fastapi import APIRouter, Request

from app.configs.settings import settings

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/info")
async def get_system_info(request: Request) -> dict:
    loaded = list(getattr(request.app.state, "loaded_extensions", []))
    has_tenants_ext = "tenants" in loaded
    has_reports_ext = "reports" in loaded
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "edition": "enterprise" if has_tenants_ext else "community",
        "single_tenant_mode": not has_tenants_ext,
        "default_tenant_id": settings.DEFAULT_TENANT_ID,
        "reports_enabled": has_reports_ext,
        # Whether the voice call center (telephony) is turned on for this
        # deployment. When false the backend never connects to the telephony
        # kernel and the agent call workspace shows a "not enabled" notice.
        "call_center_enabled": settings.CALL_CENTER_ENABLED,
    }
