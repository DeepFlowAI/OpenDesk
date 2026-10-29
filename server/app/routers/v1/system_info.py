"""Public system info — UX hints for the frontend.

This endpoint is intentionally **not** an authorisation gate. It tells the
frontend whether to render multi-tenant UI and whether reports are available.
Those flags follow which extension packages actually loaded, not a config
switch. The tenants and reports packages ship with the application, so a
normal deployment reports multi-tenant mode and reports as enabled.
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
