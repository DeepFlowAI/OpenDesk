"""
SIP extension management router (tenant admin) + agent call-device endpoints.
"""
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import (
    get_current_user,
    get_db,
    get_redis,
    require_permission,
    require_permission_short_session,
)
from app.schemas.permission import EffectivePrincipal
from app.schemas.sip_extension import (
    AvailableDeviceList,
    BindableEmployee,
    CurrentDeviceResponse,
    CurrentDeviceUpdate,
    SipExtensionCreate,
    SipExtensionListResponse,
    SipExtensionResponse,
    SipExtensionSecretResponse,
    SipExtensionUpdate,
    SipRegistrationInfo,
)
from app.services.agent_call_device_service import AgentCallDeviceService
from app.services.sip_extension_service import SipExtensionService

router = APIRouter(prefix="/sip-extensions", tags=["SipExtensions"])

EXTENSION_MANAGE = "call.admin.extension.manage"


@router.get("", response_model=SipExtensionListResponse)
async def list_sip_extensions(
    page: int = 1,
    per_page: int = 20,
    keyword: str | None = None,
    registration_status: str | None = None,
    active_status: str | None = None,
    principal: EffectivePrincipal = Depends(require_permission(EXTENSION_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """List SIP extensions with keyword / registration / active filters."""
    return await SipExtensionService.list_paginated(
        db, principal, page, per_page, keyword, registration_status, active_status
    )


@router.get("/bindable-employees", response_model=list[BindableEmployee])
async def list_bindable_employees(
    keyword: str | None = None,
    for_extension_id: int | None = None,
    principal: EffectivePrincipal = Depends(require_permission(EXTENSION_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Employees eligible to be bound to a SIP extension (dropdown source).

    Pass ``for_extension_id`` when editing so agents already bound to that
    extension remain selectable.
    """
    return await SipExtensionService.list_bindable_employees(
        db, principal, keyword, for_extension_id=for_extension_id
    )


@router.post(
    "",
    response_model=SipExtensionSecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sip_extension(
    body: SipExtensionCreate,
    principal: EffectivePrincipal = Depends(
        require_permission_short_session(EXTENSION_MANAGE)
    ),
):
    """Create a SIP extension and return the one-time full registration info."""
    return await SipExtensionService.create_managed(principal, body)


@router.put("/{extension_id}", response_model=SipExtensionResponse)
async def update_sip_extension(
    extension_id: int,
    body: SipExtensionUpdate,
    principal: EffectivePrincipal = Depends(require_permission(EXTENSION_MANAGE)),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Edit name and/or bound agent. Extension number is immutable."""
    return await SipExtensionService.update(
        db, principal, extension_id, body, set(body.model_fields_set), r
    )


@router.post(
    "/{extension_id}/reset-password",
    response_model=SipExtensionSecretResponse,
)
async def reset_sip_extension_password(
    extension_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission_short_session(EXTENSION_MANAGE)
    ),
    r: aioredis.Redis = Depends(get_redis),
):
    """Reset the extension password; the old one dies and the new one is
    returned once."""
    return await SipExtensionService.reset_password_managed(
        principal, extension_id, r
    )


@router.get(
    "/{extension_id}/registration-info",
    response_model=SipRegistrationInfo,
)
async def get_sip_extension_registration_info(
    extension_id: int,
    principal: EffectivePrincipal = Depends(
        require_permission_short_session(EXTENSION_MANAGE)
    ),
):
    """Registration info for the copy action (masked password)."""
    return await SipExtensionService.get_registration_info_managed(
        principal, extension_id
    )


@router.post("/{extension_id}/disable", response_model=SipExtensionResponse)
async def disable_sip_extension(
    extension_id: int,
    principal: EffectivePrincipal = Depends(require_permission(EXTENSION_MANAGE)),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Disable an extension (blocked while ringing / in call / current device)."""
    return await SipExtensionService.disable(db, principal, extension_id, r)


@router.post("/{extension_id}/enable", response_model=SipExtensionResponse)
async def enable_sip_extension(
    extension_id: int,
    principal: EffectivePrincipal = Depends(require_permission(EXTENSION_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Re-enable a disabled extension."""
    return await SipExtensionService.enable(db, principal, extension_id)


# ─────────── Agent call-device endpoints (own devices only) ───────────

device_router = APIRouter(prefix="/call-center/agents/me", tags=["CallCenter"])


@device_router.get(
    "/devices",
    response_model=AvailableDeviceList,
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def list_my_call_devices(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """List the current agent's selectable call devices."""
    return await AgentCallDeviceService.list_available_devices(
        db, current_user["tenant_id"], current_user["user_id"], r
    )


@device_router.get(
    "/current-device",
    response_model=CurrentDeviceResponse,
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def get_my_current_device(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Read the agent's current (restored) device selection."""
    return await AgentCallDeviceService.get_current_device(
        db, current_user["tenant_id"], current_user["user_id"], r
    )


@device_router.put(
    "/current-device",
    response_model=CurrentDeviceResponse,
    dependencies=[Depends(require_permission("call.workspace.use"))],
)
async def set_my_current_device(
    body: CurrentDeviceUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Switch the agent's current call device (idle-only)."""
    return await AgentCallDeviceService.set_current_device(
        db, current_user["tenant_id"], current_user["user_id"], body.device_type, r
    )
