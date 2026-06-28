"""
Conversation collaboration service.
"""
import logging
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.enums import AgentOnlineStatus, ConversationStatus, MessageContentType, MessageSenderType
from app.libs.realtime import get_realtime_transport
from app.models.message import Message
from app.repositories.conversation_collaboration_repository import (
    COLLABORATOR_ACTIVE,
    INVITATION_ACCEPTED,
    INVITATION_DECLINED,
    INVITATION_EXPIRED,
    INVITATION_PENDING,
    ConversationCollaborationRepository,
)
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.permission import EffectivePrincipal
from app.services.agent_status_service import AgentStatusService
from app.services.data_scope_service import DataScopeService, RESOURCE_SESSION_RECORD

logger = logging.getLogger(__name__)

COLLABORATION_INVITE_PERMISSION = "chat.conversation.collaboration.invite"
COLLABORATION_RESPOND_PERMISSION = "chat.conversation.collaboration.respond"
COLLABORATION_MESSAGE_SEND_PERMISSION = "chat.conversation.collaboration.message.send"
COLLABORATION_INVITATION_TTL_MINUTES = 5
MAX_COLLABORATION_TARGETS = 200
CHAT_NAMESPACE = "/chat"
VISITOR_NAMESPACE = "/visitor"


class ConversationCollaborationService:
    @staticmethod
    def _agent_brief(employee) -> dict | None:
        if employee is None:
            return None
        return {
            "id": employee.id,
            "display_name": employee.display_name,
            "name": employee.name or employee.username,
            "avatar": employee.avatar,
        }

    @staticmethod
    def _resolve_agent_name(employee) -> str:
        if not employee:
            return "未知员工"
        return employee.name or employee.username or "未知员工"

    @staticmethod
    def _resolve_visitor_nickname(employee) -> str:
        if not employee:
            return "客服"
        return employee.nickname or employee.name or employee.username or "客服"

    @staticmethod
    def serialize_collaborators(employees: list) -> list[dict]:
        return [
            brief
            for employee in employees
            if (brief := ConversationCollaborationService._agent_brief(employee)) is not None
        ]

    @staticmethod
    def _serialize_invitation(invitation) -> dict:
        conversation = invitation.conversation
        return {
            "id": invitation.id,
            "conversation_id": invitation.conversation_id,
            "status": invitation.status,
            "inviter": ConversationCollaborationService._agent_brief(invitation.inviter),
            "invitee": ConversationCollaborationService._agent_brief(invitation.invitee),
            "owner": ConversationCollaborationService._agent_brief(conversation.agent if conversation else None),
            "visitor_name": conversation.visitor.name if conversation and conversation.visitor else None,
            "channel_name": conversation.channel.name if conversation and conversation.channel else None,
            "last_message_preview": conversation.last_message_preview if conversation else None,
            "expires_at": invitation.expires_at,
            "responded_at": invitation.responded_at,
            "created_at": invitation.created_at,
        }

    @staticmethod
    async def _assert_can_invite(
        db: AsyncSession,
        principal: EffectivePrincipal,
        conversation,
    ) -> None:
        if not principal.has_permission(COLLABORATION_INVITE_PERMISSION):
            raise ForbiddenError("Permission denied")
        if conversation.status != ConversationStatus.ACTIVE.value:
            raise BusinessError("Conversation is not active")
        if conversation.agent_id == principal.user_id:
            return
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        DataScopeService.assert_conversation_in_scope(
            principal,
            conversation,
            peer_ids,
            RESOURCE_SESSION_RECORD,
        )

    @staticmethod
    async def _load_invitable_conversation(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        principal: EffectivePrincipal,
    ):
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")
        await ConversationCollaborationService._assert_can_invite(db, principal, conversation)
        return conversation

    @staticmethod
    async def _invite_target_allowed_ids(
        db: AsyncSession,
        principal: EffectivePrincipal,
    ) -> set[int] | None:
        scope = DataScopeService.get_scope(principal, RESOURCE_SESSION_RECORD)
        if scope == "all":
            return None
        if scope == "self":
            return {principal.user_id}
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        return set(peer_ids) | {principal.user_id}

    @staticmethod
    async def _assert_invite_target_in_scope(
        db: AsyncSession,
        principal: EffectivePrincipal,
        target_agent_id: int,
    ) -> None:
        allowed_ids = await ConversationCollaborationService._invite_target_allowed_ids(db, principal)
        if allowed_ids is not None and target_agent_id not in allowed_ids:
            raise ForbiddenError("Permission denied")

    @staticmethod
    async def list_targets(
        db: AsyncSession,
        r: aioredis.Redis,
        *,
        tenant_id: int,
        conversation_id: int,
        keyword: str | None,
        principal: EffectivePrincipal,
    ) -> dict:
        conversation = await ConversationCollaborationService._load_invitable_conversation(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            principal=principal,
        )
        now = datetime.now(timezone.utc)
        collaborator_ids = set(
            await ConversationCollaborationRepository.get_active_collaborator_agent_ids(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
            )
        )
        pending_invitee_ids = set(
            await ConversationCollaborationRepository.get_pending_invitee_ids(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                now=now,
            )
        )
        allowed_target_ids = await ConversationCollaborationService._invite_target_allowed_ids(db, principal)
        exclude_ids = {principal.user_id}
        if conversation.agent_id:
            exclude_ids.add(conversation.agent_id)

        employees = await EmployeeRepository.get_transfer_candidates(
            db,
            tenant_id=tenant_id,
            exclude_user_ids=list(exclude_ids),
            keyword=keyword,
            limit=MAX_COLLABORATION_TARGETS,
        )
        if allowed_target_ids is not None:
            employees = [employee for employee in employees if employee.id in allowed_target_ids]

        items: list[dict] = []
        for employee in employees:
            has_respond_permission = await EmployeeRepository.has_effective_permission(
                db,
                tenant_id,
                employee.id,
                COLLABORATION_RESPOND_PERMISSION,
            )
            if not has_respond_permission:
                continue
            status_data = await AgentStatusService.get_status(
                r,
                tenant_id,
                employee.id,
                employee.max_concurrent,
            )
            online_status = status_data["status"]
            disabled_reason = None
            if employee.id in collaborator_ids:
                disabled_reason = "already_joined"
            elif employee.id in pending_invitee_ids:
                disabled_reason = "pending"
            elif online_status == AgentOnlineStatus.OFFLINE.value:
                disabled_reason = "offline"
            items.append({
                "id": employee.id,
                "name": employee.name or employee.username,
                "display_name": employee.display_name,
                "job_number": employee.job_number,
                "avatar": employee.avatar,
                "online_status": online_status,
                "current_count": status_data["current_count"],
                "max_concurrent": status_data["max_concurrent"],
                "available": disabled_reason is None,
                "disabled_reason": disabled_reason,
            })

        priority = {
            AgentOnlineStatus.ONLINE.value: 0,
            AgentOnlineStatus.BUSY.value: 1,
            AgentOnlineStatus.OFFLINE.value: 2,
        }
        items.sort(key=lambda item: (item["disabled_reason"] is not None, priority.get(item["online_status"], 9), item["name"]))
        return {"items": items, "total": len(items)}

    @staticmethod
    async def create_invitation(
        db: AsyncSession,
        r: aioredis.Redis,
        *,
        tenant_id: int,
        conversation_id: int,
        invitee_id: int,
        principal: EffectivePrincipal,
    ) -> dict:
        conversation = await ConversationCollaborationService._load_invitable_conversation(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            principal=principal,
        )
        if invitee_id == principal.user_id or invitee_id == conversation.agent_id:
            raise BusinessError("Target agent is not available")
        if await ConversationCollaborationRepository.is_active_collaborator(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            agent_id=invitee_id,
        ):
            raise BusinessError("Target agent already joined")
        now = datetime.now(timezone.utc)
        existing = await ConversationCollaborationRepository.get_pending_invitation(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            invitee_id=invitee_id,
        )
        if existing and existing.expires_at > now:
            raise BusinessError("Invitation already pending")
        if existing and existing.expires_at <= now:
            existing.status = INVITATION_EXPIRED
            existing.responded_at = now

        target = await EmployeeRepository.get_by_id(db, invitee_id)
        if (
            not target
            or target.tenant_id != tenant_id
            or not target.is_active
            or not await EmployeeRepository.has_effective_permission(db, tenant_id, invitee_id, "chat.workspace.use")
            or not await EmployeeRepository.has_effective_permission(
                db,
                tenant_id,
                invitee_id,
                COLLABORATION_RESPOND_PERMISSION,
            )
        ):
            raise NotFoundError("Target employee not found")
        await ConversationCollaborationService._assert_invite_target_in_scope(db, principal, invitee_id)
        target_status = await AgentStatusService.get_status(r, tenant_id, target.id, target.max_concurrent)
        if target_status["status"] == AgentOnlineStatus.OFFLINE.value:
            raise BusinessError("Target agent is offline")

        invitation = await ConversationCollaborationRepository.create_invitation(
            db,
            {
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "inviter_id": principal.user_id,
                "invitee_id": invitee_id,
                "status": INVITATION_PENDING,
                "expires_at": now + timedelta(minutes=COLLABORATION_INVITATION_TTL_MINUTES),
            },
        )
        await db.commit()
        invitation = await ConversationCollaborationRepository.get_invitation_by_id(db, invitation.id) or invitation
        payload = ConversationCollaborationService._serialize_invitation(invitation)
        await ConversationCollaborationService._emit_invitation_created(tenant_id, invitee_id, principal.user_id, payload)
        return payload

    @staticmethod
    async def list_pending_invitations(
        db: AsyncSession,
        *,
        tenant_id: int,
        principal: EffectivePrincipal,
    ) -> dict:
        if not principal.has_permission(COLLABORATION_RESPOND_PERMISSION):
            raise ForbiddenError("Permission denied")
        now = datetime.now(timezone.utc)
        await ConversationCollaborationRepository.expire_pending_for_invitee(
            db,
            tenant_id=tenant_id,
            invitee_id=principal.user_id,
            now=now,
        )
        await db.commit()
        invitations = await ConversationCollaborationRepository.list_pending_for_invitee(
            db,
            tenant_id=tenant_id,
            invitee_id=principal.user_id,
            now=now,
        )
        items = [ConversationCollaborationService._serialize_invitation(invitation) for invitation in invitations]
        return {"items": items, "total": len(items)}

    @staticmethod
    async def respond_invitation(
        db: AsyncSession,
        *,
        tenant_id: int,
        invitation_id: int,
        action: str,
        principal: EffectivePrincipal,
    ) -> dict:
        if not principal.has_permission(COLLABORATION_RESPOND_PERMISSION):
            raise ForbiddenError("Permission denied")

        invitation = await ConversationCollaborationRepository.get_invitation_by_id(db, invitation_id)
        if not invitation or invitation.tenant_id != tenant_id or invitation.invitee_id != principal.user_id:
            raise NotFoundError("Invitation not found")
        if invitation.status != INVITATION_PENDING:
            payload = ConversationCollaborationService._serialize_invitation(invitation)
            return {"invitation": payload, "conversation": None}

        now = datetime.now(timezone.utc)
        if invitation.expires_at <= now:
            invitation.status = INVITATION_EXPIRED
            invitation.responded_at = now
            await db.commit()
            raise BusinessError("Invitation expired")
        conversation = invitation.conversation
        if not conversation or conversation.status != ConversationStatus.ACTIVE.value:
            invitation.status = INVITATION_EXPIRED
            invitation.responded_at = now
            await db.commit()
            raise BusinessError("Conversation is not active")

        if action == "decline":
            invitation.status = INVITATION_DECLINED
            invitation.responded_at = now
            await db.commit()
            invitation = await ConversationCollaborationRepository.get_invitation_by_id(db, invitation_id) or invitation
            payload = ConversationCollaborationService._serialize_invitation(invitation)
            await ConversationCollaborationService._emit_invitation_updated(tenant_id, invitation, payload)
            return {"invitation": payload, "conversation": None}

        existing = await ConversationCollaborationRepository.get_active_collaborator(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            agent_id=principal.user_id,
        )
        if existing is None:
            await ConversationCollaborationRepository.create_collaborator(
                db,
                {
                    "tenant_id": tenant_id,
                    "conversation_id": conversation.id,
                    "agent_id": principal.user_id,
                    "invitation_id": invitation.id,
                    "status": COLLABORATOR_ACTIVE,
                    "joined_at": now,
                },
            )
        invitation.status = INVITATION_ACCEPTED
        invitation.responded_at = now

        invitee = invitation.invitee or await EmployeeRepository.get_by_id(db, principal.user_id)
        invitee_name = ConversationCollaborationService._resolve_agent_name(invitee)
        invitee_nickname = ConversationCollaborationService._resolve_visitor_nickname(invitee)
        system_text = f"{invitee_name} 已加入会话"
        system_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            sender_type=MessageSenderType.SYSTEM.value,
            sender_id=None,
            content_type=MessageContentType.SYSTEM.value,
            content=system_text,
            metadata_={
                "event_type": "collaborator_joined",
                "collaborator_id": principal.user_id,
                "collaborator_name": invitee_name,
                "collaborator_nickname": invitee_nickname,
                "visible_to": ["agent", "visitor"],
            },
        )
        db.add(system_message)
        conversation.last_message_at = now
        conversation.last_message_preview = system_text[:200]
        await db.flush()
        await db.commit()

        invitation = await ConversationCollaborationRepository.get_invitation_by_id(db, invitation_id) or invitation
        payload = ConversationCollaborationService._serialize_invitation(invitation)

        from app.services.conversation_service import ConversationService

        conversation_payload = await ConversationService.get_agent_conversation(
            db,
            conversation_id=conversation.id,
            tenant_id=tenant_id,
            agent_id=principal.user_id,
            principal=principal,
        )
        message_payload = {
            "id": system_message.id,
            "conversation_id": conversation.id,
            "conversation_public_id": conversation.public_id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "sender_id": None,
            "sender_name": None,
            "sender_avatar": None,
            "content_type": MessageContentType.SYSTEM.value,
            "content": system_text,
            "created_at": now.isoformat(),
            "metadata": system_message.metadata_,
            "event_type": system_message.metadata_["event_type"],
        }
        await ConversationCollaborationService._emit_invitation_accepted(
            tenant_id,
            invitation,
            payload,
            conversation_payload,
            message_payload,
        )
        return {"invitation": payload, "conversation": conversation_payload}

    @staticmethod
    async def _emit_invitation_created(
        tenant_id: int,
        invitee_id: int,
        inviter_id: int,
        invitation_payload: dict,
    ) -> None:
        try:
            rt = get_realtime_transport()
        except RuntimeError:
            logger.debug("Realtime transport is not initialized; collaboration invite event skipped")
            return
        payload = jsonable_encoder(invitation_payload)
        await rt.emit(
            "collaboration_invitation_received",
            payload,
            room=f"agent:{tenant_id}:{invitee_id}",
            namespace=CHAT_NAMESPACE,
        )
        await rt.emit(
            "collaboration_invitation_updated",
            payload,
            room=f"agent:{tenant_id}:{inviter_id}",
            namespace=CHAT_NAMESPACE,
        )

    @staticmethod
    async def _emit_invitation_updated(tenant_id: int, invitation, invitation_payload: dict) -> None:
        try:
            rt = get_realtime_transport()
        except RuntimeError:
            logger.debug("Realtime transport is not initialized; collaboration update event skipped")
            return
        payload = jsonable_encoder(invitation_payload)
        for agent_id in {invitation.inviter_id, invitation.invitee_id}:
            if agent_id:
                await rt.emit(
                    "collaboration_invitation_updated",
                    payload,
                    room=f"agent:{tenant_id}:{agent_id}",
                    namespace=CHAT_NAMESPACE,
                )

    @staticmethod
    async def _emit_invitation_accepted(
        tenant_id: int,
        invitation,
        invitation_payload: dict,
        conversation_payload: dict,
        message_payload: dict,
    ) -> None:
        try:
            rt = get_realtime_transport()
        except RuntimeError:
            logger.debug("Realtime transport is not initialized; collaboration accepted event skipped")
            return
        await ConversationCollaborationService._emit_invitation_updated(tenant_id, invitation, invitation_payload)
        conv_room = f"conv:{invitation.conversation_id}"
        encoded_message = jsonable_encoder(message_payload)
        encoded_conversation = jsonable_encoder(conversation_payload)
        updated_payload = {
            "conversation_id": invitation.conversation_id,
            "last_message_preview": message_payload["content"],
            "last_message_at": message_payload["created_at"],
        }
        member_payload = {
            "conversation_id": invitation.conversation_id,
        }
        await rt.emit(
            "collaboration_conversation_added",
            encoded_conversation,
            room=f"agent:{tenant_id}:{invitation.invitee_id}",
            namespace=CHAT_NAMESPACE,
        )
        await rt.emit("new_message", encoded_message, room=conv_room, namespace=CHAT_NAMESPACE)
        await rt.emit("conversation_updated", updated_payload, room=conv_room, namespace=CHAT_NAMESPACE)
        conversation = getattr(invitation, "conversation", None)
        recipient_agent_ids = {
            agent_id
            for agent_id in {
                invitation.inviter_id,
                invitation.invitee_id,
                getattr(conversation, "agent_id", None),
            }
            if agent_id
        }
        for agent_id in recipient_agent_ids:
            agent_room = f"agent:{tenant_id}:{agent_id}"
            await rt.emit("new_message", encoded_message, room=agent_room, namespace=CHAT_NAMESPACE)
            await rt.emit("conversation_updated", updated_payload, room=agent_room, namespace=CHAT_NAMESPACE)
            await rt.emit("collaboration_members_updated", member_payload, room=agent_room, namespace=CHAT_NAMESPACE)
        visitor_message = dict(encoded_message)
        visitor_message.pop("conversation_id", None)
        await rt.emit("new_message", visitor_message, room=conv_room, namespace=VISITOR_NAMESPACE)
        await rt.emit("collaboration_members_updated", member_payload, room=conv_room, namespace=CHAT_NAMESPACE)
