"""Tenant event subscription management router."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_principal, get_current_principal_short_session, get_db
from app.models.event_subscription import EventSubscription
from app.schemas.event_subscription import (
    EventSubscriptionCreate,
    EventSubscriptionListResponse,
    EventSubscriptionResponse,
    EventSubscriptionSecretResponse,
    EventSubscriptionTestResponse,
    EventSubscriptionUpdate,
)
from app.schemas.permission import EffectivePrincipal
from app.services.event_subscription_service import EventSubscriptionService

router = APIRouter(prefix="/event-subscriptions", tags=["EventSubscriptions"])


@router.get("", response_model=EventSubscriptionListResponse)
async def list_event_subscriptions(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=80)] = None,
    status_filter: Annotated[Literal["active", "disabled"] | None, Query(alias="status")] = None,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List event subscriptions for the current tenant."""
    return await EventSubscriptionService.list_paginated(
        db,
        principal,
        page=page,
        per_page=per_page,
        query=q,
        status=status_filter,
    )


@router.post("", response_model=EventSubscriptionSecretResponse, status_code=status.HTTP_201_CREATED)
async def create_event_subscription(
    body: EventSubscriptionCreate,
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
) -> dict:
    """Create a subscription and return its secret once."""
    return await EventSubscriptionService.create_managed(principal, body)


@router.get("/{public_id}", response_model=EventSubscriptionResponse)
async def get_event_subscription(
    public_id: UUID,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> EventSubscription:
    """Get a subscription in the current tenant."""
    return await EventSubscriptionService.get_scoped(db, principal, public_id)


@router.put("/{public_id}", response_model=EventSubscriptionResponse)
async def update_event_subscription(
    public_id: UUID,
    body: EventSubscriptionUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
) -> EventSubscription:
    """Update subscription basic information."""
    return await EventSubscriptionService.update_managed(principal, public_id, body)


@router.post("/{public_id}/enable", response_model=EventSubscriptionResponse)
async def enable_event_subscription(
    public_id: UUID,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> EventSubscription:
    """Enable a subscription."""
    return await EventSubscriptionService.set_active(
        db, principal, public_id, is_active=True
    )


@router.post("/{public_id}/disable", response_model=EventSubscriptionResponse)
async def disable_event_subscription(
    public_id: UUID,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> EventSubscription:
    """Disable a subscription."""
    return await EventSubscriptionService.set_active(
        db, principal, public_id, is_active=False
    )


@router.post("/{public_id}/rotate-secret", response_model=EventSubscriptionSecretResponse)
async def rotate_event_subscription_secret(
    public_id: UUID,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rotate a webhook secret and return the new value once."""
    return await EventSubscriptionService.rotate_secret(db, principal, public_id)


@router.post("/{public_id}/test", response_model=EventSubscriptionTestResponse)
async def test_event_subscription(
    public_id: UUID,
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
) -> dict:
    """Send the fixed protocol verification request."""
    from app.services.event_delivery_service import EventDeliveryService

    return await EventDeliveryService.test_subscription_managed(principal, public_id)


@router.delete("/{public_id}", status_code=status.HTTP_200_OK)
async def delete_event_subscription(
    public_id: UUID,
    principal: EffectivePrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a disabled event subscription."""
    await EventSubscriptionService.delete(db, principal, public_id)
    return {"message": "Deleted successfully"}
