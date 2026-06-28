"""
Repository helpers for conversation collaboration.
"""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.conversation_collaboration import (
    ConversationCollaborationInvitation,
    ConversationCollaborator,
)
from app.models.employee import Employee

INVITATION_PENDING = "pending"
INVITATION_ACCEPTED = "accepted"
INVITATION_DECLINED = "declined"
INVITATION_EXPIRED = "expired"
COLLABORATOR_ACTIVE = "active"


class ConversationCollaborationRepository:
    @staticmethod
    def invitation_options() -> tuple:
        return (
            selectinload(ConversationCollaborationInvitation.conversation).selectinload(Conversation.visitor),
            selectinload(ConversationCollaborationInvitation.conversation).selectinload(Conversation.agent),
            selectinload(ConversationCollaborationInvitation.conversation).selectinload(Conversation.channel),
            selectinload(ConversationCollaborationInvitation.conversation).selectinload(Conversation.group),
            selectinload(ConversationCollaborationInvitation.inviter),
            selectinload(ConversationCollaborationInvitation.invitee),
        )

    @staticmethod
    async def get_invitation_by_id(
        db: AsyncSession,
        invitation_id: int,
    ) -> ConversationCollaborationInvitation | None:
        result = await db.execute(
            select(ConversationCollaborationInvitation)
            .options(*ConversationCollaborationRepository.invitation_options())
            .where(ConversationCollaborationInvitation.id == invitation_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_pending_invitation(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        invitee_id: int,
    ) -> ConversationCollaborationInvitation | None:
        result = await db.execute(
            select(ConversationCollaborationInvitation)
            .where(
                ConversationCollaborationInvitation.tenant_id == tenant_id,
                ConversationCollaborationInvitation.conversation_id == conversation_id,
                ConversationCollaborationInvitation.invitee_id == invitee_id,
                ConversationCollaborationInvitation.status == INVITATION_PENDING,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_pending_for_invitee(
        db: AsyncSession,
        *,
        tenant_id: int,
        invitee_id: int,
        now: datetime,
    ) -> list[ConversationCollaborationInvitation]:
        result = await db.execute(
            select(ConversationCollaborationInvitation)
            .options(*ConversationCollaborationRepository.invitation_options())
            .where(
                ConversationCollaborationInvitation.tenant_id == tenant_id,
                ConversationCollaborationInvitation.invitee_id == invitee_id,
                ConversationCollaborationInvitation.status == INVITATION_PENDING,
                ConversationCollaborationInvitation.expires_at > now,
            )
            .order_by(ConversationCollaborationInvitation.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def expire_pending_for_invitee(
        db: AsyncSession,
        *,
        tenant_id: int,
        invitee_id: int,
        now: datetime,
    ) -> None:
        await db.execute(
            update(ConversationCollaborationInvitation)
            .where(
                ConversationCollaborationInvitation.tenant_id == tenant_id,
                ConversationCollaborationInvitation.invitee_id == invitee_id,
                ConversationCollaborationInvitation.status == INVITATION_PENDING,
                ConversationCollaborationInvitation.expires_at <= now,
            )
            .values(status=INVITATION_EXPIRED, responded_at=now)
        )

    @staticmethod
    async def create_invitation(
        db: AsyncSession,
        data: dict,
    ) -> ConversationCollaborationInvitation:
        invitation = ConversationCollaborationInvitation(**data)
        db.add(invitation)
        await db.flush()
        return await ConversationCollaborationRepository.get_invitation_by_id(db, invitation.id) or invitation

    @staticmethod
    async def is_active_collaborator(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        agent_id: int,
    ) -> bool:
        result = await db.execute(
            select(ConversationCollaborator.id)
            .where(
                ConversationCollaborator.tenant_id == tenant_id,
                ConversationCollaborator.conversation_id == conversation_id,
                ConversationCollaborator.agent_id == agent_id,
                ConversationCollaborator.status == COLLABORATOR_ACTIVE,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_active_collaborator(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        agent_id: int,
    ) -> ConversationCollaborator | None:
        result = await db.execute(
            select(ConversationCollaborator)
            .where(
                ConversationCollaborator.tenant_id == tenant_id,
                ConversationCollaborator.conversation_id == conversation_id,
                ConversationCollaborator.agent_id == agent_id,
                ConversationCollaborator.status == COLLABORATOR_ACTIVE,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_collaborator(
        db: AsyncSession,
        data: dict,
    ) -> ConversationCollaborator:
        collaborator = ConversationCollaborator(**data)
        db.add(collaborator)
        await db.flush()
        return collaborator

    @staticmethod
    async def get_active_collaborator_agent_ids(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
    ) -> list[int]:
        result = await db.execute(
            select(ConversationCollaborator.agent_id)
            .where(
                ConversationCollaborator.tenant_id == tenant_id,
                ConversationCollaborator.conversation_id == conversation_id,
                ConversationCollaborator.status == COLLABORATOR_ACTIVE,
                ConversationCollaborator.agent_id.is_not(None),
            )
        )
        return [int(agent_id) for agent_id in result.scalars().all()]

    @staticmethod
    async def get_pending_invitee_ids(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        now: datetime,
    ) -> list[int]:
        result = await db.execute(
            select(ConversationCollaborationInvitation.invitee_id)
            .where(
                ConversationCollaborationInvitation.tenant_id == tenant_id,
                ConversationCollaborationInvitation.conversation_id == conversation_id,
                ConversationCollaborationInvitation.status == INVITATION_PENDING,
                ConversationCollaborationInvitation.expires_at > now,
                ConversationCollaborationInvitation.invitee_id.is_not(None),
            )
        )
        return [int(invitee_id) for invitee_id in result.scalars().all()]

    @staticmethod
    async def get_active_collaborator_agents_by_conversation_ids(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_ids: list[int],
    ) -> dict[int, list[Employee]]:
        if not conversation_ids:
            return {}
        result = await db.execute(
            select(ConversationCollaborator.conversation_id, Employee)
            .join(Employee, Employee.id == ConversationCollaborator.agent_id)
            .where(
                ConversationCollaborator.tenant_id == tenant_id,
                ConversationCollaborator.conversation_id.in_(conversation_ids),
                ConversationCollaborator.status == COLLABORATOR_ACTIVE,
                Employee.is_active.is_(True),
            )
            .order_by(ConversationCollaborator.joined_at.asc(), ConversationCollaborator.id.asc())
        )
        grouped: dict[int, list[Employee]] = {conversation_id: [] for conversation_id in conversation_ids}
        for conversation_id, employee in result.all():
            grouped.setdefault(conversation_id, []).append(employee)
        return grouped

    @staticmethod
    async def get_active_conversations_by_agent(
        db: AsyncSession,
        *,
        tenant_id: int,
        agent_id: int,
    ) -> list[Conversation]:
        result = await db.execute(
            select(Conversation)
            .join(ConversationCollaborator, ConversationCollaborator.conversation_id == Conversation.id)
            .options(
                selectinload(Conversation.visitor),
                selectinload(Conversation.agent),
                selectinload(Conversation.channel),
                selectinload(Conversation.group),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.status == "active",
                ConversationCollaborator.tenant_id == tenant_id,
                ConversationCollaborator.agent_id == agent_id,
                ConversationCollaborator.status == COLLABORATOR_ACTIVE,
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
        )
        return list(result.scalars().all())
