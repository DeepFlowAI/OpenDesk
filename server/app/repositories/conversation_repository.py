"""
Conversation repository
"""
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select, func, update, and_, or_, exists, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.enums import (
    ConversationStatus,
    MessageContentType,
    MessageSenderType,
    ReceptionEventType,
)
from app.libs.conversation_metrics import (
    BOT_HANDOFF_SUCCESS_STATE,
    bot_flags_for_conversation,
    compute_bot_handoff_triggered,
    compute_duration_seconds,
    compute_had_bot_session,
)
from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.reception_event_repository import ReceptionEventRepository

logger = logging.getLogger(__name__)

CONVERSATION_PUBLIC_ID_PREFIX = "cv_"
CONVERSATION_PUBLIC_ID_RANDOM_BYTES = 24
CONVERSATION_SHARE_CODE_PREFIX = "CV-"
CONVERSATION_SHARE_CODE_RANDOM_LENGTH = 8
CONVERSATION_SHARE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_PUBLIC_ID_GENERATION_ATTEMPTS = 10
MAX_SHARE_CODE_GENERATION_ATTEMPTS = 20


class ConversationRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, conversation_id: int) -> Conversation | None:
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_public_id(db: AsyncSession, public_id: str) -> Conversation | None:
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(Conversation.public_id == public_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_share_code(db: AsyncSession, share_code: str) -> Conversation | None:
        result = await db.execute(
            select(Conversation)
            .where(Conversation.share_code == share_code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def generate_public_id() -> str:
        return f"{CONVERSATION_PUBLIC_ID_PREFIX}{secrets.token_urlsafe(CONVERSATION_PUBLIC_ID_RANDOM_BYTES)}"

    @staticmethod
    def generate_share_code() -> str:
        suffix = "".join(
            secrets.choice(CONVERSATION_SHARE_CODE_ALPHABET)
            for _ in range(CONVERSATION_SHARE_CODE_RANDOM_LENGTH)
        )
        return f"{CONVERSATION_SHARE_CODE_PREFIX}{suffix}"

    @staticmethod
    async def generate_unique_public_id(db: AsyncSession) -> str:
        for _ in range(MAX_PUBLIC_ID_GENERATION_ATTEMPTS):
            public_id = ConversationRepository.generate_public_id()
            if not await ConversationRepository.get_by_public_id(db, public_id):
                return public_id
        raise RuntimeError("Failed to generate a unique conversation public ID")

    @staticmethod
    async def generate_unique_share_code(db: AsyncSession) -> str:
        for _ in range(MAX_SHARE_CODE_GENERATION_ATTEMPTS):
            share_code = ConversationRepository.generate_share_code()
            if not await ConversationRepository.get_by_share_code(db, share_code):
                return share_code
        raise RuntimeError("Failed to generate a unique conversation share code")

    @staticmethod
    async def get_active_by_agent(
        db: AsyncSession, tenant_id: int, agent_id: int
    ) -> list[Conversation]:
        """Get all active (non-closed) conversations for an agent, sorted by last message."""
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.agent_id == agent_id,
                Conversation.status.in_([ConversationStatus.ACTIVE.value, ConversationStatus.QUEUED.value]),
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
        )
        return list(result.scalars().all())

    @staticmethod
    async def has_agent_participated(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        agent_id: int,
    ) -> bool:
        result = await db.execute(
            select(Message.conversation_id)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.sender_type == MessageSenderType.AGENT.value,
                Message.sender_id == agent_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_recent_closed_by_agent(
        db: AsyncSession,
        *,
        tenant_id: int,
        agent_id: int,
        ended_since: datetime,
        before_id: int | None = None,
        limit: int = 20,
    ) -> list[Conversation]:
        participated_conversation_ids = (
            select(Message.conversation_id)
            .where(
                Message.tenant_id == tenant_id,
                Message.sender_type == MessageSenderType.AGENT.value,
                Message.sender_id == agent_id,
            )
            .distinct()
        )
        conditions = [
            Conversation.tenant_id == tenant_id,
            Conversation.status == ConversationStatus.CLOSED.value,
            Conversation.ended_at.is_not(None),
            Conversation.ended_at >= ended_since,
            or_(
                Conversation.agent_id == agent_id,
                Conversation.id.in_(participated_conversation_ids),
            ),
        ]

        if before_id is not None:
            cursor = await db.get(Conversation, before_id)
            if cursor and cursor.ended_at is not None:
                conditions.append(
                    or_(
                        Conversation.ended_at < cursor.ended_at,
                        and_(Conversation.ended_at == cursor.ended_at, Conversation.id < cursor.id),
                    )
                )

        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(*conditions)
            .order_by(Conversation.ended_at.desc(), Conversation.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_peer_conversations(
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
        scope_predicate: ColumnElement | None = None,
    ) -> list[Conversation]:
        """Get active conversations owned by other agents in the viewer's scope."""
        conditions = [
            Conversation.tenant_id == tenant_id,
            Conversation.agent_id.is_not(None),
            Conversation.agent_id != agent_id,
            Conversation.status == ConversationStatus.ACTIVE.value,
        ]
        if scope_predicate is not None:
            conditions.append(scope_predicate)

        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(*conditions)
            .order_by(Conversation.last_message_at.desc().nullslast())
        )
        return list(result.scalars().all())

    @staticmethod
    async def count_active_by_agent(db: AsyncSession, tenant_id: int, agent_id: int) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.agent_id == agent_id,
                Conversation.status == ConversationStatus.ACTIVE.value,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Conversation:
        if not data.get("public_id"):
            data = {**data, "public_id": await ConversationRepository.generate_unique_public_id(db)}
        if not data.get("share_code"):
            data = {**data, "share_code": await ConversationRepository.generate_unique_share_code(db)}
        # Materialize the bot marker at creation (bot conversations are created
        # with their OpenAgent agent id already set).
        data = {
            **data,
            "had_bot_session": compute_had_bot_session(
                data.get("open_agent_agent_id"),
                data.get("open_agent_conversation_id"),
                data.get("open_agent_conversation_external_id"),
            ),
        }
        item = Conversation(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item, attribute_names=["visitor", "agent", "channel", "group"])
        return item

    # Authoritative recompute of the materialized message counts from the
    # ``messages`` table, using the same caliber as the runtime increment and
    # the historical backfill. The phase split classifies each visitor message
    # by the human-takeover anchor (``started_at`` on bot conversations); agent
    # always counts as human phase, bot as bot phase, system as neither.
    _RECOMPUTE_MESSAGE_COUNTS_SQL = text(
        """
        UPDATE conversations SET
            visitor_message_count = (
                SELECT COUNT(*) FROM messages msg
                WHERE msg.conversation_id = conversations.id
                  AND msg.sender_type = 'visitor'
            ),
            agent_message_count = (
                SELECT COUNT(*) FROM messages msg
                WHERE msg.conversation_id = conversations.id
                  AND msg.sender_type = 'agent'
            ),
            bot_phase_message_count = (
                SELECT COUNT(*) FROM messages msg
                WHERE msg.conversation_id = conversations.id
                  AND (
                      msg.sender_type = 'bot'
                      OR (
                          msg.sender_type = 'visitor'
                          AND NOT (
                              conversations.had_bot_session = false
                              OR (
                                  conversations.started_at IS NOT NULL
                                  AND msg.created_at >= conversations.started_at
                              )
                          )
                      )
                  )
            ),
            bot_phase_visitor_message_count = (
                SELECT COUNT(*) FROM messages msg
                WHERE msg.conversation_id = conversations.id
                  AND msg.sender_type = 'visitor'
                  AND NOT (
                      conversations.had_bot_session = false
                      OR (
                          conversations.started_at IS NOT NULL
                          AND msg.created_at >= conversations.started_at
                      )
                  )
            ),
            human_phase_message_count = (
                SELECT COUNT(*) FROM messages msg
                WHERE msg.conversation_id = conversations.id
                  AND (
                      msg.sender_type = 'agent'
                      OR (
                          msg.sender_type = 'visitor'
                          AND (
                              conversations.had_bot_session = false
                              OR (
                                  conversations.started_at IS NOT NULL
                                  AND msg.created_at >= conversations.started_at
                              )
                          )
                      )
                  )
            ),
            human_phase_visitor_message_count = (
                SELECT COUNT(*) FROM messages msg
                WHERE msg.conversation_id = conversations.id
                  AND msg.sender_type = 'visitor'
                  AND (
                      conversations.had_bot_session = false
                      OR (
                          conversations.started_at IS NOT NULL
                          AND msg.created_at >= conversations.started_at
                      )
                  )
            ),
            human_phase_agent_message_count = (
                SELECT COUNT(*) FROM messages msg
                WHERE msg.conversation_id = conversations.id
                  AND msg.sender_type = 'agent'
            )
        WHERE conversations.id = :conversation_id
        """
    )

    @staticmethod
    async def recompute_message_counts(db: AsyncSession, conversation_id: int) -> None:
        """Recompute the materialized message counts for one conversation."""
        await db.execute(
            ConversationRepository._RECOMPUTE_MESSAGE_COUNTS_SQL,
            {"conversation_id": conversation_id},
        )

    # First human-agent response caliber, aligned with the first response pair of
    # ``recompute_agent_response_metrics``: take the conversation's first public
    # visitor message, then the first public agent reply after it (a proactive
    # greeting sent before any visitor message is therefore skipped). The start
    # point is the last public visitor message before that reply, so a burst of
    # consecutive visitor messages is timed from its last one. NULL when there is
    # no public visitor message or no agent reply after one.
    _RECOMPUTE_FIRST_HUMAN_RESPONSE_SQL = text(
        """
        WITH first_visitor_message AS (
            SELECT msg.id, msg.created_at
            FROM messages msg
            WHERE msg.conversation_id = :conversation_id
              AND msg.sender_type = 'visitor'
              AND msg.content_type IN ('text', 'rich_text', 'image', 'file')
            ORDER BY msg.created_at ASC, msg.id ASC
            LIMIT 1
        ),
        first_agent_reply AS (
            SELECT msg.id, msg.created_at
            FROM messages msg
            JOIN first_visitor_message fvm ON true
            WHERE msg.conversation_id = :conversation_id
              AND msg.sender_type = 'agent'
              AND msg.content_type IN ('text', 'rich_text', 'image', 'file')
              AND (
                  msg.created_at > fvm.created_at
                  OR (msg.created_at = fvm.created_at AND msg.id > fvm.id)
              )
            ORDER BY msg.created_at ASC, msg.id ASC
            LIMIT 1
        ),
        pending_visitor_message AS (
            SELECT msg.created_at
            FROM messages msg
            JOIN first_agent_reply far ON true
            WHERE msg.conversation_id = :conversation_id
              AND msg.sender_type = 'visitor'
              AND msg.content_type IN ('text', 'rich_text', 'image', 'file')
              AND (
                  msg.created_at < far.created_at
                  OR (msg.created_at = far.created_at AND msg.id < far.id)
              )
            ORDER BY msg.created_at DESC, msg.id DESC
            LIMIT 1
        )
        UPDATE conversations
        SET first_human_response_seconds = (
            SELECT GREATEST(0, EXTRACT(epoch FROM far.created_at - pvm.created_at))::int
            FROM first_agent_reply far
            JOIN pending_visitor_message pvm ON true
        )
        WHERE id = :conversation_id
          AND status = 'closed'
          AND ended_at IS NOT NULL
        """
    )

    @staticmethod
    async def recompute_first_human_response_seconds(
        db: AsyncSession,
        conversation_id: int,
    ) -> None:
        """Recompute first public human-agent response duration for one conversation."""
        await db.execute(
            ConversationRepository._RECOMPUTE_FIRST_HUMAN_RESPONSE_SQL,
            {"conversation_id": conversation_id},
        )

    # Authoritative recompute of the human-agent response stats from the
    # ``messages`` table, using the same caliber as the historical backfill:
    # over the public visitor/agent messages in chronological order, each agent
    # reply whose immediately preceding public message is a visitor message is
    # one response, timed from that last consecutive visitor message. count is 0
    # for an ended session without any response; avg is NULL in that case.
    _RECOMPUTE_AGENT_RESPONSE_METRICS_SQL = text(
        """
        WITH public_messages AS (
            SELECT
                msg.sender_type,
                msg.created_at,
                LAG(msg.sender_type) OVER w AS prev_sender_type,
                LAG(msg.created_at) OVER w AS prev_created_at
            FROM messages msg
            WHERE msg.conversation_id = :conversation_id
              AND msg.sender_type IN ('visitor', 'agent')
              AND msg.content_type IN ('text', 'rich_text', 'image', 'file')
            WINDOW w AS (ORDER BY msg.created_at ASC, msg.id ASC)
        ),
        responses AS (
            SELECT
                GREATEST(0, EXTRACT(epoch FROM created_at - prev_created_at))::int
                    AS response_seconds
            FROM public_messages
            WHERE sender_type = 'agent'
              AND prev_sender_type = 'visitor'
        )
        UPDATE conversations
        SET agent_response_count = (SELECT COUNT(*) FROM responses),
            agent_avg_response_seconds = (
                SELECT ROUND(AVG(response_seconds))::int FROM responses
            )
        WHERE id = :conversation_id
          AND status = 'closed'
          AND ended_at IS NOT NULL
        """
    )

    @staticmethod
    async def recompute_agent_response_metrics(
        db: AsyncSession,
        conversation_id: int,
    ) -> None:
        """Recompute human-agent response count and average duration for one conversation."""
        await db.execute(
            ConversationRepository._RECOMPUTE_AGENT_RESPONSE_METRICS_SQL,
            {"conversation_id": conversation_id},
        )

    @staticmethod
    async def end_conversation(
        db: AsyncSession, conversation: Conversation, ended_by: str
    ) -> Conversation:
        conversation.status = ConversationStatus.CLOSED.value
        conversation.ended_at = datetime.now(timezone.utc)
        conversation.ended_by = ended_by
        conversation.duration_seconds = compute_duration_seconds(
            conversation.started_at, conversation.ended_at
        )
        await db.flush()
        # Reconcile the materialized message counts from the source of truth so
        # the ended (and therefore reported) session is exact.
        await ConversationRepository.recompute_message_counts(db, conversation.id)
        await ConversationRepository.recompute_first_human_response_seconds(db, conversation.id)
        await ConversationRepository.recompute_agent_response_metrics(db, conversation.id)
        # Close the open reception segment with a structured event (all end paths
        # funnel through here). Only when a human was responsible at end.
        if conversation.agent_id is not None:
            await ReceptionEventRepository.create(
                db,
                {
                    "tenant_id": conversation.tenant_id,
                    "conversation_id": conversation.id,
                    "event_type": ReceptionEventType.ENDED.value,
                    "occurred_at": conversation.ended_at,
                    "agent_id": conversation.agent_id,
                    "group_id": conversation.group_id,
                    "from_agent_id": conversation.agent_id,
                },
            )
        await db.commit()
        await db.refresh(conversation)
        return conversation

    @staticmethod
    async def assign_agent(
        db: AsyncSession, conversation: Conversation, agent_id: int, group_id: int | None
    ) -> Conversation:
        conversation.agent_id = agent_id
        conversation.group_id = group_id
        conversation.status = ConversationStatus.ACTIVE.value
        conversation.started_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(conversation, attribute_names=["visitor", "agent", "channel", "group"])
        return conversation

    @staticmethod
    async def update_status(
        db: AsyncSession,
        conversation: Conversation,
        status: str,
    ) -> Conversation:
        conversation.status = status
        await db.commit()
        await db.refresh(conversation, attribute_names=["visitor", "agent", "channel", "group"])
        return conversation

    @staticmethod
    async def update_group(
        db: AsyncSession,
        conversation: Conversation,
        group_id: int,
    ) -> Conversation:
        conversation.group_id = group_id
        await db.commit()
        await db.refresh(conversation, attribute_names=["visitor", "agent", "channel", "group"])
        return conversation

    @staticmethod
    async def update_open_agent_state(
        db: AsyncSession,
        conversation: Conversation,
        data: dict,
    ) -> Conversation:
        allowed = {
            "open_agent_agent_id",
            "open_agent_agent_name",
            "open_agent_conversation_id",
            "open_agent_conversation_external_id",
            "open_agent_last_request_id",
            "open_agent_last_event_id",
            "open_agent_handoff_state",
            "open_agent_handoff_payload",
        }
        for key, value in data.items():
            if key in allowed:
                setattr(conversation, key, value)
        # Recompute the materialized bot markers from the now-current fields.
        for flag, flag_value in bot_flags_for_conversation(conversation).items():
            setattr(conversation, flag, flag_value)
        await db.commit()
        await db.refresh(conversation, attribute_names=["visitor", "agent", "channel", "group"])
        return conversation

    @staticmethod
    async def update_visitor_environment(
        db: AsyncSession,
        conversation: Conversation,
        data: dict,
    ) -> Conversation:
        allowed = {"visitor_system", "visitor_browser", "visitor_ip"}
        changed = False
        for key, value in data.items():
            if key not in allowed or value is None:
                continue
            if getattr(conversation, key) == value:
                continue
            setattr(conversation, key, value)
            changed = True
        if changed:
            await db.commit()
            await db.refresh(conversation, attribute_names=["visitor", "agent", "channel", "group"])
        return conversation

    @staticmethod
    async def update_handoff_state_if_unassigned(
        db: AsyncSession,
        conversation: Conversation,
        *,
        state: str,
        payload: dict | None,
        status: str | None = None,
        allowed_previous_states: tuple[str | None, ...] | None = None,
    ) -> tuple[Conversation, bool]:
        conditions = [
            Conversation.id == conversation.id,
            Conversation.agent_id.is_(None),
            Conversation.status.in_([
                ConversationStatus.BOT.value,
                ConversationStatus.HANDOFF_PENDING.value,
            ]),
        ]
        if allowed_previous_states is not None:
            state_conditions = []
            non_null_states = [
                item for item in allowed_previous_states
                if item is not None
            ]
            if None in allowed_previous_states:
                state_conditions.append(Conversation.open_agent_handoff_state.is_(None))
            if non_null_states:
                state_conditions.append(Conversation.open_agent_handoff_state.in_(non_null_states))
            if state_conditions:
                conditions.append(or_(*state_conditions))

        values = {
            "open_agent_handoff_state": state,
            "open_agent_handoff_payload": payload or {},
            # This path only runs for OpenAgent bot conversations, so the bot
            # marker holds; the flags track the new handoff state.
            "had_bot_session": True,
            "bot_handoff_succeeded": state == BOT_HANDOFF_SUCCESS_STATE,
            "bot_handoff_triggered": compute_bot_handoff_triggered(state),
        }
        if status is not None:
            values["status"] = status

        result = await db.execute(
            update(Conversation)
            .where(*conditions)
            .values(**values)
        )
        await db.commit()
        refreshed = await ConversationRepository.get_by_id(db, conversation.id)
        return refreshed or conversation, bool(getattr(result, "rowcount", 0))

    @staticmethod
    async def assign_agent_if_unassigned(
        db: AsyncSession,
        conversation: Conversation,
        agent_id: int,
        group_id: int | None,
        *,
        allowed_statuses: tuple[str, ...] = (
            ConversationStatus.BOT.value,
            ConversationStatus.HANDOFF_PENDING.value,
        ),
    ) -> tuple[Conversation, bool]:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation.id,
                Conversation.agent_id.is_(None),
                Conversation.status.in_(list(allowed_statuses)),
            )
            .values(
                agent_id=agent_id,
                group_id=group_id,
                status=ConversationStatus.ACTIVE.value,
                started_at=now,
            )
        )
        await db.commit()
        refreshed = await ConversationRepository.get_by_id(db, conversation.id)
        return refreshed or conversation, bool(getattr(result, "rowcount", 0))

    @staticmethod
    async def update_last_message(
        db: AsyncSession,
        conversation_id: int,
        preview: str,
        timestamp: datetime,
        increment_unread: bool = False,
    ) -> None:
        values: dict = {
            "last_message_at": timestamp,
            "last_message_preview": preview[:200] if preview else None,
        }
        if increment_unread:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(
                    **values,
                    unread_count=Conversation.unread_count + 1,
                )
            )
        else:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(**values)
            )
        await db.commit()

    @staticmethod
    async def reset_unread(db: AsyncSession, conversation_id: int) -> None:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(unread_count=0)
        )
        await db.commit()

    @staticmethod
    async def decrement_unread(db: AsyncSession, conversation_id: int) -> None:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(unread_count=func.greatest(Conversation.unread_count - 1, 0))
        )
        await db.commit()

    @staticmethod
    async def get_queued_by_tenant(
        db: AsyncSession, tenant_id: int, limit: int = 50
    ) -> list[Conversation]:
        """Get unassigned queued conversations for a tenant, oldest first."""
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.status == ConversationStatus.QUEUED.value,
                Conversation.agent_id.is_(None),
            )
            .order_by(Conversation.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_visitor_conversation(
        db: AsyncSession,
        tenant_id: int,
        visitor_id: int,
        channel_id: int,
    ) -> Conversation | None:
        """Check if visitor already has an active conversation in the channel.

        A visitor is expected to have at most one non-closed conversation per
        channel, but that invariant isn't enforced at the DB level, so a race in
        conversation creation can leave duplicates. Tolerate that here — return
        the most recent one and warn — instead of raising MultipleResultsFound.
        """
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.visitor_id == visitor_id,
                Conversation.channel_id == channel_id,
                Conversation.status.in_([
                    ConversationStatus.ACTIVE.value,
                    ConversationStatus.QUEUED.value,
                    ConversationStatus.BOT.value,
                    ConversationStatus.HANDOFF_PENDING.value,
                ]),
            )
            .order_by(Conversation.id.desc())
        )
        conversations = result.scalars().all()
        if len(conversations) > 1:
            logger.warning(
                "Visitor has %d active conversations (expected 1); using latest "
                "id=%s tenant=%s channel=%s visitor_id=%s",
                len(conversations),
                conversations[0].id,
                tenant_id,
                channel_id,
                visitor_id,
            )
        return conversations[0] if conversations else None

    @staticmethod
    async def list_stale_open_agent_bot_conversations(
        db: AsyncSession,
        *,
        cutoff_at: datetime,
        limit: int = 100,
    ) -> list[Conversation]:
        """List bot conversations whose latest bot activity is older than the cutoff."""
        bot_conversations = (
            select(
                Conversation.id.label("conversation_id"),
                Conversation.tenant_id.label("tenant_id"),
            )
            .where(Conversation.status == ConversationStatus.BOT.value)
            .subquery()
        )
        bot_activity_filter = or_(
            Message.sender_type == MessageSenderType.BOT.value,
            Message.content_type == MessageContentType.BOT_WELCOME.value,
            Message.metadata_["event_type"].astext == "open_agent_bot_started",
        )
        row_number = func.row_number().over(
            partition_by=Message.conversation_id,
            order_by=(Message.created_at.desc(), Message.id.desc()),
        ).label("row_number")
        ranked_bot_activity = (
            select(
                Message.conversation_id.label("conversation_id"),
                Message.id.label("message_id"),
                Message.created_at.label("created_at"),
                row_number,
            )
            .join(bot_conversations, bot_conversations.c.conversation_id == Message.conversation_id)
            .where(bot_activity_filter)
            .where(Message.tenant_id == bot_conversations.c.tenant_id)
            .subquery()
        )
        latest_bot_activity = (
            select(
                ranked_bot_activity.c.conversation_id,
                ranked_bot_activity.c.message_id,
                ranked_bot_activity.c.created_at,
            )
            .where(ranked_bot_activity.c.row_number == 1)
            .subquery()
        )
        visitor_after_latest_bot = exists().where(
            Message.tenant_id == Conversation.tenant_id,
            Message.conversation_id == Conversation.id,
            Message.sender_type == MessageSenderType.VISITOR.value,
            or_(
                Message.created_at > latest_bot_activity.c.created_at,
                and_(
                    Message.created_at == latest_bot_activity.c.created_at,
                    Message.id > latest_bot_activity.c.message_id,
                ),
            ),
        )
        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .join(latest_bot_activity, latest_bot_activity.c.conversation_id == Conversation.id)
            .where(
                Conversation.status == ConversationStatus.BOT.value,
                latest_bot_activity.c.created_at <= cutoff_at,
                ~visitor_after_latest_bot,
            )
            .order_by(latest_bot_activity.c.created_at.asc(), Conversation.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_visitor_history(
        db: AsyncSession,
        tenant_id: int,
        channel_id: int | None,
        visitor_id: int,
        *,
        current_conversation_id: int | None = None,
        before_id: int | None = None,
        agent_id: int | None = None,
        keyword: str | None = None,
        limit: int = 10,
        scope_predicate: ColumnElement | None = None,
    ) -> list[Conversation]:
        """Get visitor conversations, newest first."""
        sort_expr = func.coalesce(Conversation.started_at, Conversation.created_at)
        conditions = [
            Conversation.tenant_id == tenant_id,
            Conversation.visitor_id == visitor_id,
        ]
        if scope_predicate is not None:
            conditions.append(scope_predicate)
        if channel_id is not None:
            conditions.append(Conversation.channel_id == channel_id)
        if agent_id is not None:
            conditions.append(Conversation.agent_id == agent_id)
        if keyword:
            conditions.append(
                exists()
                .where(
                    Message.tenant_id == tenant_id,
                    Message.conversation_id == Conversation.id,
                    Message.content_type.in_([
                        MessageContentType.TEXT.value,
                        MessageContentType.RICH_TEXT.value,
                        MessageContentType.INTERNAL_NOTE.value,
                    ]),
                    Message.content.ilike(f"%{keyword}%"),
                )
            )

        if current_conversation_id is not None:
            conditions.append(Conversation.id != current_conversation_id)

        if before_id is not None:
            cursor = await db.get(Conversation, before_id)
            if cursor:
                cursor_sort = cursor.started_at or cursor.created_at
                conditions.append(
                    or_(
                        sort_expr < cursor_sort,
                        and_(sort_expr == cursor_sort, Conversation.id < cursor.id),
                    )
                )

        result = await db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
            )
            .where(*conditions)
            .order_by(sort_expr.desc(), Conversation.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
