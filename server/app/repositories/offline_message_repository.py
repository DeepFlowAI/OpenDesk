"""
Offline message repository.
"""
import secrets
from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.conversation import Conversation
from app.models.offline_message import OfflineMessage, OfflineMessageEntry

OFFLINE_MESSAGE_PUBLIC_ID_PREFIX = "om_"
OFFLINE_MESSAGE_PUBLIC_ID_RANDOM_BYTES = 24
MAX_PUBLIC_ID_GENERATION_ATTEMPTS = 10


class OfflineMessageRepository:
    @staticmethod
    def _with_relationships(query: Select, *, include_messages: bool = True) -> Select:
        options = [
            selectinload(OfflineMessage.visitor),
            selectinload(OfflineMessage.channel),
            selectinload(OfflineMessage.target_group),
            selectinload(OfflineMessage.conversation),
            selectinload(OfflineMessage.handled_by),
        ]
        if include_messages:
            options.append(selectinload(OfflineMessage.messages))
        return query.options(*options)

    @staticmethod
    def _with_customer_reply_relationships(query: Select) -> Select:
        return query.options(
            selectinload(OfflineMessage.visitor),
            selectinload(OfflineMessage.conversation).selectinload(Conversation.agent),
            selectinload(OfflineMessage.conversation).selectinload(Conversation.visitor),
            selectinload(OfflineMessage.conversation).selectinload(Conversation.channel),
        )

    @staticmethod
    def generate_public_id() -> str:
        return f"{OFFLINE_MESSAGE_PUBLIC_ID_PREFIX}{secrets.token_urlsafe(OFFLINE_MESSAGE_PUBLIC_ID_RANDOM_BYTES)}"

    @staticmethod
    async def get_by_public_id(db: AsyncSession, public_id: str) -> OfflineMessage | None:
        result = await db.execute(
            OfflineMessageRepository._with_relationships(
                select(OfflineMessage).where(OfflineMessage.public_id == public_id)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_public_id_for_update(db: AsyncSession, public_id: str) -> OfflineMessage | None:
        result = await db.execute(
            OfflineMessageRepository._with_relationships(
                select(OfflineMessage)
                .where(OfflineMessage.public_id == public_id)
                .with_for_update()
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, offline_message_id: int) -> OfflineMessage | None:
        result = await db.execute(
            OfflineMessageRepository._with_relationships(
                select(OfflineMessage).where(OfflineMessage.id == offline_message_id)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id_for_update(db: AsyncSession, offline_message_id: int) -> OfflineMessage | None:
        result = await db.execute(
            OfflineMessageRepository._with_relationships(
                select(OfflineMessage)
                .where(OfflineMessage.id == offline_message_id)
                .with_for_update()
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def generate_unique_public_id(db: AsyncSession) -> str:
        for _ in range(MAX_PUBLIC_ID_GENERATION_ATTEMPTS):
            public_id = OfflineMessageRepository.generate_public_id()
            if not await OfflineMessageRepository.get_by_public_id(db, public_id):
                return public_id
        raise RuntimeError("Failed to generate a unique offline message public ID")

    @staticmethod
    async def get_pending_by_visitor(
        db: AsyncSession,
        *,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
    ) -> OfflineMessage | None:
        result = await db.execute(
            OfflineMessageRepository._with_relationships(
                select(OfflineMessage)
                .where(
                    OfflineMessage.tenant_id == tenant_id,
                    OfflineMessage.channel_id == channel_id,
                    OfflineMessage.visitor_external_id == visitor_external_id,
                    OfflineMessage.status == "pending",
                )
                .order_by(OfflineMessage.id.desc())
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_pending_by_visitor_for_update(
        db: AsyncSession,
        *,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
    ) -> OfflineMessage | None:
        result = await db.execute(
            OfflineMessageRepository._with_relationships(
                select(OfflineMessage)
                .where(
                    OfflineMessage.tenant_id == tenant_id,
                    OfflineMessage.channel_id == channel_id,
                    OfflineMessage.visitor_external_id == visitor_external_id,
                    OfflineMessage.status == "pending",
                )
                .order_by(OfflineMessage.id.desc())
                .with_for_update()
            )
        )
        return result.scalars().first()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> OfflineMessage:
        if not data.get("public_id"):
            data = {**data, "public_id": await OfflineMessageRepository.generate_unique_public_id(db)}
        item = OfflineMessage(**data)
        db.add(item)
        await db.commit()
        await db.refresh(
            item,
            attribute_names=[
                "visitor",
                "channel",
                "target_group",
                "conversation",
                "handled_by",
                "messages",
            ],
        )
        return item

    @staticmethod
    async def list_by_tenant(
        db: AsyncSession,
        *,
        tenant_id: int,
        status: str | None,
        before_id: int | None,
        limit: int,
        scope_predicate: ColumnElement | None = None,
    ) -> tuple[list[OfflineMessage], bool]:
        conditions = [OfflineMessage.tenant_id == tenant_id]
        if status and status != "all":
            conditions.append(OfflineMessage.status == status)
        if scope_predicate is not None:
            conditions.append(scope_predicate)

        if before_id is not None:
            cursor = await db.get(OfflineMessage, before_id)
            if cursor:
                cursor_sort = cursor.last_message_at or cursor.created_at
                sort_expr = func.coalesce(OfflineMessage.last_message_at, OfflineMessage.created_at)
                conditions.append(
                    or_(
                        sort_expr < cursor_sort,
                        and_(sort_expr == cursor_sort, OfflineMessage.id < cursor.id),
                    )
                )

        sort_expr = func.coalesce(OfflineMessage.last_message_at, OfflineMessage.created_at)
        result = await db.execute(
            OfflineMessageRepository._with_relationships(
                select(OfflineMessage)
                .where(*conditions)
                .order_by(sort_expr.desc(), OfflineMessage.id.desc())
                .limit(limit + 1),
                include_messages=False,
            )
        )
        rows = list(result.scalars().all())
        has_more = len(rows) > limit
        return rows[:limit], has_more

    @staticmethod
    async def count_by_tenant(
        db: AsyncSession,
        *,
        tenant_id: int,
        status: str | None,
        scope_predicate: ColumnElement | None = None,
    ) -> int:
        conditions = [OfflineMessage.tenant_id == tenant_id]
        if status and status != "all":
            conditions.append(OfflineMessage.status == status)
        if scope_predicate is not None:
            conditions.append(scope_predicate)

        result = await db.execute(
            select(func.count())
            .select_from(OfflineMessage)
            .where(*conditions)
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_customer_unread_replies(
        db: AsyncSession,
        *,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
        limit: int,
    ) -> tuple[list[OfflineMessage], bool]:
        result = await db.execute(
            OfflineMessageRepository._with_customer_reply_relationships(
                select(OfflineMessage)
                .where(
                    OfflineMessage.tenant_id == tenant_id,
                    OfflineMessage.channel_id == channel_id,
                    OfflineMessage.visitor_external_id == visitor_external_id,
                    OfflineMessage.status == "converted",
                    OfflineMessage.conversation_id.is_not(None),
                    OfflineMessage.customer_unread_at.is_not(None),
                )
                .order_by(OfflineMessage.customer_unread_at.desc(), OfflineMessage.id.desc())
                .limit(limit + 1)
            )
        )
        rows = list(result.scalars().all())
        has_more = len(rows) > limit
        return rows[:limit], has_more

    @staticmethod
    async def mark_customer_unread_by_conversation(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        message_id: int,
        unread_at: datetime,
    ) -> None:
        await db.execute(
            update(OfflineMessage)
            .where(
                OfflineMessage.tenant_id == tenant_id,
                OfflineMessage.conversation_id == conversation_id,
                OfflineMessage.status == "converted",
            )
            .values(
                customer_unread_at=unread_at,
                customer_read_at=None,
                customer_unread_first_message_id=func.coalesce(
                    OfflineMessage.customer_unread_first_message_id,
                    message_id,
                ),
            )
        )
        await db.commit()

    @staticmethod
    async def mark_customer_read_by_conversation(
        db: AsyncSession,
        *,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
        conversation_id: int,
        read_at: datetime,
    ) -> None:
        await db.execute(
            update(OfflineMessage)
            .where(
                OfflineMessage.tenant_id == tenant_id,
                OfflineMessage.channel_id == channel_id,
                OfflineMessage.visitor_external_id == visitor_external_id,
                OfflineMessage.conversation_id == conversation_id,
                OfflineMessage.customer_unread_at.is_not(None),
            )
            .values(
                customer_unread_at=None,
                customer_read_at=read_at,
                customer_unread_first_message_id=None,
            )
        )
        await db.commit()

    @staticmethod
    async def list_messages(
        db: AsyncSession,
        offline_message_id: int,
        *,
        before_id: int | None = None,
        limit: int = 50,
    ) -> tuple[list[OfflineMessageEntry], bool]:
        query = select(OfflineMessageEntry).where(OfflineMessageEntry.offline_message_id == offline_message_id)
        if before_id:
            query = query.where(OfflineMessageEntry.id < before_id)
        result = await db.execute(query.order_by(OfflineMessageEntry.id.desc()).limit(limit + 1))
        rows = list(result.scalars().all())
        has_more = len(rows) > limit
        items = rows[:limit]
        items.reverse()
        return items, has_more

    @staticmethod
    async def create_message(db: AsyncSession, data: dict) -> OfflineMessageEntry:
        item = OfflineMessageEntry(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_last_message(
        db: AsyncSession,
        offline_message_id: int,
        *,
        preview: str,
        timestamp: datetime,
        increment_count: bool = True,
    ) -> None:
        values = {
            "last_message_preview": preview[:200] if preview else None,
            "last_message_at": timestamp,
        }
        if increment_count:
            await db.execute(
                update(OfflineMessage)
                .where(OfflineMessage.id == offline_message_id)
                .values(
                    **values,
                    message_count=OfflineMessage.message_count + 1,
                )
            )
        else:
            await db.execute(update(OfflineMessage).where(OfflineMessage.id == offline_message_id).values(**values))
        await db.commit()

    @staticmethod
    async def mark_converted(
        db: AsyncSession,
        offline_message: OfflineMessage,
        *,
        conversation_id: int,
        handled_by_id: int,
        handled_at: datetime,
    ) -> OfflineMessage:
        offline_message.status = "converted"
        offline_message.conversation_id = conversation_id
        offline_message.handled_by_id = handled_by_id
        offline_message.handled_at = handled_at
        await db.commit()
        await db.refresh(
            offline_message,
            attribute_names=[
                "visitor",
                "channel",
                "target_group",
                "conversation",
                "handled_by",
                "messages",
            ],
        )
        return offline_message
