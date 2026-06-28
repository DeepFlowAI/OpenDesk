"""
Socket.IO event handlers for the agent-side /chat namespace.

Events:
  connect    — authenticate agent via JWT, join agent room
  disconnect — cleanup
  join_conversation  — subscribe to an agent-visible conversation room
  leave_conversation — unsubscribe from a conversation room
  send_message       — agent sends a message
  typing             — agent is typing
  update_status      — change agent online status
  end_conversation   — agent ends a conversation
  mark_read          — agent read messages in a conversation
"""
import asyncio
import logging
import uuid

from fastapi.encoders import jsonable_encoder

from app.configs.settings import settings
from app.core.exceptions import BusinessError
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.db.redis import redis_client
from app.enums import MessageContentType, MessageSenderType, AgentOnlineStatus
from app.libs.realtime.base import BaseRealtimeTransport
from app.services.conversation_service import ConversationService
from app.services.conversation_realtime_service import ConversationRealtimeService
from app.services.agent_status_service import AgentStatusService
from app.services.data_scope_service import DataScopeService, RESOURCE_PEER_CONVERSATION
from app.services.offline_message_realtime_service import OfflineMessageRealtimeService
from app.services.permission_service import PermissionService
from app.services.queue_realtime_service import QueueRealtimeService
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService
from app.socketio.connect_throttle import ConnectRejectionTracker, client_ip_from_environ

logger = logging.getLogger(__name__)

NAMESPACE = "/chat"

# Tracks rejected agent connects per client IP so a tab stuck reconnecting with
# an expired token is escalated to a single ERROR instead of flooding WARNING.
_rejection_tracker = ConnectRejectionTracker()


def _log_rejected_connect(environ: dict, sid: str, reason: str) -> None:
    ip = client_ip_from_environ(environ) or "unknown"
    count, storm = _rejection_tracker.record(ip)
    if storm:
        logger.error(
            "Socket auth reconnect storm on %s: %d rejected connects from %s "
            "within the last minute (reason=%s)",
            NAMESPACE, count, ip, reason,
        )
    else:
        logger.debug("Chat connect rejected: %s, sid=%s ip=%s", reason, sid, ip)


async def _emit_workspace_message_event(
    rt: BaseRealtimeTransport,
    event_name: str,
    payload: dict[str, object],
    *,
    room: str,
    namespace: str,
    log_context: dict[str, object],
) -> None:
    message_flow_id = log_context.get("message_flow_id")
    tenant_id = log_context.get("tenant_id")
    user_id = log_context.get("user_id")
    conversation_id = log_context.get("conversation_id")
    message_id = log_context.get("message_id")
    try:
        await rt.emit(event_name, payload, room=room, namespace=namespace)
    except Exception:
        logger.exception(
            "workspace_message_emit_failed message_flow_id=%s tenant_id=%s user_id=%s "
            "conversation_id=%s message_id=%s event=%s room=%s namespace=%s",
            message_flow_id,
            tenant_id,
            user_id,
            conversation_id,
            message_id,
            event_name,
            room,
            namespace,
        )
        raise
    logger.info(
        "workspace_message_emit_succeeded message_flow_id=%s tenant_id=%s user_id=%s "
        "conversation_id=%s message_id=%s event=%s room=%s namespace=%s",
        message_flow_id,
        tenant_id,
        user_id,
        conversation_id,
        message_id,
        event_name,
        room,
        namespace,
    )


def _normalize_subscription_items(data: dict | None, key: str, allowed: list[str]) -> list[str]:
    raw = (data or {}).get(key)
    if isinstance(raw, str):
        requested = [raw]
    elif isinstance(raw, list):
        requested = [item for item in raw if isinstance(item, str)]
    else:
        requested = allowed
    return [item for item in allowed if item in requested]


async def _get_socket_principal(rt: BaseRealtimeTransport, sid: str):
    session = await rt.get_session(sid, namespace=NAMESPACE)
    user_id = session.get("user_id")
    tenant_id = session.get("tenant_id")
    if not user_id or not tenant_id:
        raise BusinessError(
            "Socket session is missing user context",
            status_code=401,
            code="UNAUTHORIZED",
        )

    async with AsyncSessionLocal() as db:
        return await PermissionService.get_current_principal(
            db,
            {"user_id": int(user_id), "tenant_id": int(tenant_id)},
        )


def _counter_room_for(principal, resource: str) -> str | None:
    if resource == "queue" and principal.has_permission("chat.queue.view"):
        return QueueRealtimeService.count_room(principal.tenant_id)
    if resource == "offline" and principal.has_permission("chat.offline_message.view"):
        return OfflineMessageRealtimeService.count_room(principal.tenant_id)
    return None


def _tab_room_for(principal, tab: str) -> str | None:
    if tab == "queue" and principal.has_permission("chat.queue.view"):
        return QueueRealtimeService.list_room(principal.tenant_id)
    if tab == "offline" and principal.has_permission("chat.offline_message.view"):
        return OfflineMessageRealtimeService.list_room(principal.tenant_id)
    if (
        tab == "peers"
        and principal.has_permission("chat.conversation.peer.view")
        and DataScopeService.get_scope(principal, RESOURCE_PEER_CONVERSATION) != "self"
    ):
        return ConversationRealtimeService.peers_list_room(principal.tenant_id)
    return None


def _counter_room_by_tenant(tenant_id: int, resource: str) -> str | None:
    if resource == "queue":
        return QueueRealtimeService.count_room(tenant_id)
    if resource == "offline":
        return OfflineMessageRealtimeService.count_room(tenant_id)
    return None


def _tab_room_by_tenant(tenant_id: int, tab: str) -> str | None:
    if tab == "queue":
        return QueueRealtimeService.list_room(tenant_id)
    if tab == "offline":
        return OfflineMessageRealtimeService.list_room(tenant_id)
    if tab == "peers":
        return ConversationRealtimeService.peers_list_room(tenant_id)
    return None


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
    """Try to pull queued conversations for the given agent."""
    from app.core.exceptions import ConflictError, NotFoundError
    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.employee_repository import EmployeeRepository
    from app.schemas.queue import QueuePullRequest
    from app.services.queue_service import QueueTaskService
    from app.services.queue_workspace_service import QueueWorkspaceService

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
            await QueueWorkspaceService.enqueue_conversation_if_needed(
                db,
                tenant_id,
                conv,
                source_type="visitor_waiting",
            )

        for _ in range(available_slots):
            try:
                task = await QueueTaskService.pull_next(
                    db,
                    r,
                    tenant_id,
                    agent_id,
                    QueuePullRequest(),
                )
            except NotFoundError:
                break
            except ConflictError:
                continue

            try:
                conversation_id = int(task.task_ref_id)
            except (TypeError, ValueError):
                continue

            conv = await ConversationRepository.get_by_id(db, conversation_id)
            if not conv:
                continue

            await QueueWorkspaceService._emit_assignment_events(conv, agent_id, db=db)

            logger.info("Auto-assigned queued conv %d to agent %d", conv.id, agent_id)


def register_chat_handlers(rt: BaseRealtimeTransport) -> None:

    @rt.on("connect", namespace=NAMESPACE)  # type: ignore
    async def on_connect(sid: str, environ: dict, auth: dict | None = None):
        """Authenticate agent via JWT token in auth payload."""
        token = (auth or {}).get("token") or ""
        payload = decode_access_token(token)
        if not payload:
            _log_rejected_connect(environ, sid, "invalid token")
            raise ConnectionRefusedError("Invalid token")

        user_id = payload.get("user_id") or payload.get("sub")
        tenant_id = payload.get("tenant_id")
        if not user_id or not tenant_id:
            _log_rejected_connect(environ, sid, "missing user_id or tenant_id")
            raise ConnectionRefusedError("Missing user_id or tenant_id in token")
        user_id = int(user_id)

        await rt.save_session(sid, {
            "user_id": user_id,
            "tenant_id": tenant_id,
        }, namespace=NAMESPACE)

        # Join personal agent room for targeted events
        agent_room = f"agent:{tenant_id}:{user_id}"
        await rt.join_room(sid, agent_room, namespace=NAMESPACE)
        await rt.join_room(sid, f"tenant:{tenant_id}:agents", namespace=NAMESPACE)

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
        async with AsyncSessionLocal() as db:
            from app.repositories.conversation_repository import ConversationRepository
            from app.repositories.employee_repository import EmployeeRepository

            user = await EmployeeRepository.get_by_id(db, user_id)
            max_c = user.max_concurrent if user else 10
            active_count = await ConversationRepository.count_active_by_agent(
                db,
                tenant_id,
                user_id,
            )

        await AgentStatusService.set_status(
            r,
            tenant_id,
            user_id,
            status,
            current_count=active_count,
        )

        # Becoming online is a capacity-gain event: pull any queued work the
        # agent is now eligible for, mirroring the connect-time backfill.
        if status == AgentOnlineStatus.ONLINE.value:
            try:
                await _assign_queued_conversations(rt, r, tenant_id, user_id)
            except Exception:
                logger.exception(
                    "Error auto-assigning queued conversations after status change for agent %s",
                    user_id,
                )

        # Fetch updated status to return
        status_data = await AgentStatusService.get_status(r, tenant_id, user_id, max_c)
        return {"ok": True, "status": status_data}

    @rt.on("subscribe_workspace_counters", namespace=NAMESPACE)  # type: ignore
    async def on_subscribe_workspace_counters(sid: str, data: dict | None = None):
        try:
            principal = await _get_socket_principal(rt, sid)
        except BusinessError as exc:
            logger.warning(
                "workspace_counter_subscribe_rejected sid=%s error_code=%s message=%s",
                sid,
                exc.code,
                exc.message,
            )
            return {"ok": False, "error": exc.code, "message": exc.message}

        resources = _normalize_subscription_items(data, "resources", ["queue", "offline"])
        subscribed: list[str] = []
        for resource in resources:
            room = _counter_room_for(principal, resource)
            if not room:
                continue
            await rt.join_room(sid, room, namespace=NAMESPACE)
            subscribed.append(resource)
        logger.info(
            "workspace_counter_subscribed tenant_id=%s user_id=%s sid=%s resources=%s subscribed=%s",
            principal.tenant_id,
            principal.user_id,
            sid,
            ",".join(resources),
            ",".join(subscribed),
        )
        return {"ok": True, "subscribed": subscribed}

    @rt.on("unsubscribe_workspace_counters", namespace=NAMESPACE)  # type: ignore
    async def on_unsubscribe_workspace_counters(sid: str, data: dict | None = None):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        user_id = session.get("user_id")
        if not tenant_id:
            return {"ok": True}

        resources = _normalize_subscription_items(data, "resources", ["queue", "offline"])
        unsubscribed: list[str] = []
        for resource in resources:
            room = _counter_room_by_tenant(int(tenant_id), resource)
            if room:
                await rt.leave_room(sid, room, namespace=NAMESPACE)
                unsubscribed.append(resource)
        logger.info(
            "workspace_counter_unsubscribed tenant_id=%s user_id=%s sid=%s resources=%s unsubscribed=%s",
            tenant_id,
            user_id,
            sid,
            ",".join(resources),
            ",".join(unsubscribed),
        )
        return {"ok": True}

    @rt.on("subscribe_workspace_tab", namespace=NAMESPACE)  # type: ignore
    async def on_subscribe_workspace_tab(sid: str, data: dict | None = None):
        tab = (data or {}).get("tab")
        if tab not in {"queue", "offline", "peers"}:
            logger.warning("workspace_tab_subscribe_invalid sid=%s tab=%s", sid, tab)
            return {"ok": False, "error": "INVALID_TAB"}

        try:
            principal = await _get_socket_principal(rt, sid)
        except BusinessError as exc:
            logger.warning(
                "workspace_tab_subscribe_rejected sid=%s tab=%s error_code=%s message=%s",
                sid,
                tab,
                exc.code,
                exc.message,
            )
            return {"ok": False, "error": exc.code, "message": exc.message}

        room = _tab_room_for(principal, tab)
        if not room:
            logger.warning(
                "workspace_tab_subscribe_forbidden tenant_id=%s user_id=%s sid=%s tab=%s",
                principal.tenant_id,
                principal.user_id,
                sid,
                tab,
            )
            return {"ok": False, "error": "FORBIDDEN"}
        await rt.join_room(sid, room, namespace=NAMESPACE)
        logger.info(
            "workspace_tab_subscribed tenant_id=%s user_id=%s sid=%s tab=%s room=%s",
            principal.tenant_id,
            principal.user_id,
            sid,
            tab,
            room,
        )
        return {"ok": True, "subscribed": tab}

    @rt.on("unsubscribe_workspace_tab", namespace=NAMESPACE)  # type: ignore
    async def on_unsubscribe_workspace_tab(sid: str, data: dict | None = None):
        tab = (data or {}).get("tab")
        if tab not in {"queue", "offline", "peers"}:
            logger.warning("workspace_tab_unsubscribe_invalid sid=%s tab=%s", sid, tab)
            return {"ok": True}

        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        user_id = session.get("user_id")
        if not tenant_id:
            return {"ok": True}

        room = _tab_room_by_tenant(int(tenant_id), tab)
        if room:
            await rt.leave_room(sid, room, namespace=NAMESPACE)
            logger.info(
                "workspace_tab_unsubscribed tenant_id=%s user_id=%s sid=%s tab=%s room=%s",
                tenant_id,
                user_id,
                sid,
                tab,
                room,
            )
        return {"ok": True}

    @rt.on("join_conversation", namespace=NAMESPACE)  # type: ignore
    async def on_join_conversation(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        user_id = session.get("user_id")
        tenant_id = session.get("tenant_id")
        conversation_id = data.get("conversation_id")

        if not user_id or not tenant_id or not conversation_id:
            return {"ok": False, "error": "conversation_id required"}

        try:
            conversation_id = int(conversation_id)
            async with AsyncSessionLocal() as db:
                principal = await PermissionService.get_current_principal(
                    db,
                    {"user_id": int(user_id), "tenant_id": int(tenant_id)},
                )
                await ConversationService.get_agent_conversation(
                    db,
                    conversation_id=conversation_id,
                    tenant_id=int(tenant_id),
                    agent_id=int(user_id),
                    principal=principal,
                )
        except (TypeError, ValueError):
            return {"ok": False, "error": "Invalid conversation_id"}
        except BusinessError as exc:
            return {"ok": False, "error": exc.code, "message": exc.message}

        conv_room = f"conv:{conversation_id}"
        await rt.join_room(sid, conv_room, namespace=NAMESPACE)
        return {"ok": True}

    @rt.on("leave_conversation", namespace=NAMESPACE)  # type: ignore
    async def on_leave_conversation(sid: str, data: dict):
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return {"ok": True}

        try:
            conversation_id = int(conversation_id)
        except (TypeError, ValueError):
            return {"ok": True}

        conv_room = f"conv:{conversation_id}"
        await rt.leave_room(sid, conv_room, namespace=NAMESPACE)
        return {"ok": True}

    @rt.on("send_message", namespace=NAMESPACE)  # type: ignore
    async def on_send_message(sid: str, data: dict):
        message_flow_id = uuid.uuid4().hex
        session = await rt.get_session(sid, namespace=NAMESPACE)
        user_id = session.get("user_id")
        tenant_id = session.get("tenant_id")
        conversation_id = data.get("conversation_id")
        content = data.get("content", "")
        content_type = data.get("content_type", "text")
        quoted_message_id = data.get("quoted_message_id")

        if not conversation_id or not content:
            return {"error": "conversation_id and content required"}

        try:
            user_id = int(user_id)
            tenant_id = int(tenant_id)
            conversation_id = int(conversation_id)
            quoted_message_id = int(quoted_message_id) if quoted_message_id is not None else None
        except (TypeError, ValueError):
            logger.warning(
                "workspace_message_send_invalid message_flow_id=%s sid=%s tenant_id=%s user_id=%s "
                "conversation_id=%s content_type=%s",
                message_flow_id,
                sid,
                tenant_id,
                user_id,
                conversation_id,
                content_type,
            )
            return {"error": "Invalid conversation_id"}

        logger.info(
            "workspace_message_send_received message_flow_id=%s tenant_id=%s user_id=%s sid=%s "
            "conversation_id=%s content_type=%s content_length=%d",
            message_flow_id,
            tenant_id,
            user_id,
            sid,
            conversation_id,
            content_type,
            len(str(content)),
        )

        try:
            async with AsyncSessionLocal() as db:
                principal = await PermissionService.get_current_principal(
                    db,
                    {"user_id": user_id, "tenant_id": tenant_id},
                )
                msg = await ConversationService.send_message(
                    db,
                    conversation_id=conversation_id,
                    sender_type=MessageSenderType.AGENT.value,
                    sender_id=user_id,
                    content_type=content_type,
                    content=content,
                    tenant_id=tenant_id,
                    principal=principal,
                    quoted_message_id=quoted_message_id,
                )

                # Fetch agent info for the message payload
                from app.repositories.conversation_collaboration_repository import ConversationCollaborationRepository
                from app.repositories.employee_repository import EmployeeRepository
                from app.repositories.conversation_repository import ConversationRepository
                user = await EmployeeRepository.get_by_id(db, user_id)
                conv = await ConversationRepository.get_by_id(db, conversation_id)
                collaborator_agent_ids = await ConversationCollaborationRepository.get_active_collaborator_agent_ids(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                )
        except BusinessError as exc:
            logger.warning(
                "workspace_message_save_rejected message_flow_id=%s tenant_id=%s user_id=%s "
                "conversation_id=%s content_type=%s error_code=%s message=%s",
                message_flow_id,
                tenant_id,
                user_id,
                conversation_id,
                content_type,
                exc.code,
                exc.message,
            )
            return {"ok": False, "error": exc.code, "message": exc.message}
        except Exception:
            logger.exception(
                "workspace_message_save_failed message_flow_id=%s tenant_id=%s user_id=%s "
                "conversation_id=%s content_type=%s",
                message_flow_id,
                tenant_id,
                user_id,
                conversation_id,
                content_type,
            )
            raise

        conversation_agent_id = conv.agent_id if conv else None
        is_internal_note = msg.content_type == MessageContentType.INTERNAL_NOTE.value
        logger.info(
            "workspace_message_saved message_flow_id=%s tenant_id=%s user_id=%s conversation_id=%s "
            "message_id=%s content_type=%s is_internal_note=%s conversation_agent_id=%s",
            message_flow_id,
            tenant_id,
            user_id,
            conversation_id,
            msg.id,
            msg.content_type,
            is_internal_note,
            conversation_agent_id,
        )

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
            **ConversationService._message_read_status_overlay(msg, visitor_facing=False),
        }

        # Broadcast through the same message stream used for visitor messages so
        # every agent-side UI update is driven by server-confirmed data.
        recipient_agent_ids = {int(user_id)}
        if conv and conv.agent_id:
            recipient_agent_ids.add(int(conv.agent_id))
        recipient_agent_ids.update(collaborator_agent_ids)
        emit_log_context = {
            "message_flow_id": message_flow_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "message_id": msg.id,
        }
        conversation_updated_payload = {
            "conversation_id": conversation_id,
            "last_message_preview": ConversationService.build_message_preview(
                msg_payload["content_type"],
                msg_payload["content"],
            ),
            "last_message_at": msg_payload["created_at"],
        }
        for agent_id in recipient_agent_ids:
            agent_room = f"agent:{tenant_id}:{agent_id}"
            await _emit_workspace_message_event(
                rt,
                "new_message",
                msg_payload,
                room=agent_room,
                namespace=NAMESPACE,
                log_context=emit_log_context,
            )
            await _emit_workspace_message_event(
                rt,
                "conversation_updated",
                conversation_updated_payload,
                room=agent_room,
                namespace=NAMESPACE,
                log_context=emit_log_context,
            )

        conv_room = f"conv:{conversation_id}"
        await _emit_workspace_message_event(
            rt,
            "new_message",
            msg_payload,
            room=conv_room,
            namespace=NAMESPACE,
            log_context=emit_log_context,
        )
        await _emit_workspace_message_event(
            rt,
            "conversation_updated",
            conversation_updated_payload,
            room=conv_room,
            namespace=NAMESPACE,
            log_context=emit_log_context,
        )

        if not is_internal_note:
            visitor_msg_payload = {
                **msg_payload,
                "sender_name": ConversationService.visitor_agent_display_name(user) if user else "Agent",
            }
            # The Web SDK keys messages by conversation_public_id and only marks
            # agent messages read when this id matches the open conversation, so
            # the realtime payload must carry it (the numeric id alone is not
            # enough for the visitor side to send a read receipt).
            if conv:
                visitor_msg_payload["conversation_public_id"] = conv.public_id
            await _emit_workspace_message_event(
                rt,
                "new_message",
                visitor_msg_payload,
                room=conv_room,
                namespace="/visitor",
                log_context=emit_log_context,
            )
        await ConversationRealtimeService.emit_conversation_list_updated(
            tenant_id,
            action="message",
            conversation_id=conversation_id,
            rt=rt,
            message_flow_id=message_flow_id,
        )

        logger.info(
            "workspace_message_send_completed message_flow_id=%s tenant_id=%s user_id=%s "
            "conversation_id=%s message_id=%s recipient_agent_ids=%s is_internal_note=%s",
            message_flow_id,
            tenant_id,
            user_id,
            conversation_id,
            msg.id,
            ",".join(str(agent_id) for agent_id in sorted(recipient_agent_ids)),
            is_internal_note,
        )
        return {"ok": True, "message": msg_payload}

    @rt.on("recall_message", namespace=NAMESPACE)  # type: ignore
    async def on_recall_message(sid: str, data: dict):
        message_flow_id = uuid.uuid4().hex
        session = await rt.get_session(sid, namespace=NAMESPACE)
        user_id = session.get("user_id")
        tenant_id = session.get("tenant_id")
        conversation_id = data.get("conversation_id")
        message_id = data.get("message_id")

        try:
            user_id = int(user_id)
            tenant_id = int(tenant_id)
            conversation_id = int(conversation_id)
            message_id = int(message_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Invalid message_id"}

        try:
            async with AsyncSessionLocal() as db:
                principal = await PermissionService.get_current_principal(
                    db,
                    {"user_id": user_id, "tenant_id": tenant_id},
                )
                msg, conv, conversation_update = await ConversationService.recall_agent_message(
                    db,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    tenant_id=tenant_id,
                    principal=principal,
                )
                from app.repositories.conversation_collaboration_repository import ConversationCollaborationRepository
                from app.repositories.employee_repository import EmployeeRepository

                sender = await EmployeeRepository.get_by_id(db, user_id)
                collaborator_agent_ids = await ConversationCollaborationRepository.get_active_collaborator_agent_ids(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                )
        except BusinessError as exc:
            logger.warning(
                "workspace_message_recall_rejected message_flow_id=%s tenant_id=%s user_id=%s "
                "conversation_id=%s message_id=%s error_code=%s message=%s",
                message_flow_id,
                tenant_id,
                user_id,
                conversation_id,
                message_id,
                exc.code,
                exc.message,
            )
            return {"ok": False, "error": exc.code, "message": exc.message}
        except Exception:
            logger.exception(
                "workspace_message_recall_failed message_flow_id=%s tenant_id=%s user_id=%s "
                "conversation_id=%s message_id=%s",
                message_flow_id,
                tenant_id,
                user_id,
                conversation_id,
                message_id,
            )
            raise

        recipient_agent_ids = {int(user_id)}
        if conv and conv.agent_id:
            recipient_agent_ids.add(int(conv.agent_id))
        recipient_agent_ids.update(collaborator_agent_ids)
        emit_log_context = {
            "message_flow_id": message_flow_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "message_id": msg.id,
        }
        response_payload = ConversationService._message_response_payload(
            msg,
            conversation_id=conversation_id,
            sender_name=sender.display_name or sender.name if sender else None,
            sender_avatar=sender.avatar if sender else None,
            viewer_agent_id=int(user_id),
        )
        for recipient_agent_id in recipient_agent_ids:
            agent_payload = ConversationService._message_response_payload(
                msg,
                conversation_id=conversation_id,
                sender_name=sender.display_name or sender.name if sender else None,
                sender_avatar=sender.avatar if sender else None,
                viewer_agent_id=recipient_agent_id,
            )
            if recipient_agent_id == int(user_id):
                response_payload = agent_payload
            agent_room = f"agent:{tenant_id}:{recipient_agent_id}"
            await _emit_workspace_message_event(
                rt,
                "message_recalled",
                jsonable_encoder(agent_payload),
                room=agent_room,
                namespace=NAMESPACE,
                log_context=emit_log_context,
            )
            if conversation_update:
                await _emit_workspace_message_event(
                    rt,
                    "conversation_updated",
                    jsonable_encoder({
                        **conversation_update,
                        "unread_count": conv.unread_count if conv else None,
                    }),
                    room=agent_room,
                    namespace=NAMESPACE,
                    log_context=emit_log_context,
                )

        visitor_payload = ConversationService._message_response_payload(
            msg,
            conversation_public_id=conv.public_id,
            sender_name=ConversationService.visitor_agent_display_name(sender) if sender else None,
            sender_avatar=sender.avatar if sender else None,
            visitor_facing=True,
        )
        await _emit_workspace_message_event(
            rt,
            "message_recalled",
            jsonable_encoder(visitor_payload),
            room=f"conv:{conversation_id}",
            namespace="/visitor",
            log_context=emit_log_context,
        )
        await ConversationRealtimeService.emit_conversation_list_updated(
            tenant_id,
            action="message",
            conversation_id=conversation_id,
            rt=rt,
            message_flow_id=message_flow_id,
        )
        return {"ok": True, "message": jsonable_encoder(response_payload)}

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
            payload = {"conversation_id": conversation_id}
            if data.get("stop"):
                payload["stop"] = True
            await rt.emit("agent_typing", payload, room=conv_room, namespace="/visitor")

    @rt.on("end_conversation", namespace=NAMESPACE)  # type: ignore
    async def on_end_conversation(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        conversation_id = data.get("conversation_id")

        if not conversation_id:
            return {"error": "conversation_id required"}

        r = redis_client.client
        async with AsyncSessionLocal() as db:
            principal = await PermissionService.get_current_principal(
                db,
                {"user_id": int(session.get("user_id")), "tenant_id": int(tenant_id)},
            )
            conv = await ConversationService.end_conversation(
                db,
                r,
                conversation_id,
                ended_by="agent",
                principal=principal,
            )

        end_payload = {
            "conversation_id": conversation_id,
            "conversation_public_id": conv.public_id,
            "ended_by": "agent",
        }
        conv_room = f"conv:{conversation_id}"
        agent_room = f"agent:{tenant_id}:{session.get('user_id')}"
        await rt.emit("conversation_ended", end_payload, room=agent_room, namespace=NAMESPACE)
        await rt.emit("conversation_ended", end_payload, room=conv_room, namespace=NAMESPACE)
        await rt.emit("conversation_ended", end_payload, room=conv_room, namespace="/visitor")
        await ConversationRealtimeService.emit_conversation_list_updated(
            int(tenant_id),
            action="ended",
            conversation_id=int(conversation_id),
            rt=rt,
        )

        return {"ok": True}

    @rt.on("mark_read", namespace=NAMESPACE)  # type: ignore
    async def on_mark_read(sid: str, data: dict):
        session = await rt.get_session(sid, namespace=NAMESPACE)
        tenant_id = session.get("tenant_id")
        user_id = session.get("user_id")
        conversation_id = data.get("conversation_id")
        if conversation_id:
            async with AsyncSessionLocal() as db:
                conv = await ConversationService.get_by_id(db, conversation_id)
                if conv.agent_id != int(user_id):
                    return {"ok": True}
                read_message_ids = await ConversationService.mark_read(db, conversation_id)

            conv_room = f"conv:{conversation_id}"
            agent_room = f"agent:{tenant_id}:{user_id}"
            await rt.emit("messages_read", {
                "reader": "agent",
                "conversation_id": conversation_id,
                "conversation_public_id": conv.public_id,
                "message_ids": read_message_ids,
            }, room=conv_room, namespace="/visitor")
            await rt.emit("conversation_updated", {
                "conversation_id": conversation_id,
                "unread_count": 0,
            }, room=agent_room, namespace=NAMESPACE)

        return {"ok": True}
