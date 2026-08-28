"""Embedded call integration management and public authentication routes."""
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import (
    get_current_user,
    get_db,
    get_redis,
    require_permission,
    require_permission_short_session,
)
from app.schemas.embedded_call import (
    EmbedSessionRequest,
    EmbedSessionResponse,
    EmbedSignatureRequest,
    EmbedSignatureResponse,
    EmbeddedCallIntegrationCreate,
    EmbeddedCallIntegrationListResponse,
    EmbeddedCallIntegrationResponse,
    EmbeddedCallIntegrationSecretResponse,
    EmbeddedCallIntegrationUpdate,
    EmbeddedCallSecretRotateRequest,
    EmbeddedCallCommandResponse,
    EmbeddedCallControlRequest,
    EmbeddedCallControlResponse,
    EmbeddedCallDialRequest,
)
from app.schemas.permission import EffectivePrincipal
from app.services.embedded_call_integration_service import (
    MANAGE_PERMISSION,
    EmbeddedCallIntegrationService,
)
from app.services.embedded_call_dial_service import EmbeddedCallDialService
from app.repositories.embedded_call_integration_repository import (
    EmbeddedCallIntegrationRepository,
)
from app.services.embedded_call_control_service import EmbeddedCallControlService


router = APIRouter(tags=["EmbeddedCall"])
manage_router = APIRouter(prefix="/call-center/embedded-call-integrations")
public_router = APIRouter(prefix="/public/call-center")
command_router = APIRouter(prefix="/call-center/embed/commands")
control_router = APIRouter(prefix="/call-center/embed/control")


@manage_router.get("", response_model=EmbeddedCallIntegrationListResponse)
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> EmbeddedCallIntegrationListResponse:
    return await EmbeddedCallIntegrationService.list_integrations(db, principal.tenant_id)


@manage_router.post(
    "",
    response_model=EmbeddedCallIntegrationSecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    body: EmbeddedCallIntegrationCreate,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> EmbeddedCallIntegrationSecretResponse:
    return await EmbeddedCallIntegrationService.create_integration(
        db,
        tenant_id=principal.tenant_id,
        actor_id=int(principal.user_id),
        data=body,
    )


@manage_router.delete("/{public_id}", status_code=status.HTTP_200_OK)
async def delete_integration(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> dict[str, str]:
    await EmbeddedCallIntegrationService.delete_integration(
        db, tenant_id=principal.tenant_id, public_id=public_id
    )
    return {"message": "Deleted successfully"}


@manage_router.get("/{public_id}", response_model=EmbeddedCallIntegrationResponse)
async def get_integration(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> EmbeddedCallIntegrationResponse:
    return await EmbeddedCallIntegrationService.get_integration(
        db, principal.tenant_id, public_id
    )


@manage_router.patch("/{public_id}", response_model=EmbeddedCallIntegrationResponse)
async def update_integration(
    public_id: UUID,
    body: EmbeddedCallIntegrationUpdate,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> EmbeddedCallIntegrationResponse:
    return await EmbeddedCallIntegrationService.update_integration(
        db,
        tenant_id=principal.tenant_id,
        actor_id=int(principal.user_id),
        public_id=public_id,
        data=body,
    )


@manage_router.post(
    "/{public_id}/rotate-secret",
    response_model=EmbeddedCallIntegrationSecretResponse,
)
async def rotate_secret(
    public_id: UUID,
    body: EmbeddedCallSecretRotateRequest,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> EmbeddedCallIntegrationSecretResponse:
    return await EmbeddedCallIntegrationService.rotate_secret(
        db,
        tenant_id=principal.tenant_id,
        actor_id=int(principal.user_id),
        public_id=public_id,
        grace_period_hours=body.grace_period_hours,
    )


@manage_router.delete(
    "/{public_id}/previous-secret", response_model=EmbeddedCallIntegrationResponse
)
async def revoke_previous_secret(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> EmbeddedCallIntegrationResponse:
    return await EmbeddedCallIntegrationService.revoke_previous_secret(
        db,
        tenant_id=principal.tenant_id,
        actor_id=int(principal.user_id),
        public_id=public_id,
    )


@public_router.post("/embed-signatures", response_model=EmbedSignatureResponse)
async def issue_embed_signature(
    body: EmbedSignatureRequest,
    x_opendesk_integration_secret: str = Header(...),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> EmbedSignatureResponse:
    return await EmbeddedCallIntegrationService.issue_signature(
        db,
        redis,
        data=body,
        server_secret=x_opendesk_integration_secret,
    )


@public_router.post("/embed-sessions", response_model=EmbedSessionResponse)
async def exchange_embed_signature(
    body: EmbedSessionRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> EmbedSessionResponse:
    return await EmbeddedCallIntegrationService.exchange_signature(db, redis, data=body)


@public_router.get("/embed-frame-policy", status_code=status.HTTP_204_NO_CONTENT)
async def get_embed_frame_policy(
    response: Response,
    integration_key: str = Query(..., alias="integrationKey"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    integration = await EmbeddedCallIntegrationRepository.get_by_integration_key(
        db, integration_key
    )
    if integration is None or not integration.is_enabled:
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    origins = " ".join(integration.allowed_origins)
    response.headers["X-Frame-Ancestors"] = origins
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@command_router.post("/dial", response_model=EmbeddedCallCommandResponse)
async def dial_from_embed(
    body: EmbeddedCallDialRequest,
    current_user: dict = Depends(get_current_user),
    _principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.dial.outbound")
    ),
    redis: aioredis.Redis = Depends(get_redis),
) -> EmbeddedCallCommandResponse:
    return await EmbeddedCallDialService.dial(
        redis, session=current_user, data=body
    )


@command_router.get("/{command_id}", response_model=EmbeddedCallCommandResponse)
async def get_embed_command(
    command_id: str,
    current_user: dict = Depends(get_current_user),
    _principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.dial.outbound")
    ),
    redis: aioredis.Redis = Depends(get_redis),
) -> EmbeddedCallCommandResponse:
    return await EmbeddedCallDialService.get_command(
        redis, session=current_user, command_id=command_id
    )


@control_router.post("/acquire", response_model=EmbeddedCallControlResponse)
async def acquire_embed_control(
    body: EmbeddedCallControlRequest,
    current_user: dict = Depends(get_current_user),
    _principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.workspace.use")
    ),
    redis: aioredis.Redis = Depends(get_redis),
) -> EmbeddedCallControlResponse:
    return await EmbeddedCallControlService.acquire(
        redis,
        session=current_user,
        instance_id=body.instance_id,
        surface=body.surface,
    )


@control_router.post("/heartbeat", response_model=EmbeddedCallControlResponse)
async def heartbeat_embed_control(
    body: EmbeddedCallControlRequest,
    current_user: dict = Depends(get_current_user),
    _principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.workspace.use")
    ),
    redis: aioredis.Redis = Depends(get_redis),
) -> EmbeddedCallControlResponse:
    if body.lease_token is None:
        return EmbeddedCallControlResponse(is_owner=False, expires_in=15)
    return await EmbeddedCallControlService.heartbeat(
        redis,
        session=current_user,
        instance_id=body.instance_id,
        lease_token=body.lease_token,
    )


@control_router.post("/takeover", response_model=EmbeddedCallControlResponse)
async def takeover_embed_control(
    body: EmbeddedCallControlRequest,
    current_user: dict = Depends(get_current_user),
    _principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.workspace.use")
    ),
    redis: aioredis.Redis = Depends(get_redis),
) -> EmbeddedCallControlResponse:
    return await EmbeddedCallControlService.takeover(
        redis,
        session=current_user,
        instance_id=body.instance_id,
        surface=body.surface,
    )


@control_router.post("/release", response_model=EmbeddedCallControlResponse)
async def release_embed_control(
    body: EmbeddedCallControlRequest,
    current_user: dict = Depends(get_current_user),
    _principal: EffectivePrincipal = Depends(
        require_permission_short_session("call.workspace.use")
    ),
    redis: aioredis.Redis = Depends(get_redis),
) -> EmbeddedCallControlResponse:
    if body.lease_token is None:
        return EmbeddedCallControlResponse(is_owner=False, expires_in=15)
    return await EmbeddedCallControlService.release(
        redis,
        session=current_user,
        instance_id=body.instance_id,
        lease_token=body.lease_token,
    )


router.include_router(manage_router)
router.include_router(public_router)
router.include_router(command_router)
router.include_router(control_router)
