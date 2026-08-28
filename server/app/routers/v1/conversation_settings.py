"""
Conversation settings router.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import (
    get_current_principal_short_session,
    get_current_user,
    get_db,
    require_all_permissions,
    require_permission,
)
from app.core.exceptions import ForbiddenError
from app.schemas.permission import EffectivePrincipal
from app.schemas.emoji_setting import (
    EmojiSettingPayload,
    EmojiSettingResponse,
    EmojiTargetConfigResponse,
)
from app.schemas.conversation_user_statistics import (
    ConversationUserStatFieldSettingsPayload,
    ConversationUserStatFieldSettingsResponse,
)
from app.schemas.conversation_read_status import (
    ConversationReadStatusPayload,
    ConversationReadStatusResponse,
    ConversationReadStatusTargetResponse,
)
from app.schemas.conversation_agent_display_setting import (
    ConversationAgentDisplaySettingPayload,
    ConversationAgentDisplaySettingResponse,
    ConversationAgentDisplayTargetResponse,
)
from app.schemas.conversation_announcement_rule import (
    ConversationAnnouncementRuleCreate,
    ConversationAnnouncementRuleEnabledPatch,
    ConversationAnnouncementRuleListResponse,
    ConversationAnnouncementRuleReorder,
    ConversationAnnouncementRuleResponse,
    ConversationAnnouncementRuleUpdate,
)
from app.schemas.queue_no_show_setting import (
    QueueNoShowSettingPayload,
    QueueNoShowSettingResponse,
)
from app.schemas.knowledge_input_suggestion_setting import (
    KnowledgeInputSuggestionSettingPayload,
    KnowledgeInputSuggestionSettingResponse,
)
from app.schemas.visitor_timeout_close import (
    VisitorTimeoutClosePayload,
    VisitorTimeoutCloseResponse,
)
from app.schemas.robot_qa import (
    RobotQaKnowledgeBaseListResponse,
    RobotQaDirectoryListResponse,
    RobotQaRuntimeResponse,
    RobotQaSettingPayload,
    RobotQaSettingResponse,
)
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
from app.schemas.embedded_page import (
    EmbeddedPageCreate,
    EmbeddedPageListResponse,
    EmbeddedPageLocation,
    EmbeddedPageResponse,
    EmbeddedPageUpdate,
    EmbeddedPageWorkspaceResponse,
)
from app.services.queue_no_show_setting_service import QueueNoShowSettingService
from app.services.knowledge_input_suggestion_setting_service import KnowledgeInputSuggestionSettingService
from app.services.satisfaction_survey_config_service import SatisfactionSurveyConfigService
from app.services.emoji_setting_service import EmojiSettingService
from app.services.conversation_announcement_rule_service import ConversationAnnouncementRuleService
from app.services.conversation_read_status_service import ConversationReadStatusService
from app.services.conversation_agent_display_setting_service import ConversationAgentDisplaySettingService
from app.services.conversation_user_stat_service import ConversationUserStatService
from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService
from app.services.welcome_message_rule_service import WelcomeMessageRuleService
from app.services.robot_qa_service import RobotQaService
from app.services.embedded_page_service import EmbeddedPageService

router = APIRouter(prefix="/conversation-settings", tags=["ConversationSettings"])
EMOJI_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
USER_STAT_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
VISITOR_TIMEOUT_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
QUEUE_NO_SHOW_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
KNOWLEDGE_INPUT_SUGGESTION_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
ANNOUNCEMENT_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
READ_STATUS_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
AGENT_DISPLAY_NAME_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
ROBOT_QA_ADMIN_PERMISSIONS = ["admin.access", "chat.admin.settings.manage"]
EMBEDDED_PAGE_ADMIN_PERMISSIONS_BY_LOCATION: dict[str, list[str]] = {
    "chat_auxiliary": ["admin.access", "chat.admin.settings.manage"],
    "call_screen_pop": ["admin.access", "call.admin.settings.manage"],
}
EMBEDDED_PAGE_WORKSPACE_PERMISSION_BY_LOCATION: dict[str, str] = {
    "chat_auxiliary": "chat.workspace.use",
    "call_screen_pop": "call.workspace.use",
}


def require_embedded_page_admin(principal: EffectivePrincipal, location: str) -> None:
    """Authorize embedded-page admin operations against the page's location."""
    permissions = EMBEDDED_PAGE_ADMIN_PERMISSIONS_BY_LOCATION.get(location)
    if not permissions or not principal.has_all_permissions(permissions):
        raise ForbiddenError("Permission denied")


def require_embedded_page_workspace(principal: EffectivePrincipal, location: str) -> None:
    """Authorize workspace embedded-page reads against the target location."""
    permission = EMBEDDED_PAGE_WORKSPACE_PERMISSION_BY_LOCATION.get(location)
    if not permission or not principal.has_permission(permission):
        raise ForbiddenError("Permission denied")


async def require_robot_qa_admin_short_session(
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
) -> EffectivePrincipal:
    """Authorize robot-QA proxy calls without retaining the auth DB session."""
    if not principal.has_all_permissions(ROBOT_QA_ADMIN_PERMISSIONS):
        raise ForbiddenError("Permission denied")
    return principal


async def require_robot_qa_workspace_short_session(
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
) -> EffectivePrincipal:
    """Require both workspace access and the robot-QA action permission."""
    if not principal.has_all_permissions([
        "chat.workspace.use",
        "chat.conversation.robot_qa.create",
    ]):
        raise ForbiddenError("Permission denied")
    return principal


@router.get(
    "/robot-qa",
    response_model=RobotQaSettingResponse,
    dependencies=[Depends(require_all_permissions(ROBOT_QA_ADMIN_PERMISSIONS))],
)
async def get_robot_qa_setting(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the tenant robot-QA setting."""
    return await RobotQaService.get_setting(db, current_user["tenant_id"])


@router.put("/robot-qa", response_model=RobotQaSettingResponse)
async def save_robot_qa_setting(
    body: RobotQaSettingPayload,
    principal: EffectivePrincipal = Depends(require_robot_qa_admin_short_session),
):
    """Validate and save the tenant robot-QA setting."""
    return await RobotQaService.save_setting_managed(principal.tenant_id, body)


@router.get(
    "/robot-qa/knowledge-bases",
    response_model=RobotQaKnowledgeBaseListResponse,
)
async def list_robot_qa_knowledge_bases(
    principal: EffectivePrincipal = Depends(require_robot_qa_admin_short_session),
):
    """List all OpenAgent knowledge bases available to the saved API key."""
    return await RobotQaService.list_knowledge_bases_managed(principal.tenant_id)


@router.get("/robot-qa/runtime", response_model=RobotQaRuntimeResponse)
async def get_robot_qa_runtime(
    principal: EffectivePrincipal = Depends(require_robot_qa_workspace_short_session),
):
    """Return the validated agent-workspace robot-QA runtime config."""
    return await RobotQaService.get_runtime_config_managed(principal.tenant_id)


@router.get("/robot-qa/directories", response_model=RobotQaDirectoryListResponse)
async def list_robot_qa_directories(
    principal: EffectivePrincipal = Depends(require_robot_qa_workspace_short_session),
):
    """List QA directories for the configured target knowledge base."""
    return await RobotQaService.list_directories_managed(principal.tenant_id)


@router.get(
    "/emojis",
    response_model=EmojiSettingResponse,
    dependencies=[Depends(require_all_permissions(EMOJI_ADMIN_PERMISSIONS))],
)
async def get_emoji_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current emoji panel config or a default draft."""
    return await EmojiSettingService.get_current(db, current_user["tenant_id"])


@router.put(
    "/emojis",
    response_model=EmojiSettingResponse,
    dependencies=[Depends(require_all_permissions(EMOJI_ADMIN_PERMISSIONS))],
)
async def save_emoji_settings(
    body: EmojiSettingPayload,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save visitor and agent emoji panel settings."""
    return await EmojiSettingService.save(db, current_user["tenant_id"], current_user, body)


@router.get(
    "/emojis/agent",
    response_model=EmojiTargetConfigResponse,
    dependencies=[Depends(require_permission("chat.workspace.use"))],
)
async def get_agent_emoji_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get agent-side emoji panel settings."""
    return await EmojiSettingService.get_target(db, current_user["tenant_id"], "agent")


@router.get(
    "/user-stat-fields",
    response_model=ConversationUserStatFieldSettingsResponse,
    dependencies=[Depends(require_all_permissions(USER_STAT_ADMIN_PERMISSIONS))],
)
async def get_user_stat_field_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get workspace user statistic display settings."""
    return await ConversationUserStatService.get_settings(db, current_user["tenant_id"])


@router.put(
    "/user-stat-fields",
    response_model=ConversationUserStatFieldSettingsResponse,
    dependencies=[Depends(require_all_permissions(USER_STAT_ADMIN_PERMISSIONS))],
)
async def save_user_stat_field_settings(
    body: ConversationUserStatFieldSettingsPayload,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save workspace user statistic display settings."""
    return await ConversationUserStatService.save_settings(db, current_user["tenant_id"], current_user, body)


@router.get(
    "/read-status",
    response_model=ConversationReadStatusResponse,
    dependencies=[Depends(require_all_permissions(READ_STATUS_ADMIN_PERMISSIONS))],
)
async def get_read_status_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get read-status display settings."""
    return await ConversationReadStatusService.get_current(db, current_user["tenant_id"])


@router.put(
    "/read-status",
    response_model=ConversationReadStatusResponse,
    dependencies=[Depends(require_all_permissions(READ_STATUS_ADMIN_PERMISSIONS))],
)
async def save_read_status_settings(
    body: ConversationReadStatusPayload,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save read-status display settings."""
    return await ConversationReadStatusService.save(db, current_user["tenant_id"], current_user, body)


@router.get(
    "/read-status/agent",
    response_model=ConversationReadStatusTargetResponse,
    dependencies=[Depends(require_permission("chat.workspace.use"))],
)
async def get_agent_read_status_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get agent workspace read-status display settings."""
    return await ConversationReadStatusService.get_target(db, current_user["tenant_id"], "agent_workspace")


@router.get(
    "/agent-display-name",
    response_model=ConversationAgentDisplaySettingResponse,
    dependencies=[Depends(require_all_permissions(AGENT_DISPLAY_NAME_ADMIN_PERMISSIONS))],
)
async def get_agent_display_name_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get agent display-name settings."""
    return await ConversationAgentDisplaySettingService.get_current(db, current_user["tenant_id"])


@router.get(
    "/agent-display-name/agent",
    response_model=ConversationAgentDisplayTargetResponse,
    dependencies=[Depends(require_permission("chat.workspace.use"))],
)
async def get_agent_display_name_target(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current workspace agent's configured sender name."""
    return await ConversationAgentDisplaySettingService.get_agent_target(
        db,
        current_user["tenant_id"],
        current_user["user_id"],
    )


@router.put(
    "/agent-display-name",
    response_model=ConversationAgentDisplaySettingResponse,
    dependencies=[Depends(require_all_permissions(AGENT_DISPLAY_NAME_ADMIN_PERMISSIONS))],
)
async def save_agent_display_name_settings(
    body: ConversationAgentDisplaySettingPayload,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save agent display-name settings."""
    return await ConversationAgentDisplaySettingService.save(db, current_user["tenant_id"], current_user, body)


@router.get(
    "/visitor-timeout-close",
    response_model=VisitorTimeoutCloseResponse,
    dependencies=[Depends(require_all_permissions(VISITOR_TIMEOUT_ADMIN_PERMISSIONS))],
)
async def get_visitor_timeout_close_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get visitor timeout auto-close settings or a default draft."""
    return await VisitorTimeoutCloseService.get_current(db, current_user["tenant_id"])


@router.put(
    "/visitor-timeout-close",
    response_model=VisitorTimeoutCloseResponse,
    dependencies=[Depends(require_all_permissions(VISITOR_TIMEOUT_ADMIN_PERMISSIONS))],
)
async def save_visitor_timeout_close_settings(
    body: VisitorTimeoutClosePayload,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save visitor timeout auto-close settings."""
    return await VisitorTimeoutCloseService.save(db, current_user["tenant_id"], current_user, body)


@router.get(
    "/queue-no-show",
    response_model=QueueNoShowSettingResponse,
    dependencies=[Depends(require_all_permissions(QUEUE_NO_SHOW_ADMIN_PERMISSIONS))],
)
async def get_queue_no_show_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get queue no-show cancel settings or a default draft."""
    return await QueueNoShowSettingService.get_current(db, current_user["tenant_id"])


@router.put(
    "/queue-no-show",
    response_model=QueueNoShowSettingResponse,
    dependencies=[Depends(require_all_permissions(QUEUE_NO_SHOW_ADMIN_PERMISSIONS))],
)
async def save_queue_no_show_settings(
    body: QueueNoShowSettingPayload,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save queue no-show cancel settings."""
    return await QueueNoShowSettingService.save(db, current_user["tenant_id"], current_user, body)


@router.get(
    "/knowledge-input-suggestions",
    response_model=KnowledgeInputSuggestionSettingResponse,
    dependencies=[Depends(require_all_permissions(KNOWLEDGE_INPUT_SUGGESTION_ADMIN_PERMISSIONS))],
)
async def get_knowledge_input_suggestion_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge input suggestion settings or a default draft."""
    return await KnowledgeInputSuggestionSettingService.get_current(db, current_user["tenant_id"])


@router.put(
    "/knowledge-input-suggestions",
    response_model=KnowledgeInputSuggestionSettingResponse,
    dependencies=[Depends(require_all_permissions(KNOWLEDGE_INPUT_SUGGESTION_ADMIN_PERMISSIONS))],
)
async def save_knowledge_input_suggestion_settings(
    body: KnowledgeInputSuggestionSettingPayload,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save knowledge input suggestion settings."""
    return await KnowledgeInputSuggestionSettingService.save(db, current_user["tenant_id"], current_user, body)


@router.get(
    "/knowledge-input-suggestions/agent",
    response_model=KnowledgeInputSuggestionSettingResponse,
    dependencies=[Depends(require_permission("chat.workspace.use"))],
)
async def get_agent_knowledge_input_suggestion_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get agent-side knowledge input suggestion settings."""
    return await KnowledgeInputSuggestionSettingService.get_runtime_config(db, current_user["tenant_id"])


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


@router.put(
    "/announcements/reorder",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_all_permissions(ANNOUNCEMENT_ADMIN_PERMISSIONS))],
)
async def reorder_conversation_announcements(
    body: ConversationAnnouncementRuleReorder,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reorder announcement rules by drag-and-drop."""
    await ConversationAnnouncementRuleService.reorder(db, current_user["tenant_id"], body.ordered_ids)
    return {"message": "Reordered successfully"}


@router.get(
    "/announcements",
    response_model=ConversationAnnouncementRuleListResponse,
    dependencies=[Depends(require_all_permissions(ANNOUNCEMENT_ADMIN_PERMISSIONS))],
)
async def list_conversation_announcements(
    page: int = 1,
    per_page: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List announcement rules ordered by priority."""
    return await ConversationAnnouncementRuleService.get_paginated(db, current_user["tenant_id"], page, per_page)


@router.post(
    "/announcements",
    response_model=ConversationAnnouncementRuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_all_permissions(ANNOUNCEMENT_ADMIN_PERMISSIONS))],
)
async def create_conversation_announcement(
    body: ConversationAnnouncementRuleCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new announcement rule."""
    return await ConversationAnnouncementRuleService.create(db, current_user["tenant_id"], body)


@router.get(
    "/announcements/{rule_id}",
    response_model=ConversationAnnouncementRuleResponse,
    dependencies=[Depends(require_all_permissions(ANNOUNCEMENT_ADMIN_PERMISSIONS))],
)
async def get_conversation_announcement(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an announcement rule by ID."""
    return await ConversationAnnouncementRuleService.get_by_id(db, rule_id, current_user["tenant_id"])


@router.put(
    "/announcements/{rule_id}",
    response_model=ConversationAnnouncementRuleResponse,
    dependencies=[Depends(require_all_permissions(ANNOUNCEMENT_ADMIN_PERMISSIONS))],
)
async def update_conversation_announcement(
    rule_id: int,
    body: ConversationAnnouncementRuleUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an announcement rule."""
    return await ConversationAnnouncementRuleService.update(db, rule_id, current_user["tenant_id"], body)


@router.patch(
    "/announcements/{rule_id}",
    response_model=ConversationAnnouncementRuleResponse,
    dependencies=[Depends(require_all_permissions(ANNOUNCEMENT_ADMIN_PERMISSIONS))],
)
async def patch_conversation_announcement_enabled(
    rule_id: int,
    body: ConversationAnnouncementRuleEnabledPatch,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle announcement rule enabled/disabled."""
    return await ConversationAnnouncementRuleService.patch_enabled(db, rule_id, current_user["tenant_id"], body.enabled)


@router.delete(
    "/announcements/{rule_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_all_permissions(ANNOUNCEMENT_ADMIN_PERMISSIONS))],
)
async def delete_conversation_announcement(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an announcement rule."""
    await ConversationAnnouncementRuleService.delete(db, rule_id, current_user["tenant_id"])
    return {"message": "Deleted successfully"}


@router.get(
    "/embedded-pages/workspace",
    response_model=EmbeddedPageWorkspaceResponse,
)
async def list_workspace_embedded_pages(
    location: EmbeddedPageLocation = "chat_auxiliary",
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    db: AsyncSession = Depends(get_db),
):
    """List enabled embedded pages for the agent workspace, with the agent summary."""
    require_embedded_page_workspace(principal, location)
    return await EmbeddedPageService.list_workspace_pages(
        db, principal.tenant_id, principal.user_id, location
    )


@router.get(
    "/embedded-pages",
    response_model=EmbeddedPageListResponse,
)
async def list_embedded_pages(
    location: EmbeddedPageLocation = "chat_auxiliary",
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    db: AsyncSession = Depends(get_db),
):
    """List embedded pages for one location ordered by sort order."""
    require_embedded_page_admin(principal, location)
    return await EmbeddedPageService.list_pages(db, principal.tenant_id, location)


@router.post(
    "/embedded-pages",
    response_model=EmbeddedPageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_embedded_page(
    body: EmbeddedPageCreate,
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    db: AsyncSession = Depends(get_db),
):
    """Create an embedded page."""
    require_embedded_page_admin(principal, body.location)
    return await EmbeddedPageService.create(db, principal.tenant_id, body)


@router.get(
    "/embedded-pages/{page_id}",
    response_model=EmbeddedPageResponse,
)
async def get_embedded_page(
    page_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    db: AsyncSession = Depends(get_db),
):
    """Get an embedded page by ID."""
    page = await EmbeddedPageService.get_by_id(db, page_id, principal.tenant_id)
    require_embedded_page_admin(principal, page["location"])
    return page


@router.put(
    "/embedded-pages/{page_id}",
    response_model=EmbeddedPageResponse,
)
async def update_embedded_page(
    page_id: int,
    body: EmbeddedPageUpdate,
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    db: AsyncSession = Depends(get_db),
):
    """Update an embedded page."""
    page = await EmbeddedPageService.get_by_id(db, page_id, principal.tenant_id)
    require_embedded_page_admin(principal, page["location"])
    return await EmbeddedPageService.update(db, page_id, principal.tenant_id, body)


@router.delete(
    "/embedded-pages/{page_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_embedded_page(
    page_id: int,
    principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    db: AsyncSession = Depends(get_db),
):
    """Delete an embedded page."""
    page = await EmbeddedPageService.get_by_id(db, page_id, principal.tenant_id)
    require_embedded_page_admin(principal, page["location"])
    await EmbeddedPageService.delete(db, page_id, principal.tenant_id)
    return {"message": "Deleted successfully"}
