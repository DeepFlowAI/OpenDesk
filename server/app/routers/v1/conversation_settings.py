"""
Conversation settings router.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_current_user, get_db
from app.schemas.welcome_message_rule import (
    WelcomeMessageRuleCreate,
    WelcomeMessageRuleEnabledPatch,
    WelcomeMessageRuleListResponse,
    WelcomeMessageRuleReorder,
    WelcomeMessageRuleResponse,
    WelcomeMessageRuleUpdate,
)
from app.schemas.satisfaction_survey_config import (
    SatisfactionSurveyConfigPayload,
    SatisfactionSurveyConfigResponse,
    SatisfactionSurveyEnabledPatch,
    SatisfactionSurveyVersionDetail,
    SatisfactionSurveyVersionListResponse,
)
from app.services.satisfaction_survey_config_service import SatisfactionSurveyConfigService
from app.services.welcome_message_rule_service import WelcomeMessageRuleService

router = APIRouter(prefix="/conversation-settings", tags=["ConversationSettings"])


@router.get("/satisfaction", response_model=SatisfactionSurveyConfigResponse)
async def get_satisfaction_survey_config(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current satisfaction survey config or a default draft."""
    return await SatisfactionSurveyConfigService.get_current(db, current_user["tenant_id"])


@router.put("/satisfaction", response_model=SatisfactionSurveyConfigResponse)
async def save_satisfaction_survey_config(
    body: SatisfactionSurveyConfigPayload,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save satisfaction survey config; bump version only when rating structure changes."""
    return await SatisfactionSurveyConfigService.save(db, current_user["tenant_id"], current_user, body)


@router.patch("/satisfaction/enabled", response_model=SatisfactionSurveyConfigResponse)
async def patch_satisfaction_survey_enabled(
    body: SatisfactionSurveyEnabledPatch,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle satisfaction survey config enabled state."""
    return await SatisfactionSurveyConfigService.patch_enabled(
        db,
        current_user["tenant_id"],
        current_user,
        body.enabled,
    )


@router.get("/satisfaction/versions", response_model=SatisfactionSurveyVersionListResponse)
async def list_satisfaction_survey_versions(
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List satisfaction survey config versions."""
    return await SatisfactionSurveyConfigService.list_versions(db, current_user["tenant_id"], page, per_page)


@router.get("/satisfaction/versions/{version}", response_model=SatisfactionSurveyVersionDetail)
async def get_satisfaction_survey_version(
    version: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a satisfaction survey config version snapshot."""
    return await SatisfactionSurveyConfigService.get_version(db, current_user["tenant_id"], version)


@router.put("/welcome-rules/reorder", status_code=status.HTTP_200_OK)
async def reorder_welcome_message_rules(
    body: WelcomeMessageRuleReorder,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reorder welcome message rules by drag-and-drop."""
    await WelcomeMessageRuleService.reorder(db, current_user["tenant_id"], body.ordered_ids)
    return {"message": "Reordered successfully"}


@router.get("/welcome-rules", response_model=WelcomeMessageRuleListResponse)
async def list_welcome_message_rules(
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List welcome message rules ordered by priority."""
    return await WelcomeMessageRuleService.get_paginated(db, current_user["tenant_id"], page, per_page)


@router.post(
    "/welcome-rules",
    response_model=WelcomeMessageRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_welcome_message_rule(
    body: WelcomeMessageRuleCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new welcome message rule."""
    return await WelcomeMessageRuleService.create(db, current_user["tenant_id"], body)


@router.get("/welcome-rules/{rule_id}", response_model=WelcomeMessageRuleResponse)
async def get_welcome_message_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a welcome message rule by ID."""
    return await WelcomeMessageRuleService.get_by_id(db, rule_id, current_user["tenant_id"])


@router.put("/welcome-rules/{rule_id}", response_model=WelcomeMessageRuleResponse)
async def update_welcome_message_rule(
    rule_id: int,
    body: WelcomeMessageRuleUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a welcome message rule."""
    return await WelcomeMessageRuleService.update(db, rule_id, current_user["tenant_id"], body)


@router.patch("/welcome-rules/{rule_id}", response_model=WelcomeMessageRuleResponse)
async def patch_welcome_message_rule_enabled(
    rule_id: int,
    body: WelcomeMessageRuleEnabledPatch,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle welcome message rule enabled/disabled."""
    return await WelcomeMessageRuleService.patch_enabled(db, rule_id, current_user["tenant_id"], body.enabled)


@router.delete("/welcome-rules/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_welcome_message_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a welcome message rule."""
    await WelcomeMessageRuleService.delete(db, rule_id, current_user["tenant_id"])
    return {"message": "Deleted successfully"}
