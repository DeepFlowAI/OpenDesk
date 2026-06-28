"""
Conversation collaboration models.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationCollaborationInvitation(Base, TimestampMixin):
    __tablename__ = "conversation_collaboration_invitations"
    __table_args__ = (
        Index("ix_collab_inv_tenant_conversation", "tenant_id", "conversation_id"),
        Index("ix_collab_inv_invitee_status", "tenant_id", "invitee_id", "status"),
        Index(
            "uq_collab_inv_pending_target",
            "tenant_id",
            "conversation_id",
            "invitee_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    inviter_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"))
    invitee_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped["Conversation"] = relationship("Conversation", lazy="selectin")
    inviter: Mapped["Employee | None"] = relationship("Employee", foreign_keys=[inviter_id], lazy="selectin")
    invitee: Mapped["Employee | None"] = relationship("Employee", foreign_keys=[invitee_id], lazy="selectin")


class ConversationCollaborator(Base, TimestampMixin):
    __tablename__ = "conversation_collaborators"
    __table_args__ = (
        Index("ix_collaborators_tenant_conversation_status", "tenant_id", "conversation_id", "status"),
        Index("ix_collaborators_agent_status", "tenant_id", "agent_id", "status"),
        Index(
            "uq_collaborators_active_agent",
            "tenant_id",
            "conversation_id",
            "agent_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id", ondelete="SET NULL"))
    invitation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("conversation_collaboration_invitations.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped["Conversation"] = relationship("Conversation", lazy="selectin")
    agent: Mapped["Employee | None"] = relationship("Employee", lazy="selectin")
    invitation: Mapped["ConversationCollaborationInvitation | None"] = relationship(
        "ConversationCollaborationInvitation",
        lazy="selectin",
    )
