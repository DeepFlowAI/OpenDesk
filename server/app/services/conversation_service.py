"""
Conversation service — orchestrates conversation lifecycle.

Handles creation (with routing), assignment, message sending, and ending.
"""
import json
import logging
import random
import re
from html import unescape
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError as PydanticValidationError
import redis.asyncio as aioredis

from app.core.exceptions import NotFoundError, BusinessError, ValidationError, ForbiddenError, UnauthorizedError
from app.enums import ConversationStatus, MessageSenderType, MessageContentType
from app.repositories.channel_repository import ChannelRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.offline_message_repository import OfflineMessageRepository
from app.schemas.channel import ChannelConfig
from app.schemas.open_agent_settings import OpenAgentWelcomeMessage
from app.schemas.message import FileMessageContent
from app.schemas.permission import EffectivePrincipal
from app.repositories.user_repository import UserRepository
from app.services.agent_status_service import AgentStatusService
from app.services.data_scope_service import DataScopeService, RESOURCE_PEER_CONVERSATION
from app.services.routing_service import RoutingService
from app.services.welcome_message_rule_service import WelcomeMessageRuleService

logger = logging.getLogger(__name__)

_AVATAR_COLORS = [
    "#F87171", "#FB923C", "#FBBF24", "#34D399",
    "#60A5FA", "#818CF8", "#A78BFA", "#F472B6",
]

ALLOWED_MESSAGE_CONTENT_TYPES = {
    MessageContentType.TEXT.value,
    MessageContentType.RICH_TEXT.value,
    MessageContentType.IMAGE.value,
    MessageContentType.FILE.value,
    MessageContentType.SYSTEM.value,
    MessageContentType.INTERNAL_NOTE.value,
}
MAX_TEXT_MESSAGE_LENGTH = 5000
VISITOR_HISTORY_PAGE_SIZE = 10
VISITOR_HISTORY_MESSAGE_LIMIT = 200
VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT = 1000
VISITOR_UNREAD_OFFLINE_REPLY_LIMIT = 3
WORKSPACE_MY_HISTORY_HOURS = 24
WORKSPACE_MY_HISTORY_PAGE_SIZE = 20
PEER_VIEW_PERMISSION = "chat.conversation.peer.view"
PEER_MESSAGE_SEND_PERMISSION = "chat.conversation.peer_message.send"
INTERNAL_NOTE_CREATE_PERMISSION = "chat.conversation.internal_note.create"
VISITOR_SYSTEM_MAX_LENGTH = 64
VISITOR_BROWSER_MAX_LENGTH = 128
VISITOR_IP_MAX_LENGTH = 45
QUEUE_ENTERED_SYSTEM_MESSAGE = "已进入人工客服队列"
AGENT_ASSIGNED_SYSTEM_MESSAGE = "客服已接入会话"
AGENT_ASSIGNED_EVENT_TYPE = "agent_assigned"


class ConversationService:
    @staticmethod
    def _queue_full_response(
        config: ChannelConfig,
        *,
        availability: dict | None = None,
    ) -> dict:
        from app.services.channel_service import ChannelService

        if availability is not None:
            payload = {
                **availability,
                "can_start_conversation": False,
                "reason": "queue_full",
            }
        else:
            payload = ChannelService._availability_payload(
                config,
                can_start_conversation=False,
                reason="queue_full",
                checked_at=datetime.now(timezone.utc),
            )
        return {
            "conversation": None,
            "is_new": False,
            "queue_full": True,
            "availability": payload,
        }

    @staticmethod
    def _no_assignable_queue_response(*, is_new: bool = False) -> dict:
        return {
            "conversation": None,
            "is_new": is_new,
            "no_assignable_queue": True,
        }

    @staticmethod
    def _clean_visitor_environment_value(value: object, max_length: int) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned[:max_length] if cleaned else None

    @staticmethod
    def _visitor_environment_data(
        *,
        visitor_system: object = None,
        visitor_browser: object = None,
        visitor_ip: object = None,
    ) -> dict:
        data = {
            "visitor_system": ConversationService._clean_visitor_environment_value(
                visitor_system,
                VISITOR_SYSTEM_MAX_LENGTH,
            ),
            "visitor_browser": ConversationService._clean_visitor_environment_value(
                visitor_browser,
                VISITOR_BROWSER_MAX_LENGTH,
            ),
            "visitor_ip": ConversationService._clean_visitor_environment_value(
                visitor_ip,
                VISITOR_IP_MAX_LENGTH,
            ),
        }
        return {key: value for key, value in data.items() if value is not None}

    @staticmethod
    def _is_web_channel(channel: object) -> bool:
        return str(getattr(channel, "channel_type", "") or "").lower() == "web"

    @staticmethod
    def _html_to_plain_text(content: str) -> str:
        text = re.sub(r"<[^>]*>", " ", content)
        text = unescape(text).replace("\xa0", " ")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _sanitize_rich_text_content(content: str) -> str:
        sanitized = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", content, flags=re.I)
        sanitized = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", "", sanitized, flags=re.I)
        sanitized = re.sub(r"<(iframe|object|embed)\b[^>]*>.*?<\/\1>", "", sanitized, flags=re.I | re.S)
        sanitized = re.sub(r"<(iframe|object|embed)\b[^>]*\/?>", "", sanitized, flags=re.I)
        sanitized = re.sub(r"\s+on[a-z]+\s*=\s*(\".*?\"|'.*?'|[^\s>]+)", "", sanitized, flags=re.I | re.S)
        sanitized = re.sub(r"\s+(href|src)\s*=\s*(\"|')\s*javascript:[\s\S]*?\2", "", sanitized, flags=re.I)
        sanitized = re.sub(r"\s+(href|src)\s*=\s*javascript:[^\s>]+", "", sanitized, flags=re.I)
        return sanitized.strip()

    @staticmethod
    def _public_message_item(msg, conversation_public_id: str) -> dict:
        metadata = getattr(msg, "metadata_", None) or {}
        return {
            "id": msg.id,
            "conversation_public_id": conversation_public_id,
            "sender_type": msg.sender_type,
            "sender_id": msg.sender_id,
            "sender_name": ConversationService._metadata_sender_name(msg.sender_type, metadata),
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
    def _message_visible_to(msg, target: str) -> bool:
        metadata = getattr(msg, "metadata_", None) or {}
        visible_to = metadata.get("visible_to")
        if not visible_to or not isinstance(visible_to, list):
            return True
        return target in visible_to

    @staticmethod
    def _visitor_visible_messages(messages: list) -> list:
        return [
            message
            for message in messages
            if ConversationService._message_visible_to(message, "visitor")
        ]

    @staticmethod
    def visitor_agent_display_name(agent) -> str | None:
        """Public-facing agent label for Web SDK visitors: nickname, then legal name."""
        if agent is None:
            return None
        return getattr(agent, "nickname", None) or getattr(agent, "name", None) or None

    @staticmethod
    def _metadata_sender_name(sender_type: str, metadata: dict | None) -> str | None:
        if sender_type != MessageSenderType.BOT.value:
            return None
        metadata = metadata or {}
        return (
            metadata.get("sender_name")
            or metadata.get("open_agent_agent_name")
            or "智能助手"
        )

    @staticmethod
    def _is_internal_note(content_type: str) -> bool:
        return content_type == MessageContentType.INTERNAL_NOTE.value

    @staticmethod
    def _availability_is_leave_message(availability: dict) -> bool:
        return (
            availability.get("reason") == "outside_service_hours"
            and availability.get("outside_service_hours_strategy") == "leave_message"
        )

    @staticmethod
    async def _assert_peer_scope(db: AsyncSession, principal: EffectivePrincipal) -> list[int]:
        scope = DataScopeService.get_scope(principal, RESOURCE_PEER_CONVERSATION)
        if scope == "self":
            raise ForbiddenError("Permission denied")
        return await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)

    @staticmethod
    async def _assert_conversation_view_access(
        db: AsyncSession,
        principal: EffectivePrincipal,
        conversation,
    ) -> str:
        if conversation.agent_id == principal.user_id:
            return "own"
        if conversation.status == ConversationStatus.CLOSED.value:
            participated = await ConversationRepository.has_agent_participated(
                db,
                tenant_id=conversation.tenant_id,
                conversation_id=conversation.id,
                agent_id=principal.user_id,
            )
            if participated:
                return "own"
        if not principal.has_permission(PEER_VIEW_PERMISSION):
            raise ForbiddenError("Permission denied")
        peer_ids = await ConversationService._assert_peer_scope(db, principal)
        DataScopeService.assert_conversation_in_scope(
            principal,
            conversation,
            peer_ids,
            RESOURCE_PEER_CONVERSATION,
        )
        return "peer"

    @staticmethod
    async def _assert_conversation_send_access(
        db: AsyncSession,
        principal: EffectivePrincipal,
        conversation,
        content_type: str,
    ) -> str:
        if ConversationService._is_internal_note(content_type):
            if not principal.has_permission(INTERNAL_NOTE_CREATE_PERMISSION):
                raise ForbiddenError("Permission denied")
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            DataScopeService.assert_conversation_in_scope(
                principal,
                conversation,
                peer_ids,
                RESOURCE_PEER_CONVERSATION,
            )
            return "own" if conversation.agent_id == principal.user_id else "peer"

        if conversation.agent_id == principal.user_id:
            return "own"
        if not principal.has_permission(PEER_MESSAGE_SEND_PERMISSION):
            raise ForbiddenError("Permission denied")
        peer_ids = await ConversationService._assert_peer_scope(db, principal)
        DataScopeService.assert_conversation_in_scope(
            principal,
            conversation,
            peer_ids,
            RESOURCE_PEER_CONVERSATION,
        )
        return "peer"

    @staticmethod
    def _workspace_conversation_item(
        conversation,
        *,
        viewer_relation: str,
        collaborated: bool = False,
        has_history: bool = False,
    ) -> dict:
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
            "visitor_system": getattr(conversation, "visitor_system", None),
            "visitor_browser": getattr(conversation, "visitor_browser", None),
            "visitor_ip": getattr(conversation, "visitor_ip", None),
            "unread_count": conversation.unread_count,
            "has_history_conversations": has_history,
            "viewer_relation": viewer_relation,
            "collaborated_by_current_user": collaborated,
            "created_at": conversation.created_at,
        }

    @staticmethod
    def validate_message_content(content_type: str, content: str) -> str:
        """Validate and normalize message content before persistence."""
        if content_type not in ALLOWED_MESSAGE_CONTENT_TYPES:
            raise ValidationError("Unsupported message type")

        if not content:
            raise ValidationError("Message content is required")

        if content_type in {
            MessageContentType.TEXT.value,
            MessageContentType.SYSTEM.value,
            MessageContentType.INTERNAL_NOTE.value,
        }:
            if len(content) > MAX_TEXT_MESSAGE_LENGTH:
                raise ValidationError("Message content exceeds 5000 characters")
            return content

        if content_type == MessageContentType.RICH_TEXT.value:
            sanitized = ConversationService._sanitize_rich_text_content(content)
            plain = ConversationService._html_to_plain_text(sanitized)
            has_image = bool(re.search(r"<img\b", sanitized, flags=re.I))
            if not plain and not has_image:
                raise ValidationError("Message content is required")
            if len(plain) > MAX_TEXT_MESSAGE_LENGTH:
                raise ValidationError("Message content exceeds 5000 characters")
            return sanitized

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
        if content_type == MessageContentType.INTERNAL_NOTE.value:
            return f"[内部] {content}"[:200]

        if content_type in {MessageContentType.TEXT.value, MessageContentType.SYSTEM.value}:
            return content[:200]

        if content_type == MessageContentType.SATISFACTION_EVENT.value:
            return content[:200]

        if content_type == MessageContentType.RICH_TEXT.value:
            plain = ConversationService._html_to_plain_text(content)
            if plain:
                return plain[:200]
            if re.search(r"<img\b", content, flags=re.I):
                return "[图片]"
            return "[富文本]"

        if content_type in {
            MessageContentType.WELCOME.value,
            MessageContentType.BOT_WELCOME.value,
        }:
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
    async def create_agent_assigned_system_message(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        agent_id: int,
    ):
        """Persist a system event when a queued conversation is picked up by an agent."""
        existing = await MessageRepository.get_event_message(
            db, tenant_id, conversation_id, AGENT_ASSIGNED_EVENT_TYPE
        )
        if existing is not None:
            return existing

        return await MessageRepository.create(db, {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.SYSTEM.value,
            "content": AGENT_ASSIGNED_SYSTEM_MESSAGE,
            "metadata_": {
                "event_type": AGENT_ASSIGNED_EVENT_TYPE,
                "agent_id": agent_id,
            },
        })

    @staticmethod
    async def create_welcome_message_on_agent_assignment(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
    ):
        """Persist a welcome message when a queued conversation receives an agent."""
        if await MessageRepository.has_welcome_message(db, tenant_id, conversation_id):
            return None

        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id or not conversation.agent_id:
            return None

        welcome_msg = await ConversationService._create_matched_welcome_message(db, conversation)
        if not welcome_msg:
            return None

        preview = ConversationService.build_message_preview(
            welcome_msg.content_type,
            welcome_msg.content,
        )
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            preview,
            welcome_msg.created_at or datetime.now(timezone.utc),
        )
        return welcome_msg

    @staticmethod
    def _open_agent_welcome_message_content(welcome_message: OpenAgentWelcomeMessage) -> str:
        parts: list[str] = []
        for block in welcome_message.blocks:
            if block.type == "markdown" and block.content:
                parts.append(block.content.strip())
            elif block.type == "embed" and block.embed_code:
                parts.append("[嵌入内容]")
        return "\n\n".join(part for part in parts if part).strip() or "智能助手欢迎语"

    @staticmethod
    async def _create_open_agent_welcome_message(
        db: AsyncSession,
        conversation,
        config: ChannelConfig,
        bot_name: str,
    ):
        if not config.open_agent_agent_id:
            return None

        from app.services.open_agent_settings_service import OpenAgentSettingsService

        welcome_message = await OpenAgentSettingsService.get_agent_welcome_message(
            db,
            conversation.tenant_id,
            config.open_agent_agent_id,
        )
        if not welcome_message:
            return None

        return await MessageRepository.create(db, {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.BOT_WELCOME.value,
            "content": ConversationService._open_agent_welcome_message_content(welcome_message),
            "metadata_": {
                "event_type": "open_agent_welcome_message",
                "open_agent_agent_id": config.open_agent_agent_id,
                "open_agent_agent_name": bot_name,
                "open_agent_welcome_blocks": [
                    block.model_dump()
                    for block in welcome_message.blocks
                ],
            },
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
        context_token: str | None = None,
        channel_key: str | None = None,
        visitor_system: object = None,
        visitor_browser: object = None,
        visitor_ip: object = None,
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
            if ConversationService._is_web_channel(existing.channel):
                environment_data = ConversationService._visitor_environment_data(
                    visitor_system=visitor_system,
                    visitor_browser=visitor_browser,
                    visitor_ip=visitor_ip,
                )
                if environment_data:
                    existing = await ConversationRepository.update_visitor_environment(
                        db,
                        existing,
                        environment_data,
                    )
            newly_assigned = False
            queue_position = None
            if existing.status == ConversationStatus.QUEUED.value and not existing.agent_id:
                group_id, group_member_ids, max_concurrent_map, _route_block_reason = (
                    await RoutingService.route_conversation_with_meta(
                        db, tenant_id, channel_id, r, visitor_id=existing.visitor_id
                    )
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
                        from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService

                        await VisitorTimeoutCloseService.initialize_for_conversation(db, existing)
                        newly_assigned = True
                        logger.info("Queued conv %d assigned to agent %d", existing.id, agent_id)
                if existing.status == ConversationStatus.QUEUED.value:
                    if group_id is not None and existing.group_id != group_id:
                        existing = await ConversationRepository.update_group(db, existing, group_id)

                    from app.services.queue_workspace_service import QueueWorkspaceService

                    try:
                        enqueue_result = await QueueWorkspaceService.enqueue_conversation_if_needed(
                            db,
                            tenant_id,
                            existing,
                            source_type="visitor_waiting",
                        )
                        queue_position = getattr(
                            getattr(enqueue_result, "position", None),
                            "position_overall",
                            None,
                        )
                    except BusinessError as exc:
                        if exc.code != "QUEUE_LIMIT_REACHED":
                            raise
                        logger.info(
                            "queued_conversation_reenqueue_limited tenant_id=%s conversation_id=%s",
                            tenant_id,
                            existing.id,
                        )
                        channel = await ChannelRepository.get_by_id(db, channel_id)
                        raw_channel_config = getattr(channel, "config", None) if channel else None
                        config = ChannelConfig.model_validate(
                            raw_channel_config if isinstance(raw_channel_config, dict) else {}
                        )
                        return ConversationService._queue_full_response(config)
                    if (
                        enqueue_result is None
                        and existing.group_id is None
                        and existing.status == ConversationStatus.QUEUED.value
                    ):
                        return ConversationService._no_assignable_queue_response()
            context_sync = await ConversationService._sync_web_sdk_context_if_present(
                db,
                conversation=existing,
                tenant_id=tenant_id,
                channel_id=channel_id,
                visitor_external_id=visitor_external_id,
                channel_key=channel_key,
                context_token=context_token,
                require_active_api_key=True,
            )
            return {
                "conversation": existing,
                "is_new": False,
                "newly_assigned": newly_assigned,
                **({"queue_position": queue_position} if queue_position is not None else {}),
                **({"context_sync": context_sync} if context_sync else {}),
            }

        from app.services.channel_service import ChannelService

        channel = await ChannelRepository.get_by_id(db, channel_id)
        if not channel:
            raise NotFoundError("Channel not found")

        raw_channel_config = getattr(channel, "config", None)
        config = ChannelConfig.model_validate(raw_channel_config if isinstance(raw_channel_config, dict) else {})
        environment_data = (
            ConversationService._visitor_environment_data(
                visitor_system=visitor_system,
                visitor_browser=visitor_browser,
                visitor_ip=visitor_ip,
            )
            if ConversationService._is_web_channel(channel)
            else {}
        )
        if config.open_agent_enabled:
            availability = await ChannelService.check_open_agent_bot_availability(db, channel, config)
            if not availability["can_start_conversation"]:
                if ConversationService._availability_is_leave_message(availability):
                    return {
                        "conversation": None,
                        "is_new": False,
                        "leave_message": True,
                        "availability": availability,
                    }
                return {
                    "conversation": None,
                    "is_new": False,
                    "offline": True,
                    "availability": availability,
                }

            now = datetime.now(timezone.utc)
            bot_name = config.open_agent_agent_name or "智能助手"
            conversation = await ConversationRepository.create(db, {
                "public_id": await ConversationRepository.generate_unique_public_id(db),
                "share_code": await ConversationRepository.generate_unique_share_code(db),
                "tenant_id": tenant_id,
                "visitor_id": user.id,
                "channel_id": channel_id,
                "group_id": None,
                "agent_id": None,
                "status": ConversationStatus.BOT.value,
                "started_at": now,
                "open_agent_agent_id": config.open_agent_agent_id,
                "open_agent_agent_name": bot_name,
                **environment_data,
            })
            preview_message = await MessageRepository.create(db, {
                "tenant_id": tenant_id,
                "conversation_id": conversation.id,
                "sender_type": MessageSenderType.SYSTEM.value,
                "content_type": MessageContentType.SYSTEM.value,
                "content": "智能助手开始接待",
                "metadata_": {
                    "event_type": "open_agent_bot_started",
                    "open_agent_agent_id": config.open_agent_agent_id,
                    "open_agent_agent_name": bot_name,
                },
            })
            welcome_msg = await ConversationService._create_open_agent_welcome_message(
                db,
                conversation,
                config,
                bot_name,
            )
            if welcome_msg:
                preview_message = welcome_msg
            await ConversationRepository.update_last_message(
                db,
                conversation.id,
                ConversationService.build_message_preview(preview_message.content_type, preview_message.content),
                preview_message.created_at or now,
            )
            conversation = await ConversationRepository.get_by_id(db, conversation.id)
            context_sync = await ConversationService._sync_web_sdk_context_if_present(
                db,
                conversation=conversation,
                tenant_id=tenant_id,
                channel_id=channel_id,
                visitor_external_id=visitor_external_id,
                channel_key=channel_key,
                context_token=context_token,
                require_active_api_key=True,
            )
            return {
                "conversation": conversation,
                "is_new": True,
                **({"context_sync": context_sync} if context_sync else {}),
            }

        availability = await ChannelService.check_human_service_gate(db, channel, config)
        if not availability["can_start_conversation"]:
            if ConversationService._availability_is_leave_message(availability):
                return {
                    "conversation": None,
                    "is_new": False,
                    "leave_message": True,
                    "availability": availability,
                }
            return {
                "conversation": None,
                "is_new": False,
                "offline": True,
                "availability": availability,
            }

        group_id, group_member_ids, max_concurrent_map, route_block_reason = (
            await RoutingService.route_conversation_with_meta(
                db, tenant_id, channel_id, r, visitor_id=user.id
            )
        )

        agent_id = None
        if group_member_ids:
            agent_id = await AgentStatusService.find_available_agent(
                r, tenant_id, group_member_ids, max_concurrent_map
            )

        if agent_id is None and group_id is None:
            if route_block_reason == "queue_limit":
                return ConversationService._queue_full_response(config)
            return ConversationService._no_assignable_queue_response(is_new=False)

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
            **environment_data,
        }
        conversation = await ConversationRepository.create(db, conv_data)

        if agent_id:
            await AgentStatusService.increment_count(r, tenant_id, agent_id)

        sys_content = "用户发起了新会话" if agent_id else QUEUE_ENTERED_SYSTEM_MESSAGE
        system_msg = await MessageRepository.create(db, {
            "tenant_id": tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.SYSTEM.value,
            "content": sys_content,
        })
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            ConversationService.build_message_preview(
                system_msg.content_type,
                system_msg.content,
            ),
            system_msg.created_at or now,
        )
        if agent_id:
            await ConversationService.create_welcome_message_on_agent_assignment(
                db,
                tenant_id,
                conversation.id,
            )
            from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService

            await VisitorTimeoutCloseService.initialize_for_conversation(db, conversation)

        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        queue_position = None
        if conversation and conversation.status == ConversationStatus.QUEUED.value:
            from app.services.queue_workspace_service import QueueWorkspaceService

            try:
                enqueue_result = await QueueWorkspaceService.enqueue_conversation_if_needed(
                    db,
                    tenant_id,
                    conversation,
                    source_type="visitor_waiting",
                )
                queue_position = getattr(
                    getattr(enqueue_result, "position", None),
                    "position_overall",
                    None,
                )
            except BusinessError as exc:
                if exc.code != "QUEUE_LIMIT_REACHED":
                    raise
                await db.rollback()
                return ConversationService._queue_full_response(config, availability=availability)
            if enqueue_result is None:
                await db.rollback()
                return ConversationService._no_assignable_queue_response(is_new=False)
        context_sync = await ConversationService._sync_web_sdk_context_if_present(
            db,
            conversation=conversation,
            tenant_id=tenant_id,
            channel_id=channel_id,
            visitor_external_id=visitor_external_id,
            channel_key=channel_key,
            context_token=context_token,
            require_active_api_key=True,
        )
        return {
            "conversation": conversation,
            "is_new": True,
            **({"queue_position": queue_position} if queue_position is not None else {}),
            **({"context_sync": context_sync} if context_sync else {}),
        }

    @staticmethod
    async def _sync_web_sdk_context_if_present(
        db: AsyncSession,
        *,
        conversation,
        tenant_id: int,
        channel_id: int,
        visitor_external_id: str,
        channel_key: str | None,
        context_token: str | None,
        require_active_api_key: bool,
    ) -> dict | None:
        if not context_token or not channel_key or not conversation:
            return None
        from app.services.web_sdk_context_service import WebSdkContextService

        try:
            result = await WebSdkContextService.sync_for_conversation(
                db,
                context_token=context_token,
                visitor_context={
                    "tenant_id": tenant_id,
                    "channel_id": channel_id,
                    "channel_key": channel_key,
                    "visitor_external_id": visitor_external_id,
                },
                conversation_public_id=conversation.public_id,
                require_active_api_key=require_active_api_key,
            )
            return result.to_dict()
        except (ForbiddenError, NotFoundError, UnauthorizedError, ValidationError):
            return {
                "ok": False,
                "warnings": ["CONTEXT_SYNC_FAILED"],
                "customer_synced": False,
                "session_summary_synced": False,
            }

    @staticmethod
    async def get_agent_conversations(
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
        roles: list[str] | None = None,
        principal: EffectivePrincipal | None = None,
        scope: str = "my",
    ) -> list:
        if scope not in {"my", "peers"}:
            raise ValidationError("Invalid conversation scope")

        viewer_relation = "own"
        if scope == "peers":
            if principal is None or not principal.has_permission(PEER_VIEW_PERMISSION):
                raise ForbiddenError("Permission denied")
            peer_ids = await ConversationService._assert_peer_scope(db, principal)
            scope_predicate = DataScopeService.build_session_record_predicate(
                principal,
                peer_ids,
                RESOURCE_PEER_CONVERSATION,
            )
            conversations = await ConversationRepository.get_active_peer_conversations(
                db,
                tenant_id,
                agent_id,
                scope_predicate=scope_predicate,
            )
            viewer_relation = "peer"
        else:
            conversations = await ConversationRepository.get_active_by_agent(db, tenant_id, agent_id)
        if not conversations:
            logger.debug(
                "conversation_list_empty tenant_id=%s agent_id=%s scope=%s",
                tenant_id,
                agent_id,
                scope,
            )

        if principal is not None:
            history_agent_id, history_predicate = await DataScopeService.session_history_filters(
                db, principal
            )
        else:
            can_view_all_history = "admin" in (roles or ["agent"])
            history_agent_id = None if can_view_all_history else agent_id
            history_predicate = None

        conversation_ids = [conversation.id for conversation in conversations]
        collaborated_ids = await MessageRepository.get_agent_message_conversation_ids(
            db,
            tenant_id,
            conversation_ids,
            agent_id,
        )

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
                    scope_predicate=history_predicate,
                )
                has_history = bool(history)

            items.append(ConversationService._workspace_conversation_item(
                conversation,
                viewer_relation=viewer_relation,
                collaborated=conversation.id in collaborated_ids,
                has_history=has_history,
            ))
        return items

    @staticmethod
    async def get_agent_conversation(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        roles: list[str] | None = None,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        """Get a workspace conversation with the history availability marker."""
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        if principal is not None:
            viewer_relation = await ConversationService._assert_conversation_view_access(
                db,
                principal,
                conversation,
            )
            history_agent_id, history_predicate = await DataScopeService.session_history_filters(
                db, principal
            )
        else:
            can_view_all_history = "admin" in (roles or ["agent"])
            if not can_view_all_history and conversation.agent_id != agent_id:
                raise ForbiddenError("No permission to view conversation")
            history_agent_id = None if can_view_all_history else agent_id
            history_predicate = None
            viewer_relation = "own" if conversation.agent_id == agent_id else "peer"

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
                scope_predicate=history_predicate,
            )
            has_history = bool(history)

        collaborated = False
        if principal is not None:
            collaborated_ids = await MessageRepository.get_agent_message_conversation_ids(
                db,
                tenant_id,
                [conversation.id],
                agent_id,
            )
            collaborated = conversation.id in collaborated_ids

        return ConversationService._workspace_conversation_item(
            conversation,
            viewer_relation=viewer_relation,
            collaborated=collaborated,
            has_history=has_history,
        )

    @staticmethod
    async def get_agent_history_conversations(
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
        before_id: int | None = None,
        limit: int = WORKSPACE_MY_HISTORY_PAGE_SIZE,
    ) -> dict:
        """Get the current agent's recently ended workspace conversations."""
        safe_limit = min(max(limit, 1), WORKSPACE_MY_HISTORY_PAGE_SIZE)
        ended_since = datetime.now(timezone.utc) - timedelta(hours=WORKSPACE_MY_HISTORY_HOURS)
        conversations = await ConversationRepository.get_recent_closed_by_agent(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            ended_since=ended_since,
            before_id=before_id,
            limit=safe_limit + 1,
        )
        has_more = len(conversations) > safe_limit
        if has_more:
            conversations = conversations[:safe_limit]

        items = [
            ConversationService._workspace_conversation_item(
                conversation,
                viewer_relation="own",
                collaborated=conversation.agent_id != agent_id,
                has_history=False,
            )
            for conversation in conversations
        ]
        return {"items": items, "total": len(items), "has_more": has_more}

    @staticmethod
    async def get_agent_history_conversation(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
    ) -> dict:
        """Get one closed conversation owned or handled by the current agent."""
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")
        if conversation.status != ConversationStatus.CLOSED.value:
            raise ValidationError("Conversation is not closed")
        if conversation.agent_id != agent_id:
            participated = await ConversationRepository.has_agent_participated(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                agent_id=agent_id,
            )
            if not participated:
                raise ForbiddenError("Permission denied")

        return ConversationService._workspace_conversation_item(
            conversation,
            viewer_relation="own",
            collaborated=conversation.agent_id != agent_id,
            has_history=False,
        )

    @staticmethod
    async def start_new_from_history(
        db: AsyncSession,
        r: aioredis.Redis,
        conversation_id: int,
        principal: EffectivePrincipal,
    ) -> dict:
        """Create a new active conversation for the same visitor and channel."""
        history = await ConversationRepository.get_by_id(db, conversation_id)
        if not history or history.tenant_id != principal.tenant_id:
            raise NotFoundError("Conversation not found")
        if history.status != ConversationStatus.CLOSED.value:
            raise ValidationError("Conversation is not closed")
        if history.agent_id != principal.user_id:
            participated = await ConversationRepository.has_agent_participated(
                db,
                tenant_id=principal.tenant_id,
                conversation_id=conversation_id,
                agent_id=principal.user_id,
            )
            if not participated:
                raise ForbiddenError("Permission denied")
        if not history.visitor_id or not history.channel_id:
            raise ValidationError("Conversation visitor or channel is missing")

        employee = await EmployeeRepository.get_by_id(db, principal.user_id)
        max_concurrent = employee.max_concurrent if employee else 10
        status = await AgentStatusService.get_status(
            r,
            principal.tenant_id,
            principal.user_id,
            max_concurrent,
        )
        if status["status"] != "online":
            raise BusinessError("Agent must be online to start a conversation")

        channel = await ChannelRepository.get_by_id(db, history.channel_id)
        if not channel or channel.tenant_id != principal.tenant_id:
            raise NotFoundError("Channel not found")
        if channel.channel_type != "web":
            raise BusinessError("Channel does not support starting a new conversation")

        existing = await ConversationRepository.get_active_visitor_conversation(
            db,
            tenant_id=principal.tenant_id,
            visitor_id=history.visitor_id,
            channel_id=history.channel_id,
        )
        if existing:
            if existing.agent_id == principal.user_id:
                return {
                    "conversation": ConversationService._workspace_conversation_item(
                        existing,
                        viewer_relation="own",
                        collaborated=False,
                        has_history=True,
                    ),
                    "is_new": False,
                    "already_active": True,
                }
            raise BusinessError("Visitor already has an active conversation")

        now = datetime.now(timezone.utc)
        conversation = await ConversationRepository.create(db, {
            "tenant_id": principal.tenant_id,
            "visitor_id": history.visitor_id,
            "channel_id": history.channel_id,
            "group_id": history.group_id,
            "agent_id": principal.user_id,
            "status": ConversationStatus.ACTIVE.value,
            "started_at": now,
            "unread_count": 0,
        })
        system_msg = await MessageRepository.create(db, {
            "tenant_id": principal.tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.SYSTEM.value,
            "content": "客服发起了新会话",
            "metadata_": {
                "event_type": "new_conversation_from_history",
                "source_conversation_id": history.id,
            },
        })
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            ConversationService.build_message_preview(system_msg.content_type, system_msg.content),
            system_msg.created_at or now,
        )
        await AgentStatusService.increment_count(r, principal.tenant_id, principal.user_id)
        from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService

        await VisitorTimeoutCloseService.initialize_for_conversation(db, conversation)
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        return {
            "conversation": ConversationService._workspace_conversation_item(
                conversation,
                viewer_relation="own",
                collaborated=False,
                has_history=True,
            ),
            "is_new": True,
            "already_active": False,
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
        principal: EffectivePrincipal | None = None,
    ):
        conv = await ConversationRepository.get_by_id(db, conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found")
        if principal is not None:
            if conv.tenant_id != principal.tenant_id:
                raise NotFoundError("Conversation not found")
            if conv.agent_id != principal.user_id:
                raise ForbiddenError("Permission denied")
        if conv.status == ConversationStatus.CLOSED.value:
            raise BusinessError("Conversation already closed")

        conv = await ConversationRepository.end_conversation(db, conv, ended_by)
        from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService

        await VisitorTimeoutCloseService.mark_inactive(db, conv.id)

        if conv.agent_id:
            await AgentStatusService.decrement_count(r, conv.tenant_id, conv.agent_id)
            await AgentStatusService.trigger_queue_backfill(r, conv.tenant_id, conv.agent_id)

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
        logger.info(
            "conversation_ended tenant_id=%s conversation_id=%s agent_id=%s ended_by=%s",
            conv.tenant_id,
            conv.id,
            conv.agent_id,
            ended_by,
        )

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
        metadata: dict | None = None,
        principal: EffectivePrincipal | None = None,
    ):
        conv = await ConversationRepository.get_by_id(db, conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found")
        if conv.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")
        if conv.status == ConversationStatus.CLOSED.value:
            raise BusinessError("Cannot send message to closed conversation")
        if ConversationService._is_internal_note(content_type) and sender_type != MessageSenderType.AGENT.value:
            raise ValidationError("Internal notes can only be sent by agents")
        if principal is not None:
            await ConversationService._assert_conversation_send_access(
                db,
                principal,
                conv,
                content_type,
            )

        normalized_content = ConversationService.validate_message_content(content_type, content)
        now = datetime.now(timezone.utc)
        message_metadata = metadata or {}
        if ConversationService._is_internal_note(content_type):
            message_metadata = {**message_metadata, "visibility": "internal"}
        msg = await MessageRepository.create(db, {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "sender_type": sender_type,
            "sender_id": sender_id,
            "content_type": content_type,
            "content": normalized_content,
            "metadata_": message_metadata,
        })

        preview = ConversationService.build_message_preview(content_type, normalized_content)
        increment_unread = sender_type == MessageSenderType.VISITOR.value
        await ConversationRepository.update_last_message(
            db, conversation_id, preview, now, increment_unread=increment_unread
        )
        logger.info(
            "conversation_message_saved tenant_id=%s conversation_id=%s message_id=%s "
            "sender_type=%s sender_id=%s content_type=%s increment_unread=%s",
            tenant_id,
            conversation_id,
            msg.id,
            sender_type,
            sender_id,
            content_type,
            increment_unread,
        )
        if sender_type == MessageSenderType.AGENT.value and not ConversationService._is_internal_note(content_type):
            await OfflineMessageRepository.mark_customer_unread_by_conversation(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                message_id=msg.id,
                unread_at=now,
            )
            from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService

            await VisitorTimeoutCloseService.ensure_for_agent_message(db, conv)
        elif sender_type == MessageSenderType.VISITOR.value:
            from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService

            await VisitorTimeoutCloseService.reset_on_visitor_message(db, conv, msg)
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
            include_internal=False,
            visitor_facing=True,
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
    def _public_message_payload(msg, conversation) -> dict:
        metadata = getattr(msg, "metadata_", None) or {}
        return {
            "id": msg.id,
            "conversation_public_id": conversation.public_id,
            "sender_type": msg.sender_type,
            "sender_id": msg.sender_id,
            "sender_name": ConversationService._metadata_sender_name(msg.sender_type, metadata),
            "sender_avatar": None,
            "content_type": msg.content_type,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            **ConversationService._message_event_overlay(msg),
        }

    @staticmethod
    async def _save_confirmed_by_visitor_handoff_event(
        db: AsyncSession,
        conversation,
        handoff_data: dict,
        tool_call_id: str | None,
        handoff_source: str = "bot_tool",
    ) -> dict | None:
        raw_tool_call_id = tool_call_id if isinstance(tool_call_id, str) else None
        raw_payload_tool_call_id = handoff_data.get("tool_call_id") if isinstance(handoff_data, dict) else None
        if not isinstance(raw_payload_tool_call_id, str):
            raw_payload_tool_call_id = None
        normalized_tool_call_id = (raw_tool_call_id or raw_payload_tool_call_id or "").strip() or None
        content = "您已确认转接人工客服"
        if normalized_tool_call_id:
            existing = await MessageRepository.get_handoff_event_by_tool_call_id(
                db,
                conversation.tenant_id,
                conversation.id,
                normalized_tool_call_id,
                "confirmed_by_visitor",
            )
            if existing:
                conversation = await ConversationRepository.get_by_id(db, conversation.id)
                return ConversationService._public_message_payload(existing, conversation)

        msg = await MessageRepository.create(db, {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.SYSTEM.value,
            "content": content,
            "metadata_": {
                "event_type": "open_agent_handoff_event",
                "handoff_event_type": "confirmed_by_visitor",
                "handoff_source": handoff_source,
                "handoff_payload": handoff_data,
                **({"tool_call_id": normalized_tool_call_id} if normalized_tool_call_id else {}),
            },
        })
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            content,
            msg.created_at or datetime.now(timezone.utc),
        )
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        return ConversationService._public_message_payload(msg, conversation)

    @staticmethod
    def _resolve_handoff_source(handoff_data: dict, handoff_trigger: str) -> str:
        if handoff_trigger == "visitor":
            return "visitor"
        value = handoff_data.get("handoff_source") if isinstance(handoff_data, dict) else None
        if value in {"bot_tool", "bot_event"}:
            return value
        return "bot_tool"

    @staticmethod
    async def request_human_handoff_for_session(
        db: AsyncSession,
        r: aioredis.Redis,
        conversation_public_id: str,
        visitor_context: dict,
        handoff_payload: dict | None = None,
        *,
        handoff_trigger: str = "visitor",
        tool_call_id: str | None = None,
    ) -> dict:
        """Route a bot conversation to a human agent when possible."""
        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        if conversation.status == ConversationStatus.CLOSED.value:
            raise BusinessError("Cannot transfer a closed conversation")

        if conversation.agent_id and conversation.status == ConversationStatus.ACTIVE.value:
            return {
                "ok": True,
                "already_assigned": True,
                "conversation": conversation,
                "message": None,
                "messages": [],
                "agent": conversation.agent,
            }

        from app.services.channel_service import ChannelService

        handoff_data = handoff_payload or conversation.open_agent_handoff_payload or {}
        emitted_messages: list[dict] = []
        handoff_source = ConversationService._resolve_handoff_source(
            handoff_data,
            handoff_trigger,
        )

        if handoff_trigger == "bot_confirmed":
            confirmed_message = await ConversationService._save_confirmed_by_visitor_handoff_event(
                db,
                conversation,
                handoff_data,
                tool_call_id,
                handoff_source,
            )
            if confirmed_message:
                emitted_messages.append(confirmed_message)
            conversation = await ConversationRepository.get_by_id(db, conversation.id)
            if not conversation:
                raise NotFoundError("Conversation not found")

        conversation, request_marked = await ConversationRepository.update_handoff_state_if_unassigned(
            db,
            conversation,
            state="requested",
            payload=handoff_data,
            status=ConversationStatus.HANDOFF_PENDING.value,
            allowed_previous_states=(None, "pending", "failed"),
        )
        if not request_marked:
            conversation = await ConversationRepository.get_by_id(db, conversation.id)
            if not conversation:
                raise NotFoundError("Conversation not found")
            if conversation.status == ConversationStatus.CLOSED.value:
                raise BusinessError("Cannot transfer a closed conversation")
            if conversation.agent_id and conversation.status == ConversationStatus.ACTIVE.value:
                return {
                    "ok": True,
                    "already_assigned": True,
                    "conversation": conversation,
                    "message": emitted_messages[-1] if emitted_messages else None,
                    "messages": emitted_messages,
                    "agent": conversation.agent,
                }
            return {
                "ok": False,
                "conversation": conversation,
                "message": emitted_messages[-1] if emitted_messages else None,
                "messages": emitted_messages,
                "agent": None,
                "reason": "handoff_in_progress",
            }

        target = await ChannelService.resolve_human_handoff_target(
            db,
            r,
            conversation.channel_id,
            handoff_payload=handoff_data,
            visitor_id=conversation.visitor_id,
        )

        if not target["can_start_conversation"] or not target.get("agent_id"):
            reason = target.get("reason")
            if reason == "no_available_agent" and target.get("group_id"):
                group_id = int(target["group_id"])
                conversation.group_id = group_id
                conversation = await ConversationRepository.update_open_agent_state(db, conversation, {
                    "open_agent_handoff_state": "queued",
                    "open_agent_handoff_payload": handoff_data,
                })
                conversation.group_id = group_id
                conversation = await ConversationRepository.update_status(
                    db,
                    conversation,
                    ConversationStatus.QUEUED.value,
                )
                queue_position = None
                try:
                    from app.services.queue_workspace_service import QueueWorkspaceService

                    enqueue_result = await QueueWorkspaceService.enqueue_conversation_if_needed(
                        db,
                        conversation.tenant_id,
                        conversation,
                        source_type="open_agent_handoff",
                    )
                    queue_position = getattr(
                        getattr(enqueue_result, "position", None),
                        "position_overall",
                        None,
                    )
                except BusinessError as exc:
                    if exc.code != "QUEUE_LIMIT_REACHED":
                        raise
                    channel = await ChannelRepository.get_by_id(db, conversation.channel_id)
                    config = ChannelConfig.model_validate(
                        channel.config if channel and isinstance(channel.config, dict) else {}
                    )
                    conversation = await ConversationRepository.update_open_agent_state(db, conversation, {
                        "open_agent_handoff_state": "failed",
                        "open_agent_handoff_payload": handoff_data,
                    })
                    conversation = await ConversationRepository.update_status(
                        db,
                        conversation,
                        ConversationStatus.BOT.value,
                    )
                    conversation = await ConversationRepository.get_by_id(db, conversation.id)
                    queue_full_result = ConversationService._queue_full_response(config)
                    return {
                        "ok": False,
                        "conversation": conversation,
                        "message": emitted_messages[-1] if emitted_messages else None,
                        "messages": emitted_messages,
                        "agent": None,
                        "reason": "queue_full",
                        "queue_full": True,
                        "availability": queue_full_result["availability"],
                    }

                queued_message = await MessageRepository.create(db, {
                    "tenant_id": conversation.tenant_id,
                    "conversation_id": conversation.id,
                    "sender_type": MessageSenderType.SYSTEM.value,
                    "content_type": MessageContentType.SYSTEM.value,
                    "content": QUEUE_ENTERED_SYSTEM_MESSAGE,
                    "metadata_": {
                        "event_type": "open_agent_handoff_success",
                        "handoff_payload": handoff_data,
                        "handoff_source": handoff_source,
                    },
                })
                await ConversationRepository.update_last_message(
                    db,
                    conversation.id,
                    queued_message.content,
                    queued_message.created_at or datetime.now(timezone.utc),
                )
                conversation = await ConversationRepository.get_by_id(db, conversation.id)
                queued_payload = ConversationService._public_message_payload(queued_message, conversation)
                emitted_messages.append(queued_payload)
                return {
                    "ok": True,
                    "conversation": conversation,
                    "message": queued_payload,
                    "messages": emitted_messages,
                    "agent": None,
                    **({"queue_position": queue_position} if queue_position is not None else {}),
                }

            if ConversationService._availability_is_leave_message(target):
                conversation, failed_marked = await ConversationRepository.update_handoff_state_if_unassigned(
                    db,
                    conversation,
                    state="failed",
                    payload=handoff_data,
                    status=ConversationStatus.BOT.value,
                    allowed_previous_states=("requested", "pending"),
                )
                if not failed_marked:
                    conversation = await ConversationRepository.get_by_id(db, conversation.id)
                    if not conversation:
                        raise NotFoundError("Conversation not found")
                    if conversation.agent_id and conversation.status == ConversationStatus.ACTIVE.value:
                        return {
                            "ok": True,
                            "already_assigned": True,
                            "conversation": conversation,
                            "message": emitted_messages[-1] if emitted_messages else None,
                            "messages": emitted_messages,
                            "agent": conversation.agent,
                        }
                    return {
                        "ok": False,
                        "conversation": conversation,
                        "message": emitted_messages[-1] if emitted_messages else None,
                        "messages": emitted_messages,
                        "agent": None,
                        "reason": "handoff_in_progress",
                    }
                conversation = await ConversationRepository.get_by_id(db, conversation.id)
                return {
                    "ok": False,
                    "conversation": conversation,
                    "message": emitted_messages[-1] if emitted_messages else None,
                    "messages": emitted_messages,
                    "agent": None,
                    "reason": "outside_service_hours",
                    "leave_message": True,
                    "availability": target,
                }

            content = (
                "当前人工客服不在线，您可以继续向智能助手咨询"
                if reason == "outside_service_hours"
                else "当前人工客服繁忙，您可以继续向智能助手咨询"
            )
            conversation, failed_marked = await ConversationRepository.update_handoff_state_if_unassigned(
                db,
                conversation,
                state="failed",
                payload=handoff_data,
                status=ConversationStatus.BOT.value,
                allowed_previous_states=("requested", "pending"),
            )
            if not failed_marked:
                conversation = await ConversationRepository.get_by_id(db, conversation.id)
                if not conversation:
                    raise NotFoundError("Conversation not found")
                if conversation.agent_id and conversation.status == ConversationStatus.ACTIVE.value:
                    return {
                        "ok": True,
                        "already_assigned": True,
                        "conversation": conversation,
                        "message": emitted_messages[-1] if emitted_messages else None,
                        "messages": emitted_messages,
                        "agent": conversation.agent,
                    }
                return {
                    "ok": False,
                    "conversation": conversation,
                    "message": emitted_messages[-1] if emitted_messages else None,
                    "messages": emitted_messages,
                    "agent": None,
                    "reason": "handoff_in_progress",
                }
            failed_message = await MessageRepository.create(db, {
                "tenant_id": conversation.tenant_id,
                "conversation_id": conversation.id,
                "sender_type": MessageSenderType.SYSTEM.value,
                "content_type": MessageContentType.SYSTEM.value,
                "content": content,
                "metadata_": {
                    "event_type": "open_agent_handoff_failed",
                    "reason": reason,
                    "handoff_payload": handoff_data,
                },
            })
            await ConversationRepository.update_last_message(
                db,
                conversation.id,
                content,
                failed_message.created_at or datetime.now(timezone.utc),
            )
            conversation = await ConversationRepository.get_by_id(db, conversation.id)
            failed_payload = ConversationService._public_message_payload(failed_message, conversation)
            emitted_messages.append(failed_payload)
            return {
                "ok": False,
                "conversation": conversation,
                "message": failed_payload,
                "messages": emitted_messages,
                "agent": None,
                "reason": reason,
            }

        agent_id = int(target["agent_id"])
        group_id = target.get("group_id")
        conversation, assigned = await ConversationRepository.assign_agent_if_unassigned(
            db,
            conversation,
            agent_id,
            group_id,
        )
        if not assigned:
            conversation = await ConversationRepository.get_by_id(db, conversation.id)
            if not conversation:
                raise NotFoundError("Conversation not found")
            if conversation.agent_id and conversation.status == ConversationStatus.ACTIVE.value:
                return {
                    "ok": True,
                    "already_assigned": True,
                    "conversation": conversation,
                    "message": emitted_messages[-1] if emitted_messages else None,
                    "messages": emitted_messages,
                    "agent": conversation.agent,
                }
            return {
                "ok": False,
                "conversation": conversation,
                "message": emitted_messages[-1] if emitted_messages else None,
                "messages": emitted_messages,
                "agent": None,
                "reason": "handoff_in_progress",
            }
        await AgentStatusService.increment_count(r, conversation.tenant_id, agent_id)
        from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService

        await VisitorTimeoutCloseService.initialize_for_conversation(db, conversation)
        success_message = await MessageRepository.create(db, {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.SYSTEM.value,
            "content": "已为您转接人工客服",
            "metadata_": {
                "event_type": "open_agent_handoff_success",
                "handoff_payload": handoff_data,
                "handoff_source": handoff_source,
            },
        })
        await ConversationRepository.update_open_agent_state(db, conversation, {
            "open_agent_handoff_state": "success",
            "open_agent_handoff_payload": handoff_data,
        })
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            success_message.content,
            success_message.created_at or datetime.now(timezone.utc),
        )
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        success_payload = ConversationService._public_message_payload(success_message, conversation)
        emitted_messages.append(success_payload)

        assigned_msg = await ConversationService.create_agent_assigned_system_message(
            db,
            conversation.tenant_id,
            conversation.id,
            agent_id,
        )
        if assigned_msg is not None:
            assigned_payload = ConversationService._public_message_payload(assigned_msg, conversation)
            emitted_messages.append(assigned_payload)

        welcome_msg = await ConversationService.create_welcome_message_on_agent_assignment(
            db,
            conversation.tenant_id,
            conversation.id,
        )
        if welcome_msg is not None:
            welcome_payload = ConversationService._public_message_payload(welcome_msg, conversation)
            emitted_messages.append(welcome_payload)

        latest_payload = emitted_messages[-1]
        return {
            "ok": True,
            "conversation": conversation,
            "message": latest_payload,
            "messages": emitted_messages,
            "agent": conversation.agent,
        }

    @staticmethod
    async def dismiss_bot_handoff_for_session(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
        tool_call_id: str | None = None,
    ) -> dict:
        """Visitor declined bot-initiated handoff; return conversation to bot mode."""
        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        if conversation.status == ConversationStatus.CLOSED.value:
            raise BusinessError("Cannot dismiss handoff on a closed conversation")

        if conversation.agent_id and conversation.status == ConversationStatus.ACTIVE.value:
            return {"ok": True, "conversation": conversation}

        current_state = getattr(conversation, "open_agent_handoff_state", None)
        if current_state == "dismissed":
            return {"ok": True, "conversation": conversation}
        if current_state not in {None, "pending", "failed"}:
            return {"ok": True, "conversation": conversation}

        handoff_payload = conversation.open_agent_handoff_payload or {}
        if not isinstance(handoff_payload, dict):
            handoff_payload = {}
        raw_tool_call_id = tool_call_id if isinstance(tool_call_id, str) else None
        raw_payload_tool_call_id = handoff_payload.get("tool_call_id")
        if not isinstance(raw_payload_tool_call_id, str):
            raw_payload_tool_call_id = None
        normalized_tool_call_id = (raw_tool_call_id or raw_payload_tool_call_id or "").strip() or None
        if normalized_tool_call_id:
            handoff_payload = {
                **handoff_payload,
                "tool_call_id": normalized_tool_call_id,
            }

        conversation = await ConversationRepository.update_open_agent_state(db, conversation, {
            "open_agent_handoff_state": "dismissed",
            "open_agent_handoff_payload": handoff_payload,
        })
        if conversation.status == ConversationStatus.HANDOFF_PENDING.value:
            conversation = await ConversationRepository.update_status(
                db,
                conversation,
                ConversationStatus.BOT.value,
            )
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        return {"ok": True, "conversation": conversation}

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        conversation_id: int,
        before_id: int | None = None,
        limit: int = 20,
        tenant_id: int | None = None,
        principal: EffectivePrincipal | None = None,
        include_internal: bool = True,
        visitor_facing: bool = False,
    ) -> dict:
        if tenant_id is not None and principal is not None:
            conversation = await ConversationRepository.get_by_id(db, conversation_id)
            if not conversation or conversation.tenant_id != tenant_id:
                raise NotFoundError("Conversation not found")
            await ConversationService._assert_conversation_view_access(db, principal, conversation)

        messages = await MessageRepository.get_by_conversation(
            db,
            conversation_id,
            before_id=before_id,
            limit=limit + 1,
            include_internal=include_internal,
            visibility_target="visitor" if visitor_facing else "agent",
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
            metadata = getattr(msg, "metadata_", None) or {}
            sender_name = None
            sender_avatar = None
            if msg.sender_type == MessageSenderType.AGENT.value and msg.sender_id is not None:
                agent = agent_map.get(msg.sender_id)
                if agent:
                    sender_name = (
                        ConversationService.visitor_agent_display_name(agent)
                        if visitor_facing
                        else (agent.display_name or agent.name)
                    )
                    sender_avatar = agent.avatar
            elif msg.sender_type == MessageSenderType.BOT.value:
                sender_name = ConversationService._metadata_sender_name(msg.sender_type, metadata)

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
            include_internal=False,
        )

        total_messages = 0
        agent_ids: set[int] = set()
        for messages in messages_by_conversation.values():
            for message in ConversationService._visitor_visible_messages(messages):
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
            visible_messages = ConversationService._visitor_visible_messages(raw_messages)
            remaining = max(VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT - consumed_messages, 0)
            messages = visible_messages[:remaining]
            consumed_messages += len(messages)

            message_items = []
            for msg in messages:
                metadata = getattr(msg, "metadata_", None) or {}
                sender_name = None
                sender_avatar = None
                if (
                    msg.sender_type == MessageSenderType.AGENT.value
                    and msg.sender_id is not None
                ):
                    agent = agent_map.get(msg.sender_id)
                    if agent:
                        sender_name = ConversationService.visitor_agent_display_name(agent)
                        sender_avatar = agent.avatar
                elif msg.sender_type == MessageSenderType.VISITOR.value:
                    sender_name = visitor.name
                elif msg.sender_type == MessageSenderType.BOT.value:
                    sender_name = ConversationService._metadata_sender_name(msg.sender_type, metadata)

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
                agent_name = ConversationService.visitor_agent_display_name(conversation.agent)
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
                    len(visible_messages) >= VISITOR_HISTORY_MESSAGE_LIMIT
                    or len(visible_messages) > len(messages)
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
            include_internal=False,
        )

        agent_ids: set[int] = set()
        for messages in messages_by_conversation.values():
            for message in ConversationService._visitor_visible_messages(messages):
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
            visible_messages = ConversationService._visitor_visible_messages(raw_messages)
            remaining = max(VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT - consumed_messages, 0)
            messages = visible_messages[:remaining]
            consumed_messages += len(messages)

            message_items = []
            for msg in messages:
                metadata = getattr(msg, "metadata_", None) or {}
                sender_name = None
                sender_avatar = None
                if (
                    msg.sender_type == MessageSenderType.AGENT.value
                    and msg.sender_id is not None
                ):
                    agent = agent_map.get(msg.sender_id)
                    if agent:
                        sender_name = ConversationService.visitor_agent_display_name(agent)
                        sender_avatar = agent.avatar
                elif msg.sender_type == MessageSenderType.VISITOR.value:
                    sender_name = visitor.name
                elif msg.sender_type == MessageSenderType.BOT.value:
                    sender_name = ConversationService._metadata_sender_name(msg.sender_type, metadata)

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
                agent_name = ConversationService.visitor_agent_display_name(conversation.agent)
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
                    len(visible_messages) >= VISITOR_HISTORY_MESSAGE_LIMIT
                    or len(visible_messages) > len(messages)
                ),
            })

        return {"items": items, "has_more": has_more}

    @staticmethod
    async def get_unread_offline_replies_for_session(
        db: AsyncSession,
        visitor_context: dict,
        limit: int = VISITOR_UNREAD_OFFLINE_REPLY_LIMIT,
    ) -> dict:
        """Fetch converted offline-message conversations that still need customer display."""
        safe_limit = min(max(limit, 1), VISITOR_UNREAD_OFFLINE_REPLY_LIMIT)
        rows, has_more = await OfflineMessageRepository.list_customer_unread_replies(
            db,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
            limit=safe_limit,
        )
        rows = list(reversed(rows))
        conversations = [row.conversation for row in rows if row.conversation is not None]
        conversation_ids = [conversation.id for conversation in conversations]
        messages_by_conversation = await MessageRepository.get_recent_by_conversations(
            db,
            tenant_id=visitor_context["tenant_id"],
            conversation_ids=conversation_ids,
            per_conversation_limit=VISITOR_HISTORY_MESSAGE_LIMIT,
            include_internal=False,
        )

        agent_ids: set[int] = set()
        for messages in messages_by_conversation.values():
            for message in ConversationService._visitor_visible_messages(messages):
                if (
                    message.sender_type == MessageSenderType.AGENT.value
                    and message.sender_id is not None
                ):
                    agent_ids.add(message.sender_id)

        agents = await EmployeeRepository.get_by_ids(db, list(agent_ids))
        agent_map = {agent.id: agent for agent in agents}

        items = []
        consumed_messages = 0
        for row in rows:
            conversation = row.conversation
            if conversation is None:
                continue

            raw_messages = messages_by_conversation.get(conversation.id, [])
            visible_messages = ConversationService._visitor_visible_messages(raw_messages)
            remaining = max(VISITOR_HISTORY_TOTAL_MESSAGE_LIMIT - consumed_messages, 0)
            messages = visible_messages[:remaining]
            consumed_messages += len(messages)
            visitor = row.visitor or conversation.visitor

            message_items = []
            for msg in messages:
                metadata = getattr(msg, "metadata_", None) or {}
                sender_name = None
                sender_avatar = None
                if (
                    msg.sender_type == MessageSenderType.AGENT.value
                    and msg.sender_id is not None
                ):
                    agent = agent_map.get(msg.sender_id)
                    if agent:
                        sender_name = ConversationService.visitor_agent_display_name(agent)
                        sender_avatar = agent.avatar
                elif msg.sender_type == MessageSenderType.VISITOR.value and visitor:
                    sender_name = visitor.name
                elif msg.sender_type == MessageSenderType.BOT.value:
                    sender_name = ConversationService._metadata_sender_name(msg.sender_type, metadata)

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
                agent_name = ConversationService.visitor_agent_display_name(conversation.agent)
                agent_avatar = conversation.agent.avatar

            items.append({
                "conversation_public_id": conversation.public_id,
                "offline_message_public_id": row.public_id,
                "status": conversation.status,
                "started_at": conversation.started_at,
                "ended_at": conversation.ended_at,
                "last_message_at": conversation.last_message_at,
                "created_at": conversation.created_at,
                "agent_name": agent_name,
                "agent_avatar": agent_avatar,
                "customer_unread_at": row.customer_unread_at,
                "customer_unread_message_id": row.customer_unread_first_message_id,
                "offline_reply_unread": True,
                "messages": message_items,
                "messages_truncated": (
                    len(visible_messages) >= VISITOR_HISTORY_MESSAGE_LIMIT
                    or len(visible_messages) > len(messages)
                ),
            })

        return {"items": items, "has_more": has_more}

    @staticmethod
    async def mark_customer_read_for_session(
        db: AsyncSession,
        visitor_context: dict,
        conversation_public_id: str,
    ) -> dict:
        """Mark visitor-visible offline-message replies as read without touching agent unread state."""
        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        await OfflineMessageRepository.mark_customer_read_by_conversation(
            db,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
            conversation_id=conversation.id,
            read_at=datetime.now(timezone.utc),
        )
        return {"ok": True}

    @staticmethod
    async def get_workspace_visitor_history(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        roles: list[str] | None = None,
        before_id: int | None = None,
        limit: int = VISITOR_HISTORY_PAGE_SIZE,
        q: str | None = None,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        """Fetch read-only visitor history for the agent workspace."""
        current = await ConversationRepository.get_by_id(db, conversation_id)
        if not current or current.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        if principal is not None:
            await DataScopeService.assert_conversation_access(db, principal, current)
            history_agent_id, history_predicate = await DataScopeService.session_history_filters(
                db, principal
            )
        else:
            can_view_all_history = "admin" in (roles or ["agent"])
            if not can_view_all_history and current.agent_id != agent_id:
                raise ForbiddenError("No permission to view conversation history")
            history_agent_id = None if can_view_all_history else agent_id
            history_predicate = None

        if not current.visitor:
            return {"items": [], "has_more": False}

        safe_limit = min(max(limit, 1), VISITOR_HISTORY_PAGE_SIZE)
        keyword = (q or "").strip()
        if len(keyword) > 100:
            raise ValidationError("Search query is too long")
        conversations = await ConversationRepository.get_visitor_history(
            db,
            tenant_id=tenant_id,
            channel_id=None,
            visitor_id=current.visitor.id,
            current_conversation_id=current.id,
            before_id=before_id,
            agent_id=history_agent_id,
            keyword=keyword or None,
            limit=safe_limit + 1,
            scope_predicate=history_predicate,
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
                metadata = getattr(msg, "metadata_", None) or {}
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
                elif msg.sender_type == MessageSenderType.BOT.value:
                    sender_name = ConversationService._metadata_sender_name(msg.sender_type, metadata)

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
    async def search_workspace_visitor_messages(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        principal: EffectivePrincipal,
        q: str | None = None,
        before_id: int | None = None,
        limit: int = 30,
    ) -> dict:
        """Search visible text messages for the selected workspace visitor."""
        current = await ConversationRepository.get_by_id(db, conversation_id)
        if not current or current.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        await DataScopeService.assert_conversation_access(db, principal, current)

        if not current.visitor_id:
            return {"items": [], "total": 0, "has_more": False}

        keyword = (q or "").strip()
        if len(keyword) > 100:
            raise ValidationError("Search query is too long")
        safe_limit = min(max(limit, 1), 30)
        history_agent_id, history_predicate = await DataScopeService.session_history_filters(
            db,
            principal,
        )
        rows = await MessageRepository.search_workspace_visitor_messages(
            db,
            tenant_id=tenant_id,
            visitor_id=current.visitor_id,
            keyword=keyword or None,
            before_id=before_id,
            agent_id=history_agent_id,
            limit=safe_limit + 1,
            scope_predicate=history_predicate,
        )
        has_more = len(rows) > safe_limit
        if has_more:
            rows = rows[:safe_limit]

        agent_ids: set[int] = set()
        for message, _conversation in rows:
            if message.sender_type == MessageSenderType.AGENT.value and message.sender_id is not None:
                agent_ids.add(message.sender_id)
        agents = await EmployeeRepository.get_by_ids(db, list(agent_ids))
        agent_map = {agent.id: agent for agent in agents}

        items = []
        for message, conversation in rows:
            sender_name = None
            sender_avatar = None
            if message.sender_type == MessageSenderType.AGENT.value and message.sender_id is not None:
                agent = agent_map.get(message.sender_id)
                if agent:
                    sender_name = agent.display_name or agent.name
                    sender_avatar = agent.avatar
            elif message.sender_type == MessageSenderType.VISITOR.value:
                sender_name = conversation.visitor.name if conversation.visitor else current.visitor.name
            elif message.sender_type == MessageSenderType.BOT.value:
                sender_name = ConversationService._metadata_sender_name(
                    message.sender_type,
                    getattr(message, "metadata_", None) or {},
                )

            channel = None
            if conversation.channel:
                channel = {
                    "id": conversation.channel.id,
                    "name": conversation.channel.name,
                    "channel_type": conversation.channel.channel_type,
                }

            items.append({
                "id": message.id,
                "conversation_id": message.conversation_id,
                "sender_type": message.sender_type,
                "sender_id": message.sender_id,
                "sender_name": sender_name,
                "sender_avatar": sender_avatar,
                "content_type": message.content_type,
                "content": message.content,
                "created_at": message.created_at,
                "conversation": {
                    "id": conversation.id,
                    "share_code": conversation.share_code,
                    "status": conversation.status,
                    "started_at": conversation.started_at or conversation.created_at,
                    "channel": channel,
                },
            })

        return {"items": items, "total": len(items), "has_more": has_more}

    @staticmethod
    async def mark_read(db: AsyncSession, conversation_id: int) -> None:
        await ConversationRepository.reset_unread(db, conversation_id)
        logger.info("conversation_marked_read conversation_id=%s", conversation_id)
