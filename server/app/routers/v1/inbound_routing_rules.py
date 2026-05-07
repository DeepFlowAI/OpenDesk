"""
Inbound routing rules router
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.schemas.inbound_routing_rule import (
    InboundRoutingRuleCreate,
    InboundRoutingRuleUpdate,
    InboundRoutingRuleResponse,
    InboundRoutingRuleListResponse,
    InboundRoutingRuleEnabledPatch,
    InboundRoutingRuleReorder,
)
from app.services.inbound_routing_rule_service import InboundRoutingRuleService

router = APIRouter(prefix="/inbound-routing-rules", tags=["InboundRoutingRules"])


@router.put("/reorder", status_code=status.HTTP_200_OK)
async def reorder_routing_rules(
    body: InboundRoutingRuleReorder,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    await InboundRoutingRuleService.reorder(db, tenant_id, body.ordered_ids)
    return {"message": "Reordered successfully"}


@router.get("", response_model=InboundRoutingRuleListResponse)
async def list_routing_rules(
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await InboundRoutingRuleService.get_paginated(db, tenant_id, page, per_page)


@router.post("", response_model=InboundRoutingRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_routing_rule(
    body: InboundRoutingRuleCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await InboundRoutingRuleService.create(db, tenant_id, body)


@router.get("/{rule_id}", response_model=InboundRoutingRuleResponse)
async def get_routing_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await InboundRoutingRuleService.get_by_id(db, rule_id, tenant_id)


@router.put("/{rule_id}", response_model=InboundRoutingRuleResponse)
async def update_routing_rule(
    rule_id: int,
    body: InboundRoutingRuleUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await InboundRoutingRuleService.update(db, rule_id, tenant_id, body)


@router.patch("/{rule_id}", response_model=InboundRoutingRuleResponse)
async def patch_routing_rule_enabled(
    rule_id: int,
    body: InboundRoutingRuleEnabledPatch,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    return await InboundRoutingRuleService.patch_enabled(db, rule_id, tenant_id, body.enabled)


@router.delete("/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_routing_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    await InboundRoutingRuleService.delete(db, rule_id, tenant_id)
    return {"message": "Deleted successfully"}
