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
import uuid
from contextlib import asynccontextmanager

from fastapi.encoders import jsonable_encoder

from app.db.redis import redis_client
from app.db.session import AsyncSessionLocal
from app.core.exceptions import BusinessError, UnauthorizedError
from app.libs.realtime.base import BaseRealtimeTransport
from app.services.channel_service import ChannelService
from app.services.conversation_service import ConversationService
from app.services.conversation_realtime_service import ConversationRealtimeService
from app.services.open_agent_conversation_service import OpenAgentConversationService
from app.schemas.satisfaction_survey_record import SatisfactionSubmissionPayload
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService
from app.services.visitor_web_status_service import (
    VISITOR_WEB_DISCONNECT_GRACE_SECONDS,
    VisitorWebStatusService,
)
from app.socketio.connect_throttle import ConnectRejectionTracker, client_ip_from_environ

logger = logging.getLogger(__name__)

NAMESPACE = "/visitor"

# Tracks rejected visitor connects per client IP so a widget stuck reconnecting
# with an invalid session token is escalated to a single ERROR.
_rejection_tracker = ConnectRejectionTracker()


def _log_rejected_connect(environ: dict, reason: str) -> None:
    ip = client_ip_from_environ(environ) or "unknown"
    count, storm = _rejection_tracker.record(ip)
    if storm:
        logger.error(
            "Socket auth reconnect storm on %s: %d rejected connects from %s "
            "within the last minute (reason=%s)",
            NAMESPACE, count, ip, reason,
        )


_VISITOR_START_LOCK_TTL_SECONDS = 10
_VISITOR_START_LOCK_WAIT_SECONDS = 5.0
_VISITOR_START_LOCK_POLL_SECONDS = 0.1


@asynccontextmanager
async def _visitor_start_lock(r, tenant_id: int, channel_id: int, visitor_external_id: str):
    """Serialize concurrent start_conversation for a single visitor.

    A widget that reconnects rapidly can fire start_conversation several times
    at once; without serialization each call sees "no active conversation" and
    creates its own, leaving duplicate active conversations. Best-effort: if the
    lock can't be acquired within the wait budget we proceed anyway, degrading to
    the previous behavior rather than blocking the visitor.
    """
    key = f"visitor:start_lock:{tenant_id}:{channel_id}:{visitor_external_id}"
    token = uuid.uuid4().hex
    acquired = False
    waited = 0.0
    while waited < _VISITOR_START_LOCK_WAIT_SECONDS:
        if await r.set(key, token, ex=_VISITOR_START_LOCK_TTL_SECONDS, nx=True):
            acquired = True
            break
        await asyncio.sleep(_VISITOR_START_LOCK_POLL_SECONDS)
        waited += _VISITOR_START_LOCK_POLL_SECONDS
    try:
        yield
    finally:
        if acquired:
            current = await r.get(key)
            if isinstance(current, bytes):
                current = current.decode()
            if current == token:
                await r.delete(key)


def _open_desk_messages_from_sse_events(events: list[bytes]) -> list[dict]:
    messages: list[dict] = []
    buffer = ""
    for chunk in events:
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            frame, buffer = buffer.split("\n\n", 1)
            event, data, _event_id = OpenAgentConversationService._parse_sse_frame(frame)
            if event == "open_desk_message_saved" and data:
                messages.append(data)
    return messages


def _handoff_unavailable_socket_response(result: dict) -> dict | None:
    """Map bot handoff route failures to visitor leave-message / queue-full UX."""
    if result.get("leave_message"):
        availability = result.get("availability") or {}
        return {
            "ok": False,
            "error": "LEAVE_MESSAGE",
            "reason": availability.get("reason") or result.get("reason"),
            "leave_message_prompt": availability.get("leave_message_prompt"),
        }
    if result.get("queue_full"):
        availability = result.get("availability") or {}
        return {
            "ok": False,
            "error": "QUEUE_FULL",
            "reason": availability.get("reason") or result.get("reason") or "queue_full",
            "queue_full_message": availability.get("queue_full_message"),
            "queue_full_show_leave_message_button": availability.get(
                "queue_full_show_leave_message_button",
                True,
            ),
            "queue_full_leave_message_button_label": availability.get(
                "queue_full_leave_message_button_label",
            ),
            "leave_message_prompt": availability.get("leave_message_prompt"),
        }
    return None


def _restricted_socket_response(availability: dict) -> dict:
    return {
        "ok": False,
        "error": "RESTRICTED",
        "reason": "restricted",
        "restricted_service_title": availability.get("restricted_service_title"),
        "restricted_service_message": availability.get("restricted_service_message"),
    }


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
            _log_rejected_connect(environ, "missing visitor_session_token")
            raise ConnectionRefusedError("visitor_session_token required")

        try:
            async with AsyncSessionLocal() as db:
                context = await ChannelService.validate_visitor_session_token(db, token)
        except UnauthorizedError:
            _log_rejected_connect(environ, "invalid visitor session")
            raise ConnectionRefusedError("Invalid visitor session")

        visitor_ip = client_ip_from_environ(environ)
        if visitor_ip:
            context["visitor_ip"] = visitor_ip
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

    @rt.on("visitor_presence_ping", namespace=NAMESPACE)  # type: ignore
    async def on_visitor_presence_ping(sid: str, data: dict | None = None):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        visitor_external_id = session.get("visitor_external_id")
        tenant_id = session.get("tenant_id")
        channel_id = session.get("channel_id")
        if not tenant_id or not channel_id or not visitor_external_id:
            return {"ok": False, "error": "visitor_session_required"}

        r = redis_client.client
        came_online = await VisitorWebStatusService.refresh_connection(
            r,
            tenant_id=int(tenant_id),
            channel_id=int(channel_id),
            visitor_external_id=visitor_external_id,
            sid=sid,
        )
        if came_online:
            async with AsyncSessionLocal() as db:
                await VisitorWebStatusService.emit_status_for_visitor_context(
                    rt,
                    r,
                    db,
                    tenant_id=int(tenant_id),
                    channel_id=int(channel_id),
                    visitor_external_id=visitor_external_id,
                )
        return {"ok": True}

    @rt.on("start_conversation", namespace=NAMESPACE)  # type: ignore
    async def on_start_conversation(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        visitor_external_id = session.get("visitor_external_id")
        channel_id = session.get("channel_id")

        if not channel_id:
            return {"error": "channel_id required"}

        r = redis_client.client
        payload = data if isinstance(data, dict) else {}
        context_token = payload.get("contextToken") or payload.get("context_token")
        try:
            async with _visitor_start_lock(r, int(tenant_id), int(channel_id), visitor_external_id):
                async with AsyncSessionLocal() as db:
                    result = await ConversationService.create_from_visitor(
                        db,
                        r,
                        tenant_id=tenant_id,
                        channel_id=int(channel_id),
                        visitor_external_id=visitor_external_id,
                        visitor_name=session.get("visitor_name"),
                        metadata=payload.get("metadata") or session.get("metadata"),
                        context_token=context_token if isinstance(context_token, str) else None,
                        channel_key=session.get("channel_key"),
                        visitor_system=payload.get("system") or payload.get("visitor_system"),
                        visitor_browser=payload.get("browser") or payload.get("visitor_browser"),
                        visitor_ip=session.get("visitor_ip"),
                    )
        except Exception:
            logger.exception(
                "start_conversation failed for visitor=%s channel=%s",
                visitor_external_id,
                channel_id,
            )
            return {"ok": False, "error": "INTERNAL"}

        if result.get("restricted"):
            return _restricted_socket_response(result.get("availability") or {})

        if result.get("leave_message"):
            availability = result["availability"]
            return {
                "ok": False,
                "error": "LEAVE_MESSAGE",
                "reason": availability["reason"],
                "offline_title": availability["offline_title"],
                "offline_message": availability["offline_message"],
                "leave_message_prompt": availability.get("leave_message_prompt"),
            }

        if result.get("offline"):
            availability = result["availability"]
            return {
                "ok": False,
                "error": "OFFLINE",
                "reason": availability["reason"],
                "offline_title": availability["offline_title"],
                "offline_message": availability["offline_message"],
            }

        if result.get("queue_full"):
            availability = result["availability"]
            return {
                "ok": False,
                "error": "QUEUE_FULL",
                "reason": availability["reason"],
                "queue_full_message": availability.get("queue_full_message"),
                "queue_full_show_leave_message_button": availability.get(
                    "queue_full_show_leave_message_button",
                    True,
                ),
                "queue_full_leave_message_button_label": availability.get(
                    "queue_full_leave_message_button_label",
                ),
                "leave_message_prompt": availability.get("leave_message_prompt"),
            }

        if result.get("no_assignable_queue"):
            return {
                "ok": False,
                "error": "NO_ASSIGNABLE_QUEUE",
                "reason": "no_assignable_queue",
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
                "name": ConversationService.visitor_agent_display_name(conv.agent),
                "avatar": conv.agent.avatar,
            } if conv.agent else None,
        }
        if conv.status == "queued":
            conv_payload["queue_position"] = result.get("queue_position")

        should_notify = conv.agent_id and (result["is_new"] or result.get("newly_assigned"))
        if should_notify:
            agent_room = f"agent:{tenant_id}:{conv.agent_id}"
            await rt.emit("new_conversation", {
                "conversation_id": conv.id,
                "visitor": conv_payload.get("visitor"),
                "channel": {"id": conv.channel_id} if conv.channel_id else None,
            }, room=agent_room, namespace="/chat")
            await ConversationRealtimeService.emit_conversation_list_updated(
                int(tenant_id),
                action="assigned",
                conversation_id=conv.id,
                rt=rt,
            )

        r = redis_client.client
        await VisitorWebStatusService.emit_status_for_conversation(rt, r, conv)

        return {
            "ok": True,
            "conversation": conv_payload,
            "is_new": result["is_new"],
            **({"queue_position": result["queue_position"]} if result.get("queue_position") is not None else {}),
            **({"context_sync": result["context_sync"]} if result.get("context_sync") else {}),
        }

    @rt.on("send_message", namespace=NAMESPACE)  # type: ignore
    async def on_send_message(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        content = data.get("content", "")
        content_type = data.get("content_type", "text")
        quoted_message_id = data.get("quoted_message_id")

        if not conversation_public_id or not content:
            return {"error": "conversation_public_id and content required"}

        try:
            quoted_message_id = int(quoted_message_id) if quoted_message_id is not None else None
        except (TypeError, ValueError):
            return {"ok": False, "error": "Invalid quoted_message_id"}

        try:
            async with AsyncSessionLocal() as db:
                msg_payload, _agent_id, conv = await ConversationService.send_visitor_message_for_session(
                    db,
                    conversation_public_id=conversation_public_id,
                    visitor_context=session,
                    content_type=content_type,
                    content=content,
                    quoted_message_id=quoted_message_id,
                )
                read_result = await ConversationService.mark_agent_messages_visitor_read_for_session(
                    db,
                    visitor_context=session,
                    conversation_public_id=str(conversation_public_id),
                    before_message_id=msg_payload["id"],
                )
        except BusinessError as exc:
            return {"ok": False, "error": exc.code, "message": exc.message}

        conv_room = f"conv:{conv.id}"
        await rt.emit("new_message", msg_payload, room=conv_room, namespace=NAMESPACE)

        recipient_agent_ids = set(read_result["recipient_agent_ids"])
        logger.info(
            "visitor_send_message_read_receipt_fallback tenant_id=%s channel_id=%s "
            "conversation_id=%s conversation_public_id=%s new_message_id=%s "
            "read_message_count=%s recipient_count=%s",
            tenant_id,
            session.get("channel_id"),
            read_result["conversation_id"],
            read_result["conversation_public_id"],
            msg_payload["id"],
            len(read_result["message_ids"]),
            len(recipient_agent_ids),
        )

        if recipient_agent_ids:
            agent_payload = {**msg_payload, "conversation_id": conv.id}
            agent_payload.pop("conversation_public_id", None)
            conversation_updated_payload = {
                "conversation_id": conv.id,
                "last_message_preview": ConversationService.build_message_preview(
                    msg_payload["content_type"],
                    msg_payload["content"],
                ),
                "last_message_at": msg_payload["created_at"],
                "unread_count": conv.unread_count,
            }
            for recipient_agent_id in recipient_agent_ids:
                agent_room = f"agent:{tenant_id}:{recipient_agent_id}"
                await rt.emit("new_message", agent_payload, room=agent_room, namespace="/chat")
                await rt.emit("conversation_updated", conversation_updated_payload, room=agent_room, namespace="/chat")
            await rt.emit("new_message", agent_payload, room=conv_room, namespace="/chat")
            await rt.emit("conversation_updated", conversation_updated_payload, room=conv_room, namespace="/chat")
            await ConversationRealtimeService.emit_conversation_list_updated(
                int(tenant_id),
                action="message",
                conversation_id=conv.id,
                rt=rt,
            )

        if read_result["message_ids"]:
            read_payload = {
                "reader": "visitor",
                "conversation_id": read_result["conversation_id"],
                "conversation_public_id": read_result["conversation_public_id"],
                "message_ids": read_result["message_ids"],
            }
            await rt.emit("messages_read", read_payload, room=conv_room, namespace="/chat")
            for recipient_agent_id in recipient_agent_ids:
                await rt.emit(
                    "messages_read",
                    read_payload,
                    room=f"agent:{tenant_id}:{recipient_agent_id}",
                    namespace="/chat",
                )

        return {"ok": True, "message": msg_payload}

    @rt.on("recall_message", namespace=NAMESPACE)  # type: ignore
    async def on_recall_message(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        message_id = data.get("message_id")
        if not conversation_public_id or not message_id:
            return {"ok": False, "error": "conversation_public_id and message_id required"}

        try:
            message_id = int(message_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Invalid message_id"}

        try:
            async with AsyncSessionLocal() as db:
                msg, conv, conversation_update = await ConversationService.recall_visitor_message_for_session(
                    db,
                    conversation_public_id=str(conversation_public_id),
                    visitor_context=session,
                    message_id=message_id,
                )
                from app.repositories.conversation_collaboration_repository import ConversationCollaborationRepository

                collaborator_agent_ids = await ConversationCollaborationRepository.get_active_collaborator_agent_ids(
                    db,
                    tenant_id=int(tenant_id),
                    conversation_id=conv.id,
                )
        except BusinessError as exc:
            return {"ok": False, "error": exc.code, "message": exc.message}

        visitor_payload = ConversationService._message_response_payload(
            msg,
            conversation_public_id=conv.public_id,
            sender_name=conv.visitor.name if conv.visitor else None,
            sender_avatar=None,
            visitor_facing=True,
        )
        conv_room = f"conv:{conv.id}"
        await rt.emit("message_recalled", jsonable_encoder(visitor_payload), room=conv_room, namespace=NAMESPACE)

        recipient_agent_ids = set(collaborator_agent_ids)
        if conv.agent_id:
            recipient_agent_ids.add(int(conv.agent_id))
        if recipient_agent_ids:
            agent_payload = ConversationService._message_response_payload(
                msg,
                conversation_id=conv.id,
                sender_name=conv.visitor.name if conv.visitor else None,
                sender_avatar=None,
                visitor_facing=False,
            )
            conversation_updated_payload = {
                **(conversation_update or {}),
                "conversation_id": conv.id,
                "unread_count": conv.unread_count,
            }
            for recipient_agent_id in recipient_agent_ids:
                agent_room = f"agent:{tenant_id}:{recipient_agent_id}"
                await rt.emit("message_recalled", jsonable_encoder(agent_payload), room=agent_room, namespace="/chat")
                if conversation_update:
                    await rt.emit(
                        "conversation_updated",
                        jsonable_encoder(conversation_updated_payload),
                        room=agent_room,
                        namespace="/chat",
                    )

        await ConversationRealtimeService.emit_conversation_list_updated(
            int(tenant_id),
            action="message",
            conversation_id=conv.id,
            rt=rt,
        )

        return {"ok": True, "message": jsonable_encoder(visitor_payload)}

    @rt.on("mark_read", namespace=NAMESPACE)  # type: ignore
    async def on_mark_read(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        if not conversation_public_id:
            return {"error": "conversation_public_id required"}

        async with AsyncSessionLocal() as db:
            result = await ConversationService.mark_agent_messages_visitor_read_for_session(
                db,
                visitor_context=session,
                conversation_public_id=str(conversation_public_id),
            )
        logger.info(
            "visitor_mark_read_socket tenant_id=%s channel_id=%s conversation_id=%s "
            "conversation_public_id=%s read_message_count=%s recipient_count=%s",
            session.get("tenant_id"),
            session.get("channel_id"),
            result["conversation_id"],
            result["conversation_public_id"],
            len(result["message_ids"]),
            len(result["recipient_agent_ids"]),
        )

        read_payload = {
            "reader": "visitor",
            "conversation_id": result["conversation_id"],
            "conversation_public_id": result["conversation_public_id"],
            "message_ids": result["message_ids"],
        }
        await rt.emit(
            "messages_read",
            read_payload,
            room=f"conv:{result['conversation_id']}",
            namespace="/chat",
        )
        for agent_id in result["recipient_agent_ids"]:
            await rt.emit(
                "messages_read",
                read_payload,
                room=f"agent:{result['tenant_id']}:{agent_id}",
                namespace="/chat",
            )
        return {"ok": True, "message_ids": result["message_ids"]}

    @rt.on("request_human_handoff", namespace=NAMESPACE)  # type: ignore
    async def on_request_human_handoff(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        if not conversation_public_id:
            return {"error": "conversation_public_id required"}

        tool_result_messages: list[dict] = []
        tool_result_request: tuple[str, str, str | None] | None = None
        async with AsyncSessionLocal() as db:
            logger.info(
                "visitor_handoff_requested tenant_id=%s conversation_public_id=%s "
                "sid=%s handoff_trigger=%s tool_call_id=%s",
                tenant_id,
                conversation_public_id,
                sid,
                data.get("handoff_trigger") or "visitor",
                data.get("tool_call_id") or "-",
            )
            result = await ConversationService.request_human_handoff_for_session(
                db,
                redis_client.client,
                conversation_public_id=conversation_public_id,
                visitor_context=session,
                handoff_payload=data.get("handoff_payload"),
                handoff_trigger=data.get("handoff_trigger") or "visitor",
                tool_call_id=data.get("tool_call_id"),
            )
            tool_call_id = data.get("tool_call_id")
            if data.get("handoff_trigger") == "bot_confirmed" and isinstance(tool_call_id, str) and tool_call_id:
                status, message = OpenAgentConversationService._handoff_tool_result_from_route_result(result)
                logger.info(
                    "visitor_handoff_tool_result_submit tenant_id=%s conversation_public_id=%s "
                    "sid=%s tool_call_id=%s status=%s route_ok=%s route_reason=%s",
                    tenant_id,
                    conversation_public_id,
                    sid,
                    tool_call_id,
                    status,
                    result.get("ok", False),
                    result.get("reason") or "-",
                )
                tool_result_request = (tool_call_id, status, message)

        if tool_result_request is not None:
            tool_call_id, status, message = tool_result_request
            try:
                tool_events = await OpenAgentConversationService.submit_handoff_tool_result_for_session_managed(
                    conversation_public_id=conversation_public_id,
                    visitor_context=session,
                    tool_call_id=tool_call_id,
                    status=status,
                    message=message,
                )
                tool_result_messages = _open_desk_messages_from_sse_events(tool_events)
                logger.info(
                    "visitor_handoff_tool_result_submitted tenant_id=%s conversation_public_id=%s "
                    "sid=%s tool_call_id=%s status=%s open_desk_message_count=%s",
                    tenant_id,
                    conversation_public_id,
                    sid,
                    tool_call_id,
                    status,
                    len(tool_result_messages),
                )
            except Exception:
                logger.exception("Failed to submit OpenAgent handoff tool result")

        conv = result["conversation"]
        message_payloads = result.get("messages") or []
        if not message_payloads and result.get("message"):
            message_payloads = [result["message"]]
        message_payloads = [*message_payloads, *tool_result_messages]
        conv_room = f"conv:{conv.id}"
        for msg_payload in message_payloads:
            await rt.emit("new_message", msg_payload, room=conv_room, namespace=NAMESPACE)

        msg_payload = message_payloads[-1] if message_payloads else None

        unavailable = _handoff_unavailable_socket_response(result)
        if unavailable:
            return jsonable_encoder({
                **unavailable,
                "status": conv.status,
                "message": msg_payload,
            })

        if result.get("ok") and conv.agent_id:
            agent_room = f"agent:{tenant_id}:{conv.agent_id}"
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
            await rt.emit("new_conversation", conv_payload, room=agent_room, namespace="/chat")
            await ConversationRealtimeService.emit_conversation_list_updated(
                int(tenant_id),
                action="assigned",
                conversation_id=conv.id,
                rt=rt,
            )
            if msg_payload:
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
                await rt.emit("new_message", agent_payload, room=conv_room, namespace="/chat")
                await rt.emit("conversation_updated", {
                    "conversation_id": conv.id,
                    "last_message_preview": ConversationService.build_message_preview(
                        msg_payload["content_type"],
                        msg_payload["content"],
                    ),
                    "last_message_at": msg_payload["created_at"],
                    "unread_count": conv.unread_count,
                }, room=conv_room, namespace="/chat")

            await rt.emit("conversation_assigned", {
                "conversation_id": conv.id,
                "conversation_public_id": conv.public_id,
                "agent": {
                    "id": conv.agent.id,
                    "name": ConversationService.visitor_agent_display_name(conv.agent),
                    "avatar": conv.agent.avatar,
                } if conv.agent else None,
            }, room=f"conv:{conv.id}", namespace=NAMESPACE)

        logger.info(
            "visitor_handoff_completed tenant_id=%s conversation_id=%s conversation_public_id=%s "
            "sid=%s ok=%s reason=%s status=%s agent_id=%s message_count=%s tool_result_message_count=%s",
            tenant_id,
            conv.id,
            conv.public_id,
            sid,
            result.get("ok", False),
            result.get("reason") or "-",
            conv.status,
            conv.agent_id or "-",
            len(message_payloads),
            len(tool_result_messages),
        )
        return jsonable_encoder({
            "ok": result.get("ok", False),
            "reason": result.get("reason"),
            "status": conv.status,
            "message": msg_payload,
            "agent": {
                "id": conv.agent.id,
                "name": ConversationService.visitor_agent_display_name(conv.agent),
                "avatar": conv.agent.avatar,
            } if conv.agent else None,
            **({"queue_position": result["queue_position"]} if result.get("queue_position") is not None else {}),
        })

    @rt.on("dismiss_human_handoff", namespace=NAMESPACE)  # type: ignore
    async def on_dismiss_human_handoff(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        if not conversation_public_id:
            return {"error": "conversation_public_id required"}

        tool_result_messages: list[dict] = []
        tool_result_request: tuple[str, str, str] | None = None
        async with AsyncSessionLocal() as db:
            result = await ConversationService.dismiss_bot_handoff_for_session(
                db,
                conversation_public_id=conversation_public_id,
                visitor_context=session,
                tool_call_id=data.get("tool_call_id"),
            )
            tool_call_id = data.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                tool_result_request = (
                    tool_call_id,
                    OpenAgentConversationService._HANDOFF_TOOL_RESULT_FAILED,
                    "用户选择继续咨询智能助手。",
                )

        if tool_result_request is not None:
            tool_call_id, status, message = tool_result_request
            try:
                tool_events = await OpenAgentConversationService.submit_handoff_tool_result_for_session_managed(
                    conversation_public_id=conversation_public_id,
                    visitor_context=session,
                    tool_call_id=tool_call_id,
                    status=status,
                    message=message,
                )
                tool_result_messages = _open_desk_messages_from_sse_events(tool_events)
            except Exception:
                logger.exception("Failed to submit OpenAgent dismissed handoff tool result")

        conv = result["conversation"]
        conv_room = f"conv:{conv.id}"
        for msg_payload in tool_result_messages:
            await rt.emit("new_message", msg_payload, room=conv_room, namespace=NAMESPACE)
            agent_payload = {**msg_payload, "conversation_id": conv.id}
            agent_payload.pop("conversation_public_id", None)
            await rt.emit("new_message", agent_payload, room=conv_room, namespace="/chat")
        return jsonable_encoder({
            "ok": result.get("ok", False),
            "status": conv.status,
        })

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
