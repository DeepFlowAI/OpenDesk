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
            await ConversationRealtimeService.emit_conversation_list_updated(
                int(tenant_id),
                action="message",
                conversation_id=conv.id,
                rt=rt,
            )

        return {"ok": True, "message": msg_payload}

    @rt.on("request_human_handoff", namespace=NAMESPACE)  # type: ignore
    async def on_request_human_handoff(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_public_id = data.get("conversation_public_id") or data.get("conversation_id")
        if not conversation_public_id:
            return {"error": "conversation_public_id required"}

        tool_result_messages: list[dict] = []
        async with AsyncSessionLocal() as db:
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
                try:
                    tool_events = await OpenAgentConversationService.submit_handoff_tool_result_for_session(
                        db,
                        conversation_public_id=conversation_public_id,
                        visitor_context=session,
                        tool_call_id=tool_call_id,
                        status=status,
                        message=message,
                    )
                    tool_result_messages = _open_desk_messages_from_sse_events(tool_events)
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

        async with AsyncSessionLocal() as db:
            result = await ConversationService.dismiss_bot_handoff_for_session(
                db,
                conversation_public_id=conversation_public_id,
                visitor_context=session,
                tool_call_id=data.get("tool_call_id"),
            )
            tool_call_id = data.get("tool_call_id")
            tool_result_messages: list[dict] = []
            if isinstance(tool_call_id, str) and tool_call_id:
                try:
                    tool_events = await OpenAgentConversationService.submit_handoff_tool_result_for_session(
                        db,
                        conversation_public_id=conversation_public_id,
                        visitor_context=session,
                        tool_call_id=tool_call_id,
                        status=OpenAgentConversationService._HANDOFF_TOOL_RESULT_FAILED,
                        message="用户选择继续咨询智能助手。",
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
