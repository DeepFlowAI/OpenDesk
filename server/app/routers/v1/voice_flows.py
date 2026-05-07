"""
Voice flow router — minimal CRUD for Flow Studio (full editor in 1.6.2)
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.voice_flow import (
    VoiceFlowCreate,
    VoiceFlowUpdate,
    VoiceFlowResponse,
    VoiceFlowListResponse,
    VoiceFlowSelectListResponse,
)
from app.services.voice_flow_service import VoiceFlowService

router = APIRouter(prefix="/voice-flows", tags=["VoiceFlows"])


@router.get("/select", response_model=VoiceFlowSelectListResponse)
async def list_voice_flows_for_select(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enabled, non-deleted flows for routing rule dropdown."""
    tenant_id = current_user["tenant_id"]
    return await VoiceFlowService.list_for_select(db, tenant_id)


@router.get("", response_model=VoiceFlowListResponse)
async def list_voice_flows(
    page: int = 1,
    per_page: int = 10,
    keyword: str | None = None,
    include_deleted: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await VoiceFlowService.get_paginated(
        db, tenant_id, page, per_page, keyword, include_deleted
    )


@router.post("", response_model=VoiceFlowResponse, status_code=status.HTTP_201_CREATED)
async def create_voice_flow(
    body: VoiceFlowCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await VoiceFlowService.create(db, tenant_id, body)


@router.get("/{flow_id}", response_model=VoiceFlowResponse)
async def get_voice_flow(
    flow_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await VoiceFlowService.get_by_id(db, flow_id, tenant_id)


@router.put("/{flow_id}", response_model=VoiceFlowResponse)
async def update_voice_flow(
    flow_id: int,
    body: VoiceFlowUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await VoiceFlowService.update(db, flow_id, tenant_id, body)


@router.delete("/{flow_id}", status_code=status.HTTP_200_OK)
async def delete_voice_flow(
    flow_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    await VoiceFlowService.delete(db, flow_id, tenant_id)
    return {"message": "Deleted successfully"}
