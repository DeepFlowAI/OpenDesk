"""
Session record router — read-only APIs for historical conversation records
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.session_record import (
    SessionRecordListResponse,
    SessionRecordDetailResponse,
    SessionRecordMessageListResponse,
)
from app.services.session_record_service import SessionRecordService

router = APIRouter(prefix="/session-records", tags=["SessionRecords"])


@router.get("", response_model=SessionRecordListResponse)
async def list_session_records(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    start_date: datetime | None = Query(None, description="Filter: started_at >="),
    end_date: datetime | None = Query(None, description="Filter: started_at <="),
    agent_id: int | None = Query(None, description="Filter by agent user ID"),
    visitor_id: int | None = Query(None, description="Filter by visitor user ID"),
    keyword: str | None = Query(None, max_length=100, description="Search visitor name or conversation ID"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List historical session records with optional filters and pagination."""
    tenant_id = user["tenant_id"]
    roles = user.get("roles", ["agent"])

    effective_agent_id = agent_id
    if "admin" not in roles:
        effective_agent_id = user["user_id"]

    return await SessionRecordService.get_paginated(
        db,
        tenant_id=tenant_id,
        page=page,
        per_page=per_page,
        agent_id=effective_agent_id,
        visitor_id=visitor_id,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
    )


@router.get("/{record_id}", response_model=SessionRecordDetailResponse)
async def get_session_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get a single session record by ID."""
    return await SessionRecordService.get_by_id(db, record_id)


@router.get("/{record_id}/messages", response_model=SessionRecordMessageListResponse)
async def list_session_record_messages(
    record_id: int,
    after_id: int | None = Query(None, description="Cursor: load messages after this ID"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get messages for a session record (forward cursor pagination)."""
    return await SessionRecordService.get_messages(
        db, conversation_id=record_id, after_id=after_id, limit=limit
    )
