"""
Session routing rules router
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.session_routing_rule import (
    SessionRoutingRuleCreate,
    SessionRoutingRuleUpdate,
    SessionRoutingRuleResponse,
    SessionRoutingRuleListResponse,
    SessionRoutingRuleEnabledPatch,
    SessionRoutingRuleReorder,
)
from app.services.session_routing_rule_service import SessionRoutingRuleService

router = APIRouter(prefix="/session-routing-rules", tags=["SessionRoutingRules"])


@router.put("/reorder", status_code=status.HTTP_200_OK)
async def reorder_session_routing_rules(
    body: SessionRoutingRuleReorder,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reorder session routing rules by drag-and-drop"""
    tenant_id = current_user["tenant_id"]
    await SessionRoutingRuleService.reorder(db, tenant_id, body.ordered_ids)
    return {"message": "Reordered successfully"}


@router.get("", response_model=SessionRoutingRuleListResponse)
async def list_session_routing_rules(
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List session routing rules ordered by priority"""
    tenant_id = current_user["tenant_id"]
    return await SessionRoutingRuleService.get_paginated(db, tenant_id, page, per_page)


@router.post("", response_model=SessionRoutingRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_session_routing_rule(
    body: SessionRoutingRuleCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new session routing rule"""
    tenant_id = current_user["tenant_id"]
    return await SessionRoutingRuleService.create(db, tenant_id, body)


@router.get("/{rule_id}", response_model=SessionRoutingRuleResponse)
async def get_session_routing_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a session routing rule by ID"""
    tenant_id = current_user["tenant_id"]
    return await SessionRoutingRuleService.get_by_id(db, rule_id, tenant_id)


@router.put("/{rule_id}", response_model=SessionRoutingRuleResponse)
async def update_session_routing_rule(
    rule_id: int,
    body: SessionRoutingRuleUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a session routing rule"""
    tenant_id = current_user["tenant_id"]
    return await SessionRoutingRuleService.update(db, rule_id, tenant_id, body)


@router.patch("/{rule_id}", response_model=SessionRoutingRuleResponse)
async def patch_session_routing_rule_enabled(
    rule_id: int,
    body: SessionRoutingRuleEnabledPatch,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle session routing rule enabled/disabled"""
    tenant_id = current_user["tenant_id"]
    return await SessionRoutingRuleService.patch_enabled(db, rule_id, tenant_id, body.enabled)


@router.delete("/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_session_routing_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a session routing rule"""
    tenant_id = current_user["tenant_id"]
    await SessionRoutingRuleService.delete(db, rule_id, tenant_id)
    return {"message": "Deleted successfully"}
