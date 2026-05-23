"""
Satisfaction survey invitation and submission service.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError, ValidationError
from app.enums import ConversationStatus
from app.libs.realtime.base import BaseRealtimeTransport
from app.libs.realtime.factory import get_realtime_transport
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.satisfaction_survey_record import SatisfactionSurveyRecord
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.satisfaction_survey_config_repository import SatisfactionSurveyConfigRepository
from app.repositories.satisfaction_survey_record_repository import SatisfactionSurveyRecordRepository
from app.schemas.satisfaction_survey_config import SatisfactionSurveyConfigPayload
from app.schemas.satisfaction_survey_record import SatisfactionSubmissionPayload, SatisfactionSubmissionTypePayload

logger = logging.getLogger(__name__)

MAX_REMARK_LENGTH = 500


class SatisfactionSurveyRecordService:
    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_list_param(value: list[str] | str | None) -> list[str] | None:
        if value is None:
            return None
        raw_items = value if isinstance(value, list) else [value]
        items: list[str] = []
        for raw in raw_items:
            for part in str(raw).split(","):
                item = part.strip()
                if item and item not in items:
                    items.append(item)
        return items or None

    @staticmethod
    def _included_types(snapshot: dict) -> list[str]:
        types: list[str] = []
        if (snapshot.get("service") or {}).get("enabled"):
            types.append("service")
        if (snapshot.get("product") or {}).get("enabled"):
            types.append("product")
        return types

    @staticmethod
    def _event_message_to_response(message: Message) -> dict:
        metadata = getattr(message, "metadata_", None) or {}
        if not metadata and getattr(message, "event_type", None):
            metadata = {
                "event_type": getattr(message, "event_type"),
                "satisfaction_record_id": getattr(message, "record_id", 0),
                "actor_type": getattr(message, "actor_type", None),
                "actor_id": getattr(message, "actor_id", None),
                "actor_name": getattr(message, "actor_name", None),
                "config_version": getattr(message, "config_version", 0),
            }
        return {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "record_id": int(metadata.get("satisfaction_record_id") or 0),
            "event_type": metadata.get("event_type") or "",
            "actor_type": metadata.get("actor_type") or "system",
            "actor_id": metadata.get("actor_id") if metadata.get("actor_id") is not None else getattr(message, "sender_id", None),
            "actor_name": metadata.get("actor_name"),
            "summary": getattr(message, "content", None) or getattr(message, "summary", ""),
            "config_version": int(metadata.get("config_version") or 0),
            "occurred_at": getattr(message, "created_at", None) or getattr(message, "occurred_at", None),
            "metadata": metadata,
        }

    @staticmethod
    def _result_to_response(result: dict | None) -> dict | None:
        if not result:
            return None
        return {
            "type": result.get("type"),
            "rating_mode": result.get("rating_mode") or "",
            "section_title": result.get("section_title"),
            "option_key": result.get("option_key") or "",
            "option_name": result.get("option_name") or "",
            "labels": result.get("labels") or [],
            "remark": result.get("remark"),
            "resolved": result.get("resolved"),
            "submitted_at": result.get("submitted_at"),
        }

    @staticmethod
    def _record_to_response(record: SatisfactionSurveyRecord) -> dict:
        snapshot = SatisfactionSurveyConfigPayload.model_validate(record.config_snapshot or {})
        return {
            "id": record.id,
            "conversation_id": record.conversation_id,
            "config_version": record.config_version,
            "config_snapshot": snapshot.model_dump(mode="json"),
            "invitation_source": record.invitation_source,
            "invited_by_id": record.invited_by_id,
            "invited_by_name": record.invited_by_name,
            "invited_at": record.invited_at,
            "status": record.status,
            "survey_types": record.survey_types or [],
            "service_result": SatisfactionSurveyRecordService._result_to_response(record.service_result),
            "product_result": SatisfactionSurveyRecordService._result_to_response(record.product_result),
            "submitted_at": record.submitted_at,
        }

    @staticmethod
    def _summary_for_record(record: SatisfactionSurveyRecord | None) -> dict:
        if not record:
            return {"status": "none", "labels": []}
        labels: list[str] = []
        if record.status == "submitted":
            for survey_type, result in (("service", record.service_result), ("product", record.product_result)):
                if result:
                    type_label = "服务" if survey_type == "service" else "产品"
                    option_name = result.get("option_name") or "-"
                    labels.append(f"{type_label} · {option_name}")
        return {
            "status": record.status,
            "labels": labels,
            "invited_at": record.invited_at,
            "submitted_at": record.submitted_at,
            "config_version": record.config_version,
        }

    @staticmethod
    def _has_feedback(record: SatisfactionSurveyRecord | None) -> bool:
        return bool(record and (record.service_result or record.product_result or record.submitted_at))

    @staticmethod
    def _preserved_feedback_fields(record: SatisfactionSurveyRecord | None) -> dict:
        return {
            "service_result": record.service_result if record else None,
            "product_result": record.product_result if record else None,
            "submitted_at": record.submitted_at if record else None,
        }

    @staticmethod
    async def _current_snapshot(db: AsyncSession, tenant_id: int) -> tuple[int, dict]:
        current = await SatisfactionSurveyConfigRepository.get_current(db, tenant_id)
        if not current or current.current_version is None:
            raise BusinessError("Satisfaction survey is not configured", code="SATISFACTION_NOT_CONFIGURED")
        version = await SatisfactionSurveyConfigRepository.get_version(db, tenant_id, current.current_version)
        if not version:
            raise BusinessError("Satisfaction survey version is unavailable", code="SATISFACTION_VERSION_MISSING")
        snapshot = version.snapshot or {}
        if not snapshot.get("enabled"):
            raise BusinessError("Satisfaction survey is disabled", code="SATISFACTION_DISABLED")
        if not SatisfactionSurveyRecordService._included_types(snapshot):
            raise BusinessError("No satisfaction type is enabled", code="SATISFACTION_TYPE_DISABLED")
        return version.version, snapshot

    @staticmethod
    def _disabled_reason(
        conversation: Conversation,
        snapshot: dict | None,
        record: SatisfactionSurveyRecord | None,
        user: dict,
        config_error_code: str | None = None,
    ) -> str | None:
        roles = user.get("roles", ["agent"])
        if "admin" not in roles and conversation.agent_id != user.get("user_id"):
            return "no_permission"
        if conversation.status == ConversationStatus.CLOSED.value:
            return "conversation_closed"
        if config_error_code == "SATISFACTION_DISABLED":
            return "satisfaction_disabled"
        if config_error_code == "SATISFACTION_TYPE_DISABLED":
            return "no_satisfaction_type"
        if config_error_code in {"SATISFACTION_NOT_CONFIGURED", "SATISFACTION_VERSION_MISSING"}:
            return "satisfaction_not_configured"
        if not snapshot:
            return "satisfaction_not_configured"
        if not snapshot.get("enabled"):
            return "satisfaction_disabled"
        triggers = snapshot.get("triggers") or {}
        if not triggers.get("agent_invite"):
            return "agent_invite_disabled"
        if not SatisfactionSurveyRecordService._included_types(snapshot):
            return "no_satisfaction_type"
        if (
            record
            and (record.status == "submitted" or SatisfactionSurveyRecordService._has_feedback(record))
            and triggers.get("limit_one_response_per_type", True)
        ):
            return "feedback_submitted"
        return None

    @staticmethod
    def _public_initiate_disabled_reason(
        conversation: Conversation,
        snapshot: dict | None,
        record: SatisfactionSurveyRecord | None,
        config_error_code: str | None = None,
    ) -> str | None:
        if conversation.status == ConversationStatus.CLOSED.value:
            return "conversation_closed"
        if config_error_code == "SATISFACTION_DISABLED":
            return "satisfaction_disabled"
        if config_error_code == "SATISFACTION_TYPE_DISABLED":
            return "no_satisfaction_type"
        if config_error_code in {"SATISFACTION_NOT_CONFIGURED", "SATISFACTION_VERSION_MISSING"}:
            return "satisfaction_not_configured"
        if not snapshot:
            return "satisfaction_not_configured"
        if not snapshot.get("enabled"):
            return "satisfaction_disabled"
        triggers = snapshot.get("triggers") or {}
        if not triggers.get("user_initiated"):
            return "user_initiated_disabled"
        if not SatisfactionSurveyRecordService._included_types(snapshot):
            return "no_satisfaction_type"
        if (
            record
            and SatisfactionSurveyRecordService._has_feedback(record)
            and triggers.get("limit_one_response_per_type", True)
        ):
            return "feedback_submitted"
        return None

    @staticmethod
    def _session_end_invite_disabled_reason(
        conversation: Conversation,
        snapshot: dict | None,
        record: SatisfactionSurveyRecord | None,
        config_error_code: str | None = None,
    ) -> str | None:
        if conversation.status != ConversationStatus.CLOSED.value:
            return "conversation_not_closed"
        if config_error_code == "SATISFACTION_DISABLED":
            return "satisfaction_disabled"
        if config_error_code == "SATISFACTION_TYPE_DISABLED":
            return "no_satisfaction_type"
        if config_error_code in {"SATISFACTION_NOT_CONFIGURED", "SATISFACTION_VERSION_MISSING"}:
            return "satisfaction_not_configured"
        if not snapshot:
            return "satisfaction_not_configured"
        if not snapshot.get("enabled"):
            return "satisfaction_disabled"
        triggers = snapshot.get("triggers") or {}
        if not triggers.get("session_end_invite"):
            return "session_end_invite_disabled"
        if not SatisfactionSurveyRecordService._included_types(snapshot):
            return "no_satisfaction_type"
        if (
            record
            and SatisfactionSurveyRecordService._has_feedback(record)
            and triggers.get("limit_one_response_per_type", True)
        ):
            return "feedback_submitted"
        return None

    @staticmethod
    async def _load_conversation_for_agent(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        user: dict,
    ) -> Conversation:
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")
        roles = user.get("roles", ["agent"])
        if "admin" not in roles and conversation.agent_id != user.get("user_id"):
            raise ForbiddenError("No permission to access conversation")
        return conversation

    @staticmethod
    async def get_conversation_state(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        user: dict,
    ) -> dict:
        conversation = await SatisfactionSurveyRecordService._load_conversation_for_agent(
            db, conversation_id, tenant_id, user
        )
        record = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation_id)
        snapshot: dict | None = None
        config_error_code: str | None = None
        try:
            _version, snapshot = await SatisfactionSurveyRecordService._current_snapshot(db, tenant_id)
        except BusinessError as exc:
            config_error_code = exc.code
            snapshot = None

        disabled_reason = SatisfactionSurveyRecordService._disabled_reason(
            conversation,
            snapshot,
            record,
            user,
            config_error_code,
        )
        return {
            "can_invite": disabled_reason is None,
            "disabled_reason": disabled_reason,
            "needs_confirmation": False,
            "record": SatisfactionSurveyRecordService._record_to_response(record) if record else None,
            "summary": SatisfactionSurveyRecordService._summary_for_record(record),
        }

    @staticmethod
    async def send_agent_invitation(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        user: dict,
        *,
        force: bool = False,
    ) -> dict:
        conversation = await SatisfactionSurveyRecordService._load_conversation_for_agent(
            db, conversation_id, tenant_id, user
        )
        config_version, snapshot = await SatisfactionSurveyRecordService._current_snapshot(db, tenant_id)
        existing = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation_id)
        disabled_reason = SatisfactionSurveyRecordService._disabled_reason(conversation, snapshot, existing, user)
        if disabled_reason:
            raise BusinessError(f"Cannot send satisfaction survey: {disabled_reason}", code="SATISFACTION_INVITE_DISABLED")

        if existing and existing.status == "invited" and not force:
            return {
                "can_invite": True,
                "disabled_reason": None,
                "needs_confirmation": True,
                "record": SatisfactionSurveyRecordService._record_to_response(existing),
                "summary": SatisfactionSurveyRecordService._summary_for_record(existing),
            }

        actor = await EmployeeRepository.get_by_id(db, int(user["user_id"]))
        actor_name = (
            actor.display_name or actor.name
            if actor
            else str(user.get("display_name") or user.get("name") or user.get("username") or "Agent")
        )
        now = SatisfactionSurveyRecordService._now()
        survey_types = SatisfactionSurveyRecordService._included_types(snapshot)
        preserved_feedback = SatisfactionSurveyRecordService._preserved_feedback_fields(existing)
        record_data = {
            "tenant_id": tenant_id,
            "conversation_id": conversation.id,
            "visitor_id": conversation.visitor_id,
            "channel_id": conversation.channel_id,
            "config_version": config_version,
            "config_snapshot": snapshot,
            "invitation_source": "agent",
            "invited_by_id": user["user_id"],
            "invited_by_name": actor_name[:128] if actor_name else None,
            "invited_at": now,
            "status": "invited",
            "survey_types": survey_types,
            **preserved_feedback,
        }
        message_data = {
            "tenant_id": tenant_id,
            "conversation_id": conversation.id,
            "actor_id": user["user_id"],
            "summary": f"{actor_name or '客服'} 发送了满意度邀请",
            "config_version": config_version,
            "occurred_at": now,
            "metadata_": {
                "event_type": "invitation_sent",
                "actor_type": "agent",
                "actor_id": user["user_id"],
                "actor_name": actor_name[:128] if actor_name else None,
                "survey_types": survey_types,
            },
        }
        record, message = await SatisfactionSurveyRecordRepository.create_or_update_invitation(
            db, conversation.id, record_data, message_data
        )
        state = {
            "can_invite": True,
            "disabled_reason": None,
            "needs_confirmation": False,
            "record": SatisfactionSurveyRecordService._record_to_response(record),
            "summary": SatisfactionSurveyRecordService._summary_for_record(record),
            "latest_event": SatisfactionSurveyRecordService._event_message_to_response(message),
        }
        await SatisfactionSurveyRecordService.emit_invitation_event(conversation, state)
        return state

    @staticmethod
    async def send_session_end_invitation(
        db: AsyncSession,
        conversation: Conversation,
    ) -> dict | None:
        snapshot: dict | None = None
        config_error_code: str | None = None
        config_version = 0
        try:
            config_version, snapshot = await SatisfactionSurveyRecordService._current_snapshot(
                db,
                conversation.tenant_id,
            )
        except BusinessError as exc:
            config_error_code = exc.code

        existing = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation.id)
        disabled_reason = SatisfactionSurveyRecordService._session_end_invite_disabled_reason(
            conversation,
            snapshot,
            existing,
            config_error_code,
        )
        if disabled_reason:
            return None

        if existing and existing.status == "invited" and not SatisfactionSurveyRecordService._has_feedback(existing):
            return {
                "record": SatisfactionSurveyRecordService._record_to_response(existing),
                "summary": SatisfactionSurveyRecordService._summary_for_record(existing),
            }

        now = SatisfactionSurveyRecordService._now()
        survey_types = SatisfactionSurveyRecordService._included_types(snapshot or {})
        preserved_feedback = SatisfactionSurveyRecordService._preserved_feedback_fields(existing)
        record_data = {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "visitor_id": conversation.visitor_id,
            "channel_id": conversation.channel_id,
            "config_version": config_version,
            "config_snapshot": snapshot,
            "invitation_source": "system",
            "invited_by_id": None,
            "invited_by_name": "系统",
            "invited_at": now,
            "status": "invited",
            "survey_types": survey_types,
            **preserved_feedback,
        }
        message_data = {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "actor_id": None,
            "summary": "系统在会话结束后发送了满意度邀请",
            "config_version": config_version,
            "occurred_at": now,
            "metadata_": {
                "event_type": "invitation_sent",
                "actor_type": "system",
                "actor_id": None,
                "actor_name": "系统",
                "survey_types": survey_types,
                "invitation_trigger": "session_end",
            },
        }
        record, message = await SatisfactionSurveyRecordRepository.create_or_update_invitation(
            db,
            conversation.id,
            record_data,
            message_data,
        )
        state = {
            "record": SatisfactionSurveyRecordService._record_to_response(record),
            "summary": SatisfactionSurveyRecordService._summary_for_record(record),
            "latest_event": SatisfactionSurveyRecordService._event_message_to_response(message),
        }
        await SatisfactionSurveyRecordService.emit_invitation_event(conversation, state)
        return state

    @staticmethod
    async def get_public_invitation(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
    ) -> dict:
        conversation = await SatisfactionSurveyRecordService._load_conversation_for_visitor(
            db,
            conversation_public_id,
            visitor_context,
        )
        record = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation.id)
        snapshot: dict | None = None
        config_error_code: str | None = None
        try:
            _version, snapshot = await SatisfactionSurveyRecordService._current_snapshot(db, conversation.tenant_id)
        except BusinessError as exc:
            config_error_code = exc.code
            snapshot = None

        disabled_reason = SatisfactionSurveyRecordService._public_initiate_disabled_reason(
            conversation,
            snapshot,
            record,
            config_error_code,
        )
        invitation = None
        if record and record.status == "invited":
            invitation = SatisfactionSurveyRecordService._record_to_response(record)
        return {
            "invitation": invitation,
            "can_initiate": disabled_reason is None,
            "disabled_reason": disabled_reason,
        }

    @staticmethod
    async def create_user_initiated_invitation(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
    ) -> dict:
        conversation = await SatisfactionSurveyRecordService._load_conversation_for_visitor(
            db,
            conversation_public_id,
            visitor_context,
        )
        existing = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation.id)
        if existing and existing.status == "invited":
            return {
                "invitation": SatisfactionSurveyRecordService._record_to_response(existing),
                "can_initiate": True,
                "disabled_reason": None,
            }

        config_version, snapshot = await SatisfactionSurveyRecordService._current_snapshot(db, conversation.tenant_id)
        disabled_reason = SatisfactionSurveyRecordService._public_initiate_disabled_reason(
            conversation,
            snapshot,
            existing,
        )
        if disabled_reason:
            raise BusinessError(
                f"Cannot start satisfaction survey: {disabled_reason}",
                code="SATISFACTION_USER_INITIATED_DISABLED",
            )

        now = SatisfactionSurveyRecordService._now()
        survey_types = SatisfactionSurveyRecordService._included_types(snapshot)
        visitor_name = (
            (conversation.visitor.name if conversation.visitor else None)
            or visitor_context.get("visitor_name")
            or "访客"
        )
        preserved_feedback = SatisfactionSurveyRecordService._preserved_feedback_fields(existing)
        record_data = {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "visitor_id": conversation.visitor_id,
            "channel_id": conversation.channel_id,
            "config_version": config_version,
            "config_snapshot": snapshot,
            "invitation_source": "visitor",
            "invited_by_id": conversation.visitor_id,
            "invited_by_name": str(visitor_name)[:128] if visitor_name else None,
            "invited_at": now,
            "status": "invited",
            "survey_types": survey_types,
            **preserved_feedback,
        }
        record = await SatisfactionSurveyRecordRepository.create_or_update_record(
            db,
            conversation.id,
            record_data,
        )
        return {
            "invitation": SatisfactionSurveyRecordService._record_to_response(record),
            "can_initiate": True,
            "disabled_reason": None,
        }

    @staticmethod
    async def _load_conversation_for_visitor(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
    ) -> Conversation:
        conversation = await ConversationRepository.get_by_public_id(db, conversation_public_id)
        if not conversation:
            raise NotFoundError("Conversation not found")
        if (
            conversation.tenant_id != visitor_context["tenant_id"]
            or conversation.channel_id != visitor_context["channel_id"]
            or not conversation.visitor
            or conversation.visitor.external_id != visitor_context["visitor_external_id"]
        ):
            raise NotFoundError("Conversation not found")
        return conversation

    @staticmethod
    def _enabled_option_map(settings: dict) -> dict[str, dict]:
        return {
            str(option.get("key") or ""): option
            for option in settings.get("rating_options") or []
            if option.get("enabled", True) and option.get("key")
        }

    @staticmethod
    def _validate_type_submission(
        survey_type: str,
        settings: dict,
        payload: SatisfactionSubmissionTypePayload,
        submitted_at: datetime,
    ) -> dict:
        options = SatisfactionSurveyRecordService._enabled_option_map(settings)
        option = options.get(payload.rating_option_key)
        if not option:
            raise ValidationError(f"Invalid {survey_type} rating option")

        available_labels = [str(label) for label in option.get("labels") or []]
        invalid_labels = [label for label in payload.labels if label not in available_labels]
        if invalid_labels:
            raise ValidationError(f"Invalid {survey_type} labels")

        if settings.get("tag_selection_mode") == "single" and len(payload.labels) > 1:
            raise ValidationError(f"{survey_type} accepts only one label")

        remark_enabled = settings.get("remark_enabled", True)
        remark_requirement = option.get("remark_requirement") or "optional"
        remark = (payload.remark or "").strip()
        if not remark_enabled:
            remark = ""
        elif remark_requirement == "hidden":
            remark = ""
        elif remark_requirement == "required" and not remark:
            raise ValidationError(f"{survey_type} remark is required")
        if len(remark) > MAX_REMARK_LENGTH:
            raise ValidationError("Remark must be at most 500 characters")

        resolved = None
        if survey_type == "service" and settings.get("show_resolution"):
            if payload.resolved is None:
                raise ValidationError("Please select whether the issue was resolved")
            resolved = bool(payload.resolved)

        return {
            "type": survey_type,
            "rating_mode": settings.get("rating_mode") or "",
            "section_title": settings.get("section_title"),
            "option_key": option.get("key"),
            "option_name": option.get("name"),
            "labels": payload.labels,
            "remark": remark,
            "resolved": resolved,
            "submitted_at": submitted_at.isoformat(),
        }

    @staticmethod
    async def submit_public_feedback(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
        payload: SatisfactionSubmissionPayload,
    ) -> dict:
        conversation = await SatisfactionSurveyRecordService._load_conversation_for_visitor(
            db, conversation_public_id, visitor_context
        )
        record = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation.id)
        if not record:
            raise NotFoundError("Satisfaction invitation not found")

        snapshot = record.config_snapshot or {}
        triggers = snapshot.get("triggers") or {}
        if SatisfactionSurveyRecordService._has_feedback(record) and triggers.get("limit_one_response_per_type", True):
            raise BusinessError("Feedback submitted", code="SATISFACTION_ALREADY_SUBMITTED")

        submitted_at = SatisfactionSurveyRecordService._now()
        survey_types = record.survey_types or SatisfactionSurveyRecordService._included_types(snapshot)
        service_result = None
        product_result = None
        if "service" in survey_types:
            if payload.service is None:
                raise ValidationError("Please select a service rating")
            service_result = SatisfactionSurveyRecordService._validate_type_submission(
                "service",
                snapshot.get("service") or {},
                payload.service,
                submitted_at,
            )
        if "product" in survey_types:
            if payload.product is None:
                raise ValidationError("Please select a product rating")
            product_result = SatisfactionSurveyRecordService._validate_type_submission(
                "product",
                snapshot.get("product") or {},
                payload.product,
                submitted_at,
            )

        message_data = {
            "tenant_id": record.tenant_id,
            "conversation_id": record.conversation_id,
            "actor_id": conversation.visitor_id,
            "summary": "访客提交了满意度评价",
            "config_version": record.config_version,
            "occurred_at": submitted_at,
            "metadata_": {
                "event_type": "feedback_submitted",
                "actor_type": "visitor",
                "actor_id": conversation.visitor_id,
                "actor_name": conversation.visitor.name if conversation.visitor else "访客",
                "survey_types": survey_types,
            },
        }
        data = {
            "status": "submitted",
            "service_result": service_result,
            "product_result": product_result,
            "submitted_at": submitted_at,
        }
        record, message = await SatisfactionSurveyRecordRepository.save_submission(db, record, data, message_data)
        response = {
            "record": SatisfactionSurveyRecordService._record_to_response(record),
            "latest_event": SatisfactionSurveyRecordService._event_message_to_response(message),
        }
        await SatisfactionSurveyRecordService.emit_submission_event(conversation, response)
        return response

    @staticmethod
    async def get_session_record_satisfaction(
        db: AsyncSession,
        record_id: int,
        tenant_id: int,
        user: dict,
    ) -> dict:
        conversation = await SatisfactionSurveyRecordService._load_conversation_for_agent(
            db, record_id, tenant_id, user
        )
        record = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation.id)
        events = await SatisfactionSurveyRecordRepository.get_event_messages_by_conversation(db, conversation.id)
        return {
            "record": SatisfactionSurveyRecordService._record_to_response(record) if record else None,
            "events": [SatisfactionSurveyRecordService._event_message_to_response(event) for event in events],
        }

    @staticmethod
    async def get_filter_options(db: AsyncSession, tenant_id: int) -> dict:
        try:
            current_version, snapshot = await SatisfactionSurveyRecordService._current_snapshot(db, tenant_id)
        except BusinessError:
            return {"configured": False, "current_version": None, "survey_types": []}

        def option_rows(settings: dict) -> list[dict]:
            return [
                {"key": str(option.get("key")), "label": str(option.get("name") or option.get("key"))}
                for option in settings.get("rating_options") or []
                if option.get("enabled", True) and option.get("key")
            ]

        def label_rows(settings: dict) -> list[dict]:
            labels: list[str] = []
            for option in settings.get("rating_options") or []:
                if not option.get("enabled", True):
                    continue
                for label in option.get("labels") or []:
                    text = str(label).strip()
                    if text and text not in labels:
                        labels.append(text)
            return [{"key": label, "label": label} for label in labels]

        service = snapshot.get("service") or {}
        product = snapshot.get("product") or {}
        return {
            "configured": True,
            "current_version": current_version,
            "survey_types": SatisfactionSurveyRecordService._included_types(snapshot),
            "show_resolution": bool(service.get("enabled") and service.get("show_resolution")),
            "service_options": option_rows(service) if service.get("enabled") else [],
            "service_labels": label_rows(service) if service.get("enabled") else [],
            "product_options": option_rows(product) if product.get("enabled") else [],
            "product_labels": label_rows(product) if product.get("enabled") else [],
        }

    @staticmethod
    def build_event_message(event: Message | dict) -> dict:
        data = (
            SatisfactionSurveyRecordService._event_message_to_response(event)
            if isinstance(event, Message)
            else event
        )
        return {
            "id": int(data["id"]),
            "conversation_id": data["conversation_id"],
            "sender_type": "system",
            "sender_id": data.get("actor_id"),
            "sender_name": data.get("actor_name"),
            "sender_avatar": None,
            "content_type": "satisfaction_event",
            "content": data["summary"],
            "created_at": data["occurred_at"],
            "metadata": data.get("metadata") or {},
            "event_type": data["event_type"],
            "satisfaction_record_id": data["record_id"],
            "config_version": data["config_version"],
        }

    @staticmethod
    async def emit_invitation_event(conversation: Conversation, state: dict) -> None:
        event = state.get("latest_event")
        record = state.get("record")
        if not event or not record:
            return
        await SatisfactionSurveyRecordService._emit_safe(
            "satisfaction_invitation_sent",
            {
                "conversation_id": conversation.id,
                "conversation_public_id": conversation.public_id,
                "record": record,
                "event": event,
                "message": SatisfactionSurveyRecordService.build_event_message(event),
            },
            conversation=conversation,
            include_visitor=True,
        )

    @staticmethod
    async def emit_submission_event(conversation: Conversation, response: dict) -> None:
        event = response.get("latest_event")
        record = response.get("record")
        if not event or not record:
            return
        await SatisfactionSurveyRecordService._emit_safe(
            "satisfaction_feedback_submitted",
            {
                "conversation_id": conversation.id,
                "conversation_public_id": conversation.public_id,
                "record": record,
                "event": event,
                "message": SatisfactionSurveyRecordService.build_event_message(event),
            },
            conversation=conversation,
            include_visitor=False,
        )

    @staticmethod
    async def _emit_safe(
        event_name: str,
        payload: dict[str, Any],
        *,
        conversation: Conversation,
        include_visitor: bool,
    ) -> None:
        try:
            rt: BaseRealtimeTransport = get_realtime_transport()
        except RuntimeError:
            return
        try:
            if conversation.agent_id:
                await rt.emit(
                    event_name,
                    jsonable_encoder(payload),
                    room=f"agent:{conversation.tenant_id}:{conversation.agent_id}",
                    namespace="/chat",
                )
            if include_visitor:
                await rt.emit(
                    event_name,
                    jsonable_encoder(payload),
                    room=f"conv:{conversation.id}",
                    namespace="/visitor",
                )
        except Exception:
            logger.exception("Failed to emit %s for conversation %s", event_name, conversation.id)

    @staticmethod
    def record_summary(record: SatisfactionSurveyRecord | None) -> dict:
        return SatisfactionSurveyRecordService._summary_for_record(record)
