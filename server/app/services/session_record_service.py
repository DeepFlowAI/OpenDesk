"""
Session record service — business logic for historical session queries
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.enums import QueueChannel, QueueTaskType, QueueType
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.session_record_repository import SessionRecordRepository
from app.repositories.satisfaction_survey_record_repository import SatisfactionSurveyRecordRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService, RESOURCE_SESSION_RECORD
from app.services.queue_history_service import QueueHistoryService
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService


class SessionRecordService:
    @staticmethod
    def _bot_sender_name(conversation, metadata: dict) -> str:
        return (
            metadata.get("sender_name")
            or metadata.get("open_agent_agent_name")
            or getattr(conversation, "open_agent_agent_name", None)
            or "智能助手"
        )

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
            scope_predicate=scope_predicate,
        )
        satisfaction_by_conversation = await SatisfactionSurveyRecordRepository.get_by_conversation_ids(
            db,
            [item.id for item in items],
        )
        queue_summaries = await QueueHistoryService.summaries_for_refs(
            db,
            tenant_id,
            channel=QueueChannel.ONLINE_CHAT.value,
            task_types=[QueueTaskType.CONVERSATION.value, QueueTaskType.OPEN_AGENT_HANDOFF.value],
            ref_ids=[str(item.id) for item in items],
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": [
                SessionRecordService._conversation_to_response(
                    item,
                    satisfaction_by_conversation.get(item.id),
                    queue_summary=queue_summaries.get(str(item.id)),
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
        queue_summary: dict | None = None,
    ) -> dict:
        queue_summary = _effective_queue_summary(conversation, queue_summary)
        return {
            "id": conversation.id,
            "public_id": conversation.public_id,
            "share_code": conversation.share_code,
            "visitor": conversation.visitor,
            "agent": conversation.agent,
            "channel": conversation.channel,
            "status": conversation.status,
            "started_at": conversation.started_at,
            "ended_at": conversation.ended_at,
            "ended_by": conversation.ended_by,
            "created_at": conversation.created_at,
            "last_message_preview": getattr(conversation, "last_message_preview", None),
            "satisfaction": SatisfactionSurveyRecordService.record_summary(satisfaction_record),
            "related_tickets": SessionRecordService._ticket_briefs(related_tickets or []),
            "last_assigned_queue": queue_summary.get("last_assigned_queue"),
            "queue_duration_seconds": queue_summary.get("queue_duration_seconds"),
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
        queue_summaries = await QueueHistoryService.summaries_for_refs(
            db,
            tenant_id,
            channel=QueueChannel.ONLINE_CHAT.value,
            task_types=[QueueTaskType.CONVERSATION.value, QueueTaskType.OPEN_AGENT_HANDOFF.value],
            ref_ids=[str(conversation_id)],
        )
        return SessionRecordService._conversation_to_response(
            item,
            satisfaction,
            related_tickets,
            queue_summary=queue_summaries.get(str(conversation_id)),
        )

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
                "content": msg.content,
                "metadata": metadata,
                "created_at": msg.created_at,
                "event_type": metadata.get("event_type"),
                "satisfaction_record_id": metadata.get("satisfaction_record_id"),
                "config_version": metadata.get("config_version"),
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


def _effective_queue_summary(conversation, queue_summary: dict | None) -> dict:
    fallback = _queue_summary_from_conversation(conversation)
    queue_summary = queue_summary or {}
    return {
        "last_assigned_queue": (
            queue_summary.get("last_assigned_queue")
            or fallback.get("last_assigned_queue")
        ),
        "queue_duration_seconds": (
            queue_summary.get("queue_duration_seconds")
            if queue_summary.get("queue_duration_seconds") is not None
            else fallback.get("queue_duration_seconds")
        ),
    }


def _queue_summary_from_conversation(conversation) -> dict:
    queue = None
    group = getattr(conversation, "group", None)
    if group is not None and getattr(group, "name", None):
        queue = {
            "queue_type": QueueType.EMPLOYEE_GROUP.value,
            "queue_id": group.id,
            "name": group.name,
        }
    else:
        agent = getattr(conversation, "agent", None)
        if agent is not None:
            name = (
                getattr(agent, "display_name", None)
                or getattr(agent, "nickname", None)
                or getattr(agent, "name", None)
                or getattr(agent, "username", None)
            )
            if name:
                queue = {
                    "queue_type": QueueType.EMPLOYEE.value,
                    "queue_id": agent.id,
                    "name": name,
                }

    if queue is None:
        return {}

    return {
        "last_assigned_queue": queue,
        "queue_duration_seconds": None,
    }
