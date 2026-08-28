"""Visitor form-message configuration and atomic ticket submission service."""

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import re
import uuid
from urllib.parse import urlparse

from fastapi import UploadFile
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import BusinessError, ConflictError, NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.enums import ConversationStatus, QueueTaskStatus, QueueType
from app.models.conversation import Conversation
from app.libs.storage import create_storage_client
from app.models.channel_form_config_version import ChannelFormConfigVersion
from app.repositories.channel_form_config_version_repository import (
    ChannelFormConfigVersionRepository,
)
from app.repositories.channel_form_submission_repository import (
    ChannelFormSubmissionRepository,
)
from app.repositories.channel_repository import ChannelRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.queue_repository import QueueCandidateRepository, QueueTaskRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.schemas.channel import ChannelConfig, strip_rich_text
from app.schemas.channel_form_submission import PublicFormMessageSubmitRequest
from app.schemas.ticket import TicketCreate
from app.services.offline_message_service import OfflineMessageService
from app.services.conversation_file_service import ConversationFileService
from app.services.queue_service import QueueTaskService
from app.services.ticket_service import TicketService

FORM_SUBMISSION_ENDED_BY = "visitor_form_message_submitted"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9()\-\s.]{5,32}$")


class ChannelFormSubmissionService:
    @staticmethod
    def _find_config_field(config: dict, field_ref: str) -> dict | None:
        for field in config.get("fields") or []:
            ref = (
                f"key:{field['field_key']}"
                if field.get("field_key")
                else f"id:{field.get('field_id')}"
            )
            if ref == field_ref:
                return field
        return None

    @staticmethod
    async def get_public_config(db: AsyncSession, visitor_context: dict) -> dict:
        channel = await ChannelRepository.get_by_id(db, int(visitor_context["channel_id"]))
        if not channel or channel.tenant_id != int(visitor_context["tenant_id"]):
            raise NotFoundError("Channel not found")
        config = ChannelConfig.model_validate(channel.config or {})
        if config.leave_message_mode != "form" or config.form_message_config_version is None:
            raise NotFoundError("Form message is not available")
        from app.services.channel_service import ChannelService

        await ChannelService._build_form_config_snapshot(
            db,
            channel.tenant_id,
            config.form_message_config.model_dump(),
        )
        version = await ChannelFormConfigVersionRepository.get_by_channel_version(
            db,
            channel.tenant_id,
            channel.id,
            config.form_message_config_version,
        )
        if not version:
            raise NotFoundError("Form message is not available")
        return {"version": version.version, "config": version.config}

    @staticmethod
    def _has_value(value: object, field_type: str) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(strip_rich_text(value) if field_type == "rich_text" else value.strip())
        if isinstance(value, (list, dict)):
            return len(value) > 0
        return True

    @staticmethod
    def _validate_field_value(field: dict, value: object) -> object:
        definition = field["definition"]
        field_type = str(definition.get("field_type") or "")
        type_config = definition.get("type_config") or {}
        name = str(definition.get("name") or "Field")
        if not ChannelFormSubmissionService._has_value(value, field_type):
            if field.get("required"):
                raise ValidationError(f"Enter {name}")
            return None

        if field_type in {"single_line_text", "multi_line_text", "rich_text", "email", "phone", "url", "time"}:
            if not isinstance(value, str):
                raise ValidationError(f"{name} has an invalid format")
            max_length = int(type_config.get("max_length") or (5000 if field_type == "rich_text" else 2048))
            if len(value) > max_length:
                raise ValidationError(f"{name} is too long")
        if field_type == "email" and not EMAIL_PATTERN.fullmatch(str(value)):
            raise ValidationError(f"{name} has an invalid format")
        if field_type == "phone" and not PHONE_PATTERN.fullmatch(str(value)):
            raise ValidationError(f"{name} has an invalid format")
        if field_type == "url":
            parsed = urlparse(str(value))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValidationError(f"{name} has an invalid format")
        if field_type == "number":
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise ValidationError(f"{name} has an invalid format") from None
            minimum = type_config.get("min")
            maximum = type_config.get("max")
            if minimum is not None and number < Decimal(str(minimum)):
                raise ValidationError(f"{name} is below the minimum")
            if maximum is not None and number > Decimal(str(maximum)):
                raise ValidationError(f"{name} exceeds the maximum")
        if field_type == "date":
            try:
                date.fromisoformat(str(value))
            except ValueError:
                raise ValidationError(f"{name} has an invalid format") from None
        if field_type == "time":
            try:
                time.fromisoformat(str(value))
            except ValueError:
                raise ValidationError(f"{name} has an invalid format") from None
        if field_type == "datetime":
            try:
                datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                raise ValidationError(f"{name} has an invalid format") from None
        if field_type in {"single_select", "single_select_tree"}:
            allowed = {
                str(item.get("value"))
                for item in [*(definition.get("options") or []), *(definition.get("tree_nodes") or [])]
            }
            if str(value) not in allowed:
                raise ValidationError(f"{name} has an invalid option")
        if field_type in {"multi_select", "multi_select_tree"}:
            if not isinstance(value, list):
                raise ValidationError(f"{name} has an invalid format")
            allowed = {
                str(item.get("value"))
                for item in [*(definition.get("options") or []), *(definition.get("tree_nodes") or [])]
            }
            if any(str(item) not in allowed for item in value):
                raise ValidationError(f"{name} has an invalid option")
        if field_type == "file" and not isinstance(value, list):
            raise ValidationError(f"{name} has an invalid format")
        return value

    @staticmethod
    def _validate_submission_files(
        config: dict,
        values: dict[str, object],
        *,
        tenant_id: int,
        channel_id: int,
    ) -> None:
        expected_prefix = f"form-message-files/{tenant_id}/{channel_id}/"
        public_prefix = f"{settings.OSS_ADDR}/"
        for field in config.get("fields") or []:
            if field.get("definition", {}).get("field_type") != "file":
                continue
            ref = (
                f"key:{field['field_key']}"
                if field.get("field_key")
                else f"id:{field.get('field_id')}"
            )
            value = values.get(ref)
            if not value:
                continue
            if not isinstance(value, list):
                raise ValidationError("File field has an invalid format")
            max_count = max(
                1,
                int(field.get("definition", {}).get("type_config", {}).get("max_file_count") or 1),
            )
            if len(value) > max_count:
                raise ValidationError("File field exceeds the maximum file count")
            for item in value:
                if not isinstance(item, dict):
                    raise ValidationError("File field has an invalid format")
                file_id = item.get("file_id")
                url = item.get("url")
                if not isinstance(file_id, str) or not isinstance(url, str):
                    raise ValidationError("File field has an invalid format")
                key = ConversationFileService.decode_file_id(file_id)
                if not key.startswith(expected_prefix) or url != f"{public_prefix}{key}":
                    raise ValidationError("File does not belong to this form")

    @staticmethod
    async def upload_public_file_managed(
        visitor_context: dict,
        version_number: int,
        field_ref: str,
        file: UploadFile,
    ) -> dict:
        tenant_id = int(visitor_context["tenant_id"])
        channel_id = int(visitor_context["channel_id"])
        async with AsyncSessionLocal() as db:
            version = await ChannelFormConfigVersionRepository.get_by_channel_version(
                db,
                tenant_id,
                channel_id,
                version_number,
            )
            field = (
                ChannelFormSubmissionService._find_config_field(version.config, field_ref)
                if version
                else None
            )
            if not field or field.get("definition", {}).get("field_type") != "file":
                raise NotFoundError("Form file field not found")
            type_config = dict(field["definition"].get("type_config") or {})

        raw_name, data, content_type, safe_ext = await ConversationFileService.read_validated_upload(file)
        max_mb = float(type_config.get("max_file_size_mb") or 100)
        if len(data) > max_mb * 1024 * 1024:
            raise ValidationError("File exceeds the configured size limit")
        allowed = {
            item.strip().lower().lstrip(".")
            for item in re.split(r"[,，]", str(type_config.get("allowed_mime_types") or ""))
            if item.strip()
        }
        blocked = {
            item.strip().lower().lstrip(".")
            for item in re.split(r"[,，]", str(type_config.get("blocked_mime_types") or ""))
            if item.strip()
        }
        extension = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
        if extension in blocked or (allowed and extension not in allowed and content_type not in allowed):
            raise ValidationError("File type is not allowed")

        date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = (
            f"form-message-files/{tenant_id}/{channel_id}/{date_prefix}/"
            f"{uuid.uuid4().hex}.{safe_ext}"
        )
        storage = create_storage_client()
        url = await storage.upload(key, data, content_type=content_type)
        return {
            "file_id": ConversationFileService.encode_file_id(key),
            "url": url,
            "name": raw_name,
            "size": len(data),
            "content_type": content_type,
        }

    @staticmethod
    def _build_ticket_and_snapshot(config: dict, values: dict[str, object]) -> tuple[TicketCreate, list[dict]]:
        configured_fields = config.get("fields") or []
        allowed_refs = {
            f"key:{field['field_key']}" if field.get("field_key") else f"id:{field.get('field_id')}"
            for field in configured_fields
        }
        if set(values) - allowed_refs:
            raise ValidationError("Form contains fields that are not configured")

        system_values: dict[str, object] = {}
        custom_values: dict[str, object] = {}
        snapshot: list[dict] = []
        for index, field in enumerate(configured_fields):
            ref = f"key:{field['field_key']}" if field.get("field_key") else f"id:{field.get('field_id')}"
            value = ChannelFormSubmissionService._validate_field_value(field, values.get(ref))
            definition = field["definition"]
            if field.get("field_key") and value is not None:
                system_values[str(field["field_key"])] = value
            if field.get("field_id") and value is not None:
                custom_values[str(field["field_id"])] = value
            snapshot.append({
                "field_key": field.get("field_key"),
                "field_id": field.get("field_id"),
                "name": definition.get("name"),
                "field_type": definition.get("field_type"),
                "required": bool(field.get("required")),
                "sort_order": index,
                "value": value,
                "type_config": definition.get("type_config") or {},
                "options": definition.get("options") or [],
                "tree_nodes": definition.get("tree_nodes") or [],
            })

        title = str(system_values.get("title") or "").strip()
        if not title:
            title = f"Web SDK 表单留言 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        ticket = TicketCreate(
            title=title,
            description=system_values.get("description"),
            priority=system_values.get("priority") or "medium",
            custom_fields=custom_values,
        )
        return ticket, snapshot

    @staticmethod
    async def _resolve_source(
        db: AsyncSession,
        redis: aioredis.Redis,
        visitor_context: dict,
        visitor_user_id: int,
        body: PublicFormMessageSubmitRequest,
    ) -> tuple[Conversation | None, int | None]:
        conversation = None
        if body.conversation_public_id:
            conversation = await ConversationRepository.get_by_public_id(db, body.conversation_public_id)
            if (
                not conversation
                or conversation.tenant_id != int(visitor_context["tenant_id"])
                or conversation.channel_id != int(visitor_context["channel_id"])
                or conversation.visitor_id != visitor_user_id
            ):
                raise NotFoundError("Conversation not found")
            if body.source == "queue_waiting":
                if conversation.status != ConversationStatus.QUEUED.value or conversation.group_id is None:
                    raise ConflictError("Conversation is no longer queued")
                return conversation, conversation.group_id
            if body.source in {"bot_handoff", "bot_action", "queue_full"}:
                if conversation.status not in {
                    ConversationStatus.BOT.value,
                    ConversationStatus.HANDOFF_PENDING.value,
                }:
                    raise ConflictError("Bot conversation is no longer available")
                return conversation, body.queue_id or conversation.group_id
            raise ValidationError("Conversation is not valid for this form source")

        if body.source in {"queue_waiting", "bot_handoff", "bot_action"}:
            raise ValidationError("Conversation is required for this form source")
        try:
            _channel, _config, _gate, group_id = await OfflineMessageService._ensure_leave_message_allowed(
                db,
                redis,
                int(visitor_context["channel_id"]),
                visitor_user_id,
                source="queue_full" if body.source == "queue_full" else None,
                queue_type=body.queue_type,
                queue_id=body.queue_id,
            )
        except BusinessError as exc:
            if body.queue_id is None or exc.message != "Queue not found":
                raise
            group_id = None
        return None, group_id

    @staticmethod
    async def _finalize_source_conversation(
        db: AsyncSession,
        conversation: Conversation | None,
        source: str,
    ) -> None:
        if not conversation:
            return
        if source == "queue_waiting":
            task = await QueueTaskRepository.get_active_conversation_task_for_update(
                db,
                conversation.tenant_id,
                conversation.id,
            )
            if not task:
                raise ConflictError("Queue task is not active")
            await QueueTaskRepository.mark_terminal(
                db,
                task,
                QueueTaskStatus.CANCELED.value,
                now=datetime.now(timezone.utc),
                reason=FORM_SUBMISSION_ENDED_BY,
            )
            await QueueTaskService._record_event(db, task, "canceled", reason=FORM_SUBMISSION_ENDED_BY)
            await QueueTaskService._materialize_conversation_summary(db, task)
        await ConversationRepository.end_conversation(db, conversation, FORM_SUBMISSION_ENDED_BY)

    @staticmethod
    async def _existing_response(db: AsyncSession, submission, duplicated: bool) -> dict:
        ticket = await TicketRepository.get_by_id(db, submission.ticket_id)
        version = await db.get(ChannelFormConfigVersion, submission.config_version_id)
        if not ticket or not version:
            raise NotFoundError("Form submission not found")
        config = version.config
        return {
            "ticket_id": ticket.id,
            "ticket_number": ticket.ticket_number,
            "success_title": config["success_title"],
            "success_description": config["success_description"],
            "show_ticket_number": bool(config.get("show_ticket_number", True)),
            "duplicated": duplicated,
        }

    @staticmethod
    async def submit(
        db: AsyncSession,
        redis: aioredis.Redis,
        visitor_context: dict,
        body: PublicFormMessageSubmitRequest,
    ) -> dict:
        tenant_id = int(visitor_context["tenant_id"])
        channel_id = int(visitor_context["channel_id"])
        visitor_external_id = str(visitor_context["visitor_external_id"])
        existing = await ChannelFormSubmissionRepository.get_by_idempotency_key(
            db,
            tenant_id=tenant_id,
            channel_id=channel_id,
            visitor_external_id=visitor_external_id,
            idempotency_key=body.idempotency_key,
        )
        if existing:
            return await ChannelFormSubmissionService._existing_response(db, existing, True)

        version = await ChannelFormConfigVersionRepository.get_by_channel_version(
            db,
            tenant_id,
            channel_id,
            body.version,
        )
        if not version:
            raise ConflictError("Form configuration has changed")

        visitor = await UserRepository.get_by_external_id(db, tenant_id, visitor_external_id)
        if not visitor:
            visitor = await UserRepository.create(
                db,
                {
                    "tenant_id": tenant_id,
                    "external_id": visitor_external_id,
                    "name": visitor_context.get("visitor_name") or f"访客 {visitor_external_id[:6]}",
                    "channel_id": channel_id,
                    "metadata_": visitor_context.get("metadata") or {},
                },
                commit=False,
            )

        conversation, group_id = await ChannelFormSubmissionService._resolve_source(
            db,
            redis,
            visitor_context,
            visitor.id,
            body,
        )
        if group_id is not None and not await QueueCandidateRepository.queue_exists(
            db,
            tenant_id,
            QueueType.EMPLOYEE_GROUP.value,
            group_id,
        ):
            group_id = None
        ChannelFormSubmissionService._validate_submission_files(
            version.config,
            body.values,
            tenant_id=tenant_id,
            channel_id=channel_id,
        )
        ticket_data, snapshot = ChannelFormSubmissionService._build_ticket_and_snapshot(
            version.config,
            body.values,
        )
        ticket_data.user_id = visitor.id
        ticket_data.conversation_id = conversation.id if conversation else None
        ticket_data.assignee_group_id = group_id
        ticket = await TicketService.create_ticket(
            db,
            tenant_id,
            ticket_data,
            actor_id=None,
            commit=False,
        )
        submission = await ChannelFormSubmissionRepository.create(db, {
            "tenant_id": tenant_id,
            "channel_id": channel_id,
            "config_version_id": version.id,
            "ticket_id": ticket["id"],
            "visitor_user_id": visitor.id,
            "visitor_external_id": visitor_external_id,
            "conversation_id": conversation.id if conversation else None,
            "source": body.source,
            "queue_type": body.queue_type,
            "queue_id": group_id,
            "idempotency_key": body.idempotency_key,
            "field_snapshot": snapshot,
        })
        await ChannelFormSubmissionService._finalize_source_conversation(db, conversation, body.source)
        await db.commit()
        return await ChannelFormSubmissionService._existing_response(db, submission, False)
