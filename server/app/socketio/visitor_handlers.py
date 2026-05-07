"""
Socket.IO event handlers for the visitor-side /visitor namespace.

Events:
  connect    — visitor connects (no auth, but needs channel_id + visitor_id)
  disconnect — cleanup
  start_conversation — visitor initiates a new conversation
  send_message       — visitor sends a message
  typing             — visitor is typing
"""
import logging

from app.db.session import AsyncSessionLocal
from app.db.redis import redis_client
from app.enums import MessageSenderType
from app.libs.realtime.base import BaseRealtimeTransport
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

NAMESPACE = "/visitor"


def register_visitor_handlers(rt: BaseRealtimeTransport) -> None:

    @rt.on("connect", namespace=NAMESPACE)  # type: ignore
    async def on_connect(sid: str, environ: dict, auth: dict | None = None):
        """Visitor connects with channel_id, visitor_external_id, tenant_id."""
        auth = auth or {}
        tenant_id = auth.get("tenant_id")
        visitor_external_id = auth.get("visitor_external_id")

        if not tenant_id or not visitor_external_id:
            raise ConnectionRefusedError("tenant_id and visitor_external_id required")

        await rt.save_session(sid, {
            "tenant_id": int(tenant_id),
            "visitor_external_id": visitor_external_id,
            "channel_id": auth.get("channel_id"),
            "visitor_name": auth.get("visitor_name"),
        }, namespace=NAMESPACE)

        # Join visitor personal room
        visitor_room = f"visitor:{tenant_id}:{visitor_external_id}"
        await rt.join_room(sid, visitor_room, namespace=NAMESPACE)

        logger.info("Visitor connected: %s sid=%s", visitor_external_id, sid)

    @rt.on("disconnect", namespace=NAMESPACE)  # type: ignore
    async def on_disconnect(sid: str):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        logger.info("Visitor disconnected: %s", session.get("visitor_external_id"))

    @rt.on("start_conversation", namespace=NAMESPACE)  # type: ignore
    async def on_start_conversation(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        visitor_external_id = session.get("visitor_external_id")
        channel_id = data.get("channel_id") or session.get("channel_id")

        if not channel_id:
            return {"error": "channel_id required"}

        r = redis_client.client
        async with AsyncSessionLocal() as db:
            result = await ConversationService.create_from_visitor(
                db, r,
                tenant_id=tenant_id,
                channel_id=int(channel_id),
                visitor_external_id=visitor_external_id,
                visitor_name=session.get("visitor_name"),
                metadata=data.get("metadata"),
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
        conv_room = f"conv:{conv.id}"

        # Join conversation room for visitor
        await rt.join_room(sid, conv_room, namespace=NAMESPACE)

        conv_payload = {
            "id": conv.id,
            "status": conv.status,
            "visitor": {
                "id": conv.visitor.id,
                "name": conv.visitor.name,
                "avatar_color": conv.visitor.avatar_color,
            } if conv.visitor else None,
            "agent": {
                "id": conv.agent.id,
                "name": conv.agent.display_name or conv.agent.name,
                "avatar": conv.agent.avatar,
            } if conv.agent else None,
        }

        # Notify the assigned agent (new conversation or queued conversation just assigned)
        should_notify = conv.agent_id and (result["is_new"] or result.get("newly_assigned"))
        if should_notify:
            agent_room = f"agent:{tenant_id}:{conv.agent_id}"
            await rt.emit("new_conversation", {
                "conversation_id": conv.id,
                "visitor": conv_payload.get("visitor"),
                "channel": {"id": conv.channel_id} if conv.channel_id else None,
            }, room=agent_room, namespace="/chat")

        return {"ok": True, "conversation": conv_payload, "is_new": result["is_new"]}

    @rt.on("send_message", namespace=NAMESPACE)  # type: ignore
    async def on_send_message(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_id = data.get("conversation_id")
        content = data.get("content", "")
        content_type = data.get("content_type", "text")

        if not conversation_id or not content:
            return {"error": "conversation_id and content required"}

        async with AsyncSessionLocal() as db:
            # Get visitor id
            from app.repositories.user_repository import UserRepository
            visitor = await UserRepository.get_by_external_id(
                db, tenant_id, session.get("visitor_external_id")
            )
            visitor_id = visitor.id if visitor else None

            msg = await ConversationService.send_message(
                db,
                conversation_id=conversation_id,
                sender_type=MessageSenderType.VISITOR.value,
                sender_id=visitor_id,
                content_type=content_type,
                content=content,
                tenant_id=tenant_id,
            )

        msg_payload = {
            "id": msg.id,
            "conversation_id": conversation_id,
            "sender_type": "visitor",
            "sender_id": visitor_id,
            "sender_name": visitor.name if visitor else None,
            "sender_avatar": None,
            "content_type": msg.content_type,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }

        conv_room = f"conv:{conversation_id}"
        await rt.emit("new_message", msg_payload, room=conv_room, namespace="/chat")
        await rt.emit("new_message", msg_payload, room=conv_room, namespace=NAMESPACE)

        # Also send to agent's personal room so messages arrive
        # even when the agent hasn't opened this conversation
        async with AsyncSessionLocal() as db:
            conv = await ConversationService.get_by_id(db, conversation_id)
            if conv and conv.agent_id:
                agent_room = f"agent:{tenant_id}:{conv.agent_id}"
                await rt.emit("new_message", msg_payload, room=agent_room, namespace="/chat")
                await rt.emit("conversation_updated", {
                    "conversation_id": conversation_id,
                    "last_message_preview": ConversationService.build_message_preview(msg.content_type, msg.content),
                    "last_message_at": msg_payload["created_at"],
                    "unread_count": conv.unread_count,
                }, room=agent_room, namespace="/chat")

        return {"ok": True, "message": msg_payload}

    @rt.on("typing", namespace=NAMESPACE)  # type: ignore
    async def on_typing(sid: str, data: dict):
        conversation_id = data.get("conversation_id")
        if conversation_id:
            conv_room = f"conv:{conversation_id}"
            await rt.emit("visitor_typing", {"conversation_id": conversation_id}, room=conv_room, namespace="/chat")
