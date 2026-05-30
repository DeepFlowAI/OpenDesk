"""
Session record service — business logic for historical session queries
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.session_record_repository import SessionRecordRepository
from app.repositories.satisfaction_survey_record_repository import SatisfactionSurveyRecordRepository
from app.repositories.ticket_repository import TicketRepository
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
    ) -> dict:
        filter_options = await SatisfactionSurveyRecordService.get_filter_options(db, tenant_id)
        items, total = await SessionRecordRepository.get_paginated(
            db,
            tenant_id=tenant_id,
            page=page,
            per_page=per_page,
            agent_id=agent_id,
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
    def _conversation_to_response(conversation, satisfaction_record=None, related_tickets=None) -> dict:
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
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, conversation_id: int):
        item = await SessionRecordRepository.get_by_id(db, conversation_id, tenant_id)
        if not item:
            raise NotFoundError("Session record not found")
        satisfaction = await SatisfactionSurveyRecordRepository.get_by_conversation(db, conversation_id)
        related_tickets = await TicketRepository.list_by_conversation_id(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        return SessionRecordService._conversation_to_response(item, satisfaction, related_tickets)

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        conversation_id: int,
        after_id: int | None = None,
        limit: int = 20,
    ) -> dict:
        """Get messages with forward cursor pagination and sender info enrichment."""
        item = await SessionRecordRepository.get_by_id(db, conversation_id)
        if not item:
            raise NotFoundError("Session record not found")

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
