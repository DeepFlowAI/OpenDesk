"""
Conversation repository
"""
import secrets
from datetime import datetime, timezone

from sqlalchemy import select, func, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.enums import ConversationStatus
from app.models.conversation import Conversation

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
        item = Conversation(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item, attribute_names=["visitor", "agent", "channel", "group"])
        return item

    @staticmethod
    async def end_conversation(
        db: AsyncSession, conversation: Conversation, ended_by: str
    ) -> Conversation:
        conversation.status = ConversationStatus.CLOSED.value
        conversation.ended_at = datetime.now(timezone.utc)
        conversation.ended_by = ended_by
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
        """Check if visitor already has an active conversation in the channel."""
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
        )
        return result.scalar_one_or_none()

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
