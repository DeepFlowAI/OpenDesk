"""
Socket.IO event handlers for the agent-side /chat namespace.

Events:
  connect    — authenticate agent via JWT, join agent room
  disconnect — cleanup
  send_message       — agent sends a message
  typing             — agent is typing
  update_status      — change agent online status
  end_conversation   — agent ends a conversation
  mark_read          — agent read messages in a conversation
"""
import asyncio
import logging

from fastapi.encoders import jsonable_encoder

from app.configs.settings import settings
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.db.redis import redis_client
from app.enums import MessageSenderType, AgentOnlineStatus
from app.libs.realtime.base import BaseRealtimeTransport
from app.services.conversation_service import ConversationService
from app.services.agent_status_service import AgentStatusService
from app.services.permission_service import PermissionService
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService

logger = logging.getLogger(__name__)

NAMESPACE = "/chat"


async def _finalize_offline_after_grace(
    tenant_id: int, user_id: int, sid: str, grace_seconds: int
) -> None:
    """Wait out the disconnect grace window then attempt to flip to offline.

    The finalize step is sid-aware: if the agent reconnected during the grace
    window, ``finalize_disconnect_if_stale`` is a no-op.
    """
    try:
        await asyncio.sleep(max(0, grace_seconds))
        r = redis_client.client
        await AgentStatusService.finalize_disconnect_if_stale(
            r, tenant_id, user_id, sid
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "Error finalizing offline for agent=%s sid=%s", user_id, sid
        )


async def _assign_queued_conversations(
    rt: BaseRealtimeTransport,
    r,
    tenant_id: int,
    agent_id: int,
) -> None:
    """Try to assign unassigned queued conversations to the given agent."""
    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.employee_repository import EmployeeRepository

    async with AsyncSessionLocal() as db:
        user = await EmployeeRepository.get_by_id(db, agent_id)
        max_concurrent = user.max_concurrent if user else 10

        status_data = await AgentStatusService.get_status(r, tenant_id, agent_id, max_concurrent)
        if status_data["status"] != AgentOnlineStatus.ONLINE.value:
            return

        current_count = status_data["current_count"]
        available_slots = max(0, max_concurrent - current_count)
        if available_slots <= 0:
            return

        queued = await ConversationRepository.get_queued_by_tenant(
            db, tenant_id, limit=available_slots
        )
        if not queued:
            return

        for conv in queued:
            conv = await ConversationRepository.assign_agent(db, conv, agent_id, conv.group_id)
            await AgentStatusService.increment_count(r, tenant_id, agent_id)

            agent_room = f"agent:{tenant_id}:{agent_id}"
            conv_payload = {
                "conversation_id": conv.id,
                "visitor": {
                    "id": conv.visitor.id,
                    "public_id": conv.visitor.public_id,
                    "name": conv.visitor.name,
                    "avatar_color": conv.visitor.avatar_color,
                } if conv.visitor else None,
                "channel": {"id": conv.channel_id} if conv.channel_id else None,
            }
            await rt.emit("new_conversation", conv_payload, room=agent_room, namespace=NAMESPACE)

            # Also notify visitor that conversation is now active
            visitor_room = f"conv:{conv.id}"
            await rt.emit("conversation_assigned", {
                "conversation_id": conv.id,
                "conversation_public_id": conv.public_id,
                "agent": {
                    "id": user.id,
                    "name": user.display_name or user.name,
                    "avatar": user.avatar,
                } if user else None,
            }, room=visitor_room, namespace="/visitor")

            logger.info("Auto-assigned queued conv %d to agent %d", conv.id, agent_id)


def register_chat_handlers(rt: BaseRealtimeTransport) -> None:

    @rt.on("connect", namespace=NAMESPACE)  # type: ignore
    async def on_connect(sid: str, environ: dict, auth: dict | None = None):
        """Authenticate agent via JWT token in auth payload."""
        token = (auth or {}).get("token") or ""
        payload = decode_access_token(token)
        if not payload:
            logger.warning("Chat connect rejected: invalid token, sid=%s", sid)
            raise ConnectionRefusedError("Invalid token")

        user_id = payload.get("user_id") or payload.get("sub")
        tenant_id = payload.get("tenant_id")
        if not user_id or not tenant_id:
            raise ConnectionRefusedError("Missing user_id or tenant_id in token")
        user_id = int(user_id)

        await rt.save_session(sid, {
            "user_id": user_id,
            "tenant_id": tenant_id,
        }, namespace=NAMESPACE)

        # Join personal agent room for targeted events
        agent_room = f"agent:{tenant_id}:{user_id}"
        await rt.join_room(sid, agent_room, namespace=NAMESPACE)

        # Track the active Socket.IO sid to avoid stale disconnects overwriting a newer connection.
        r = redis_client.client
        await AgentStatusService.mark_connected(r, tenant_id, user_id, sid)

        # Sync current_count from DB so the counter survives reconnects
        from app.repositories.conversation_repository import ConversationRepository
        async with AsyncSessionLocal() as db:
            active_count = await ConversationRepository.count_active_by_agent(db, tenant_id, user_id)
        await AgentStatusService.set_count(r, tenant_id, user_id, active_count)

        logger.info("Agent connected: user_id=%s sid=%s active_count=%d", user_id, sid, active_count)

        # Try queued conversations after connect; the status check keeps
        # offline or busy agents from receiving work implicitly.
        try:
            await _assign_queued_conversations(rt, r, tenant_id, user_id)
        except Exception:
            logger.exception("Error auto-assigning queued conversations for agent %s", user_id)

    @rt.on("disconnect", namespace=NAMESPACE)  # type: ignore
    async def on_disconnect(sid: str):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        user_id = session.get("user_id")
        tenant_id = session.get("tenant_id")
        if not (user_id and tenant_id):
            return

        r = redis_client.client
        grace = settings.AGENT_OFFLINE_GRACE_SECONDS
        scheduled = await AgentStatusService.schedule_disconnect(
            r, tenant_id, user_id, sid, grace_seconds=grace
        )
        if not scheduled:
            return

        # Defer the actual offline transition; a reconnect within the grace
        # window will cancel it (sid mismatch in finalize Lua script).
        asyncio.create_task(
            _finalize_offline_after_grace(tenant_id, user_id, sid, grace)
        )

    @rt.on("update_status", namespace=NAMESPACE)  # type: ignore
    async def on_update_status(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        user_id = session.get("user_id")
        tenant_id = session.get("tenant_id")
        status = data.get("status")

        if not status or status not in [s.value for s in AgentOnlineStatus]:
            return {"error": "Invalid status"}

        r = redis_client.client
        await AgentStatusService.set_status(r, tenant_id, user_id, status)

        # Fetch updated status to return
        async with AsyncSessionLocal() as db:
            from app.repositories.employee_repository import EmployeeRepository
            user = await EmployeeRepository.get_by_id(db, user_id)
            max_c = user.max_concurrent if user else 10

        status_data = await AgentStatusService.get_status(r, tenant_id, user_id, max_c)
        return {"ok": True, "status": status_data}

    @rt.on("send_message", namespace=NAMESPACE)  # type: ignore
    async def on_send_message(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        user_id = session.get("user_id")
        tenant_id = session.get("tenant_id")
        conversation_id = data.get("conversation_id")
        content = data.get("content", "")
        content_type = data.get("content_type", "text")

        if not conversation_id or not content:
            return {"error": "conversation_id and content required"}

        async with AsyncSessionLocal() as db:
            msg = await ConversationService.send_message(
                db,
                conversation_id=conversation_id,
                sender_type=MessageSenderType.AGENT.value,
                sender_id=user_id,
                content_type=content_type,
                content=content,
                tenant_id=tenant_id,
            )

            # Fetch agent info for the message payload
            from app.repositories.employee_repository import EmployeeRepository
            user = await EmployeeRepository.get_by_id(db, user_id)

        msg_payload = {
            "id": msg.id,
            "conversation_id": conversation_id,
            "sender_type": "agent",
            "sender_id": user_id,
            "sender_name": user.display_name or user.name if user else "Agent",
            "sender_avatar": user.avatar if user else None,
            "content_type": msg.content_type,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            **ConversationService._message_event_overlay(msg),
        }

        # Broadcast through the same message stream used for visitor messages so
        # every agent-side UI update is driven by server-confirmed data.
        conv_room = f"conv:{conversation_id}"
        agent_room = f"agent:{tenant_id}:{user_id}"
        await rt.emit("new_message", msg_payload, room=agent_room, namespace=NAMESPACE)
        await rt.emit("new_message", msg_payload, room=conv_room, namespace="/visitor")

        return {"ok": True, "message": msg_payload}

    @rt.on("send_satisfaction_invitation", namespace=NAMESPACE)  # type: ignore
    async def on_send_satisfaction_invitation(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        user_id = session.get("user_id")
        tenant_id = session.get("tenant_id")
        conversation_id = data.get("conversation_id")
        force = bool(data.get("force"))

        if not conversation_id:
            return {"error": "conversation_id required"}

        async with AsyncSessionLocal() as db:
            principal = await PermissionService.get_current_principal(
                db, {"user_id": int(user_id), "tenant_id": int(tenant_id)}
            )
            state = await SatisfactionSurveyRecordService.send_agent_invitation(
                db,
                conversation_id=int(conversation_id),
                tenant_id=int(tenant_id),
                user={"user_id": int(user_id), "tenant_id": int(tenant_id)},
                force=force,
                principal=principal,
            )
        return {"ok": True, "state": jsonable_encoder(state)}

    @rt.on("typing", namespace=NAMESPACE)  # type: ignore
    async def on_typing(sid: str, data: dict):
        conversation_id = data.get("conversation_id")
        if conversation_id:
            conv_room = f"conv:{conversation_id}"
            await rt.emit("agent_typing", {"conversation_id": conversation_id}, room=conv_room, namespace="/visitor")

    @rt.on("end_conversation", namespace=NAMESPACE)  # type: ignore
    async def on_end_conversation(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_id = data.get("conversation_id")

        if not conversation_id:
            return {"error": "conversation_id required"}

        r = redis_client.client
        async with AsyncSessionLocal() as db:
            conv = await ConversationService.end_conversation(
                db, r, conversation_id, ended_by="agent"
            )

        end_payload = {
            "conversation_id": conversation_id,
            "conversation_public_id": conv.public_id,
            "ended_by": "agent",
        }
        conv_room = f"conv:{conversation_id}"
        agent_room = f"agent:{tenant_id}:{session.get('user_id')}"
        await rt.emit("conversation_ended", end_payload, room=agent_room, namespace=NAMESPACE)
        await rt.emit("conversation_ended", end_payload, room=conv_room, namespace="/visitor")

        return {"ok": True}

    @rt.on("mark_read", namespace=NAMESPACE)  # type: ignore
    async def on_mark_read(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        user_id = session.get("user_id")
        conversation_id = data.get("conversation_id")
        if conversation_id:
            async with AsyncSessionLocal() as db:
                await ConversationService.mark_read(db, conversation_id)
                conv = await ConversationService.get_by_id(db, conversation_id)

            conv_room = f"conv:{conversation_id}"
            agent_room = f"agent:{tenant_id}:{user_id}"
            await rt.emit("messages_read", {
                "conversation_id": conversation_id,
                "conversation_public_id": conv.public_id,
            }, room=conv_room, namespace="/visitor")
            await rt.emit("conversation_updated", {
                "conversation_id": conversation_id,
                "unread_count": 0,
            }, room=agent_room, namespace=NAMESPACE)

        return {"ok": True}
