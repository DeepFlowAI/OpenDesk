"""Read VoiceSpeed robot-stage transcripts for the call workspace.

OpenDesk does not persist a copy. After a short DB lookup (CDR, bot_started,
credentials, assignment), the VoiceSpeed HTTP call runs with no session held.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import redis_client
from app.db.session import AsyncSessionLocal
from app.libs.voice_speed import create_voice_speed_client
from app.libs.voice_speed.base import (
    VoiceSpeedCallTranscript,
    VoiceSpeedCallTranscriptMessage,
    VoiceSpeedClientError,
)
from app.models.call_record import CallRecord
from app.repositories.call_event_repository import CallEventRepository
from app.repositories.call_record_repository import CallRecordRepository
from app.schemas.call_center import BotTranscriptMessage, BotTranscriptResponse
from app.schemas.permission import EffectivePrincipal
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.call_record_service import CallRecordService
from app.services.open_agent_settings_service import OpenAgentSettingsService

_HIDDEN = BotTranscriptResponse(available=False, status="empty")
_LIVE_STATES = frozenset({"reserved", "ringing", "in_call", "after_call_work"})


def map_bot_messages(
    raw: list[VoiceSpeedCallTranscriptMessage],
) -> list[BotTranscriptMessage]:
    """Apply the screen-pop interrupt rules to VoiceSpeed messages."""
    visible: list[BotTranscriptMessage] = []
    for item in raw:
        if item.role == "user":
            if item.content:
                visible.append(
                    BotTranscriptMessage(role="user", text=item.content, interrupted=False)
                )
            continue
        if item.role != "assistant":
            continue
        if item.interrupted and item.heard_content == "":
            continue
        if item.interrupted and item.heard_content is not None:
            text = item.heard_content
        else:
            text = item.content
        if not text:
            continue
        visible.append(
            BotTranscriptMessage(role="bot", text=text, interrupted=item.interrupted)
        )
    return visible


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _history_entered_human(row: CallRecord) -> bool:
    return bool(
        row.actual_reception_type == "bot_agent"
        or row.first_agent_connected_at
        or row.bot_handoff_succeeded_at
    )


class BotTranscriptService:

    @staticmethod
    async def get_for_workspace_managed(
        principal: EffectivePrincipal,
        call_id: str,
    ) -> BotTranscriptResponse:
        employee_id = principal.user_id
        if not employee_id:
            return _HIDDEN

        async with AsyncSessionLocal() as db:
            prepared = await BotTranscriptService._prepare(
                db, tenant_id=principal.tenant_id, call_id=call_id
            )

        if prepared is None:
            return _HIDDEN
        assigned = (
            prepared.last_serving_agent_id == employee_id
            or await BotTranscriptService._has_live_assignment(
                principal.tenant_id, employee_id, call_id
            )
        )
        if not assigned:
            return _HIDDEN
        return await BotTranscriptService._fetch(
            prepared, entered_human=True
        )

    @staticmethod
    async def get_for_record_managed(
        principal: EffectivePrincipal,
        public_id: UUID,
    ) -> BotTranscriptResponse:
        async with AsyncSessionLocal() as db:
            row = await CallRecordService.get_scoped_row_by_public_id(
                db, public_id, principal.tenant_id, principal
            )
            prepared = await BotTranscriptService._prepare_row(db, row)
            entered_human = _history_entered_human(row)

        if prepared is None:
            return _HIDDEN
        return await BotTranscriptService._fetch(prepared, entered_human=entered_human)

    @staticmethod
    async def _prepare(
        db: AsyncSession, *, tenant_id: int, call_id: str
    ) -> "_PreparedBotCall | None":
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if row is None:
            return None
        return await BotTranscriptService._prepare_row(db, row)

    @staticmethod
    async def _prepare_row(db: AsyncSession, row: CallRecord) -> "_PreparedBotCall | None":
        event = await CallEventRepository.get_latest_of_type(db, row.id, "bot_started")
        agent_id = (event.actor_id or event.target_id or "").strip() if event else ""
        if not agent_id:
            return None
        credentials = await OpenAgentSettingsService.get_voice_speed_credentials(
            db, row.tenant_id
        )
        snapshot_name = None
        if event is not None:
            snapshot_name = event.actor_name_snapshot or event.target_name_snapshot
        return _PreparedBotCall(
            call_id=row.call_id,
            agent_id=agent_id,
            agent_name_snapshot=snapshot_name,
            credentials=credentials,
            last_serving_agent_id=row.last_serving_agent_id,
        )

    @staticmethod
    async def _has_live_assignment(tenant_id: int, employee_id: int, call_id: str) -> bool:
        r = redis_client.client
        if r is None:
            return False
        snap = await CcAgentResourceService.get_snapshot(r, tenant_id, employee_id)
        if not snap:
            return False
        if snap.get("resource_state") not in _LIVE_STATES:
            return False
        return call_id in {snap.get("current_call_id"), snap.get("wrap_up_call_id")}

    @staticmethod
    async def _fetch(
        prepared: "_PreparedBotCall", *, entered_human: bool
    ) -> BotTranscriptResponse:
        if prepared.credentials is None:
            return BotTranscriptResponse(
                available=True,
                status="error",
                agent_name=prepared.agent_name_snapshot,
                entered_human=entered_human,
            )
        base_url, api_key = prepared.credentials
        client = create_voice_speed_client()
        try:
            transcript = await client.get_call_transcript(
                base_url, api_key, prepared.agent_id, prepared.call_id
            )
        except VoiceSpeedClientError as exc:
            if exc.status_code == 404:
                return BotTranscriptResponse(
                    available=True,
                    status="empty",
                    agent_name=prepared.agent_name_snapshot,
                    entered_human=entered_human,
                )
            return BotTranscriptResponse(
                available=True,
                status="error",
                agent_name=prepared.agent_name_snapshot,
                entered_human=entered_human,
            )
        return BotTranscriptService._to_response(
            transcript, prepared.agent_name_snapshot, entered_human
        )

    @staticmethod
    def _to_response(
        transcript: VoiceSpeedCallTranscript,
        fallback_name: str | None,
        entered_human: bool,
    ) -> BotTranscriptResponse:
        messages = map_bot_messages(transcript.messages)
        return BotTranscriptResponse(
            available=True,
            status="ok" if messages else "empty",
            agent_name=transcript.agent_name or fallback_name,
            handoff_at=_parse_iso(transcript.handoff_at),
            entered_human=entered_human,
            messages=messages,
        )


class _PreparedBotCall:
    __slots__ = (
        "call_id",
        "agent_id",
        "agent_name_snapshot",
        "credentials",
        "last_serving_agent_id",
    )

    def __init__(
        self,
        *,
        call_id: str,
        agent_id: str,
        agent_name_snapshot: str | None,
        credentials: tuple[str, str] | None,
        last_serving_agent_id: int | None = None,
    ) -> None:
        self.call_id = call_id
        self.agent_id = agent_id
        self.agent_name_snapshot = agent_name_snapshot
        self.credentials = credentials
        self.last_serving_agent_id = last_serving_agent_id
