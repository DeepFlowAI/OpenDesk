"""
Session record service — business logic for historical session queries
"""
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.reception_segment_repository import ReceptionSegmentRepository
from app.repositories.session_record_repository import SessionRecordRepository
from app.repositories.satisfaction_survey_record_repository import SatisfactionSurveyRecordRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService, RESOURCE_SESSION_RECORD
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService


class SessionRecordService:
    _BOT_HANDOFF_STATUS_MAP = {
        "pending": "waiting_confirmation",
        "requested": "handoff_in_progress",
        "queued": "in_queue",
        "success": "succeeded",
        "failed": "failed",
        "dismissed": "dismissed",
    }

    @staticmethod
    def _bot_sender_name(conversation, metadata: dict) -> str:
        return (
            metadata.get("sender_name")
            or metadata.get("open_agent_agent_name")
            or getattr(conversation, "open_agent_agent_name", None)
            or "智能助手"
        )

    @staticmethod
    def _session_type(conversation) -> str | None:
        # Read the materialized bot flags (same caliber as the list filter), so
        # display and filtering never diverge and we avoid re-deriving the OR
        # over the three OpenAgent identity fields.
        if getattr(conversation, "had_bot_session", False):
            if getattr(conversation, "bot_handoff_succeeded", False):
                return "bot_human"
            return "bot"
        return "human"

    @staticmethod
    def _bot_handoff_status(conversation, session_type: str | None) -> str | None:
        if session_type not in {"bot", "bot_human"}:
            return None
        state = getattr(conversation, "open_agent_handoff_state", None)
        if state is None:
            return "not_triggered"
        return SessionRecordService._BOT_HANDOFF_STATUS_MAP.get(state)

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        agent_id: int | None = None,
        visitor_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        keyword: str | None = None,
        satisfaction_statuses: list[str] | None = None,
        satisfaction_resolved: list[str] | None = None,
        service_rating_options: list[str] | None = None,
        service_labels: list[str] | None = None,
        product_rating_options: list[str] | None = None,
        product_labels: list[str] | None = None,
        session_type: Literal["human", "bot", "bot_human"] | None = None,
        has_queue: bool | None = None,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        peer_ids: list[int] = []
        scope_predicate = None
        effective_agent_id = agent_id
        if principal is not None:
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            scope_predicate = DataScopeService.build_session_record_predicate(principal, peer_ids)
            effective_agent_id = DataScopeService.resolve_agent_filter(
                principal,
                RESOURCE_SESSION_RECORD,
                agent_id,
                peer_ids,
            )
        filter_options = await SatisfactionSurveyRecordService.get_filter_options(db, tenant_id)
        items, total = await SessionRecordRepository.get_paginated(
            db,
            tenant_id=tenant_id,
            page=page,
            per_page=per_page,
            agent_id=effective_agent_id,
            visitor_id=visitor_id,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            satisfaction_statuses=satisfaction_statuses,
            current_satisfaction_version=filter_options.get("current_version"),
            satisfaction_resolved=satisfaction_resolved,
            service_rating_options=service_rating_options,
            service_labels=service_labels,
            product_rating_options=product_rating_options,
            product_labels=product_labels,
            session_type=session_type,
            has_queue=has_queue,
            scope_predicate=scope_predicate,
        )
        satisfaction_by_conversation = await SatisfactionSurveyRecordRepository.get_by_conversation_ids(
            db,
            [item.id for item in items],
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": [
                SessionRecordService._conversation_to_response(
                    item,
                    satisfaction_by_conversation.get(item.id),
                )
                for item in items
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    def _ticket_briefs(tickets) -> list[dict]:
        return [
            {
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
            }
            for ticket in tickets
        ]

    @staticmethod
    def _conversation_to_response(
        conversation,
        satisfaction_record=None,
        related_tickets=None,
    ) -> dict:
        session_type = SessionRecordService._session_type(conversation)
        visitor_message_count = getattr(conversation, "visitor_message_count", 0) or 0
        agent_message_count = getattr(conversation, "agent_message_count", 0) or 0
        return {
            "id": conversation.id,
            "public_id": conversation.public_id,
            "share_code": conversation.share_code,
            "session_type": session_type,
            "bot_handoff_status": SessionRecordService._bot_handoff_status(conversation, session_type),
            "visitor": conversation.visitor,
            "agent": conversation.agent,
            "channel": conversation.channel,
            "status": conversation.status,
            "started_at": conversation.started_at,
            "ended_at": conversation.ended_at,
            "ended_by": conversation.ended_by,
            "duration_seconds": getattr(conversation, "duration_seconds", None),
            "visitor_system": getattr(conversation, "visitor_system", None),
            "visitor_browser": getattr(conversation, "visitor_browser", None),
            "visitor_ip": getattr(conversation, "visitor_ip", None),
            "created_at": conversation.created_at,
            "message_count": visitor_message_count + agent_message_count,
            "visitor_message_count": visitor_message_count,
            "agent_message_count": agent_message_count,
            "bot_phase_message_count": getattr(conversation, "bot_phase_message_count", 0) or 0,
            "human_phase_message_count": getattr(conversation, "human_phase_message_count", 0) or 0,
            "human_phase_visitor_message_count": getattr(
                conversation, "human_phase_visitor_message_count", 0
            ) or 0,
            "human_phase_agent_message_count": getattr(
                conversation, "human_phase_agent_message_count", 0
            ) or 0,
            "last_message_preview": getattr(conversation, "last_message_preview", None),
            "satisfaction": SatisfactionSurveyRecordService.record_summary(satisfaction_record),
            "related_tickets": SessionRecordService._ticket_briefs(related_tickets or []),
            "last_assigned_queue": _last_assigned_queue(conversation),
            "queue_duration_seconds": getattr(conversation, "total_queue_duration_seconds", None),
            "first_human_response_seconds": getattr(conversation, "first_human_response_seconds", None),
            "agent_response_count": getattr(conversation, "agent_response_count", None),
            "agent_avg_response_seconds": getattr(conversation, "agent_avg_response_seconds", None),
            "has_queue": bool((getattr(conversation, "total_queue_duration_seconds", None) or 0) > 0),
            "queue_entered_at": getattr(conversation, "queue_entered_at", None),
            "queue_assigned_at": getattr(conversation, "queue_assigned_at", None),
            "queue_result": getattr(conversation, "queue_result", None),
            "reception_segment_count": getattr(conversation, "reception_segment_count", 0) or 0,
            "reception_transfer_count": getattr(conversation, "reception_transfer_count", 0) or 0,
            "reception_final_agent_id": getattr(conversation, "reception_final_agent_id", None),
            "reception_participants": getattr(conversation, "reception_participants", None) or [],
            "reception_generation_status": getattr(conversation, "reception_generation_status", None),
        }

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        principal: EffectivePrincipal | None = None,
    ):
        item = await SessionRecordRepository.get_by_id(db, conversation_id, tenant_id)
        if not item:
            raise NotFoundError("Session record not found")
        if principal is not None:
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            DataScopeService.assert_conversation_in_scope(principal, item, peer_ids)
        satisfaction = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation_id)
        related_tickets = await TicketRepository.list_by_conversation_id(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        return SessionRecordService._conversation_to_response(
            item,
            satisfaction,
            related_tickets,
        )

    @staticmethod
    async def get_reception_trajectory(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        """Return the conversation's reception segments and generation status."""
        item = await SessionRecordRepository.get_by_id(db, conversation_id, tenant_id)
        if not item:
            raise NotFoundError("Session record not found")
        if principal is not None:
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            DataScopeService.assert_conversation_in_scope(principal, item, peer_ids)
        segments = await ReceptionSegmentRepository.list_for_conversation(db, conversation_id)
        return {
            "conversation_id": conversation_id,
            "conversation_status": item.status,
            "generation_status": getattr(item, "reception_generation_status", None),
            "segments": [
                {
                    "seq_no": segment.seq_no,
                    "agent_id": segment.agent_id,
                    "agent_name": segment.agent_name_snapshot,
                    "group_id": segment.group_id,
                    "group_name": segment.group_name_snapshot,
                    "started_at": segment.started_at,
                    "ended_at": segment.ended_at,
                    "duration_seconds": segment.duration_seconds,
                    "entry_reason": segment.entry_reason,
                    "end_reason": segment.end_reason,
                    "from_agent_id": segment.from_agent_id,
                    "to_agent_id": segment.to_agent_id,
                    "visitor_message_count": segment.visitor_message_count,
                    "agent_message_count": segment.agent_message_count,
                    "first_response_seconds": segment.first_response_seconds,
                    "avg_response_seconds": segment.avg_response_seconds,
                }
                for segment in segments
            ],
        }

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        conversation_id: int,
        after_id: int | None = None,
        limit: int = 20,
        tenant_id: int | None = None,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        """Get messages with forward cursor pagination and sender info enrichment."""
        item = await SessionRecordRepository.get_by_id(db, conversation_id, tenant_id)
        if not item:
            raise NotFoundError("Session record not found")
        if principal is not None:
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            DataScopeService.assert_conversation_in_scope(principal, item, peer_ids)

        messages = await SessionRecordRepository.get_messages(
            db, conversation_id, after_id=after_id, limit=limit + 1
        )
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        enriched = []
        agent_ids = list({
            msg.sender_id
            for msg in messages
            if msg.sender_type == "agent" and msg.sender_id is not None
        })
        agents = {agent.id: agent for agent in await EmployeeRepository.get_by_ids(db, agent_ids)}

        from app.services.conversation_service import ConversationService
        for msg in messages:
            metadata = msg.metadata_ or {}
            entry = {
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "sender_type": msg.sender_type,
                "sender_id": msg.sender_id,
                "sender_name": None,
                "sender_avatar": None,
                "content_type": msg.content_type,
                "content": ConversationService._message_response_content(msg),
                "created_at": msg.created_at,
                **ConversationService._message_event_overlay(msg),
                **ConversationService._message_recall_overlay(msg),
            }
            if msg.sender_type == "visitor" and item.visitor:
                entry["sender_name"] = item.visitor.name
            elif msg.sender_type == "agent" and item.agent:
                agent = agents.get(msg.sender_id) if msg.sender_id is not None else item.agent
                entry["sender_name"] = (agent.display_name or agent.name) if agent else (item.agent.display_name or item.agent.name)
                entry["sender_avatar"] = agent.avatar if agent and hasattr(agent, "avatar") else None
            elif msg.sender_type == "bot":
                entry["sender_name"] = SessionRecordService._bot_sender_name(item, metadata)
            enriched.append(entry)

        return {"items": enriched, "has_more": has_more}


def _last_assigned_queue(conversation) -> dict | None:
    """Build the last-assigned-queue brief from materialized conversation columns."""
    queue_type = getattr(conversation, "last_assigned_queue_type", None)
    queue_id = getattr(conversation, "last_assigned_queue_id", None)
    name = getattr(conversation, "last_assigned_queue_name", None)
    if not queue_type or queue_id is None or not name:
        return None
    return {"queue_type": queue_type, "queue_id": queue_id, "name": name}
