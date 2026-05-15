"""
Conversation transfer service.

Implements the MVP "force transfer" behaviour: the requesting agent picks an
online colleague and the conversation is immediately reassigned without the
target's confirmation.

Side effects on a successful transfer:
    1. ``conversations.agent_id`` updated
    2. A ``system`` message is appended ("{initiator_name} 将会话转接给 {to_name}")
    3. ``conversations.last_message_*`` updated
       — (1)(2)(3) all share a single transaction commit so a partial failure
       never leaves the conversation reassigned without an audit message.
    4. Redis ``current_count`` decremented for the from-agent and incremented
       for the to-agent (best-effort, after DB commit succeeds)
    5. Realtime events emitted (best-effort):
        - ``new_message`` to ``conv:{id}`` on both /chat and /visitor namespaces
        - ``conversation_transferred`` to from-agent's personal room
        - ``conversation_transferred`` to to-agent's personal room (with a
          full conversation payload so the receiving client can add the row
          directly without an extra fetch)
"""
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessError,
    ForbiddenError,
    NotFoundError,
)
from app.enums import (
    AgentOnlineStatus,
    ConversationStatus,
    MessageContentType,
    MessageSenderType,
)
from app.libs.realtime import get_realtime_transport
from app.models.conversation import Conversation
from app.models.employee import Employee
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.services.agent_status_service import AgentStatusService

logger = logging.getLogger(__name__)

CHAT_NAMESPACE = "/chat"
VISITOR_NAMESPACE = "/visitor"
MAX_TARGETS_RETURNED = 200


def _iso(value: datetime | None) -> str | None:
    """Serialize ``datetime`` to ISO 8601 string for transport-friendly dicts.

    Used by both the REST response and the Socket.IO ``conversation_transferred``
    payload — Socket.IO has no Pydantic layer to coerce ``datetime`` into a
    JSON-safe value, so emitting raw datetimes silently failed to broadcast
    in production. ConversationResponse (Pydantic v2) accepts ISO strings
    transparently, so the same shape works for the REST path too.
    """
    return value.isoformat() if value is not None else None


def _serialize_conversation(
    conversation: Conversation, *, has_history: bool = False
) -> dict:
    """Match the ConversationResponse shape used by /api/v1/conversations.

    Returns a fully JSON-serializable dict (no ``datetime`` objects) so the
    same payload can be returned via REST AND emitted over Socket.IO without
    surprises. Keeping a single shape avoids drift between the two surfaces.

    ``has_history`` is computed by callers when they have the right viewer
    context (e.g. the receiving agent's tenant + agent_id).
    """
    return {
        "id": conversation.id,
        "tenant_id": conversation.tenant_id,
        "visitor": (
            {
                "id": conversation.visitor.id,
                "external_id": conversation.visitor.external_id,
                "name": conversation.visitor.name,
                "avatar_color": conversation.visitor.avatar_color,
            }
            if conversation.visitor
            else None
        ),
        "agent": (
            {
                "id": conversation.agent.id,
                "display_name": conversation.agent.display_name,
                "name": conversation.agent.name,
                "avatar": conversation.agent.avatar,
            }
            if conversation.agent
            else None
        ),
        "channel": (
            {
                "id": conversation.channel.id,
                "name": conversation.channel.name,
                "channel_type": conversation.channel.channel_type,
            }
            if conversation.channel
            else None
        ),
        "group": (
            {
                "id": conversation.group.id,
                "name": conversation.group.name,
            }
            if conversation.group
            else None
        ),
        "status": conversation.status,
        "started_at": _iso(conversation.started_at),
        "ended_at": _iso(conversation.ended_at),
        "ended_by": conversation.ended_by,
        "last_message_at": _iso(conversation.last_message_at),
        "last_message_preview": conversation.last_message_preview,
        "unread_count": conversation.unread_count,
        "has_history_conversations": has_history,
        "created_at": _iso(conversation.created_at),
    }


async def _has_visitor_history_for_agent(
    db: AsyncSession,
    *,
    conversation: Conversation,
    viewer_agent_id: int | None,
    viewer_is_admin: bool,
) -> bool:
    """Whether the visitor has any other conversation visible to ``viewer``.

    Mirrors the logic in ``ConversationService.get_agent_conversation``: an
    admin sees every visitor conversation; a regular agent only sees the ones
    they handled themselves.
    """
    if not conversation.visitor_id:
        return False
    history = await ConversationRepository.get_visitor_history(
        db,
        tenant_id=conversation.tenant_id,
        channel_id=None,
        visitor_id=conversation.visitor_id,
        current_conversation_id=conversation.id,
        agent_id=None if viewer_is_admin else viewer_agent_id,
        limit=1,
    )
    return bool(history)


class TransferService:

    @staticmethod
    def _is_admin(roles: list[str] | None) -> bool:
        return "admin" in (roles or [])

    @staticmethod
    def _resolve_display_name(employee: Employee | None) -> str:
        """Pick the most user-friendly name for system message rendering."""
        if not employee:
            return "未知员工"
        return employee.display_name or employee.name or employee.username or "未知员工"

    @staticmethod
    async def list_targets(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        current_user_id: int,
        keyword: str | None = None,
        conversation_id: int | None = None,
        roles: list[str] | None = None,
    ) -> dict:
        """Return online-first ranked transfer candidates with realtime status.

        ``conversation_id`` lets the requester pick a target in the context of
        a specific conversation. The same authorization rules as the transfer
        endpoint apply: admins may inspect any conversation; regular agents
        may only inspect conversations they own. This prevents a regular
        agent from probing the candidate list with a foreign ``conversation_id``
        to infer who currently owns it.
        """
        exclude_ids = {current_user_id}
        if conversation_id is not None:
            conversation = await ConversationRepository.get_by_id(db, conversation_id)
            if not conversation or conversation.tenant_id != tenant_id:
                raise NotFoundError("Conversation not found")
            if (
                not TransferService._is_admin(roles)
                and conversation.agent_id != current_user_id
            ):
                raise ForbiddenError("No permission to inspect this conversation")
            if conversation.agent_id:
                exclude_ids.add(conversation.agent_id)

        employees = await EmployeeRepository.get_transfer_candidates(
            db,
            tenant_id=tenant_id,
            exclude_user_ids=list(exclude_ids),
            keyword=keyword,
            limit=MAX_TARGETS_RETURNED,
        )

        items: list[dict] = []
        for emp in employees:
            status_data = await AgentStatusService.get_status(
                r, tenant_id, emp.id, emp.max_concurrent
            )
            items.append({
                "id": emp.id,
                "name": emp.name or emp.username,
                "display_name": emp.display_name,
                "job_number": emp.job_number,
                "avatar": emp.avatar,
                "online_status": status_data["status"],
                "current_count": status_data["current_count"],
                "max_concurrent": status_data["max_concurrent"],
            })

        priority = {
            AgentOnlineStatus.ONLINE.value: 0,
            AgentOnlineStatus.BUSY.value: 1,
            AgentOnlineStatus.OFFLINE.value: 2,
        }
        items.sort(key=lambda it: (priority.get(it["online_status"], 9), it["name"] or ""))

        return {"items": items, "total": len(items)}

    @staticmethod
    async def _emit_transfer_events(
        conversation: Conversation,
        message_payload: dict,
        from_agent_id: int | None,
        target_agent_id: int,
        receiver_payload: dict,
    ) -> None:
        """Broadcast the system message and notify both ends of the transfer."""
        rt = get_realtime_transport()
        tenant_id = conversation.tenant_id
        conv_room = f"conv:{conversation.id}"

        # System message to target agent's personal room + visitor conv room
        to_agent_room = f"agent:{tenant_id}:{target_agent_id}"
        await rt.emit("new_message", message_payload, room=to_agent_room, namespace=CHAT_NAMESPACE)
        await rt.emit("new_message", message_payload, room=conv_room, namespace=VISITOR_NAMESPACE)

        base_payload = {
            "conversation_id": conversation.id,
            "from_agent_id": from_agent_id,
            "to_agent_id": target_agent_id,
        }

        if from_agent_id and from_agent_id != target_agent_id:
            from_room = f"agent:{tenant_id}:{from_agent_id}"
            await rt.emit(
                "conversation_transferred",
                base_payload,
                room=from_room,
                namespace=CHAT_NAMESPACE,
            )

        # Receiving side gets the full conversation so the client can
        # `addConversation(...)` directly without re-fetching.
        to_room = f"agent:{tenant_id}:{target_agent_id}"
        to_payload = {
            **base_payload,
            "conversation": receiver_payload,
        }
        await rt.emit(
            "conversation_transferred",
            to_payload,
            room=to_room,
            namespace=CHAT_NAMESPACE,
        )

    @staticmethod
    async def transfer_conversation(
        db: AsyncSession,
        r: aioredis.Redis,
        conversation_id: int,
        target_agent_id: int,
        current_user_id: int,
        tenant_id: int,
        roles: list[str] | None = None,
    ) -> dict:
        # ── 1. Validate inputs (read-only) ──────────────────────────────
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        is_admin = TransferService._is_admin(roles)
        if not is_admin and conversation.agent_id != current_user_id:
            raise ForbiddenError("No permission to transfer this conversation")

        if conversation.status != ConversationStatus.ACTIVE.value:
            raise BusinessError("Conversation already closed")

        from_agent_id = conversation.agent_id
        if target_agent_id == from_agent_id:
            raise BusinessError("Cannot transfer to current agent")

        target = await EmployeeRepository.get_by_id(db, target_agent_id)
        if (
            not target
            or target.tenant_id != tenant_id
            or not target.is_active
            or "agent" not in (target.roles or [])
        ):
            raise NotFoundError("Target employee not found")

        target_status = await AgentStatusService.get_status(
            r, tenant_id, target.id, target.max_concurrent
        )
        if target_status["status"] != AgentOnlineStatus.ONLINE.value:
            raise BusinessError("Target agent is not online")

        # Initiator may differ from the conversation's current agent (admin
        # transferring on behalf of someone else). The requirement names the
        # initiator in the audit message.
        initiator = await EmployeeRepository.get_by_id(db, current_user_id)
        initiator_name = TransferService._resolve_display_name(initiator)
        to_name = TransferService._resolve_display_name(target)
        system_text = f"{initiator_name} 将会话转接给 {to_name}"
        now = datetime.now(timezone.utc)

        # ── 2. Atomic DB write with optimistic concurrency check ─────────
        # The reassign is a conditional UPDATE that will only flip the row
        # when its current state still matches what we read above (same
        # owner + still active). This guards against two concurrent transfer
        # requests both passing the read-side checks and producing duplicate
        # audit messages / mismatched Redis counters.
        try:
            update_values: dict = {
                "agent_id": target.id,
                "last_message_at": now,
                "last_message_preview": system_text[:200],
            }
            update_stmt = (
                update(Conversation)
                .where(
                    Conversation.id == conversation.id,
                    Conversation.status == ConversationStatus.ACTIVE.value,
                    (
                        Conversation.agent_id == from_agent_id
                        if from_agent_id is not None
                        else Conversation.agent_id.is_(None)
                    ),
                )
                .values(**update_values)
            )
            update_result = await db.execute(update_stmt)
            if update_result.rowcount == 0:
                # Someone else closed or transferred the conversation between
                # our read and our write — abort cleanly so callers see a
                # consistent error rather than a half-applied state.
                await db.rollback()
                raise BusinessError(
                    "Conversation was transferred or closed by another request"
                )

            system_message = Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                sender_type=MessageSenderType.SYSTEM.value,
                content_type=MessageContentType.SYSTEM.value,
                content=system_text,
            )
            db.add(system_message)

            await db.flush()
            await db.commit()
        except BusinessError:
            raise
        except Exception:
            await db.rollback()
            raise

        # Reload everything we previously cached on the ORM instance so the
        # downstream payload reflects the post-update state (agent relation,
        # agent_id, last_message_*).
        await db.refresh(
            conversation,
            attribute_names=[
                "agent_id",
                "last_message_at",
                "last_message_preview",
                "visitor",
                "agent",
                "channel",
                "group",
            ],
        )

        # ── 3. Best-effort Redis counter maintenance ────────────────────
        # Already-committed DB state is the source of truth. Clients reconcile
        # via the next list refresh if a counter update transiently fails.
        if from_agent_id and from_agent_id != target.id:
            try:
                await AgentStatusService.decrement_count(r, tenant_id, from_agent_id)
            except Exception:
                logger.exception(
                    "Failed to decrement count for agent %s after transfer", from_agent_id
                )
        try:
            await AgentStatusService.increment_count(r, tenant_id, target.id)
        except Exception:
            logger.exception(
                "Failed to increment count for agent %s after transfer", target.id
            )

        # ── 4. Build payloads (with history flag) + broadcast ───────────
        # The receiver sees this conversation through their own permission
        # lens, so compute history availability from the target's perspective.
        # The initiator's REST response uses their own perspective.
        target_is_admin = "admin" in (target.roles or [])
        receiver_has_history = await _has_visitor_history_for_agent(
            db,
            conversation=conversation,
            viewer_agent_id=target.id,
            viewer_is_admin=target_is_admin,
        )
        initiator_has_history = await _has_visitor_history_for_agent(
            db,
            conversation=conversation,
            viewer_agent_id=current_user_id,
            viewer_is_admin=is_admin,
        )

        receiver_payload = _serialize_conversation(
            conversation, has_history=receiver_has_history
        )

        message_payload = {
            "id": system_message.id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "sender_id": None,
            "sender_name": None,
            "sender_avatar": None,
            "content_type": MessageContentType.SYSTEM.value,
            "content": system_text,
            "created_at": (
                system_message.created_at.isoformat() if system_message.created_at else None
            ),
        }
        try:
            await TransferService._emit_transfer_events(
                conversation,
                message_payload,
                from_agent_id,
                target.id,
                receiver_payload,
            )
        except Exception:
            logger.exception(
                "Failed to broadcast transfer events for conversation %s",
                conversation.id,
            )

        logger.info(
            "Conversation %s transferred from agent %s to agent %s by user %s",
            conversation.id,
            from_agent_id,
            target.id,
            current_user_id,
        )

        return _serialize_conversation(conversation, has_history=initiator_has_history)
