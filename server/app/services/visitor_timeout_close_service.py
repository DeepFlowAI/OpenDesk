"""
Visitor timeout auto-close business logic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ConversationStatus, MessageContentType, MessageSenderType
from app.models.visitor_timeout_close import VisitorTimeoutCloseSetting, VisitorTimeoutCloseState
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.visitor_timeout_close_repository import (
    VisitorTimeoutCloseSettingRepository,
    VisitorTimeoutCloseStateRepository,
)
from app.schemas.visitor_timeout_close import (
    DEFAULT_CLOSE_REMINDER_CONTENT,
    DEFAULT_FIRST_REMINDER_CONTENT,
    VisitorTimeoutClosePayload,
    VisitorTimeoutCloseResponse,
)
from app.services.agent_status_service import AgentStatusService
from app.services.conversation_realtime_service import ConversationRealtimeService

logger = logging.getLogger(__name__)

AUTO_CLOSE_ENDED_BY = "system_timeout"
FIRST_REMINDER_EVENT_TYPE = "visitor_timeout_first_reminder"
AUTO_CLOSE_EVENT_TYPE = "visitor_timeout_auto_close"
AUTO_TOOL_NAME = "访客超时自动关闭工具"
CLAIM_LEASE_SECONDS = 300
VISITOR_MESSAGE_CONTENT_TYPES = {
    MessageContentType.TEXT.value,
    MessageContentType.RICH_TEXT.value,
    MessageContentType.IMAGE.value,
    MessageContentType.FILE.value,
}


class VisitorTimeoutCloseService:
    @staticmethod
    def default_payload() -> VisitorTimeoutClosePayload:
        return VisitorTimeoutClosePayload(
            enabled=False,
            first_normal_minutes=110,
            close_normal_minutes=120,
            vip_enabled=False,
            first_vip_minutes=110,
            close_vip_minutes=120,
            first_reminder_content=DEFAULT_FIRST_REMINDER_CONTENT,
            close_reminder_content=DEFAULT_CLOSE_REMINDER_CONTENT,
            notify_agent=True,
            notify_visitor=True,
        )

    @staticmethod
    def _actor_name(current_user: dict) -> str | None:
        for key in ("display_name", "name", "username", "email"):
            value = current_user.get(key)
            if value:
                return str(value)[:128]
        return None

    @staticmethod
    def _row_to_payload(row: VisitorTimeoutCloseSetting) -> VisitorTimeoutClosePayload:
        return VisitorTimeoutClosePayload(
            enabled=row.enabled,
            first_normal_minutes=row.first_normal_minutes,
            close_normal_minutes=row.close_normal_minutes,
            vip_enabled=row.vip_enabled,
            first_vip_minutes=row.first_vip_minutes,
            close_vip_minutes=row.close_vip_minutes,
            first_reminder_content=row.first_reminder_content,
            close_reminder_content=row.close_reminder_content,
            notify_agent=row.notify_agent,
            notify_visitor=row.notify_visitor,
        )

    @staticmethod
    def _row_to_response(row: VisitorTimeoutCloseSetting, configured: bool = True) -> VisitorTimeoutCloseResponse:
        data = VisitorTimeoutCloseService._row_to_payload(row).model_dump(mode="json")
        data.update(
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "configured": configured,
                "version": row.version,
                "updated_by_id": row.updated_by_id,
                "updated_by_name": row.updated_by_name,
                "updated_at": row.updated_at,
            }
        )
        return VisitorTimeoutCloseResponse.model_validate(data)

    @staticmethod
    def _default_response(tenant_id: int) -> VisitorTimeoutCloseResponse:
        data = VisitorTimeoutCloseService.default_payload().model_dump(mode="json")
        data.update(
            {
                "id": None,
                "tenant_id": tenant_id,
                "configured": False,
                "version": 1,
                "updated_by_id": None,
                "updated_by_name": None,
                "updated_at": None,
            }
        )
        return VisitorTimeoutCloseResponse.model_validate(data)

    @staticmethod
    async def get_current(db: AsyncSession, tenant_id: int) -> VisitorTimeoutCloseResponse:
        row = await VisitorTimeoutCloseSettingRepository.get_by_tenant(db, tenant_id)
        if not row:
            return VisitorTimeoutCloseService._default_response(tenant_id)
        return VisitorTimeoutCloseService._row_to_response(row)

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        current_user: dict,
        payload: VisitorTimeoutClosePayload,
    ) -> VisitorTimeoutCloseResponse:
        row = await VisitorTimeoutCloseSettingRepository.save(
            db,
            tenant_id,
            {
                **payload.model_dump(mode="json"),
                "updated_by_id": current_user.get("user_id"),
                "updated_by_name": VisitorTimeoutCloseService._actor_name(current_user),
            },
        )
        logger.info(
            "visitor_timeout_close_settings_saved tenant_id=%s setting_id=%s enabled=%s "
            "vip_enabled=%s notify_agent=%s notify_visitor=%s version=%s updated_by_id=%s",
            tenant_id,
            row.id,
            row.enabled,
            row.vip_enabled,
            row.notify_agent,
            row.notify_visitor,
            row.version,
            row.updated_by_id,
        )
        return VisitorTimeoutCloseService._row_to_response(row)

    @staticmethod
    async def _setting_or_default(db: AsyncSession, tenant_id: int) -> tuple[VisitorTimeoutClosePayload, int]:
        row = await VisitorTimeoutCloseSettingRepository.get_by_tenant(db, tenant_id)
        if row:
            return VisitorTimeoutCloseService._row_to_payload(row), row.version
        return VisitorTimeoutCloseService.default_payload(), 1

    @staticmethod
    def _is_vip_conversation(conversation) -> bool:
        visitor = getattr(conversation, "visitor", None)
        return str(getattr(visitor, "level", "") or "").lower() == "vip"

    @staticmethod
    def _thresholds(payload: VisitorTimeoutClosePayload, conversation) -> tuple[int, int]:
        if payload.vip_enabled and VisitorTimeoutCloseService._is_vip_conversation(conversation):
            return payload.first_vip_minutes, payload.close_vip_minutes
        return payload.first_normal_minutes, payload.close_normal_minutes

    @staticmethod
    def _next_check_at(
        payload: VisitorTimeoutClosePayload,
        conversation,
        anchor_at: datetime,
        first_reminded_at: datetime | None,
    ) -> datetime | None:
        if not payload.enabled:
            return None
        first_minutes, close_minutes = VisitorTimeoutCloseService._thresholds(payload, conversation)
        target_minutes = close_minutes if first_reminded_at is not None else first_minutes
        return anchor_at + timedelta(minutes=target_minutes)

    @staticmethod
    def _is_locked(state: VisitorTimeoutCloseState | None) -> bool:
        return bool(state and getattr(state, "timeout_locked_at", None) is not None)

    @staticmethod
    async def initialize_for_conversation(
        db: AsyncSession,
        conversation,
        *,
        anchor_at: datetime | None = None,
        commit: bool = True,
    ) -> VisitorTimeoutCloseState | None:
        if not conversation or conversation.status != ConversationStatus.ACTIVE.value or not conversation.agent_id:
            return None
        if getattr(conversation, "visitor", None) is None:
            conversation = await ConversationRepository.get_by_id(db, conversation.id)
            if not conversation:
                return None
        existing = await VisitorTimeoutCloseStateRepository.get_by_conversation(db, conversation.id)
        if VisitorTimeoutCloseService._is_locked(existing):
            return existing
        payload, version = await VisitorTimeoutCloseService._setting_or_default(db, conversation.tenant_id)
        effective_anchor_at = anchor_at or conversation.started_at or datetime.now(timezone.utc)
        next_check_at = VisitorTimeoutCloseService._next_check_at(payload, conversation, effective_anchor_at, None)
        return await VisitorTimeoutCloseStateRepository.upsert_for_conversation(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            anchor_at=effective_anchor_at,
            anchor_message_id=None,
            first_reminded_at=None,
            closed_at=None,
            next_check_at=next_check_at,
            config_version=version,
            commit=commit,
        )

    @staticmethod
    async def reset_on_visitor_message(
        db: AsyncSession,
        conversation,
        message,
        *,
        commit: bool = True,
    ) -> VisitorTimeoutCloseState | None:
        if not conversation or conversation.status != ConversationStatus.ACTIVE.value or not conversation.agent_id:
            return None
        if message.content_type not in VISITOR_MESSAGE_CONTENT_TYPES:
            return None
        if getattr(conversation, "visitor", None) is None:
            conversation = await ConversationRepository.get_by_id(db, conversation.id)
            if not conversation:
                return None
        existing = await VisitorTimeoutCloseStateRepository.get_by_conversation(db, conversation.id)
        if VisitorTimeoutCloseService._is_locked(existing):
            return existing
        payload, version = await VisitorTimeoutCloseService._setting_or_default(db, conversation.tenant_id)
        anchor_at = message.created_at or datetime.now(timezone.utc)
        next_check_at = VisitorTimeoutCloseService._next_check_at(payload, conversation, anchor_at, None)
        return await VisitorTimeoutCloseStateRepository.upsert_for_conversation(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            anchor_at=anchor_at,
            anchor_message_id=message.id,
            first_reminded_at=None,
            closed_at=None,
            next_check_at=next_check_at,
            config_version=version,
            commit=commit,
        )

    @staticmethod
    async def ensure_for_agent_message(
        db: AsyncSession,
        conversation,
        *,
        commit: bool = True,
    ) -> VisitorTimeoutCloseState | None:
        if not conversation or conversation.status != ConversationStatus.ACTIVE.value or not conversation.agent_id:
            return None
        existing = await VisitorTimeoutCloseStateRepository.get_by_conversation(db, conversation.id)
        if existing:
            return existing
        return await VisitorTimeoutCloseService.initialize_for_conversation(db, conversation, commit=commit)

    @staticmethod
    async def lock_conversation_timeout(
        db: AsyncSession,
        conversation,
        *,
        actor_id: int,
        commit: bool = True,
    ) -> VisitorTimeoutCloseState | None:
        state = await VisitorTimeoutCloseService.ensure_for_agent_message(db, conversation, commit=commit)
        if state is None:
            return None
        if getattr(state, "timeout_locked_at", None) is not None:
            return state
        return await VisitorTimeoutCloseStateRepository.update(
            db,
            state,
            {
                "timeout_locked_at": datetime.now(timezone.utc),
                "timeout_locked_by_id": actor_id,
                "next_check_at": None,
            },
            commit=commit,
        )

    @staticmethod
    async def unlock_conversation_timeout(
        db: AsyncSession,
        conversation,
        *,
        commit: bool = True,
    ) -> VisitorTimeoutCloseState | None:
        if not conversation or conversation.status != ConversationStatus.ACTIVE.value or not conversation.agent_id:
            return None
        if getattr(conversation, "visitor", None) is None:
            conversation = await ConversationRepository.get_by_id(db, conversation.id)
            if not conversation:
                return None
        state = await VisitorTimeoutCloseStateRepository.get_by_conversation(db, conversation.id)
        if state is None:
            state = await VisitorTimeoutCloseService.initialize_for_conversation(db, conversation, commit=commit)
            if state is None:
                return None
        payload, version = await VisitorTimeoutCloseService._setting_or_default(db, conversation.tenant_id)
        anchor_at = datetime.now(timezone.utc)
        next_check_at = VisitorTimeoutCloseService._next_check_at(payload, conversation, anchor_at, None)
        return await VisitorTimeoutCloseStateRepository.update(
            db,
            state,
            {
                "anchor_at": anchor_at,
                "anchor_message_id": None,
                "first_reminded_at": None,
                "closed_at": None,
                "next_check_at": next_check_at,
                "config_version": version,
                "timeout_locked_at": None,
                "timeout_locked_by_id": None,
            },
            commit=commit,
        )

    @staticmethod
    async def mark_inactive(
        db: AsyncSession,
        conversation_id: int,
        *,
        commit: bool = True,
    ) -> None:
        state = await VisitorTimeoutCloseStateRepository.get_by_conversation(db, conversation_id)
        if not state:
            return
        await VisitorTimeoutCloseStateRepository.update(
            db,
            state,
            {"next_check_at": None, "timeout_locked_at": None, "timeout_locked_by_id": None},
            commit=commit,
        )

    @staticmethod
    async def process_due_states(
        db: AsyncSession,
        r: aioredis.Redis | None = None,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> dict[str, int]:
        checked_at = now or datetime.now(timezone.utc)
        lease_until = checked_at + timedelta(seconds=CLAIM_LEASE_SECONDS)
        result = {"checked": 0, "reminded": 0, "closed": 0, "skipped": 0}
        while result["checked"] < limit:
            state = await VisitorTimeoutCloseStateRepository.claim_due(
                db,
                now=checked_at,
                lease_until=lease_until,
            )
            if state is None:
                break
            result["checked"] += 1
            outcome = await VisitorTimeoutCloseService.process_state(db, state, r, now=checked_at)
            if outcome in result:
                result[outcome] += 1
        return result

    @staticmethod
    async def process_state(
        db: AsyncSession,
        state: VisitorTimeoutCloseState,
        r: aioredis.Redis | None = None,
        *,
        now: datetime | None = None,
    ) -> str:
        checked_at = now or datetime.now(timezone.utc)
        fresh_state = await VisitorTimeoutCloseStateRepository.get_by_conversation(db, state.conversation_id)
        if fresh_state is None:
            return "skipped"
        state = fresh_state
        if VisitorTimeoutCloseService._is_locked(state):
            await VisitorTimeoutCloseStateRepository.update(db, state, {"next_check_at": None})
            return "skipped"
        conversation = await ConversationRepository.get_by_id(db, state.conversation_id)
        if (
            not conversation
            or conversation.tenant_id != state.tenant_id
            or conversation.status != ConversationStatus.ACTIVE.value
            or not conversation.agent_id
        ):
            await VisitorTimeoutCloseStateRepository.update(db, state, {"next_check_at": None})
            return "skipped"

        payload, version = await VisitorTimeoutCloseService._setting_or_default(db, conversation.tenant_id)
        if not payload.enabled:
            await VisitorTimeoutCloseStateRepository.update(
                db,
                state,
                {"next_check_at": None, "config_version": version},
            )
            return "skipped"

        latest_user_message = await MessageRepository.get_latest_by_sender(
            db,
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            sender_type=MessageSenderType.VISITOR.value,
            content_types=VISITOR_MESSAGE_CONTENT_TYPES,
        )
        if latest_user_message and (
            state.anchor_message_id != latest_user_message.id
            or latest_user_message.created_at > state.anchor_at
        ):
            await VisitorTimeoutCloseService.reset_on_visitor_message(db, conversation, latest_user_message)
            return "skipped"

        first_minutes, close_minutes = VisitorTimeoutCloseService._thresholds(payload, conversation)
        elapsed_seconds = (checked_at - state.anchor_at).total_seconds()
        if elapsed_seconds >= close_minutes * 60:
            await VisitorTimeoutCloseService._auto_close(
                db,
                state,
                conversation,
                payload,
                version,
                close_minutes,
                checked_at,
                r,
            )
            return "closed"

        if elapsed_seconds >= first_minutes * 60 and state.first_reminded_at is None:
            await VisitorTimeoutCloseService._send_reminder(
                db,
                state,
                conversation,
                payload,
                version,
                first_minutes,
                checked_at,
            )
            return "reminded"

        next_check_at = VisitorTimeoutCloseService._next_check_at(
            payload,
            conversation,
            state.anchor_at,
            state.first_reminded_at,
        )
        await VisitorTimeoutCloseStateRepository.update(
            db,
            state,
            {"next_check_at": next_check_at, "config_version": version},
        )
        return "skipped"

    @staticmethod
    def _visible_to(payload: VisitorTimeoutClosePayload) -> list[str]:
        visible_to: list[str] = []
        if payload.notify_agent:
            visible_to.append("agent")
        if payload.notify_visitor:
            visible_to.append("visitor")
        return visible_to

    @staticmethod
    async def _create_timeout_message(
        db: AsyncSession,
        conversation,
        *,
        content: str,
        event_type: str,
        actions: list[str],
        timeout_minutes: int,
        payload: VisitorTimeoutClosePayload,
        version: int,
        anchor_at: datetime,
    ):
        return await MessageRepository.create(
            db,
            {
                "tenant_id": conversation.tenant_id,
                "conversation_id": conversation.id,
                "sender_type": MessageSenderType.SYSTEM.value,
                "content_type": MessageContentType.SYSTEM.value,
                "content": content,
                "metadata_": {
                    "event_type": event_type,
                    "actor_type": "system_auto_tool",
                    "actor_name": AUTO_TOOL_NAME,
                    "actions": actions,
                    "timeout_minutes": timeout_minutes,
                    "visible_to": VisitorTimeoutCloseService._visible_to(payload),
                    "anchor_at": anchor_at.isoformat(),
                    "config_version": version,
                },
            },
        )

    @staticmethod
    async def _send_reminder(
        db: AsyncSession,
        state: VisitorTimeoutCloseState,
        conversation,
        payload: VisitorTimeoutClosePayload,
        version: int,
        timeout_minutes: int,
        now: datetime,
    ) -> None:
        message = await VisitorTimeoutCloseService._create_timeout_message(
            db,
            conversation,
            content=payload.first_reminder_content,
            event_type=FIRST_REMINDER_EVENT_TYPE,
            actions=["send_reminder"],
            timeout_minutes=timeout_minutes,
            payload=payload,
            version=version,
            anchor_at=state.anchor_at,
        )
        _, close_minutes = VisitorTimeoutCloseService._thresholds(payload, conversation)
        await VisitorTimeoutCloseStateRepository.update(
            db,
            state,
            {
                "first_reminded_at": now,
                "next_check_at": state.anchor_at + timedelta(minutes=close_minutes),
                "config_version": version,
            },
        )
        await VisitorTimeoutCloseService._emit_timeout_message(conversation, message, payload)
        logger.info(
            "visitor_timeout_first_reminder_sent tenant_id=%s conversation_id=%s agent_id=%s "
            "state_id=%s message_id=%s config_version=%s anchor_at=%s reminded_at=%s "
            "timeout_minutes=%s next_check_at=%s visible_to=%s",
            conversation.tenant_id,
            conversation.id,
            conversation.agent_id,
            state.id,
            message.id,
            version,
            state.anchor_at.isoformat(),
            now.isoformat(),
            timeout_minutes,
            (state.anchor_at + timedelta(minutes=close_minutes)).isoformat(),
            ",".join(VisitorTimeoutCloseService._visible_to(payload)),
        )

    @staticmethod
    async def _auto_close(
        db: AsyncSession,
        state: VisitorTimeoutCloseState,
        conversation,
        payload: VisitorTimeoutClosePayload,
        version: int,
        timeout_minutes: int,
        now: datetime,
        r: aioredis.Redis | None,
    ) -> None:
        message = await VisitorTimeoutCloseService._create_timeout_message(
            db,
            conversation,
            content=payload.close_reminder_content,
            event_type=AUTO_CLOSE_EVENT_TYPE,
            actions=["send_reminder", "close_conversation"],
            timeout_minutes=timeout_minutes,
            payload=payload,
            version=version,
            anchor_at=state.anchor_at,
        )
        conversation = await ConversationRepository.end_conversation(db, conversation, AUTO_CLOSE_ENDED_BY)
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            payload.close_reminder_content,
            message.created_at or now,
        )
        await VisitorTimeoutCloseStateRepository.update(
            db,
            state,
            {
                "closed_at": now,
                "next_check_at": None,
                "config_version": version,
            },
        )
        if r is not None and conversation.agent_id:
            await AgentStatusService.decrement_count(r, conversation.tenant_id, conversation.agent_id)
            await AgentStatusService.trigger_queue_backfill(r, conversation.tenant_id, conversation.agent_id)
        try:
            from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService

            await SatisfactionSurveyRecordService.send_session_end_invitation(db, conversation)
        except Exception:
            logger.exception("Failed to send timeout session-end satisfaction invitation for conversation %s", conversation.id)

        from app.services.reception_segment_service import ReceptionSegmentService

        await ReceptionSegmentService.generate_for_conversation(db, conversation.id)

        await VisitorTimeoutCloseService._emit_timeout_message(conversation, message, payload)
        await VisitorTimeoutCloseService._emit_conversation_ended(conversation)
        logger.info(
            "visitor_timeout_auto_closed tenant_id=%s conversation_id=%s agent_id=%s "
            "state_id=%s message_id=%s config_version=%s anchor_at=%s closed_at=%s "
            "elapsed_minutes=%.2f timeout_minutes=%s visible_to=%s",
            conversation.tenant_id,
            conversation.id,
            conversation.agent_id,
            state.id,
            message.id,
            version,
            state.anchor_at.isoformat(),
            now.isoformat(),
            (now - state.anchor_at).total_seconds() / 60,
            timeout_minutes,
            ",".join(VisitorTimeoutCloseService._visible_to(payload)),
        )

    @staticmethod
    def _message_payload(conversation, message, *, public: bool = False) -> dict:
        payload = {
            "id": message.id,
            "sender_type": message.sender_type,
            "sender_id": message.sender_id,
            "sender_name": None,
            "sender_avatar": None,
            "content_type": message.content_type,
            "content": message.content,
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "metadata": message.metadata_ or {},
            "event_type": (message.metadata_ or {}).get("event_type"),
            "satisfaction_record_id": (message.metadata_ or {}).get("satisfaction_record_id"),
            "config_version": (message.metadata_ or {}).get("config_version"),
        }
        if public:
            payload["conversation_public_id"] = conversation.public_id
        else:
            payload["conversation_id"] = conversation.id
        return payload

    @staticmethod
    async def _emit_timeout_message(conversation, message, payload: VisitorTimeoutClosePayload) -> None:
        try:
            from app.libs.realtime import get_realtime_transport

            rt = get_realtime_transport()
        except RuntimeError:
            return
        conv_room = f"conv:{conversation.id}"
        if payload.notify_agent:
            agent_payload = VisitorTimeoutCloseService._message_payload(conversation, message)
            if conversation.agent_id:
                await rt.emit(
                    "new_message",
                    agent_payload,
                    room=f"agent:{conversation.tenant_id}:{conversation.agent_id}",
                    namespace="/chat",
                )
            await rt.emit("new_message", agent_payload, room=conv_room, namespace="/chat")
        if payload.notify_visitor:
            visitor_payload = VisitorTimeoutCloseService._message_payload(conversation, message, public=True)
            await rt.emit("new_message", visitor_payload, room=conv_room, namespace="/visitor")

    @staticmethod
    async def _emit_conversation_ended(conversation) -> None:
        try:
            from app.libs.realtime import get_realtime_transport

            rt = get_realtime_transport()
        except RuntimeError:
            return
        end_payload = {
            "conversation_id": conversation.id,
            "conversation_public_id": conversation.public_id,
            "ended_by": AUTO_CLOSE_ENDED_BY,
        }
        conv_room = f"conv:{conversation.id}"
        if conversation.agent_id:
            await rt.emit(
                "conversation_ended",
                end_payload,
                room=f"agent:{conversation.tenant_id}:{conversation.agent_id}",
                namespace="/chat",
            )
        await rt.emit("conversation_ended", end_payload, room=conv_room, namespace="/chat")
        await rt.emit("conversation_ended", end_payload, room=conv_room, namespace="/visitor")
        await ConversationRealtimeService.emit_conversation_list_updated(
            conversation.tenant_id,
            action="ended",
            conversation_id=conversation.id,
            rt=rt,
        )
