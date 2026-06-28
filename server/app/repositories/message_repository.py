"""
Message repository
"""
import json
from datetime import datetime

from sqlalchemy import case, select, func, or_, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.enums import MessageContentType, MessageSenderType
from app.libs.conversation_metrics import message_count_increments
from app.models.conversation import Conversation
from app.models.message import Message


class MessageRepository:
    READ_STATUS_CONTENT_TYPES = {
        MessageContentType.TEXT.value,
        MessageContentType.RICH_TEXT.value,
        MessageContentType.IMAGE.value,
        MessageContentType.FILE.value,
    }

    @staticmethod
    async def get_by_conversation(
        db: AsyncSession,
        conversation_id: int,
        before_id: int | None = None,
        limit: int = 20,
        include_internal: bool = True,
        visibility_target: str | None = None,
    ) -> list[Message]:
        """Fetch messages for a conversation, paginated by cursor (before_id)."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
        )
        if not include_internal:
            query = query.where(Message.content_type != MessageContentType.INTERNAL_NOTE.value)
        if visibility_target:
            visible_to = Message.metadata_["visible_to"]
            query = query.where(
                or_(
                    Message.metadata_.op("?")("visible_to").is_(False),
                    func.jsonb_typeof(visible_to) != "array",
                    visible_to.contains([visibility_target]),
                )
            )
        if before_id:
            query = query.where(Message.id < before_id)
        query = query.order_by(Message.id.desc()).limit(limit)
        result = await db.execute(query)
        items = list(result.scalars().all())
        items.reverse()  # return in chronological order
        return items

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Message:
        item = Message(**data)
        db.add(item)
        await MessageRepository._increment_conversation_message_counts(
            db, item.conversation_id, item.sender_type
        )
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def _increment_conversation_message_counts(
        db: AsyncSession,
        conversation_id: int,
        sender_type: str,
    ) -> None:
        """Bump the materialized per-conversation message counts for one message.

        Mirrors ``message_count_increments``: the phase split for visitor
        messages depends on whether the conversation has been taken over by a
        human (``had_bot_session = false OR started_at IS NOT NULL``), so it is
        expressed as an in-row SQL CASE — no extra read, race-free, committed in
        the same transaction as the message insert. The end-of-conversation
        reconcile recomputes authoritatively from ``messages`` to absorb drift.
        """
        bot_phase_inc = message_count_increments(sender_type, in_human_phase=False)
        human_phase_inc = message_count_increments(sender_type, in_human_phase=True)
        columns = set(bot_phase_inc) | set(human_phase_inc)
        if not columns:
            return

        in_human_phase = or_(
            Conversation.had_bot_session.is_(False),
            Conversation.started_at.is_not(None),
        )
        values: dict = {}
        for column in columns:
            column_attr = getattr(Conversation, column)
            phase_bot = bot_phase_inc.get(column, 0)
            phase_human = human_phase_inc.get(column, 0)
            if phase_bot == phase_human:
                values[column] = column_attr + phase_bot
            else:
                values[column] = column_attr + case(
                    (in_human_phase, phase_human), else_=phase_bot
                )

        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(**values)
        )

    @staticmethod
    async def get_by_id_for_conversation(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        message_id: int,
    ) -> Message | None:
        result = await db.execute(
            select(Message).where(
                Message.id == message_id,
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_by_conversation_id(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
    ) -> Message | None:
        """Fetch the latest persisted message in a conversation."""
        result = await db.execute(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def recall_message(
        db: AsyncSession,
        message: Message,
        *,
        recalled_at: datetime,
        recalled_by_type: str,
        recalled_by_id: int | None,
        recalled_by_name: str | None,
    ) -> Message:
        """Mark a message as recalled without deleting its audit record."""
        message.is_recalled = True
        message.recalled_at = recalled_at
        message.recalled_by_type = recalled_by_type
        message.recalled_by_id = recalled_by_id
        message.recalled_by_name = recalled_by_name
        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    async def get_file_message_by_file_id(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        file_id: str,
    ) -> Message | None:
        """Find the conversation message that references a conversation file id."""
        result = await db.execute(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.content_type.in_([MessageContentType.IMAGE.value, MessageContentType.FILE.value]),
                Message.content.contains(file_id),
            )
            .order_by(Message.id.desc())
        )
        for message in result.scalars().all():
            try:
                payload = json.loads(message.content)
            except json.JSONDecodeError:
                continue
            if payload.get("file_id") == file_id or payload.get("thumbnail_file_id") == file_id:
                return message
        return None

    @staticmethod
    async def update_metadata(db: AsyncSession, message: Message, metadata: dict) -> Message:
        message.metadata_ = metadata
        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    async def get_messages_quoting_message(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        message_id: int,
    ) -> list[Message]:
        result = await db.execute(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.metadata_["quote"]["message_id"].astext == str(message_id),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_agent_messages_visitor_read(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        read_at: datetime,
        before_message_id: int | None = None,
    ) -> list[int]:
        query = update(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            Message.sender_type == MessageSenderType.AGENT.value,
            Message.content_type.in_(MessageRepository.READ_STATUS_CONTENT_TYPES),
            Message.visitor_read_at.is_(None),
        )
        if before_message_id is not None:
            query = query.where(Message.id < before_message_id)
        result = await db.execute(
            query
            .values(visitor_read_at=read_at)
            .returning(Message.id)
        )
        await db.commit()
        return list(result.scalars().all())

    @staticmethod
    async def mark_visitor_messages_agent_read(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        read_at: datetime,
    ) -> list[int]:
        result = await db.execute(
            update(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.sender_type == MessageSenderType.VISITOR.value,
                Message.content_type.in_(MessageRepository.READ_STATUS_CONTENT_TYPES),
                Message.agent_read_at.is_(None),
            )
            .values(agent_read_at=read_at)
            .returning(Message.id)
        )
        await db.commit()
        return list(result.scalars().all())

    @staticmethod
    async def has_welcome_message(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
    ) -> bool:
        result = await db.execute(
            select(Message.id).where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.content_type == MessageContentType.WELCOME.value,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_welcome_message(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
    ) -> Message | None:
        result = await db.execute(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.content_type == MessageContentType.WELCOME.value,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_event_message(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        event_type: str,
    ) -> Message | None:
        """Fetch the latest system message carrying the given metadata event_type."""
        result = await db.execute(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.content_type == MessageContentType.SYSTEM.value,
                Message.metadata_["event_type"].astext == event_type,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_by_sender(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        sender_type: str,
        content_types: set[str] | None = None,
    ) -> Message | None:
        """Fetch the latest message for one sender side in a conversation."""
        query = select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            Message.sender_type == sender_type,
        )
        if content_types:
            query = query.where(Message.content_type.in_(sorted(content_types)))
        result = await db.execute(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_open_agent_bot_activity(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
    ) -> Message | None:
        """Fetch the latest bot-side activity that can anchor bot idle timeout."""
        result = await db.execute(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                or_(
                    Message.sender_type == MessageSenderType.BOT.value,
                    Message.content_type == MessageContentType.BOT_WELCOME.value,
                    Message.metadata_["event_type"].astext == "open_agent_bot_started",
                ),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def has_visitor_message_after(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        anchor_message_id: int,
        anchor_created_at: datetime | None,
    ) -> bool:
        """Return whether a visitor sent anything after the anchor message."""
        after_anchor = Message.id > anchor_message_id
        if anchor_created_at is not None:
            after_anchor = or_(
                Message.created_at > anchor_created_at,
                and_(
                    Message.created_at == anchor_created_at,
                    Message.id > anchor_message_id,
                ),
            )
        result = await db.execute(
            select(Message.id)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.sender_type == MessageSenderType.VISITOR.value,
                after_anchor,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_by_client_message_id(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        client_message_id: str,
        sender_type: str = "visitor",
    ) -> Message | None:
        """Fetch an idempotent message by the client-provided turn key."""
        result = await db.execute(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.sender_type == sender_type,
                Message.metadata_["client_message_id"].astext == client_message_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_handoff_event_by_tool_call_id(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        tool_call_id: str,
        handoff_event_type: str,
    ) -> Message | None:
        """Fetch an OpenAgent handoff system event for idempotent event handling."""
        result = await db.execute(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.sender_type == "system",
                Message.content_type == "system",
                Message.metadata_["event_type"].astext == "open_agent_handoff_event",
                Message.metadata_["handoff_event_type"].astext == handoff_event_type,
                Message.metadata_["tool_call_id"].astext == tool_call_id,
            ).order_by(Message.id.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def count_by_conversation(db: AsyncSession, conversation_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(Message).where(
                Message.conversation_id == conversation_id
            )
        )
        return result.scalar_one()

    @staticmethod
    async def get_recent_by_conversations(
        db: AsyncSession,
        tenant_id: int,
        conversation_ids: list[int],
        per_conversation_limit: int = 200,
        include_internal: bool = True,
    ) -> dict[int, list[Message]]:
        """Fetch recent messages for multiple conversations with a per-conversation cap."""
        if not conversation_ids:
            return {}

        row_number = func.row_number().over(
            partition_by=Message.conversation_id,
            order_by=Message.id.desc(),
        ).label("row_number")
        ranked_query = (
            select(Message, row_number)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id.in_(conversation_ids),
            )
        )
        if not include_internal:
            ranked_query = ranked_query.where(Message.content_type != MessageContentType.INTERNAL_NOTE.value)
        ranked = ranked_query.subquery()
        message_alias = aliased(Message, ranked)
        result = await db.execute(
            select(message_alias)
            .where(ranked.c.row_number <= per_conversation_limit)
            .order_by(message_alias.conversation_id.asc(), message_alias.id.asc())
        )

        grouped: dict[int, list[Message]] = {conversation_id: [] for conversation_id in conversation_ids}
        for message in result.scalars().all():
            grouped.setdefault(message.conversation_id, []).append(message)
        return grouped

    @staticmethod
    async def get_agent_message_conversation_ids(
        db: AsyncSession,
        tenant_id: int,
        conversation_ids: list[int],
        agent_id: int,
    ) -> set[int]:
        """Return conversation IDs where the agent has already sent a message."""
        if not conversation_ids:
            return set()
        result = await db.execute(
            select(Message.conversation_id)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id.in_(conversation_ids),
                Message.sender_type == MessageSenderType.AGENT.value,
                Message.sender_id == agent_id,
            )
            .distinct()
        )
        return set(result.scalars().all())

    @staticmethod
    async def search_workspace_visitor_messages(
        db: AsyncSession,
        *,
        tenant_id: int,
        visitor_id: int,
        keyword: str | None = None,
        before_id: int | None = None,
        agent_id: int | None = None,
        limit: int = 31,
        scope_predicate: ColumnElement | None = None,
    ) -> list[tuple[Message, Conversation]]:
        """Search accessible text messages for one workspace visitor."""
        conditions = [
            Message.tenant_id == tenant_id,
            Conversation.tenant_id == tenant_id,
            Conversation.visitor_id == visitor_id,
            Message.content_type.in_([
                MessageContentType.TEXT.value,
                MessageContentType.RICH_TEXT.value,
                MessageContentType.INTERNAL_NOTE.value,
            ]),
            Message.is_recalled.is_(False),
        ]
        if keyword:
            conditions.append(Message.content.ilike(f"%{keyword}%"))
        if before_id is not None:
            conditions.append(Message.id < before_id)
        if agent_id is not None:
            conditions.append(Conversation.agent_id == agent_id)
        if scope_predicate is not None:
            conditions.append(scope_predicate)

        result = await db.execute(
            select(Message, Conversation)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(*conditions)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(result.all())
