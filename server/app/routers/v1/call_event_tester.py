"""Routes for the call integration tester's per-user event receiver."""
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.db.deps import get_redis, require_permission_short_session
from app.schemas.call_event_tester import (
    CallEventTesterEventListResponse,
    CallEventTesterReceiverResponse,
    CallEventTesterSecretRequest,
)
from app.schemas.permission import EffectivePrincipal
from app.services.call_event_tester_service import (
    MAX_BODY_BYTES,
    CallEventTesterService,
)
from app.services.embedded_call_integration_service import MANAGE_PERMISSION

router = APIRouter(
    prefix="/call-center/event-tester/receiver", tags=["call-event-tester"]
)
public_router = APIRouter(
    prefix="/public/call-center/event-tester", tags=["call-event-tester"]
)

require_manage = require_permission_short_session(MANAGE_PERMISSION)


@router.get("", response_model=CallEventTesterReceiverResponse)
async def get_receiver(
    principal: EffectivePrincipal = Depends(require_manage),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await CallEventTesterService.get_receiver(
        redis, principal.tenant_id, principal.user_id
    )


@router.post("/rotate", response_model=CallEventTesterReceiverResponse)
async def rotate_receiver(
    principal: EffectivePrincipal = Depends(require_manage),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await CallEventTesterService.rotate_receiver(
        redis, principal.tenant_id, principal.user_id
    )


@router.put("/secret", response_model=CallEventTesterReceiverResponse)
async def set_receiver_secret(
    payload: CallEventTesterSecretRequest,
    principal: EffectivePrincipal = Depends(require_manage),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await CallEventTesterService.set_secret(
        redis, principal.tenant_id, principal.user_id, payload.secret
    )


@router.get("/events", response_model=CallEventTesterEventListResponse)
async def list_receiver_events(
    after: int = Query(0, ge=0),
    principal: EffectivePrincipal = Depends(require_manage),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await CallEventTesterService.list_events(
        redis, principal.tenant_id, principal.user_id, after
    )


@router.delete("/events", status_code=status.HTTP_204_NO_CONTENT)
async def clear_receiver_events(
    principal: EffectivePrincipal = Depends(require_manage),
    redis: aioredis.Redis = Depends(get_redis),
):
    await CallEventTesterService.clear_events(
        redis, principal.tenant_id, principal.user_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.post("/{token}/webhook", include_in_schema=False)
async def receive_webhook(
    token: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_opendesk_delivery: str | None = Header(default=None),
    user_agent: str | None = Header(default=None),
    redis: aioredis.Redis = Depends(get_redis),
):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        return Response(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    body = await request.body()
    code = await CallEventTesterService.receive(
        redis,
        token,
        body=body,
        authorization=authorization,
        delivery_id=x_opendesk_delivery,
        user_agent=user_agent,
    )
    return Response(status_code=code)
