"""Admin routes for call event subscription rules."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_permission
from app.schemas.call_event_subscription import (
    CallEventRuleListResponse,
    CallEventRuleOptionsResponse,
    CallEventRuleResponse,
    CallEventRuleSave,
)
from app.schemas.permission import EffectivePrincipal
from app.services.call_event_subscription_service import (
    MANAGE_PERMISSION,
    CallEventSubscriptionService,
)

router = APIRouter(
    prefix="/call-center/event-subscription-rules", tags=["CallEventSubscriptions"]
)


@router.get("", response_model=CallEventRuleListResponse)
async def list_rules(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=50),
    status_filter: Literal["active", "inactive"] | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> CallEventRuleListResponse:
    return await CallEventSubscriptionService.list_rules(
        db, principal, page=page, per_page=per_page, q=q, status=status_filter
    )


@router.get("/options", response_model=CallEventRuleOptionsResponse)
async def list_subscription_options(
    rule_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> CallEventRuleOptionsResponse:
    return await CallEventSubscriptionService.list_options(db, principal, rule_id)


@router.post("", response_model=CallEventRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: CallEventRuleSave,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> CallEventRuleResponse:
    return await CallEventSubscriptionService.create_rule(db, principal, body)


@router.get("/{rule_id}", response_model=CallEventRuleResponse)
async def get_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> CallEventRuleResponse:
    return await CallEventSubscriptionService.get_rule(db, principal, rule_id)


@router.put("/{rule_id}", response_model=CallEventRuleResponse)
async def update_rule(
    rule_id: UUID,
    body: CallEventRuleSave,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> CallEventRuleResponse:
    return await CallEventSubscriptionService.update_rule(db, principal, rule_id, body)


@router.post("/{rule_id}/enable", response_model=CallEventRuleResponse)
async def enable_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> CallEventRuleResponse:
    return await CallEventSubscriptionService.set_active(db, principal, rule_id, True)


@router.post("/{rule_id}/disable", response_model=CallEventRuleResponse)
async def disable_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> CallEventRuleResponse:
    return await CallEventSubscriptionService.set_active(db, principal, rule_id, False)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(require_permission(MANAGE_PERMISSION)),
) -> Response:
    await CallEventSubscriptionService.delete_rule(db, principal, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
