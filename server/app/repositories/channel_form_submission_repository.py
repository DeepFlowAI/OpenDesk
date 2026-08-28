"""Data access for successful Web SDK form-message submissions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_form_submission import ChannelFormSubmission
from app.models.channel import Channel
from app.models.conversation import Conversation


class ChannelFormSubmissionRepository:
    @staticmethod
    async def get_by_idempotency_key(
        db: AsyncSession,
        *,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
        idempotency_key: str,
    ) -> ChannelFormSubmission | None:
        result = await db.execute(
            select(ChannelFormSubmission).where(
                ChannelFormSubmission.tenant_id == tenant_id,
                ChannelFormSubmission.channel_id == channel_id,
                ChannelFormSubmission.visitor_external_id == visitor_external_id,
                ChannelFormSubmission.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_ticket_id(
        db: AsyncSession,
        tenant_id: int,
        ticket_id: int,
    ) -> ChannelFormSubmission | None:
        result = await db.execute(
            select(ChannelFormSubmission).where(
                ChannelFormSubmission.tenant_id == tenant_id,
                ChannelFormSubmission.ticket_id == ticket_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_detail_by_ticket_id(
        db: AsyncSession,
        tenant_id: int,
        ticket_id: int,
    ) -> tuple[ChannelFormSubmission, str, str | None] | None:
        result = await db.execute(
            select(ChannelFormSubmission, Channel.name, Conversation.public_id)
            .join(Channel, Channel.id == ChannelFormSubmission.channel_id)
            .outerjoin(Conversation, Conversation.id == ChannelFormSubmission.conversation_id)
            .where(
                ChannelFormSubmission.tenant_id == tenant_id,
                ChannelFormSubmission.ticket_id == ticket_id,
            )
        )
        row = result.one_or_none()
        if not row:
            return None
        return row[0], row[1], row[2]

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ChannelFormSubmission:
        item = ChannelFormSubmission(**data)
        db.add(item)
        await db.flush()
        return item
