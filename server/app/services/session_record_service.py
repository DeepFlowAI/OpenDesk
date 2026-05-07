"""
Session record service — business logic for historical session queries
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.session_record_repository import SessionRecordRepository


class SessionRecordService:

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
    ) -> dict:
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
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, conversation_id: int):
        item = await SessionRecordRepository.get_by_id(db, conversation_id)
        if not item:
            raise NotFoundError("Session record not found")
        return item

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
        for msg in messages:
            entry = {
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "sender_type": msg.sender_type,
                "sender_id": msg.sender_id,
                "sender_name": None,
                "sender_avatar": None,
                "content_type": msg.content_type,
                "content": msg.content,
                "created_at": msg.created_at,
            }
            if msg.sender_type == "visitor" and item.visitor:
                entry["sender_name"] = item.visitor.name
            elif msg.sender_type == "agent" and item.agent:
                entry["sender_name"] = item.agent.display_name or item.agent.name
                entry["sender_avatar"] = item.agent.avatar if hasattr(item.agent, "avatar") else None
            enriched.append(entry)

        return {"items": enriched, "has_more": has_more}
