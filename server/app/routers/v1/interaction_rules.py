"""
Interaction rules router — CRUD endpoints nested under form layouts
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.fd_interaction_rule import (
    FdInteractionRuleCreate,
    FdInteractionRuleUpdate,
    FdInteractionRuleResponse,
    FdInteractionRuleListResponse,
    InteractionRuleSortRequest,
)
from app.services.fd_interaction_rule_service import FdInteractionRuleService

router = APIRouter(prefix="/form-layouts/{layout_id}/interaction-rules", tags=["InteractionRules"])


@router.get("", response_model=FdInteractionRuleListResponse)
async def list_interaction_rules(
    layout_id: int,
    page: int = 1,
    per_page: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List interaction rules for a layout"""
    return await FdInteractionRuleService.get_paginated(db, layout_id, user["tenant_id"], page, per_page)


@router.post("", response_model=FdInteractionRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_interaction_rule(
    layout_id: int,
    body: FdInteractionRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create an interaction rule"""
    return await FdInteractionRuleService.create(db, layout_id, user["tenant_id"], body)


@router.get("/{rule_id}", response_model=FdInteractionRuleResponse)
async def get_interaction_rule(
    layout_id: int,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get interaction rule by ID"""
    return await FdInteractionRuleService.get_by_id(db, rule_id, user["tenant_id"])


@router.put("/{rule_id}", response_model=FdInteractionRuleResponse)
async def update_interaction_rule(
    layout_id: int,
    rule_id: int,
    body: FdInteractionRuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update an interaction rule"""
    return await FdInteractionRuleService.update(db, rule_id, user["tenant_id"], body)


@router.delete("/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_interaction_rule(
    layout_id: int,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete an interaction rule"""
    await FdInteractionRuleService.delete(db, rule_id, user["tenant_id"])
    return {"message": "Deleted successfully"}


@router.put("/sort", status_code=status.HTTP_200_OK)
async def sort_interaction_rules(
    layout_id: int,
    body: InteractionRuleSortRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Reorder interaction rules"""
    await FdInteractionRuleService.sort(db, layout_id, user["tenant_id"], body)
    return {"message": "Sort updated"}
