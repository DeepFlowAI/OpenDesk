"""
Message repository
"""
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.enums import MessageContentType, MessageSenderType
from app.models.conversation import Conversation
from app.models.message import Message


class MessageRepository:

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
        await db.commit()
        await db.refresh(item)
        return item

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
