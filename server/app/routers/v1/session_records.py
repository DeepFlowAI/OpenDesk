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
from app.schemas.satisfaction_survey_record import (
    SatisfactionFilterOptionsResponse,
    SessionRecordSatisfactionResponse,
)
from app.services.session_record_service import SessionRecordService
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService

router = APIRouter(prefix="/session-records", tags=["SessionRecords"])


@router.get("", response_model=SessionRecordListResponse)
async def list_session_records(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    start_date: datetime | None = Query(None, description="Filter: started_at >="),
    end_date: datetime | None = Query(None, description="Filter: started_at <="),
    agent_id: int | None = Query(None, description="Filter by agent user ID"),
    visitor_id: int | None = Query(None, description="Filter by visitor user ID"),
    keyword: str | None = Query(None, max_length=100, description="Search visitor name, share code, or conversation public ID"),
    satisfaction_status: list[str] | None = Query(None, description="Satisfaction statuses: none, invited, submitted"),
    satisfaction_resolved: list[str] | None = Query(None, description="Service resolution: resolved, unresolved"),
    satisfaction_service_option: list[str] | None = Query(None, description="Current-version service rating option keys"),
    satisfaction_service_label: list[str] | None = Query(None, description="Current-version service labels"),
    satisfaction_product_option: list[str] | None = Query(None, description="Current-version product rating option keys"),
    satisfaction_product_label: list[str] | None = Query(None, description="Current-version product labels"),
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
        satisfaction_statuses=SatisfactionSurveyRecordService._normalize_list_param(satisfaction_status),
        satisfaction_resolved=SatisfactionSurveyRecordService._normalize_list_param(satisfaction_resolved),
        service_rating_options=SatisfactionSurveyRecordService._normalize_list_param(satisfaction_service_option),
        service_labels=SatisfactionSurveyRecordService._normalize_list_param(satisfaction_service_label),
        product_rating_options=SatisfactionSurveyRecordService._normalize_list_param(satisfaction_product_option),
        product_labels=SatisfactionSurveyRecordService._normalize_list_param(satisfaction_product_label),
    )


@router.get("/satisfaction/filter-options", response_model=SatisfactionFilterOptionsResponse)
async def get_satisfaction_filter_options(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get current-version satisfaction filter options for session records."""
    return await SatisfactionSurveyRecordService.get_filter_options(db, user["tenant_id"])


@router.get("/{record_id}", response_model=SessionRecordDetailResponse)
async def get_session_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get a single session record by ID."""
    return await SessionRecordService.get_by_id(db, record_id)


@router.get("/{record_id}/satisfaction", response_model=SessionRecordSatisfactionResponse)
async def get_session_record_satisfaction(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get structured satisfaction records for a session record."""
    return await SatisfactionSurveyRecordService.get_session_record_satisfaction(
        db,
        record_id=record_id,
        tenant_id=user["tenant_id"],
        user=user,
    )


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
