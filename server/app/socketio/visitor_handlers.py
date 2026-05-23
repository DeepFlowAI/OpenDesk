"""
Socket.IO event handlers for the visitor-side /visitor namespace.

Events:
  connect    — visitor connects with a visitor session token
  disconnect — cleanup
  start_conversation — visitor initiates a new conversation
  send_message       — visitor sends a message
  typing             — visitor is typing
"""
import asyncio
import logging

from fastapi.encoders import jsonable_encoder

from app.db.redis import redis_client
from app.db.session import AsyncSessionLocal
from app.core.exceptions import UnauthorizedError
from app.libs.realtime.base import BaseRealtimeTransport
from app.services.channel_service import ChannelService
from app.services.conversation_service import ConversationService
from app.schemas.satisfaction_survey_record import SatisfactionSubmissionPayload
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService
from app.services.visitor_web_status_service import (
    VISITOR_WEB_DISCONNECT_GRACE_SECONDS,
    VisitorWebStatusService,
)

logger = logging.getLogger(__name__)

NAMESPACE = "/visitor"


async def _finalize_visitor_disconnect_after_grace(
    rt: BaseRealtimeTransport,
    tenant_id: int,
    channel_id: int,
    visitor_external_id: str,
    sid: str,
) -> None:
    """Delay offline emission so fast refresh/reconnect does not flicker."""
    try:
        await asyncio.sleep(VISITOR_WEB_DISCONNECT_GRACE_SECONDS)
        r = redis_client.client
        status = await VisitorWebStatusService.mark_disconnected(
            r,
            tenant_id=tenant_id,
            channel_id=channel_id,
            visitor_external_id=visitor_external_id,
            sid=sid,
        )
        if status != "offline":
            return
        async with AsyncSessionLocal() as db:
            await VisitorWebStatusService.emit_status_for_visitor_context(
                rt,
                r,
                db,
                tenant_id=tenant_id,
                channel_id=channel_id,
                visitor_external_id=visitor_external_id,
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Error finalizing visitor Web offline sid=%s", sid)


def register_visitor_handlers(rt: BaseRealtimeTransport) -> None:

    @rt.on("connect", namespace=NAMESPACE)  # type: ignore
    async def on_connect(sid: str, environ: dict, auth: dict | None = None):
        """Visitor connects with a visitor session token."""
        token = (auth or {}).get("visitor_session_token")
        if not token:
            raise ConnectionRefusedError("visitor_session_token required")

        try:
            async with AsyncSessionLocal() as db:
                context = await ChannelService.validate_visitor_session_token(db, token)
        except UnauthorizedError:
            raise ConnectionRefusedError("Invalid visitor session")

        await rt.save_session(sid, context, namespace=NAMESPACE)

        visitor_room = f"visitor:{context['tenant_id']}:{context['visitor_external_id']}"
        await rt.join_room(sid, visitor_room, namespace=NAMESPACE)

        r = redis_client.client
        await VisitorWebStatusService.mark_connected(
            r,
            tenant_id=context["tenant_id"],
            channel_id=context["channel_id"],
            visitor_external_id=context["visitor_external_id"],
            sid=sid,
        )
        async with AsyncSessionLocal() as db:
            await VisitorWebStatusService.emit_status_for_visitor_context(
                rt,
                r,
                db,
                tenant_id=context["tenant_id"],
                channel_id=context["channel_id"],
                visitor_external_id=context["visitor_external_id"],
            )

        logger.info("Visitor connected: %s sid=%s", context["visitor_external_id"], sid)

    @rt.on("disconnect", namespace=NAMESPACE)  # type: ignore
    async def on_disconnect(sid: str):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        visitor_external_id = session.get("visitor_external_id")
        tenant_id = session.get("tenant_id")
        channel_id = session.get("channel_id")
        logger.info("Visitor disconnected: %s", visitor_external_id)
        if tenant_id and channel_id and visitor_external_id:
            asyncio.create_task(
                _finalize_visitor_disconnect_after_grace(
                    rt,
                    tenant_id=int(tenant_id),
                    channel_id=int(channel_id),
                    visitor_external_id=visitor_external_id,
                    sid=sid,
                )
            )

    @rt.on("start_conversation", namespace=NAMESPACE)  # type: ignore
    async def on_start_conversation(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        visitor_external_id = session.get("visitor_external_id")
        channel_id = session.get("channel_id")

        if not channel_id:
            return {"error": "channel_id required"}

        r = redis_client.client
        async with AsyncSessionLocal() as db:
            result = await ConversationService.create_from_visitor(
                db,
                r,
                tenant_id=tenant_id,
                channel_id=int(channel_id),
                visitor_external_id=visitor_external_id,
                visitor_name=session.get("visitor_name"),
                metadata=data.get("metadata") or session.get("metadata"),
            )

        if result.get("offline"):
            availability = result["availability"]
            return {
                "ok": False,
                "error": "OFFLINE",
                "reason": availability["reason"],
                "offline_title": availability["offline_title"],
                "offline_message": availability["offline_message"],
            }

        conv = result["conversation"]
        if (
            conv.tenant_id != tenant_id
            or conv.channel_id != int(channel_id)
            or not conv.visitor
            or conv.visitor.external_id != visitor_external_id
        ):
            logger.warning(
                "Visitor conversation ownership mismatch: sid=%s conv=%s tenant=%s channel=%s visitor=%s",
                sid,
                getattr(conv, "id", None),
                tenant_id,
                channel_id,
                visitor_external_id,
            )
            return {"error": "conversation ownership mismatch"}

        conv_room = f"conv:{conv.id}"
        await rt.join_room(sid, conv_room, namespace=NAMESPACE)

        conv_payload = {
            "conversation_public_id": conv.public_id,
            "status": conv.status,
            "visitor": {
                "id": conv.visitor.id,
                "public_id": conv.visitor.public_id,
                "name": conv.visitor.name,
                "avatar_color": conv.visitor.avatar_color,
            } if conv.visitor else None,
            "agent": {
                "id": conv.agent.id,
                "name": conv.agent.display_name or conv.agent.name,
                "avatar": conv.agent.avatar,
            } if conv.agent else None,
        }

        should_notify = conv.agent_id and (result["is_new"] or result.get("newly_assigned"))
        if should_notify:
            agent_room = f"agent:{tenant_id}:{conv.agent_id}"
            await rt.emit("new_conversation", {
                "conversation_id": conv.id,
                "visitor": conv_payload.get("visitor"),
                "channel": {"id": conv.channel_id} if conv.channel_id else None,
            }, room=agent_room, namespace="/chat")

        r = redis_client.client
        await VisitorWebStatusService.emit_status_for_conversation(rt, r, conv)

        return {"ok": True, "conversation": conv_payload, "is_new": result["is_new"]}

    @rt.on("send_message", namespace=NAMESPACE)  # type: ignore
    async def on_send_message(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        content = data.get("content", "")
        content_type = data.get("content_type", "text")

        if not conversation_public_id or not content:
            return {"error": "conversation_public_id and content required"}

        async with AsyncSessionLocal() as db:
            msg_payload, agent_id, conv = await ConversationService.send_visitor_message_for_session(
                db,
                conversation_public_id=conversation_public_id,
                visitor_context=session,
                content_type=content_type,
                content=content,
            )

        conv_room = f"conv:{conv.id}"
        await rt.emit("new_message", msg_payload, room=conv_room, namespace=NAMESPACE)

        if agent_id:
            agent_room = f"agent:{tenant_id}:{agent_id}"
            agent_payload = {**msg_payload, "conversation_id": conv.id}
            agent_payload.pop("conversation_public_id", None)
            await rt.emit("new_message", agent_payload, room=agent_room, namespace="/chat")
            await rt.emit("conversation_updated", {
                "conversation_id": conv.id,
                "last_message_preview": ConversationService.build_message_preview(
                    msg_payload["content_type"],
                    msg_payload["content"],
                ),
                "last_message_at": msg_payload["created_at"],
                "unread_count": conv.unread_count,
            }, room=agent_room, namespace="/chat")

        return {"ok": True, "message": msg_payload}

    @rt.on("submit_satisfaction_feedback", namespace=NAMESPACE)  # type: ignore
    async def on_submit_satisfaction_feedback(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        if not conversation_public_id:
            return {"error": "conversation_public_id required"}

        try:
            payload = SatisfactionSubmissionPayload.model_validate(data.get("feedback") or data)
        except Exception:
            return {"error": "Invalid satisfaction feedback"}

        async with AsyncSessionLocal() as db:
            result = await SatisfactionSurveyRecordService.submit_public_feedback(
                db,
                conversation_public_id=conversation_public_id,
                visitor_context=session,
                payload=payload,
            )
        return jsonable_encoder({"ok": True, **result})

    @rt.on("typing", namespace=NAMESPACE)  # type: ignore
    async def on_typing(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        content = data.get("content")
        typing_content = content[:5000] if isinstance(content, str) else None
        if conversation_public_id:
            async with AsyncSessionLocal() as db:
                conv = await ConversationService.get_conversation_for_visitor_session(
                    db,
                    conversation_public_id=conversation_public_id,
                    tenant_id=session["tenant_id"],
                    channel_id=session["channel_id"],
                    visitor_external_id=session["visitor_external_id"],
                )
                if conv.agent_id:
                    agent_room = f"agent:{tenant_id}:{conv.agent_id}"
                    payload = {"conversation_id": conv.id}
                    if typing_content is not None:
                        payload["content"] = typing_content
                    await rt.emit("visitor_typing", payload, room=agent_room, namespace="/chat")
