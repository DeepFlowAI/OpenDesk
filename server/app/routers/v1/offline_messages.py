"""
Agent-facing offline message APIs.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_redis, get_current_principal, require_permission
from app.libs.realtime import get_realtime_transport
from app.schemas.conversation_file import ConversationFileAccessResponse
from app.schemas.offline_message import (
    OfflineMessageAssignRequest,
    OfflineMessageAssignSelfRequest,
    OfflineMessageCountResponse,
    OfflineMessageConvertResponse,
    OfflineMessageDetail,
    OfflineMessageListResponse,
)
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_service import ConversationService
from app.services.offline_message_service import OfflineMessageService

router = APIRouter(
    prefix="/offline-messages",
    tags=["OfflineMessages"],
    dependencies=[Depends(require_permission("chat.offline_message.view"))],
)


@router.get("", response_model=OfflineMessageListResponse)
async def list_offline_messages(
    status: Literal["pending", "converted", "all"] = Query("pending"),
    before_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    return await OfflineMessageService.list_for_agent(
        db,
        principal,
        status=status,
        before_id=before_id,
        limit=limit,
    )


@router.get("/count", response_model=OfflineMessageCountResponse)
async def count_offline_messages(
    status: Literal["pending", "converted", "all"] = Query("pending"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    return await OfflineMessageService.count_for_agent(
        db,
        principal,
        status=status,
    )


@router.get("/{offline_message_id}", response_model=OfflineMessageDetail)
async def get_offline_message(
    offline_message_id: int,
    before_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    return await OfflineMessageService.get_for_agent(
        db,
        principal,
        offline_message_id,
        before_id=before_id,
        limit=limit,
    )


@router.post("/{offline_message_id}/conversation", response_model=OfflineMessageConvertResponse)
async def create_conversation_from_offline_message(
    offline_message_id: int,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    result = await OfflineMessageService.create_conversation(
        db,
        r,
        principal,
        offline_message_id,
    )
    await _emit_conversation_created(result)
    return result


@router.post("/{offline_message_id}/assign-self", response_model=OfflineMessageConvertResponse)
async def assign_offline_message_to_self(
    offline_message_id: int,
    body: OfflineMessageAssignSelfRequest | None = None,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    result = await OfflineMessageService.create_conversation(
        db,
        r,
        principal,
        offline_message_id,
        reason=body.reason if body else None,
    )
    await _emit_conversation_created(result)
    return result


@router.post("/{offline_message_id}/assign", response_model=OfflineMessageConvertResponse)
async def assign_offline_message_to_agent(
    offline_message_id: int,
    body: OfflineMessageAssignRequest,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    result = await OfflineMessageService.assign_to_agent(
        db,
        r,
        principal,
        offline_message_id,
        body.agent_id,
        reason=body.reason,
    )
    await _emit_conversation_created(result)
    return result


@router.get(
    "/{offline_message_id}/files/{file_id}/url",
    response_model=ConversationFileAccessResponse,
)
async def get_offline_message_file_url(
    offline_message_id: int,
    file_id: str,
    download_name: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    return await OfflineMessageService.get_temporary_url_for_agent(
        db,
        principal,
        offline_message_id,
        file_id=file_id,
        download_name=download_name,
        download=download,
    )


async def _emit_conversation_created(result: dict) -> None:
    conversation = result["conversation"]
    offline_message = result["offline_message"]
    try:
        rt = get_realtime_transport()
    except RuntimeError:
        return

    visitor = offline_message.get("visitor")
    visitor_external_id = offline_message.get("visitor_external_id")
    tenant_id = offline_message.get("tenant_id")
    payload = jsonable_encoder({
        "offline_message_public_id": offline_message["public_id"],
        "conversation_public_id": conversation.public_id,
        "conversation_id": conversation.id,
        "status": conversation.status,
        "agent": {
            "id": conversation.agent.id,
            "name": ConversationService.visitor_agent_display_name(conversation.agent),
            "avatar": conversation.agent.avatar,
        } if conversation.agent else None,
    })
    if tenant_id and visitor_external_id:
        await rt.emit(
            "offline_message_conversation_created",
            payload,
            room=f"visitor:{tenant_id}:{visitor_external_id}",
            namespace="/visitor",
        )

    if conversation.agent_id:
        await rt.emit(
            "new_conversation",
            jsonable_encoder({
                "conversation_id": conversation.id,
                "visitor": {
                    "id": visitor.id,
                    "public_id": visitor.public_id,
                    "name": visitor.name,
                    "avatar_color": visitor.avatar_color,
                } if visitor else None,
                "channel": {"id": conversation.channel_id} if conversation.channel_id else None,
            }),
            room=f"agent:{tenant_id}:{conversation.agent_id}",
            namespace="/chat",
        )
