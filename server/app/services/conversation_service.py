"""
Conversation service — orchestrates conversation lifecycle.

Handles creation (with routing), assignment, message sending, and ending.
"""
import json
import logging
import random
import re
from html import unescape
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError as PydanticValidationError
import redis.asyncio as aioredis

from app.core.exceptions import NotFoundError, BusinessError, ValidationError, ForbiddenError
from app.enums import ConversationStatus, MessageSenderType, MessageContentType
from app.repositories.channel_repository import ChannelRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message import FileMessageContent
from app.repositories.user_repository import UserRepository
from app.services.agent_status_service import AgentStatusService
from app.services.routing_service import RoutingService
from app.services.welcome_message_rule_service import WelcomeMessageRuleService

logger = logging.getLogger(__name__)

_AVATAR_COLORS = [
    "#F87171", "#FB923C", "#FBBF24", "#34D399",
    "#60A5FA", "#818CF8", "#A78BFA", "#F472B6",
]

ALLOWED_MESSAGE_CONTENT_TYPES = {
    MessageContentType.TEXT.value,
    MessageContentType.IMAGE.value,
    MessageContentType.FILE.value,
    MessageContentType.SYSTEM.value,
}
MAX_TEXT_MESSAGE_LENGTH = 5000
VISITOR_HISTORY_PAGE_SIZE = 10
VISITOR_HISTORY_MESSAGE_LIMIT = 200
VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT = 1000


class ConversationService:
    @staticmethod
    def _html_to_plain_text(content: str) -> str:
        text = re.sub(r"<[^>]*>", " ", content)
        text = unescape(text).replace("\xa0", " ")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _public_message_item(msg, conversation_public_id: str) -> dict:
        return {
            "id": msg.id,
            "conversation_public_id": conversation_public_id,
            "sender_type": msg.sender_type,
            "sender_id": msg.sender_id,
            "sender_name": None,
            "sender_avatar": None,
            "content_type": msg.content_type,
            "content": msg.content,
            "created_at": msg.created_at,
            **ConversationService._message_event_overlay(msg),
        }

    @staticmethod
    def _message_event_overlay(msg) -> dict:
        metadata = getattr(msg, "metadata_", None) or {}
        return {
            "metadata": metadata,
            "event_type": metadata.get("event_type"),
            "satisfaction_record_id": metadata.get("satisfaction_record_id"),
            "config_version": metadata.get("config_version"),
        }

    @staticmethod
    def validate_message_content(content_type: str, content: str) -> str:
        """Validate and normalize message content before persistence."""
        if content_type not in ALLOWED_MESSAGE_CONTENT_TYPES:
            raise ValidationError("Unsupported message type")

        if not content:
            raise ValidationError("Message content is required")

        if content_type in {MessageContentType.TEXT.value, MessageContentType.SYSTEM.value}:
            if len(content) > MAX_TEXT_MESSAGE_LENGTH:
                raise ValidationError("Message content exceeds 5000 characters")
            return content

        try:
            payload = json.loads(content)
            parsed = FileMessageContent.model_validate(payload)
        except (json.JSONDecodeError, PydanticValidationError):
            raise ValidationError("Invalid file message content")

        if content_type == MessageContentType.IMAGE.value and not parsed.mime_type.startswith("image/"):
            raise ValidationError("Image message requires an image MIME type")

        return parsed.model_dump_json(exclude_none=True)

    @staticmethod
    def build_message_preview(content_type: str, content: str) -> str:
        """Build a concise conversation preview for text and structured file messages."""
        if content_type in {MessageContentType.TEXT.value, MessageContentType.SYSTEM.value}:
            return content[:200]

        if content_type == MessageContentType.SATISFACTION_EVENT.value:
            return content[:200]

        if content_type == MessageContentType.WELCOME.value:
            return ConversationService._html_to_plain_text(content)[:200]

        if content_type in {MessageContentType.IMAGE.value, MessageContentType.FILE.value}:
            try:
                payload = FileMessageContent.model_validate(json.loads(content))
            except (json.JSONDecodeError, PydanticValidationError):
                return f"[{content_type}]"
            if content_type == MessageContentType.IMAGE.value:
                return "[图片]"
            return f"[附件] {payload.name}"[:200]

        return f"[{content_type}]"

    @staticmethod
    async def _create_matched_welcome_message(
        db: AsyncSession,
        conversation,
    ):
        channel = conversation.channel
        if not channel and conversation.channel_id:
            channel = await ChannelRepository.get_by_id(db, conversation.channel_id)
        if not channel:
            return None

        welcome_message = await WelcomeMessageRuleService.match_public_welcome_message(db, channel)
        if not welcome_message:
            return None

        return await MessageRepository.create(db, {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.WELCOME.value,
            "content": welcome_message["content"],
        })

    @staticmethod
    async def create_from_visitor(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
        visitor_name: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create or resume a conversation for an end user.

        Steps:
        1. Get or create user
        2. Check if user already has an active conversation
        3. Route to agent group via session routing rules
        4. Find available agent in group (round-robin)
        5. Create conversation record
        6. Create system message
        """
        auto_name = visitor_name or f"访客 {visitor_external_id[:6]}"
        user, _ = await UserRepository.get_or_create(
            db,
            tenant_id,
            visitor_external_id,
            defaults={
                "name": auto_name,
                "avatar_color": random.choice(_AVATAR_COLORS),
                "channel_id": channel_id,
                "metadata_": metadata or {},
            },
        )
        update_data = {}
        if visitor_name and user.name != visitor_name:
            update_data["name"] = visitor_name
        if metadata:
            update_data["metadata_"] = {**(user.metadata_ or {}), **metadata}
        if update_data:
            user = await UserRepository.update(db, user, update_data)

        existing = await ConversationRepository.get_active_visitor_conversation(
            db,
            tenant_id=tenant_id,
            visitor_id=user.id,
            channel_id=channel_id,
        )
        if existing:
            newly_assigned = False
            if existing.status == ConversationStatus.QUEUED.value and not existing.agent_id:
                group_id, group_member_ids, max_concurrent_map = await RoutingService.route_conversation(
                    db, tenant_id, channel_id
                )
                if group_member_ids:
                    agent_id = await AgentStatusService.find_available_agent(
                        r, tenant_id, group_member_ids, max_concurrent_map
                    )
                    if agent_id:
                        existing = await ConversationRepository.assign_agent(
                            db, existing, agent_id, group_id
                        )
                        await AgentStatusService.increment_count(r, tenant_id, agent_id)
                        newly_assigned = True
                        logger.info("Queued conv %d assigned to agent %d", existing.id, agent_id)
            return {"conversation": existing, "is_new": False, "newly_assigned": newly_assigned}

        from app.services.channel_service import ChannelService
        availability = await ChannelService.check_channel_availability(
            db,
            r,
            channel_id,
        )
        if not availability["can_start_conversation"]:
            return {
                "conversation": None,
                "is_new": False,
                "offline": True,
                "availability": availability,
            }

        group_id, group_member_ids, max_concurrent_map = await RoutingService.route_conversation(
            db, tenant_id, channel_id
        )

        agent_id = None
        if group_member_ids:
            agent_id = await AgentStatusService.find_available_agent(
                r, tenant_id, group_member_ids, max_concurrent_map
            )

        now = datetime.now(timezone.utc)
        conv_data = {
            "public_id": await ConversationRepository.generate_unique_public_id(db),
            "share_code": await ConversationRepository.generate_unique_share_code(db),
            "tenant_id": tenant_id,
            "visitor_id": user.id,
            "channel_id": channel_id,
            "group_id": group_id,
            "agent_id": agent_id,
            "status": ConversationStatus.ACTIVE.value if agent_id else ConversationStatus.QUEUED.value,
            "started_at": now if agent_id else None,
        }
        conversation = await ConversationRepository.create(db, conv_data)

        if agent_id:
            await AgentStatusService.increment_count(r, tenant_id, agent_id)

        sys_content = "用户发起了新会话" if agent_id else "等待客服接入..."
        preview_message = await MessageRepository.create(db, {
            "tenant_id": tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.SYSTEM.value,
            "content": sys_content,
        })
        welcome_msg = await ConversationService._create_matched_welcome_message(db, conversation)
        if welcome_msg:
            preview_message = welcome_msg
        preview = ConversationService.build_message_preview(
            preview_message.content_type,
            preview_message.content,
        )
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            preview,
            preview_message.created_at or now,
        )

        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        return {"conversation": conversation, "is_new": True}

    @staticmethod
    async def get_agent_conversations(
        db: AsyncSession, tenant_id: int, agent_id: int, roles: list[str] | None = None
    ) -> list:
        conversations = await ConversationRepository.get_active_by_agent(db, tenant_id, agent_id)
        can_view_all_history = "admin" in (roles or ["agent"])
        history_agent_id = None if can_view_all_history else agent_id

        items = []
        for conversation in conversations:
            has_history = False
            if conversation.visitor_id:
                history = await ConversationRepository.get_visitor_history(
                    db,
                    tenant_id=tenant_id,
                    channel_id=None,
                    visitor_id=conversation.visitor_id,
                    current_conversation_id=conversation.id,
                    agent_id=history_agent_id,
                    limit=1,
                )
                has_history = bool(history)

            items.append({
                "id": conversation.id,
                "public_id": conversation.public_id,
                "share_code": conversation.share_code,
                "tenant_id": conversation.tenant_id,
                "visitor": conversation.visitor,
                "agent": conversation.agent,
                "channel": conversation.channel,
                "group": conversation.group,
                "status": conversation.status,
                "started_at": conversation.started_at,
                "ended_at": conversation.ended_at,
                "ended_by": conversation.ended_by,
                "last_message_at": conversation.last_message_at,
                "last_message_preview": conversation.last_message_preview,
                "unread_count": conversation.unread_count,
                "has_history_conversations": has_history,
                "created_at": conversation.created_at,
            })
        return items

    @staticmethod
    async def get_agent_conversation(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        roles: list[str] | None = None,
    ) -> dict:
        """Get a workspace conversation with the history availability marker."""
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        can_view_all_history = "admin" in (roles or ["agent"])
        if not can_view_all_history and conversation.agent_id != agent_id:
            raise ForbiddenError("No permission to view conversation")

        has_history = False
        if conversation.visitor_id:
            history = await ConversationRepository.get_visitor_history(
                db,
                tenant_id=tenant_id,
                channel_id=None,
                visitor_id=conversation.visitor_id,
                current_conversation_id=conversation.id,
                agent_id=None if can_view_all_history else agent_id,
                limit=1,
            )
            has_history = bool(history)

        return {
            "id": conversation.id,
            "public_id": conversation.public_id,
            "share_code": conversation.share_code,
            "tenant_id": conversation.tenant_id,
            "visitor": conversation.visitor,
            "agent": conversation.agent,
            "channel": conversation.channel,
            "group": conversation.group,
            "status": conversation.status,
            "started_at": conversation.started_at,
            "ended_at": conversation.ended_at,
            "ended_by": conversation.ended_by,
            "last_message_at": conversation.last_message_at,
            "last_message_preview": conversation.last_message_preview,
            "unread_count": conversation.unread_count,
            "has_history_conversations": has_history,
            "created_at": conversation.created_at,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, conversation_id: int):
        conv = await ConversationRepository.get_by_id(db, conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found")
        return conv

    @staticmethod
    async def end_conversation(
        db: AsyncSession,
        r: aioredis.Redis,
        conversation_id: int,
        ended_by: str = "agent",
    ):
        conv = await ConversationRepository.get_by_id(db, conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found")
        if conv.status == ConversationStatus.CLOSED.value:
            raise BusinessError("Conversation already closed")

        conv = await ConversationRepository.end_conversation(db, conv, ended_by)

        if conv.agent_id:
            await AgentStatusService.decrement_count(r, conv.tenant_id, conv.agent_id)

        now = datetime.now(timezone.utc)
        end_text = "客服已结束会话" if ended_by == "agent" else "用户已结束会话"
        await MessageRepository.create(db, {
            "tenant_id": conv.tenant_id,
            "conversation_id": conv.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.SYSTEM.value,
            "content": end_text,
        })
        await ConversationRepository.update_last_message(db, conv.id, end_text, now)

        try:
            from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService

            await SatisfactionSurveyRecordService.send_session_end_invitation(db, conv)
        except Exception:
            logger.exception("Failed to send session-end satisfaction invitation for conversation %s", conv.id)

        return conv

    @staticmethod
    async def send_message(
        db: AsyncSession,
        conversation_id: int,
        sender_type: str,
        sender_id: int | None,
        content_type: str,
        content: str,
        tenant_id: int,
    ):
        conv = await ConversationRepository.get_by_id(db, conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found")
        if conv.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")
        if conv.status == ConversationStatus.CLOSED.value:
            raise BusinessError("Cannot send message to closed conversation")

        normalized_content = ConversationService.validate_message_content(content_type, content)
        now = datetime.now(timezone.utc)
        msg = await MessageRepository.create(db, {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "sender_type": sender_type,
            "sender_id": sender_id,
            "content_type": content_type,
            "content": normalized_content,
        })

        preview = ConversationService.build_message_preview(content_type, normalized_content)
        increment_unread = sender_type == MessageSenderType.VISITOR.value
        await ConversationRepository.update_last_message(
            db, conversation_id, preview, now, increment_unread=increment_unread
        )
        return msg

    @staticmethod
    async def get_conversation_for_visitor_session(
        db: AsyncSession,
        conversation_public_id: str,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
    ):
        """Load a public conversation and verify it belongs to the visitor session."""
        conversation = await ConversationRepository.get_by_public_id(db, conversation_public_id)
        if not conversation:
            raise NotFoundError("Conversation not found")
        if conversation.tenant_id != tenant_id or conversation.channel_id != channel_id:
            raise NotFoundError("Conversation not found")
        if not conversation.visitor or conversation.visitor.external_id != visitor_external_id:
            raise NotFoundError("Conversation not found")
        return conversation

    @staticmethod
    async def get_public_messages_for_session(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
        before_id: int | None = None,
        limit: int = 20,
    ) -> dict:
        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        result = await ConversationService.get_messages(
            db,
            conversation.id,
            before_id=before_id,
            limit=limit,
        )
        for item in result["items"]:
            item["conversation_public_id"] = conversation.public_id
            item.pop("conversation_id", None)
        return result

    @staticmethod
    async def send_visitor_message_for_session(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
        content_type: str,
        content: str,
    ) -> tuple[dict, int | None, object | None]:
        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        visitor = await UserRepository.get_by_external_id(
            db,
            visitor_context["tenant_id"],
            visitor_context["visitor_external_id"],
        )
        visitor_id = visitor.id if visitor else None
        msg = await ConversationService.send_message(
            db,
            conversation_id=conversation.id,
            sender_type=MessageSenderType.VISITOR.value,
            sender_id=visitor_id,
            content_type=content_type,
            content=content,
            tenant_id=visitor_context["tenant_id"],
        )
        msg_payload = {
            "id": msg.id,
            "conversation_public_id": conversation.public_id,
            "sender_type": msg.sender_type,
            "sender_id": msg.sender_id,
            "sender_name": visitor.name if visitor else None,
            "sender_avatar": None,
            "content_type": msg.content_type,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            **ConversationService._message_event_overlay(msg),
        }
        return msg_payload, conversation.agent_id, conversation

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        conversation_id: int,
        before_id: int | None = None,
        limit: int = 20,
    ) -> dict:
        messages = await MessageRepository.get_by_conversation(
            db, conversation_id, before_id=before_id, limit=limit + 1
        )
        has_more = len(messages) > limit
        if has_more:
            messages = messages[1:]

        agent_ids = list({
            msg.sender_id
            for msg in messages
            if msg.sender_type == MessageSenderType.AGENT.value and msg.sender_id is not None
        })
        agents = await EmployeeRepository.get_by_ids(db, agent_ids)
        agent_map = {agent.id: agent for agent in agents}

        items = []
        for msg in messages:
            sender_name = None
            sender_avatar = None
            if msg.sender_type == MessageSenderType.AGENT.value and msg.sender_id is not None:
                agent = agent_map.get(msg.sender_id)
                if agent:
                    sender_name = agent.display_name or agent.name
                    sender_avatar = agent.avatar

            items.append({
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "sender_type": msg.sender_type,
                "sender_id": msg.sender_id,
                "sender_name": sender_name,
                "sender_avatar": sender_avatar,
                "content_type": msg.content_type,
                "content": msg.content,
                "created_at": msg.created_at,
                **ConversationService._message_event_overlay(msg),
            })

        return {"items": items, "has_more": has_more}

    @staticmethod
    async def has_visitor_history(
        db: AsyncSession,
        channel_id: int,
        visitor_external_id: str | None,
        current_conversation_id: int | None = None,
        current_conversation_public_id: str | None = None,
    ) -> bool:
        """Return whether the visitor has any non-current conversation in this channel."""
        if not visitor_external_id:
            return False

        channel = await ChannelRepository.get_by_id(db, channel_id)
        if not channel:
            return False

        visitor = await UserRepository.get_by_external_id(
            db,
            channel.tenant_id,
            visitor_external_id,
        )
        if not visitor:
            return False

        internal_current_id = current_conversation_id
        if current_conversation_public_id:
            current = await ConversationRepository.get_by_public_id(db, current_conversation_public_id)
            internal_current_id = current.id if current else None

        conversations = await ConversationRepository.get_visitor_history(
            db,
            tenant_id=channel.tenant_id,
            channel_id=channel_id,
            visitor_id=visitor.id,
            current_conversation_id=internal_current_id,
            limit=1,
        )
        return bool(conversations)

    @staticmethod
    async def get_visitor_history(
        db: AsyncSession,
        channel_id: int,
        visitor_external_id: str,
        current_conversation_id: int | None = None,
        before_id: int | None = None,
        limit: int = VISITOR_HISTORY_PAGE_SIZE,
    ) -> dict:
        """Fetch visitor conversation history for a web channel."""
        channel = await ChannelRepository.get_by_id(db, channel_id)
        if not channel:
            raise NotFoundError("Channel not found")

        visitor = await UserRepository.get_by_external_id(
            db,
            channel.tenant_id,
            visitor_external_id,
        )
        if not visitor:
            return {"items": [], "has_more": False}

        safe_limit = min(max(limit, 1), VISITOR_HISTORY_PAGE_SIZE)
        conversations = await ConversationRepository.get_visitor_history(
            db,
            tenant_id=channel.tenant_id,
            channel_id=channel_id,
            visitor_id=visitor.id,
            current_conversation_id=current_conversation_id,
            before_id=before_id,
            limit=safe_limit + 1,
        )
        has_more = len(conversations) > safe_limit
        if has_more:
            conversations = conversations[:safe_limit]

        conversation_ids = [conversation.id for conversation in conversations]
        messages_by_conversation = await MessageRepository.get_recent_by_conversations(
            db,
            tenant_id=channel.tenant_id,
            conversation_ids=conversation_ids,
            per_conversation_limit=VISITOR_HISTORY_MESSAGE_LIMIT,
        )

        total_messages = 0
        agent_ids: set[int] = set()
        for messages in messages_by_conversation.values():
            for message in messages:
                if total_messages >= VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT:
                    break
                total_messages += 1
                if (
                    message.sender_type == MessageSenderType.AGENT.value
                    and message.sender_id is not None
                ):
                    agent_ids.add(message.sender_id)

        agents = await EmployeeRepository.get_by_ids(db, list(agent_ids))
        agent_map = {agent.id: agent for agent in agents}

        items = []
        consumed_messages = 0
        for conversation in conversations:
            raw_messages = messages_by_conversation.get(conversation.id, [])
            remaining = max(VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT - consumed_messages, 0)
            messages = raw_messages[:remaining]
            consumed_messages += len(messages)

            message_items = []
            for msg in messages:
                sender_name = None
                sender_avatar = None
                if (
                    msg.sender_type == MessageSenderType.AGENT.value
                    and msg.sender_id is not None
                ):
                    agent = agent_map.get(msg.sender_id)
                    if agent:
                        sender_name = agent.display_name or agent.name
                        sender_avatar = agent.avatar
                elif msg.sender_type == MessageSenderType.VISITOR.value:
                    sender_name = visitor.name

                message_items.append({
                    "id": msg.id,
                    "conversation_id": msg.conversation_id,
                    "sender_type": msg.sender_type,
                    "sender_id": msg.sender_id,
                    "sender_name": sender_name,
                    "sender_avatar": sender_avatar,
                    "content_type": msg.content_type,
                    "content": msg.content,
                    "created_at": msg.created_at,
                    **ConversationService._message_event_overlay(msg),
                })

            agent_name = None
            agent_avatar = None
            if conversation.agent:
                agent_name = conversation.agent.display_name or conversation.agent.name
                agent_avatar = conversation.agent.avatar

            items.append({
                "id": conversation.id,
                "status": conversation.status,
                "started_at": conversation.started_at,
                "ended_at": conversation.ended_at,
                "last_message_at": conversation.last_message_at,
                "created_at": conversation.created_at,
                "agent_name": agent_name,
                "agent_avatar": agent_avatar,
                "messages": message_items,
                "messages_truncated": (
                    len(raw_messages) >= VISITOR_HISTORY_MESSAGE_LIMIT
                    or len(raw_messages) > len(messages)
                ),
            })

        return {"items": items, "has_more": has_more}

    @staticmethod
    async def get_visitor_history_for_session(
        db: AsyncSession,
        visitor_context: dict,
        current_conversation_public_id: str | None = None,
        before_public_id: str | None = None,
        limit: int = VISITOR_HISTORY_PAGE_SIZE,
    ) -> dict:
        """Fetch visitor history for the token-bound channel and visitor."""
        visitor = await UserRepository.get_by_external_id(
            db,
            visitor_context["tenant_id"],
            visitor_context["visitor_external_id"],
        )
        if not visitor:
            return {"items": [], "has_more": False}

        current_conversation_id = None
        if current_conversation_public_id:
            current = await ConversationRepository.get_by_public_id(db, current_conversation_public_id)
            if current and current.tenant_id == visitor_context["tenant_id"]:
                current_conversation_id = current.id

        before_id = None
        if before_public_id:
            before = await ConversationRepository.get_by_public_id(db, before_public_id)
            if before and before.tenant_id == visitor_context["tenant_id"]:
                before_id = before.id

        safe_limit = min(max(limit, 1), VISITOR_HISTORY_PAGE_SIZE)
        conversations = await ConversationRepository.get_visitor_history(
            db,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_id=visitor.id,
            current_conversation_id=current_conversation_id,
            before_id=before_id,
            limit=safe_limit + 1,
        )
        has_more = len(conversations) > safe_limit
        if has_more:
            conversations = conversations[:safe_limit]

        conversation_ids = [conversation.id for conversation in conversations]
        messages_by_conversation = await MessageRepository.get_recent_by_conversations(
            db,
            tenant_id=visitor_context["tenant_id"],
            conversation_ids=conversation_ids,
            per_conversation_limit=VISITOR_HISTORY_MESSAGE_LIMIT,
        )

        agent_ids: set[int] = set()
        for messages in messages_by_conversation.values():
            for message in messages:
                if (
                    message.sender_type == MessageSenderType.AGENT.value
                    and message.sender_id is not None
                ):
                    agent_ids.add(message.sender_id)

        agents = await EmployeeRepository.get_by_ids(db, list(agent_ids))
        agent_map = {agent.id: agent for agent in agents}

        items = []
        consumed_messages = 0
        for conversation in conversations:
            raw_messages = messages_by_conversation.get(conversation.id, [])
            remaining = max(VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT - consumed_messages, 0)
            messages = raw_messages[:remaining]
            consumed_messages += len(messages)

            message_items = []
            for msg in messages:
                sender_name = None
                sender_avatar = None
                if (
                    msg.sender_type == MessageSenderType.AGENT.value
                    and msg.sender_id is not None
                ):
                    agent = agent_map.get(msg.sender_id)
                    if agent:
                        sender_name = agent.display_name or agent.name
                        sender_avatar = agent.avatar
                elif msg.sender_type == MessageSenderType.VISITOR.value:
                    sender_name = visitor.name

                message_items.append({
                    "id": msg.id,
                    "conversation_public_id": conversation.public_id,
                    "sender_type": msg.sender_type,
                    "sender_id": msg.sender_id,
                    "sender_name": sender_name,
                    "sender_avatar": sender_avatar,
                    "content_type": msg.content_type,
                    "content": msg.content,
                    "created_at": msg.created_at,
                    **ConversationService._message_event_overlay(msg),
                })

            agent_name = None
            agent_avatar = None
            if conversation.agent:
                agent_name = conversation.agent.display_name or conversation.agent.name
                agent_avatar = conversation.agent.avatar

            items.append({
                "conversation_public_id": conversation.public_id,
                "status": conversation.status,
                "started_at": conversation.started_at,
                "ended_at": conversation.ended_at,
                "last_message_at": conversation.last_message_at,
                "created_at": conversation.created_at,
                "agent_name": agent_name,
                "agent_avatar": agent_avatar,
                "messages": message_items,
                "messages_truncated": (
                    len(raw_messages) >= VISITOR_HISTORY_MESSAGE_LIMIT
                    or len(raw_messages) > len(messages)
                ),
            })

        return {"items": items, "has_more": has_more}

    @staticmethod
    async def get_workspace_visitor_history(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        roles: list[str] | None = None,
        before_id: int | None = None,
        limit: int = VISITOR_HISTORY_PAGE_SIZE,
    ) -> dict:
        """Fetch read-only visitor history for the agent workspace."""
        current = await ConversationRepository.get_by_id(db, conversation_id)
        if not current or current.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        can_view_all_history = "admin" in (roles or ["agent"])
        if not can_view_all_history and current.agent_id != agent_id:
            raise ForbiddenError("No permission to view conversation history")

        if not current.visitor:
            return {"items": [], "has_more": False}

        safe_limit = min(max(limit, 1), VISITOR_HISTORY_PAGE_SIZE)
        conversations = await ConversationRepository.get_visitor_history(
            db,
            tenant_id=tenant_id,
            channel_id=None,
            visitor_id=current.visitor.id,
            current_conversation_id=current.id,
            before_id=before_id,
            agent_id=None if can_view_all_history else agent_id,
            limit=safe_limit + 1,
        )
        has_more = len(conversations) > safe_limit
        if has_more:
            conversations = conversations[:safe_limit]

        conversation_ids = [conversation.id for conversation in conversations]
        messages_by_conversation = await MessageRepository.get_recent_by_conversations(
            db,
            tenant_id=tenant_id,
            conversation_ids=conversation_ids,
            per_conversation_limit=VISITOR_HISTORY_MESSAGE_LIMIT,
        )

        agent_ids: set[int] = set()
        for messages in messages_by_conversation.values():
            for message in messages:
                if (
                    message.sender_type == MessageSenderType.AGENT.value
                    and message.sender_id is not None
                ):
                    agent_ids.add(message.sender_id)

        agents = await EmployeeRepository.get_by_ids(db, list(agent_ids))
        agent_map = {agent.id: agent for agent in agents}

        items = []
        consumed_messages = 0
        for conversation in conversations:
            raw_messages = messages_by_conversation.get(conversation.id, [])
            remaining = max(VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT - consumed_messages, 0)
            messages = raw_messages[:remaining]
            consumed_messages += len(messages)

            message_items = []
            for msg in messages:
                sender_name = None
                sender_avatar = None
                if (
                    msg.sender_type == MessageSenderType.AGENT.value
                    and msg.sender_id is not None
                ):
                    agent = agent_map.get(msg.sender_id)
                    if agent:
                        sender_name = agent.display_name or agent.name
                        sender_avatar = agent.avatar
                elif msg.sender_type == MessageSenderType.VISITOR.value:
                    sender_name = current.visitor.name

                message_items.append({
                    "id": msg.id,
                    "conversation_id": msg.conversation_id,
                    "sender_type": msg.sender_type,
                    "sender_id": msg.sender_id,
                    "sender_name": sender_name,
                    "sender_avatar": sender_avatar,
                    "content_type": msg.content_type,
                    "content": msg.content,
                    "created_at": msg.created_at,
                    **ConversationService._message_event_overlay(msg),
                })

            channel = None
            if conversation.channel:
                channel = {
                    "id": conversation.channel.id,
                    "name": conversation.channel.name,
                    "channel_type": conversation.channel.channel_type,
                }

            agent = None
            if conversation.agent:
                agent = {
                    "id": conversation.agent.id,
                    "display_name": conversation.agent.display_name,
                    "name": conversation.agent.name,
                    "avatar": conversation.agent.avatar,
                }

            items.append({
                "id": conversation.id,
                "status": conversation.status,
                "started_at": conversation.started_at,
                "ended_at": conversation.ended_at,
                "last_message_at": conversation.last_message_at,
                "created_at": conversation.created_at,
                "channel": channel,
                "agent": agent,
                "messages": message_items,
                "messages_truncated": (
                    len(raw_messages) >= VISITOR_HISTORY_MESSAGE_LIMIT
                    or len(raw_messages) > len(messages)
                ),
            })

        return {"items": items, "has_more": has_more}

    @staticmethod
    async def mark_read(db: AsyncSession, conversation_id: int) -> None:
        await ConversationRepository.reset_unread(db, conversation_id)
