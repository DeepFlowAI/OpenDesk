"""
Offline message service.
"""
import json
import logging
import random
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError, ValidationError
from app.enums import ConversationStatus, MessageContentType, MessageSenderType
from app.libs.storage import create_storage_client
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.offline_message import OfflineMessage, OfflineMessageEntry
from app.repositories.channel_repository import ChannelRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.offline_message_repository import OfflineMessageRepository
from app.repositories.user_repository import UserRepository
from app.schemas.channel import ChannelConfig
from app.schemas.permission import EffectivePrincipal
from app.services.agent_status_service import AgentStatusService
from app.services.channel_service import ChannelService
from app.services.conversation_file_service import (
    BLOCKED_CONVERSATION_FILE_EXTENSIONS,
    MAX_CONVERSATION_FILE_SIZE,
    TEMPORARY_URL_EXPIRES_SECONDS,
    ConversationFileService,
)
from app.services.conversation_service import ConversationService
from app.services.data_scope_service import DataScopeService, RESOURCE_OFFLINE_MESSAGE
from app.services.offline_message_realtime_service import OfflineMessageRealtimeService
from app.services.routing_service import RoutingService

logger = logging.getLogger(__name__)

_AVATAR_COLORS = [
    "#F87171", "#FB923C", "#FBBF24", "#34D399",
    "#60A5FA", "#818CF8", "#A78BFA", "#F472B6",
]
OFFLINE_MESSAGE_CONVERSATION_CREATED_TEXT = "客服已基于留言创建会话"
OFFLINE_MESSAGE_CONVERSATION_CREATED_EVENT = "offline_message_conversation_created"
OFFLINE_MESSAGE_PROMPT_EVENT = "leave_message_prompt"
OFFLINE_MESSAGE_ASSIGN_SELF_PERMISSION = "chat.queue.assign_self"
OFFLINE_MESSAGE_ASSIGN_OTHER_PERMISSION = "chat.queue.assign_other"
VISITOR_ENVIRONMENT_METADATA_KEY = "visitor_environment"


class OfflineMessageService:
    @staticmethod
    def _metadata(row) -> dict:
        return getattr(row, "metadata_", None) or {}

    @staticmethod
    def _visitor_environment_metadata(
        *,
        visitor_system: object = None,
        visitor_browser: object = None,
        visitor_ip: object = None,
    ) -> dict:
        data = ConversationService._visitor_environment_data(
            visitor_system=visitor_system,
            visitor_browser=visitor_browser,
            visitor_ip=visitor_ip,
        )
        environment = {
            "system": data.get("visitor_system"),
            "browser": data.get("visitor_browser"),
            "ip": data.get("visitor_ip"),
        }
        return {key: value for key, value in environment.items() if value is not None}

    @staticmethod
    def _merge_visitor_environment_metadata(
        metadata: dict | None,
        *,
        visitor_system: object = None,
        visitor_browser: object = None,
        visitor_ip: object = None,
    ) -> dict:
        base = dict(metadata) if isinstance(metadata, dict) else {}
        environment = OfflineMessageService._visitor_environment_metadata(
            visitor_system=visitor_system,
            visitor_browser=visitor_browser,
            visitor_ip=visitor_ip,
        )
        if not environment:
            return base
        existing = base.get(VISITOR_ENVIRONMENT_METADATA_KEY)
        base[VISITOR_ENVIRONMENT_METADATA_KEY] = {
            **(existing if isinstance(existing, dict) else {}),
            **environment,
        }
        return base

    @staticmethod
    def _conversation_environment_from_metadata(metadata: dict | None) -> dict:
        if not isinstance(metadata, dict):
            return {}
        environment = metadata.get(VISITOR_ENVIRONMENT_METADATA_KEY)
        if not isinstance(environment, dict):
            return {}
        return ConversationService._visitor_environment_data(
            visitor_system=environment.get("system"),
            visitor_browser=environment.get("browser"),
            visitor_ip=environment.get("ip"),
        )

    @staticmethod
    def _brief(row: OfflineMessage) -> dict:
        return {
            "id": row.id,
            "public_id": row.public_id,
            "tenant_id": row.tenant_id,
            "status": row.status,
            "visitor": row.visitor,
            "channel": row.channel,
            "target_group": row.target_group,
            "conversation": row.conversation,
            "visitor_external_id": row.visitor_external_id,
            "visitor_name": row.visitor_name,
            "handled_by_id": row.handled_by_id,
            "handled_at": row.handled_at,
            "last_message_at": row.last_message_at,
            "last_message_preview": row.last_message_preview,
            "message_count": row.message_count,
            "metadata": OfflineMessageService._metadata(row),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def _entry_payload(entry: OfflineMessageEntry, row: OfflineMessage) -> dict:
        sender_name = None
        sender_avatar = None
        if entry.sender_type == MessageSenderType.VISITOR.value and row.visitor:
            sender_name = row.visitor.name
        return {
            "id": entry.id,
            "offline_message_id": entry.offline_message_id,
            "sender_type": entry.sender_type,
            "sender_id": entry.sender_id,
            "sender_name": sender_name,
            "sender_avatar": sender_avatar,
            "content_type": entry.content_type,
            "content": entry.content,
            "metadata": OfflineMessageService._metadata(entry),
            "created_at": entry.created_at,
        }

    @staticmethod
    def _assign_permission_flags(principal: EffectivePrincipal) -> tuple[bool, bool]:
        can_assign_self = principal.has_permission(OFFLINE_MESSAGE_ASSIGN_SELF_PERMISSION)
        can_assign_other = (
            principal.has_permission(OFFLINE_MESSAGE_ASSIGN_OTHER_PERMISSION)
            and DataScopeService.get_scope(principal, RESOURCE_OFFLINE_MESSAGE) != "self"
        )
        return can_assign_self, can_assign_other

    @staticmethod
    def _assignable_agent_ids(
        principal: EffectivePrincipal,
        scope: str,
        peer_employee_ids: list[int],
    ) -> set[int] | None:
        if scope == "all":
            return None
        return set(peer_employee_ids) | {principal.user_id}

    @staticmethod
    async def _assert_assign_target_allowed(
        db: AsyncSession,
        principal: EffectivePrincipal,
        agent_id: int,
    ) -> None:
        if not await EmployeeRepository.has_effective_permission(
            db,
            principal.tenant_id,
            agent_id,
            "chat.workspace.use",
        ):
            raise NotFoundError("Agent not found")
        scope = DataScopeService.get_scope(principal, RESOURCE_OFFLINE_MESSAGE)
        if scope == "self" and agent_id != principal.user_id:
            raise ForbiddenError("Permission denied")
        if scope != "all" and agent_id != principal.user_id:
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            allowed_ids = OfflineMessageService._assignable_agent_ids(principal, scope, peer_ids)
            if allowed_ids is not None and agent_id not in allowed_ids:
                raise ForbiddenError("Permission denied")

    @staticmethod
    async def _append_assignment_internal_note(
        db: AsyncSession,
        principal: EffectivePrincipal,
        conversation: Conversation,
        reason: str | None,
    ) -> None:
        note = (reason or "").strip()
        if not note:
            return
        await ConversationService.send_message(
            db,
            conversation_id=conversation.id,
            sender_type=MessageSenderType.AGENT.value,
            sender_id=principal.user_id,
            content_type=MessageContentType.INTERNAL_NOTE.value,
            content=note,
            tenant_id=principal.tenant_id,
        )

    @staticmethod
    def _public_entry_payload(entry: OfflineMessageEntry, row: OfflineMessage) -> dict:
        metadata = {
            **OfflineMessageService._metadata(entry),
            "offline_message_public_id": row.public_id,
        }
        return {
            "id": entry.id,
            "conversation_public_id": row.public_id,
            "sender_type": entry.sender_type,
            "sender_id": entry.sender_id,
            "sender_name": row.visitor.name if row.visitor else row.visitor_name,
            "sender_avatar": None,
            "content_type": entry.content_type,
            "content": entry.content,
            "metadata": metadata,
            "created_at": entry.created_at,
            "event_type": None,
            "satisfaction_record_id": None,
            "config_version": None,
        }

    @staticmethod
    def _build_leave_message_prompt_entry(
        row: OfflineMessage,
        leave_message_prompt: str,
    ) -> OfflineMessageEntry | None:
        prompt = ConversationService._html_to_plain_text(leave_message_prompt).strip()
        if not prompt:
            return None
        return OfflineMessageEntry(
            tenant_id=row.tenant_id,
            offline_message_id=row.id,
            sender_type=MessageSenderType.SYSTEM.value,
            sender_id=None,
            content_type=MessageContentType.SYSTEM.value,
            content=prompt,
            metadata_={
                "offline_message_public_id": row.public_id,
                "offline_message_event": OFFLINE_MESSAGE_PROMPT_EVENT,
            },
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    async def _assert_view_access(
        db: AsyncSession,
        principal: EffectivePrincipal,
        row: OfflineMessage,
    ) -> None:
        if row.tenant_id != principal.tenant_id:
            logger.warning(
                "offline_message_forbidden tenant_id=%s user_id=%s offline_message_id=%s "
                "row_tenant_id=%s reason=tenant_mismatch",
                principal.tenant_id,
                principal.user_id,
                row.id,
                row.tenant_id,
            )
            raise NotFoundError("Offline message not found")
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        try:
            DataScopeService.assert_offline_message_in_scope(principal, row, peer_ids)
        except ForbiddenError:
            logger.warning(
                "offline_message_forbidden tenant_id=%s user_id=%s offline_message_id=%s "
                "target_group_id=%s reason=scope_filtered",
                principal.tenant_id,
                principal.user_id,
                row.id,
                row.target_group_id,
            )
            raise

    @staticmethod
    async def _get_for_session(
        db: AsyncSession,
        public_id: str,
        visitor_context: dict,
    ) -> OfflineMessage:
        row = await OfflineMessageRepository.get_by_public_id(db, public_id)
        if not row:
            raise NotFoundError("Offline message not found")
        if row.tenant_id != visitor_context["tenant_id"]:
            raise NotFoundError("Offline message not found")
        if row.channel_id != visitor_context["channel_id"]:
            raise NotFoundError("Offline message not found")
        if row.visitor_external_id != visitor_context["visitor_external_id"]:
            raise NotFoundError("Offline message not found")
        return row

    @staticmethod
    async def _get_for_session_for_update(
        db: AsyncSession,
        public_id: str,
        visitor_context: dict,
    ) -> OfflineMessage:
        row = await OfflineMessageRepository.get_by_public_id_for_update(db, public_id)
        if not row:
            raise NotFoundError("Offline message not found")
        if row.tenant_id != visitor_context["tenant_id"]:
            raise NotFoundError("Offline message not found")
        if row.channel_id != visitor_context["channel_id"]:
            raise NotFoundError("Offline message not found")
        if row.visitor_external_id != visitor_context["visitor_external_id"]:
            raise NotFoundError("Offline message not found")
        return row

    @staticmethod
    async def _ensure_leave_message_allowed(
        db: AsyncSession,
        r: aioredis.Redis,
        channel_id: int,
        visitor_id: int | None,
    ) -> tuple[object, ChannelConfig, dict, int | None]:
        channel = await ChannelRepository.get_by_id(db, channel_id)
        if not channel:
            raise NotFoundError("Channel not found")
        config = ChannelConfig.model_validate(channel.config or {})
        gate = await ChannelService.check_human_service_gate(db, channel, config)
        if gate["can_start_conversation"] or gate["reason"] != "outside_service_hours":
            raise BusinessError("Leave message is only available outside service hours")
        if config.outside_service_hours_strategy != "leave_message":
            raise BusinessError("Leave message is not enabled for this channel")

        group_id, _, _ = await RoutingService.route_conversation(
            db,
            channel.tenant_id,
            channel.id,
            r,
            visitor_id=visitor_id,
        )
        return channel, config, gate, group_id

    @staticmethod
    async def create_or_continue_for_session(
        db: AsyncSession,
        r: aioredis.Redis,
        visitor_context: dict,
        *,
        visitor_name: str | None = None,
        metadata: dict | None = None,
        visitor_system: object = None,
        visitor_browser: object = None,
    ) -> dict:
        tenant_id, channel_id, visitor_external_id, visitor, group_id, row_metadata, _leave_message_prompt = (
            await OfflineMessageService._prepare_leave_message_session(
                db,
                r,
                visitor_context,
                visitor_name=visitor_name,
                metadata=metadata,
                visitor_system=visitor_system,
                visitor_browser=visitor_browser,
            )
        )

        row = await OfflineMessageRepository.get_pending_by_visitor(
            db,
            tenant_id=tenant_id,
            channel_id=channel_id,
            visitor_external_id=visitor_external_id,
        )
        if not row:
            row = await OfflineMessageRepository.create(db, {
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "visitor_id": visitor.id,
                "visitor_external_id": visitor_external_id,
                "visitor_name": visitor.name,
                "target_group_id": group_id,
                "status": "pending",
                "metadata_": row_metadata,
            })
        else:
            existing_metadata = {
                **OfflineMessageService._metadata(row),
                **(metadata if isinstance(metadata, dict) else {}),
            }
            updated_metadata = OfflineMessageService._merge_visitor_environment_metadata(
                existing_metadata,
                visitor_system=visitor_system,
                visitor_browser=visitor_browser,
                visitor_ip=visitor_context.get("visitor_ip"),
            )
            if OfflineMessageService._metadata(row) != updated_metadata:
                row.metadata_ = updated_metadata
                await db.commit()
        return await OfflineMessageService.get_public_response(
            db,
            row.public_id,
            visitor_context,
            limit=200,
        )

    @staticmethod
    async def _prepare_leave_message_session(
        db: AsyncSession,
        r: aioredis.Redis,
        visitor_context: dict,
        *,
        visitor_name: str | None = None,
        metadata: dict | None = None,
        visitor_system: object = None,
        visitor_browser: object = None,
    ) -> tuple[int, int, str, object, int | None, dict, str]:
        tenant_id = int(visitor_context["tenant_id"])
        channel_id = int(visitor_context["channel_id"])
        visitor_external_id = visitor_context["visitor_external_id"]
        auto_name = visitor_name or visitor_context.get("visitor_name") or f"访客 {visitor_external_id[:6]}"
        base_metadata = metadata or visitor_context.get("metadata") or {}
        row_metadata = OfflineMessageService._merge_visitor_environment_metadata(
            base_metadata,
            visitor_system=visitor_system,
            visitor_browser=visitor_browser,
            visitor_ip=visitor_context.get("visitor_ip"),
        )

        visitor, _ = await UserRepository.get_or_create(
            db,
            tenant_id,
            visitor_external_id,
            defaults={
                "name": auto_name,
                "avatar_color": random.choice(_AVATAR_COLORS),
                "channel_id": channel_id,
                "metadata_": base_metadata,
            },
        )
        update_data = {}
        if auto_name and visitor.name != auto_name:
            update_data["name"] = auto_name
        merged_metadata = base_metadata
        if merged_metadata:
            update_data["metadata_"] = {**(visitor.metadata_ or {}), **merged_metadata}
        if update_data:
            visitor = await UserRepository.update(db, visitor, update_data)

        _channel, config, _gate, group_id = await OfflineMessageService._ensure_leave_message_allowed(
            db,
            r,
            channel_id,
            visitor.id,
        )
        return tenant_id, channel_id, visitor_external_id, visitor, group_id, row_metadata, config.leave_message_prompt

    @staticmethod
    async def get_current_for_session(
        db: AsyncSession,
        visitor_context: dict,
        *,
        before_id: int | None = None,
        limit: int = 50,
    ) -> dict | None:
        row = await OfflineMessageRepository.get_pending_by_visitor(
            db,
            tenant_id=int(visitor_context["tenant_id"]),
            channel_id=int(visitor_context["channel_id"]),
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        if not row:
            return None
        return await OfflineMessageService.get_public_response(
            db,
            row.public_id,
            visitor_context,
            before_id=before_id,
            limit=limit,
        )

    @staticmethod
    async def create_or_continue_and_send_for_session(
        db: AsyncSession,
        r: aioredis.Redis,
        visitor_context: dict,
        *,
        content_type: str,
        content: str,
        visitor_system: object = None,
        visitor_browser: object = None,
    ) -> dict:
        if content_type not in {MessageContentType.TEXT.value, MessageContentType.IMAGE.value, MessageContentType.FILE.value}:
            raise ValidationError("Unsupported message type")
        normalized_content = ConversationService.validate_message_content(content_type, content)
        tenant_id, channel_id, visitor_external_id, visitor, group_id, row_metadata, leave_message_prompt = (
            await OfflineMessageService._prepare_leave_message_session(
                db,
                r,
                visitor_context,
                visitor_system=visitor_system,
                visitor_browser=visitor_browser,
            )
        )
        row = await OfflineMessageRepository.get_pending_by_visitor_for_update(
            db,
            tenant_id=tenant_id,
            channel_id=channel_id,
            visitor_external_id=visitor_external_id,
        )
        created = False
        try:
            if not row:
                row = OfflineMessage(
                    public_id=await OfflineMessageRepository.generate_unique_public_id(db),
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    visitor_id=visitor.id,
                    visitor_external_id=visitor_external_id,
                    visitor_name=visitor.name,
                    target_group_id=group_id,
                    status="pending",
                    message_count=0,
                    metadata_=row_metadata,
                )
                db.add(row)
                await db.flush()
                created = True
            elif row.status != "pending":
                raise BusinessError("Offline message has already been converted")
            else:
                updated_metadata = OfflineMessageService._merge_visitor_environment_metadata(
                    OfflineMessageService._metadata(row),
                    visitor_system=visitor_system,
                    visitor_browser=visitor_browser,
                    visitor_ip=visitor_context.get("visitor_ip"),
                )
                if OfflineMessageService._metadata(row) != updated_metadata:
                    row.metadata_ = updated_metadata

            created_entries: list[OfflineMessageEntry] = []
            if created:
                prompt_msg = OfflineMessageService._build_leave_message_prompt_entry(
                    row,
                    leave_message_prompt,
                )
                if prompt_msg:
                    db.add(prompt_msg)
                    await db.flush()
                    created_entries.append(prompt_msg)

            msg = OfflineMessageEntry(
                tenant_id=row.tenant_id,
                offline_message_id=row.id,
                sender_type=MessageSenderType.VISITOR.value,
                sender_id=row.visitor_id,
                content_type=content_type,
                content=normalized_content,
                metadata_={"offline_message_public_id": row.public_id},
                created_at=datetime.now(timezone.utc),
            )
            db.add(msg)
            await db.flush()
            created_entries.append(msg)
            row.last_message_preview = ConversationService.build_message_preview(content_type, normalized_content)
            row.last_message_at = msg.created_at
            row.message_count = (row.message_count or 0) + len(created_entries)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        row = await OfflineMessageRepository.get_by_id(db, row.id)
        if not row:
            raise NotFoundError("Offline message not found")
        await OfflineMessageRealtimeService.emit_updated(
            row,
            action="created" if created else "message",
        )
        return {
            "ok": True,
            "offline_message_public_id": row.public_id,
            "message": OfflineMessageService._public_entry_payload(msg, row),
            "messages": [
                OfflineMessageService._public_entry_payload(entry, row)
                for entry in created_entries
            ],
        }

    @staticmethod
    async def create_or_continue_and_send_file_for_session(
        db: AsyncSession,
        r: aioredis.Redis,
        visitor_context: dict,
        file: UploadFile,
        *,
        visitor_system: object = None,
        visitor_browser: object = None,
    ) -> dict:
        tenant_id, channel_id, visitor_external_id, visitor, group_id, row_metadata, leave_message_prompt = (
            await OfflineMessageService._prepare_leave_message_session(
                db,
                r,
                visitor_context,
                visitor_system=visitor_system,
                visitor_browser=visitor_browser,
            )
        )
        row = await OfflineMessageRepository.get_pending_by_visitor_for_update(
            db,
            tenant_id=tenant_id,
            channel_id=channel_id,
            visitor_external_id=visitor_external_id,
        )
        created = False
        try:
            if not row:
                row = OfflineMessage(
                    public_id=await OfflineMessageRepository.generate_unique_public_id(db),
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    visitor_id=visitor.id,
                    visitor_external_id=visitor_external_id,
                    visitor_name=visitor.name,
                    target_group_id=group_id,
                    status="pending",
                    message_count=0,
                    metadata_=row_metadata,
                )
                db.add(row)
                await db.flush()
                created = True
            elif row.status != "pending":
                raise BusinessError("Offline message has already been converted")
            else:
                updated_metadata = OfflineMessageService._merge_visitor_environment_metadata(
                    OfflineMessageService._metadata(row),
                    visitor_system=visitor_system,
                    visitor_browser=visitor_browser,
                    visitor_ip=visitor_context.get("visitor_ip"),
                )
                if OfflineMessageService._metadata(row) != updated_metadata:
                    row.metadata_ = updated_metadata

            created_entries: list[OfflineMessageEntry] = []
            if created:
                prompt_msg = OfflineMessageService._build_leave_message_prompt_entry(
                    row,
                    leave_message_prompt,
                )
                if prompt_msg:
                    db.add(prompt_msg)
                    await db.flush()
                    created_entries.append(prompt_msg)

            uploaded = await OfflineMessageService._upload_file(db, row, file)
            content_type = MessageContentType.IMAGE.value if uploaded["mime_type"].startswith("image/") else MessageContentType.FILE.value
            content = json.dumps({
                "schema_version": uploaded["schema_version"],
                "file_id": uploaded["file_id"],
                "name": uploaded["name"],
                "size": uploaded["size"],
                "mime_type": uploaded["mime_type"],
            })
            normalized_content = ConversationService.validate_message_content(content_type, content)
            msg = OfflineMessageEntry(
                tenant_id=row.tenant_id,
                offline_message_id=row.id,
                sender_type=MessageSenderType.VISITOR.value,
                sender_id=row.visitor_id,
                content_type=content_type,
                content=normalized_content,
                metadata_={"offline_message_public_id": row.public_id},
                created_at=datetime.now(timezone.utc),
            )
            db.add(msg)
            await db.flush()
            created_entries.append(msg)
            row.last_message_preview = ConversationService.build_message_preview(content_type, normalized_content)
            row.last_message_at = msg.created_at
            row.message_count = (row.message_count or 0) + len(created_entries)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        row = await OfflineMessageRepository.get_by_id(db, row.id)
        if not row:
            raise NotFoundError("Offline message not found")
        await OfflineMessageRealtimeService.emit_updated(
            row,
            action="created" if created else "message",
        )
        return {
            "ok": True,
            "offline_message_public_id": row.public_id,
            "message": OfflineMessageService._public_entry_payload(msg, row),
            "messages": [
                OfflineMessageService._public_entry_payload(entry, row)
                for entry in created_entries
            ],
        }

    @staticmethod
    async def get_public_response(
        db: AsyncSession,
        public_id: str,
        visitor_context: dict,
        *,
        before_id: int | None = None,
        limit: int = 50,
    ) -> dict:
        row = await OfflineMessageService._get_for_session(db, public_id, visitor_context)
        entries, has_more = await OfflineMessageRepository.list_messages(
            db,
            row.id,
            before_id=before_id,
            limit=limit,
        )
        return {
            "offline_message_public_id": row.public_id,
            "status": row.status,
            "messages": [OfflineMessageService._public_entry_payload(entry, row) for entry in entries],
            "has_more": has_more,
            "conversation_public_id": row.conversation.public_id if row.conversation else None,
        }

    @staticmethod
    async def send_public_message(
        db: AsyncSession,
        public_id: str,
        visitor_context: dict,
        *,
        content_type: str,
        content: str,
        visitor_system: object = None,
        visitor_browser: object = None,
    ) -> dict:
        if content_type not in {MessageContentType.TEXT.value, MessageContentType.IMAGE.value, MessageContentType.FILE.value}:
            raise ValidationError("Unsupported message type")

        normalized_content = ConversationService.validate_message_content(content_type, content)
        try:
            row = await OfflineMessageService._get_for_session_for_update(db, public_id, visitor_context)
            if row.status != "pending":
                raise BusinessError("Offline message has already been converted")
            row_metadata = OfflineMessageService._merge_visitor_environment_metadata(
                OfflineMessageService._metadata(row),
                visitor_system=visitor_system,
                visitor_browser=visitor_browser,
                visitor_ip=visitor_context.get("visitor_ip"),
            )
            if OfflineMessageService._metadata(row) != row_metadata:
                row.metadata_ = row_metadata

            msg = OfflineMessageEntry(
                tenant_id=row.tenant_id,
                offline_message_id=row.id,
                sender_type=MessageSenderType.VISITOR.value,
                sender_id=row.visitor_id,
                content_type=content_type,
                content=normalized_content,
                metadata_={"offline_message_public_id": row.public_id},
                created_at=datetime.now(timezone.utc),
            )
            db.add(msg)
            await db.flush()
            row.last_message_preview = ConversationService.build_message_preview(content_type, normalized_content)
            row.last_message_at = msg.created_at
            row.message_count = (row.message_count or 0) + 1
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        row = await OfflineMessageRepository.get_by_id(db, row.id)
        if not row:
            raise NotFoundError("Offline message not found")
        await OfflineMessageRealtimeService.emit_updated(row, action="message")
        return OfflineMessageService._public_entry_payload(msg, row)

    @staticmethod
    async def list_for_agent(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        status: str | None = "pending",
        before_id: int | None = None,
        limit: int = 50,
    ) -> dict:
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        predicate = DataScopeService.build_offline_message_predicate(principal, peer_ids)
        rows, has_more = await OfflineMessageRepository.list_by_tenant(
            db,
            tenant_id=principal.tenant_id,
            status=status,
            before_id=before_id,
            limit=limit,
            scope_predicate=predicate,
        )
        return {
            "items": [OfflineMessageService._brief(row) for row in rows],
            "has_more": has_more,
            "total": None,
        }

    @staticmethod
    async def count_for_agent(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        status: str | None = "pending",
    ) -> dict:
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        predicate = DataScopeService.build_offline_message_predicate(principal, peer_ids)
        total = await OfflineMessageRepository.count_by_tenant(
            db,
            tenant_id=principal.tenant_id,
            status=status,
            scope_predicate=predicate,
        )
        return {"total": total}

    @staticmethod
    async def get_for_agent(
        db: AsyncSession,
        principal: EffectivePrincipal,
        offline_message_id: int,
        *,
        before_id: int | None = None,
        limit: int = 100,
    ) -> dict:
        row = await OfflineMessageRepository.get_by_id(db, offline_message_id)
        if not row:
            raise NotFoundError("Offline message not found")
        await OfflineMessageService._assert_view_access(db, principal, row)
        entries, has_more = await OfflineMessageRepository.list_messages(
            db,
            row.id,
            before_id=before_id,
            limit=limit,
        )
        can_assign_self, can_assign_other = OfflineMessageService._assign_permission_flags(principal)
        return {
            **OfflineMessageService._brief(row),
            "messages": [OfflineMessageService._entry_payload(entry, row) for entry in entries],
            "has_more_messages": has_more,
            "can_assign_self": can_assign_self,
            "can_assign_other": can_assign_other,
        }

    @staticmethod
    async def create_conversation(
        db: AsyncSession,
        r: aioredis.Redis,
        principal: EffectivePrincipal,
        offline_message_id: int,
        *,
        reason: str | None = None,
    ) -> dict:
        if not principal.has_permission(OFFLINE_MESSAGE_ASSIGN_SELF_PERMISSION):
            raise ForbiddenError("Permission denied")
        return await OfflineMessageService._convert_to_conversation(
            db,
            r,
            principal,
            offline_message_id,
            principal.user_id,
            reason=reason,
        )

    @staticmethod
    async def assign_to_agent(
        db: AsyncSession,
        r: aioredis.Redis,
        principal: EffectivePrincipal,
        offline_message_id: int,
        agent_id: int,
        *,
        reason: str | None = None,
    ) -> dict:
        if not principal.has_permission(OFFLINE_MESSAGE_ASSIGN_OTHER_PERMISSION):
            raise ForbiddenError("Permission denied")
        scope = DataScopeService.get_scope(principal, RESOURCE_OFFLINE_MESSAGE)
        if scope == "self":
            raise ForbiddenError("Permission denied")
        await OfflineMessageService._assert_assign_target_allowed(db, principal, agent_id)
        return await OfflineMessageService._convert_to_conversation(
            db,
            r,
            principal,
            offline_message_id,
            agent_id,
            reason=reason,
        )

    @staticmethod
    async def _convert_to_conversation(
        db: AsyncSession,
        r: aioredis.Redis,
        principal: EffectivePrincipal,
        offline_message_id: int,
        agent_id: int,
        *,
        reason: str | None = None,
    ) -> dict:
        copied_messages: list[Message] = []
        try:
            row = await OfflineMessageRepository.get_by_id_for_update(db, offline_message_id)
            if not row:
                raise NotFoundError("Offline message not found")
            await OfflineMessageService._assert_view_access(db, principal, row)
            if row.status != "pending":
                raise BusinessError("Offline message has already been converted")
            if not row.messages:
                raise ValidationError("Offline message has no content")
            if not row.visitor_id:
                raise ValidationError("Offline message visitor is missing")

            existing = await ConversationRepository.get_active_visitor_conversation(
                db,
                tenant_id=row.tenant_id,
                visitor_id=row.visitor_id,
                channel_id=row.channel_id,
            )
            reused_existing_conversation = existing is not None
            if existing:
                if existing.agent_id != agent_id:
                    raise BusinessError("Visitor already has an active conversation")
                conversation = existing
            else:
                now = datetime.now(timezone.utc)
                environment_data = (
                    OfflineMessageService._conversation_environment_from_metadata(
                        OfflineMessageService._metadata(row)
                    )
                    if ConversationService._is_web_channel(getattr(row, "channel", None))
                    else {}
                )
                conversation = Conversation(
                    public_id=await ConversationRepository.generate_unique_public_id(db),
                    share_code=await ConversationRepository.generate_unique_share_code(db),
                    tenant_id=row.tenant_id,
                    visitor_id=row.visitor_id,
                    channel_id=row.channel_id,
                    group_id=row.target_group_id,
                    agent_id=agent_id,
                    status=ConversationStatus.ACTIVE.value,
                    started_at=now,
                    unread_count=1,
                    **environment_data,
                )
                db.add(conversation)
                await db.flush()

            for entry in row.messages:
                metadata = {
                    **OfflineMessageService._metadata(entry),
                    "offline_message_public_id": row.public_id,
                    "offline_message_entry_id": entry.id,
                }
                msg = Message(
                    tenant_id=row.tenant_id,
                    conversation_id=conversation.id,
                    sender_type=entry.sender_type,
                    sender_id=entry.sender_id,
                    content_type=entry.content_type,
                    content=entry.content,
                    metadata_=metadata,
                    created_at=entry.created_at,
                )
                db.add(msg)
                copied_messages.append(msg)
            await db.flush()

            event_time = datetime.now(timezone.utc)
            system_msg = Message(
                tenant_id=row.tenant_id,
                conversation_id=conversation.id,
                sender_type=MessageSenderType.SYSTEM.value,
                content_type=MessageContentType.SYSTEM.value,
                content=OFFLINE_MESSAGE_CONVERSATION_CREATED_TEXT,
                metadata_={
                    "event_type": OFFLINE_MESSAGE_CONVERSATION_CREATED_EVENT,
                    "offline_message_public_id": row.public_id,
                    "offline_message_id": row.id,
                },
                created_at=event_time,
            )
            db.add(system_msg)
            await db.flush()
            copied_messages.append(system_msg)

            last_msg = copied_messages[-1]
            conversation.last_message_preview = ConversationService.build_message_preview(
                last_msg.content_type,
                last_msg.content,
            )
            conversation.last_message_at = last_msg.created_at or event_time
            row.status = "converted"
            row.conversation_id = conversation.id
            row.handled_by_id = principal.user_id
            row.handled_at = datetime.now(timezone.utc)
            await OfflineMessageService._append_assignment_internal_note(
                db,
                principal,
                conversation,
                reason,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if not reused_existing_conversation:
            await AgentStatusService.increment_count(r, row.tenant_id, agent_id)
        row = await OfflineMessageRepository.get_by_id(db, offline_message_id)
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        if not row or not conversation:
            raise NotFoundError("Converted offline message not found")
        await OfflineMessageRealtimeService.emit_updated(row, action="converted")
        logger.info(
            "offline_message_converted tenant_id=%s user_id=%s target_agent_id=%s offline_message_id=%s "
            "conversation_id=%s copied_messages=%d reused_existing=%s",
            row.tenant_id,
            principal.user_id,
            agent_id,
            row.id,
            conversation.id,
            len(copied_messages),
            reused_existing_conversation,
        )
        assigned_employee = await EmployeeRepository.get_by_id(db, agent_id)
        message_payloads = []
        for msg in copied_messages:
            metadata = msg.metadata_ or {}
            message_payloads.append({
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "sender_type": msg.sender_type,
                "sender_id": msg.sender_id,
                "sender_name": row.visitor.name if msg.sender_type == MessageSenderType.VISITOR.value and row.visitor else None,
                "sender_avatar": None,
                "content_type": msg.content_type,
                "content": msg.content,
                "metadata": metadata,
                "created_at": msg.created_at,
                "event_type": metadata.get("event_type"),
                "satisfaction_record_id": metadata.get("satisfaction_record_id"),
                "config_version": metadata.get("config_version"),
            })
        if assigned_employee and conversation:
            conversation.agent = assigned_employee
        return {
            "offline_message": OfflineMessageService._brief(row),
            "conversation": conversation,
            "messages": message_payloads,
            "assigned_to_current_user": agent_id == principal.user_id,
            "assigned_agent": assigned_employee,
            "reused_existing_conversation": reused_existing_conversation,
        }

    @staticmethod
    async def _upload_file(
        db: AsyncSession,
        row: OfflineMessage,
        file: UploadFile,
    ) -> dict:
        raw_name = file.filename or "upload"
        ext = ConversationFileService._extension(raw_name)
        if ext in BLOCKED_CONVERSATION_FILE_EXTENSIONS:
            raise ValidationError(f"File type .{ext} is not allowed for security reasons")

        data = await file.read()
        if not data:
            raise ValidationError("File is empty")
        if len(data) > MAX_CONVERSATION_FILE_SIZE:
            raise ValidationError("File size exceeds 100MB limit")

        safe_ext = ext if ext and ext not in BLOCKED_CONVERSATION_FILE_EXTENSIONS else "bin"
        date_prefix = datetime.now().strftime("%Y%m%d")
        key = f"offline-message-files/{row.tenant_id}/{row.id}/{date_prefix}/{uuid.uuid4().hex}.{safe_ext}"

        storage = create_storage_client()
        content_type = file.content_type or "application/octet-stream"
        ConversationFileService._validate_magic_number(content_type, data)
        await storage.upload(key, data, content_type=content_type)

        file_id = ConversationFileService.encode_file_id(key)
        access_url = await OfflineMessageService.get_temporary_url(
            db,
            row,
            file_id=file_id,
            download_name=raw_name,
            download=False,
        )
        return {
            "schema_version": 1,
            "file_id": file_id,
            "name": raw_name,
            "size": len(data),
            "mime_type": content_type,
            "access_url": access_url["url"],
        }

    @staticmethod
    async def upload_public_file(
        db: AsyncSession,
        public_id: str,
        visitor_context: dict,
        file: UploadFile,
    ) -> dict:
        try:
            row = await OfflineMessageService._get_for_session_for_update(db, public_id, visitor_context)
            if row.status != "pending":
                raise BusinessError("Offline message has already been converted")
            uploaded = await OfflineMessageService._upload_file(db, row, file)
            await db.commit()
            return uploaded
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def get_temporary_url(
        db: AsyncSession,
        row: OfflineMessage,
        *,
        file_id: str,
        download_name: str | None = None,
        download: bool = False,
    ) -> dict:
        key = ConversationFileService.decode_file_id(file_id)
        expected_prefix = f"offline-message-files/{row.tenant_id}/{row.id}/"
        if not key.startswith(expected_prefix):
            raise ValidationError("File does not belong to offline message")

        storage = create_storage_client()
        url = await storage.get_temporary_url(
            key,
            expires_seconds=TEMPORARY_URL_EXPIRES_SECONDS,
            download_name=ConversationFileService._safe_download_name(download_name or "download") if download else None,
        )
        return {"url": url, "expires_seconds": TEMPORARY_URL_EXPIRES_SECONDS}

    @staticmethod
    async def get_temporary_url_for_public(
        db: AsyncSession,
        public_id: str,
        visitor_context: dict,
        *,
        file_id: str,
        download_name: str | None = None,
        download: bool = False,
    ) -> dict:
        row = await OfflineMessageService._get_for_session(db, public_id, visitor_context)
        return await OfflineMessageService.get_temporary_url(
            db,
            row,
            file_id=file_id,
            download_name=download_name,
            download=download,
        )

    @staticmethod
    async def get_temporary_url_for_agent(
        db: AsyncSession,
        principal: EffectivePrincipal,
        offline_message_id: int,
        *,
        file_id: str,
        download_name: str | None = None,
        download: bool = False,
    ) -> dict:
        row = await OfflineMessageRepository.get_by_id(db, offline_message_id)
        if not row:
            raise NotFoundError("Offline message not found")
        await OfflineMessageService._assert_view_access(db, principal, row)
        return await OfflineMessageService.get_temporary_url(
            db,
            row,
            file_id=file_id,
            download_name=download_name,
            download=download,
        )

    @staticmethod
    def conversation_file_id_belongs_to_offline_message(file_id: str, tenant_id: int) -> bool:
        try:
            key = ConversationFileService.decode_file_id(file_id)
        except ValidationError:
            return False
        return key.startswith(f"offline-message-files/{tenant_id}/")
