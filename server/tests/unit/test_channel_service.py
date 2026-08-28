"""
Unit tests for channel service configuration and availability logic.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import UnauthorizedError, ValidationError
from app.core.security import create_visitor_session_token, decode_access_token
from app.services.web_sdk_context_service import VisitorIdentityResolution
from app.schemas.channel import (
    ChannelConfig,
    DEFAULT_LEAVE_MESSAGE_PROMPT,
    DEFAULT_OFFLINE_MESSAGE,
    DEFAULT_OFFLINE_TITLE,
    DEFAULT_OPEN_AGENT_HANDOFF_LABEL,
    DEFAULT_QUEUE_LEAVE_MESSAGE_BUTTON_LABEL,
    DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL,
    DEFAULT_QUEUE_FULL_MESSAGE,
    DEFAULT_QUEUE_MESSAGE,
    DEFAULT_RESTRICTED_SERVICE_MESSAGE,
    DEFAULT_RESTRICTED_SERVICE_TITLE,
)
from app.schemas.open_agent_settings import (
    OpenAgentAIDisclaimer,
    OpenAgentAgentListResponse,
    OpenAgentAgentSummary,
    OpenAgentAttachmentHandoffStatus,
    OpenAgentVisitorRuntimeConfig,
    OpenAgentWelcomeMessage,
)
from app.schemas.visitor_session import VisitorSessionRequest
from app.services.channel_service import ChannelService
from app.services.conversation_service import ConversationService


@pytest.mark.asyncio
async def test_persist_channel_creates_new_version_when_field_snapshot_changes(monkeypatch):
    db = AsyncMock()
    channel = SimpleNamespace(id=3, tenant_id=7, config={})
    snapshot = {
        "title": "Form",
        "fields": [{"field_key": "title", "required": True, "definition": {"name": "New title"}}],
    }
    create_version = AsyncMock()
    update_channel = AsyncMock(return_value=channel)
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService._build_form_config_snapshot",
        AsyncMock(return_value=snapshot),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelFormConfigVersionRepository.get_by_channel_version",
        AsyncMock(return_value=SimpleNamespace(config={**snapshot, "fields": []})),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelFormConfigVersionRepository.create",
        create_version,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelRepository.update",
        update_channel,
    )

    await ChannelService._persist_channel_with_form_version(
        db,
        item=channel,
        payload={
            "tenant_id": 7,
            "config": {
                "leave_message_mode": "form",
                "form_message_config_version": 1,
                "form_message_config": {
                    "title": "Form",
                    "fields": [{"field_key": "title", "required": True}],
                },
            },
        },
        previous_config={
            "leave_message_mode": "form",
            "form_message_config_version": 1,
            "form_message_config": {
                "title": "Form",
                "fields": [{"field_key": "title", "required": True}],
            },
        },
        create=False,
    )

    assert update_channel.await_args.args[2]["config"]["form_message_config_version"] == 2
    create_version.assert_awaited_once()
    assert create_version.await_args.kwargs["version"] == 2
    assert create_version.await_args.kwargs["config"] == snapshot


@pytest.mark.asyncio
async def test_persist_channel_reuses_version_when_form_snapshot_is_unchanged(monkeypatch):
    db = AsyncMock()
    channel = SimpleNamespace(id=18, tenant_id=7, config={})
    snapshot = {
        "title": "Form",
        "fields": [{"field_key": "title", "required": True, "definition": {"name": "Title"}}],
    }
    create_version = AsyncMock()
    update_channel = AsyncMock(return_value=channel)
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService._build_form_config_snapshot",
        AsyncMock(return_value=snapshot),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelFormConfigVersionRepository.get_by_channel_version",
        AsyncMock(return_value=SimpleNamespace(config=snapshot)),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelFormConfigVersionRepository.create",
        create_version,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelRepository.update",
        update_channel,
    )

    await ChannelService._persist_channel_with_form_version(
        db,
        item=channel,
        payload={
            "tenant_id": 7,
            "config": {
                "language_strategy": "fixed",
                "default_language": "fr-FR",
                "leave_message_mode": "form",
                "form_message_config": {
                    "title": "Form",
                    "fields": [{"field_key": "title", "required": True}],
                },
            },
        },
        previous_config={
            "language_strategy": "browser",
            "default_language": "en",
            "leave_message_mode": "form",
            "form_message_config_version": 1,
            "form_message_config": {
                "title": "Form",
                "fields": [{"field_key": "title", "required": True}],
            },
        },
        create=False,
    )

    assert update_channel.await_args.args[2]["config"]["form_message_config_version"] == 1
    create_version.assert_not_awaited()


def _service_hours(**overrides):
    data = {
        "id": 1,
        "tenant_id": 7,
        "weekly_schedules": [
            {"day_of_week": 1, "slots": [{"start": "09:00", "end": "18:00"}]},
        ],
        "holidays": [],
        "makeup_days": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_channel_config_uses_default_offline_message():
    config = ChannelConfig()

    assert config.offline_title == DEFAULT_OFFLINE_TITLE
    assert config.offline_message == DEFAULT_OFFLINE_MESSAGE
    assert config.service_hours_enabled is False
    assert config.service_hours_id is None
    assert config.outside_service_hours_strategy == "offline_message"
    assert config.leave_message_prompt == DEFAULT_LEAVE_MESSAGE_PROMPT
    assert config.restricted_service_message == DEFAULT_RESTRICTED_SERVICE_MESSAGE
    assert config.queue_message == DEFAULT_QUEUE_MESSAGE
    assert config.queue_full_message == DEFAULT_QUEUE_FULL_MESSAGE
    assert config.queue_show_leave_message_button is False
    assert config.queue_leave_message_button_label == DEFAULT_QUEUE_LEAVE_MESSAGE_BUTTON_LABEL
    assert config.queue_full_show_leave_message_button is True
    assert config.queue_full_leave_message_button_label == DEFAULT_QUEUE_FULL_LEAVE_MESSAGE_BUTTON_LABEL
    assert config.use_agent_avatar is False
    assert config.agent_default_avatar_url is None
    assert config.send_button_bg_color is None
    assert config.language_strategy == "browser"
    assert config.default_language == "en"
    assert config.open_agent_enabled is False
    assert config.open_agent_bot_strategy == "always"
    assert config.open_agent_avatar_url is None
    assert config.open_agent_attachment_upload_enabled is False
    assert config.open_agent_handoff_label == DEFAULT_OPEN_AGENT_HANDOFF_LABEL
    assert config.open_agent_handoff_after_messages == 2
    assert config.open_agent_handoff_behavior == "confirm"
    assert config.open_agent_custom_buttons_enabled is False
    assert config.open_agent_custom_buttons == []
    assert config.human_custom_buttons_enabled is False
    assert config.human_custom_buttons == []
    assert config.assist_panel_enabled is False
    assert config.assist_panel_title is None
    assert config.assist_panel_react_code is None
    assert config.assist_panel_config == {}
    assert config.leave_message_mode == "conversation"
    assert config.form_message_config.fields == []
    assert config.form_message_config_version is None


def test_channel_config_requires_form_fields_and_required_field():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(leave_message_mode="form")

    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            leave_message_mode="form",
            form_message_config={
                "fields": [{"field_key": "title", "required": False}],
            },
        )

    config = ChannelConfig(
        leave_message_mode="form",
        form_message_config={
            "fields": [{"field_key": "title", "required": True}],
        },
    )

    assert config.form_message_config.fields[0].field_key == "title"


def test_channel_config_rejects_duplicate_or_ambiguous_form_field_references():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            form_message_config={
                "fields": [
                    {"field_key": "title", "required": True},
                    {"field_key": "title", "required": False},
                ],
            },
        )

    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            form_message_config={
                "fields": [{"field_key": "title", "field_id": 1, "required": True}],
            },
        )


@pytest.mark.asyncio
async def test_build_form_config_snapshot_rejects_internal_ticket_fields(monkeypatch):
    monkeypatch.setattr(
        "app.services.channel_service.FdFieldDefinitionService.get_unified_list",
        AsyncMock(return_value={
            "items": [
                {
                    "key": "status",
                    "id": None,
                    "domain": "ticket",
                    "source": "system",
                    "name": "状态",
                    "field_type": "single_select",
                    "type_config": {},
                    "status": "active",
                    "sort_order": 1,
                    "options": [],
                    "tree_nodes": [],
                },
            ],
        }),
    )

    with pytest.raises(ValidationError):
        await ChannelService._build_form_config_snapshot(
            AsyncMock(),
            7,
            {"fields": [{"field_key": "status", "field_id": None, "required": True}]},
        )


def test_channel_config_accepts_fixed_language_strategy():
    config = ChannelConfig(language_strategy="fixed", default_language="fr-FR")

    assert config.language_strategy == "fixed"
    assert config.default_language == "fr-FR"


def test_channel_config_rejects_invalid_language_settings():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(language_strategy="unsupported")

    with pytest.raises(PydanticValidationError):
        ChannelConfig(default_language="de-DE")


def test_generate_copy_name_uses_next_available_suffix():
    result = ChannelService._generate_copy_name(
        "测试",
        ["测试", "测试副本1", "测试副本2"],
    )

    assert result == "测试副本3"


def test_generate_copy_name_truncates_long_source_name():
    source_name = "测" * 64
    result = ChannelService._generate_copy_name(source_name, [])

    assert result.endswith("副本1")
    assert len(result) == 64


def test_channel_config_rejects_empty_offline_title():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(offline_title="  ")


def test_channel_config_rejects_empty_rich_text_offline_message():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(offline_message="<p>&nbsp;</p>")


def test_channel_config_rejects_empty_queue_messages():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(queue_message="<p>&nbsp;</p>")

    with pytest.raises(PydanticValidationError):
        ChannelConfig(queue_full_message="<p>&nbsp;</p>")


def test_channel_config_rejects_empty_restricted_service_message():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(restricted_service_message="<p>&nbsp;</p>")


def test_availability_payload_includes_restricted_copy():
    payload = ChannelService._availability_payload(
        ChannelConfig(
            restricted_service_message="暂时无法提供在线咨询",
            queue_show_leave_message_button=True,
            queue_leave_message_button_label="稍后留言",
        ),
        can_start_conversation=False,
        reason="restricted",
        checked_at=datetime.now(timezone.utc),
    )

    assert payload["reason"] == "restricted"
    assert payload["restricted_service_title"] == DEFAULT_RESTRICTED_SERVICE_TITLE
    assert payload["restricted_service_message"] == "暂时无法提供在线咨询"
    assert payload["queue_show_leave_message_button"] is True
    assert payload["queue_leave_message_button_label"] == "稍后留言"


def test_channel_config_validates_queue_full_leave_message_button_label():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            queue_show_leave_message_button=True,
            queue_leave_message_button_label="  ",
        )

    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            queue_show_leave_message_button=True,
            queue_leave_message_button_label="x" * 17,
        )

    config = ChannelConfig(
        queue_show_leave_message_button=False,
        queue_leave_message_button_label="",
    )
    assert config.queue_show_leave_message_button is False

    with pytest.raises(PydanticValidationError):
        ChannelConfig(queue_full_leave_message_button_label="  ")

    with pytest.raises(PydanticValidationError):
        ChannelConfig(queue_full_leave_message_button_label="x" * 17)

    config = ChannelConfig(
        queue_full_show_leave_message_button=False,
        queue_full_leave_message_button_label="",
    )
    assert config.queue_full_show_leave_message_button is False


def test_channel_config_accepts_custom_buttons():
    config = ChannelConfig(
        open_agent_custom_buttons_enabled=True,
        open_agent_custom_buttons=[
            {"label": "  问价格  ", "action_type": "send_message", "message": "  我想了解价格  "},
            {"label": "官网", "action_type": "link", "url": "https://example.com"},
        ],
        human_custom_buttons_enabled=True,
        human_custom_buttons=[
            {"label": "工单", "action_type": "link", "url": "http://example.com/tickets", "enabled": False},
        ],
    )

    assert config.open_agent_custom_buttons[0].label == "问价格"
    assert config.open_agent_custom_buttons[0].message == "我想了解价格"
    assert config.open_agent_custom_buttons[0].url is None
    assert config.open_agent_custom_buttons[1].message is None
    assert config.human_custom_buttons[0].enabled is False


def test_channel_config_validates_custom_buttons():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(open_agent_custom_buttons=[
            {"label": "", "action_type": "send_message", "message": "hi"},
        ])

    with pytest.raises(PydanticValidationError):
        ChannelConfig(open_agent_custom_buttons=[
            {"label": "咨询", "action_type": "send_message", "message": ""},
        ])

    with pytest.raises(PydanticValidationError):
        ChannelConfig(human_custom_buttons=[
            {"label": "官网", "action_type": "link", "url": "ftp://example.com"},
        ])

    with pytest.raises(PydanticValidationError):
        ChannelConfig(human_custom_buttons=[
            {"label": f"按钮{i}", "action_type": "send_message", "message": "hi"}
            for i in range(9)
        ])


def test_channel_config_requires_agent_when_open_agent_enabled():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(open_agent_enabled=True)


def test_channel_config_rejects_invalid_handoff_threshold():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            open_agent_enabled=True,
            open_agent_agent_id=1,
            open_agent_handoff_after_messages=100,
        )


def test_channel_config_rejects_long_open_agent_avatar_url():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(open_agent_avatar_url=f"https://example.com/{'x' * 500}")


def test_channel_config_normalizes_agent_default_avatar_url():
    config = ChannelConfig(agent_default_avatar_url="  https://cdn.example.com/agent.png  ")
    assert config.agent_default_avatar_url == "https://cdn.example.com/agent.png"

    blank_config = ChannelConfig(agent_default_avatar_url="  ")
    assert blank_config.agent_default_avatar_url is None


def test_channel_config_rejects_long_agent_default_avatar_url():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(agent_default_avatar_url=f"https://example.com/{'x' * 500}")


def test_channel_config_requires_assist_panel_code_when_enabled():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(assist_panel_enabled=True)


def test_channel_config_accepts_safe_assist_panel_config():
    config = ChannelConfig(
        assist_panel_enabled=True,
        assist_panel_title="辅助信息",
        assist_panel_react_code="export default function AssistApp() { return null }",
        assist_panel_config={"items": [{"question": "Price?", "message": "Tell me pricing"}]},
    )

    assert config.assist_panel_enabled is True
    assert config.assist_panel_title == "辅助信息"
    assert config.assist_panel_config["items"][0]["message"] == "Tell me pricing"


def test_channel_config_rejects_unsafe_assist_panel_code():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            assist_panel_enabled=True,
            assist_panel_react_code="export default function AssistApp() { window.location.href = '/' }",
        )


def test_channel_config_rejects_assist_panel_function_constructor():
    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            assist_panel_enabled=True,
            assist_panel_react_code="export default function AssistApp() { return Function('return null')() }",
        )


def test_is_within_service_hours_uses_weekly_schedule():
    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)

    assert ChannelService.is_within_service_hours(_service_hours(), now) is True


def test_is_within_service_hours_holiday_overrides_weekly_schedule():
    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    service_hours = _service_hours(
        holidays=[{"name": "Holiday", "start": "2026-05-04T00:00", "end": "2026-05-04T23:59"}]
    )

    assert ChannelService.is_within_service_hours(service_hours, now) is False


def test_is_within_service_hours_makeup_day_overrides_holiday():
    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    service_hours = _service_hours(
        holidays=[{"name": "Holiday", "start": "2026-05-04T00:00", "end": "2026-05-04T23:59"}],
        makeup_days=[{"name": "Makeup", "start": "2026-05-04T09:00", "end": "2026-05-04T18:00"}],
    )

    assert ChannelService.is_within_service_hours(service_hours, now) is True


@pytest.mark.asyncio
async def test_normalize_config_requires_service_hours_when_enabled():
    with pytest.raises(ValidationError):
        await ChannelService._normalize_config(
            AsyncMock(),
            7,
            ChannelConfig(service_hours_enabled=True, service_hours_id=None),
        )


@pytest.mark.asyncio
async def test_normalize_config_requires_bot_service_hours(monkeypatch):
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.list_active_agents",
        AsyncMock(return_value=OpenAgentAgentListResponse(
            items=[OpenAgentAgentSummary(id=1, name="Support Agent", status="active")],
            total=1,
            page=1,
            per_page=100,
            pages=1,
        )),
    )

    with pytest.raises(PydanticValidationError):
        ChannelConfig(
            open_agent_enabled=True,
            open_agent_agent_id=1,
            open_agent_bot_strategy="service_hours",
        )


@pytest.mark.asyncio
async def test_normalize_config_saves_active_open_agent(monkeypatch):
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.list_active_agents",
        AsyncMock(return_value=OpenAgentAgentListResponse(
            items=[OpenAgentAgentSummary(id=1, name="Support Agent", status="active")],
            total=1,
            page=1,
            per_page=100,
            pages=1,
        )),
    )

    result = await ChannelService._normalize_config(
        AsyncMock(),
        7,
        ChannelConfig(open_agent_enabled=True, open_agent_agent_id=1),
    )

    assert result["open_agent_enabled"] is True
    assert result["open_agent_agent_id"] == 1
    assert result["open_agent_agent_name"] == "Support Agent"
    assert result["open_agent_bot_service_hours_id"] is None


@pytest.mark.asyncio
async def test_normalize_config_rejects_attachment_upload_without_handoff_tool(monkeypatch):
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.list_active_agents",
        AsyncMock(return_value=OpenAgentAgentListResponse(
            items=[OpenAgentAgentSummary(id=1, name="Support Agent", status="active")],
            total=1,
            page=1,
            per_page=100,
            pages=1,
        )),
    )
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.get_attachment_handoff_status",
        AsyncMock(return_value=OpenAgentAttachmentHandoffStatus(
            ready=False,
            reason="not_configured",
        )),
    )

    with pytest.raises(ValidationError):
        await ChannelService._normalize_config(
            AsyncMock(),
            7,
            ChannelConfig(
                open_agent_enabled=True,
                open_agent_agent_id=1,
                open_agent_attachment_upload_enabled=True,
            ),
        )


@pytest.mark.asyncio
async def test_normalize_config_preserves_custom_buttons():
    result = await ChannelService._normalize_config(
        AsyncMock(),
        7,
        ChannelConfig(
            human_custom_buttons_enabled=True,
            human_custom_buttons=[
                {"label": "帮助", "action_type": "send_message", "message": "我需要帮助"},
            ],
        ),
    )

    assert result["human_custom_buttons_enabled"] is True
    assert result["human_custom_buttons"] == [
        {
            "label": "帮助",
            "action_type": "send_message",
            "message": "我需要帮助",
            "url": None,
            "enabled": True,
        },
    ]
    assert result["open_agent_custom_buttons_enabled"] is False
    assert result["open_agent_custom_buttons"] == []


@pytest.mark.asyncio
async def test_normalize_config_rejects_unavailable_open_agent(monkeypatch):
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.list_active_agents",
        AsyncMock(return_value=OpenAgentAgentListResponse(
            items=[OpenAgentAgentSummary(id=2, name="Other Agent", status="active")],
            total=1,
            page=1,
            per_page=100,
            pages=1,
        )),
    )

    with pytest.raises(ValidationError):
        await ChannelService._normalize_config(
            AsyncMock(),
            7,
            ChannelConfig(open_agent_enabled=True, open_agent_agent_id=1),
        )


@pytest.mark.asyncio
async def test_public_config_returns_open_agent_welcome_message(monkeypatch):
    channel_key = "ch_abcdefghijklmnopqrstuvwxyz"
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key=channel_key,
        name="Bot Channel",
        channel_type="web",
        access_mode="url",
        logo_url=None,
        favicon_url=None,
        public_access_enabled=True,
        config=ChannelConfig(open_agent_enabled=True, open_agent_agent_id=1).model_dump(),
    )
    welcome_message = OpenAgentWelcomeMessage.model_validate({
        "enabled": True,
        "blocks": [{"type": "markdown", "content": "Hello from bot"}],
    })
    ai_disclaimer = OpenAgentAIDisclaimer(
        enabled=True,
        content="本内容由AI生成，仅供参考",
    )
    availability = {
        "can_start_conversation": True,
        "reason": "available",
        "offline_title": DEFAULT_OFFLINE_TITLE,
        "offline_message": DEFAULT_OFFLINE_MESSAGE,
        "outside_service_hours_strategy": "offline_message",
        "leave_message_prompt": DEFAULT_LEAVE_MESSAGE_PROMPT,
        "checked_at": None,
    }

    class _FakeSessionContext:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *_exc_info):
            return None

    monkeypatch.setattr(
        "app.services.channel_service.AsyncSessionLocal",
        lambda: _FakeSessionContext(),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelRepository.get_by_key",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.check_channel_availability",
        AsyncMock(return_value=availability),
    )
    monkeypatch.setattr(
        "app.services.channel_service.OpenAgentSettingsService.get_agent_visitor_runtime_config_managed",
        AsyncMock(return_value=OpenAgentVisitorRuntimeConfig(
            welcome_message=welcome_message,
            ai_disclaimer=ai_disclaimer,
        )),
    )
    monkeypatch.setattr(
        "app.services.conversation_announcement_rule_service."
        "ConversationAnnouncementRuleService.match_public_announcement",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.conversation_read_status_service."
        "ConversationReadStatusService.get_public_config",
        AsyncMock(return_value={"agent_workspace_enabled": True, "web_sdk_enabled": True}),
    )

    result = await ChannelService.get_public_config_with_availability_by_key_managed(
        AsyncMock(),
        channel_key,
    )

    assert result["welcome_message"] is None
    assert result["open_agent_welcome_message"] == welcome_message
    assert result["open_agent_ai_disclaimer"] == ai_disclaimer


@pytest.mark.asyncio
async def test_check_channel_availability_returns_no_agent(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        config=ChannelConfig(service_hours_enabled=False).model_dump(),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.routing_service.RoutingService.route_conversation",
        AsyncMock(return_value=(None, [], {})),
    )

    result = await ChannelService.check_channel_availability(AsyncMock(), AsyncMock(), 10)

    assert result["can_start_conversation"] is False
    assert result["reason"] == "no_available_agent"
    assert result["offline_title"] == DEFAULT_OFFLINE_TITLE
    assert result["offline_message"] == DEFAULT_OFFLINE_MESSAGE
    assert result["outside_service_hours_strategy"] == "offline_message"


@pytest.mark.asyncio
async def test_human_service_gate_returns_leave_message_strategy(monkeypatch):
    channel = SimpleNamespace(id=10, tenant_id=7)
    config = ChannelConfig(
        service_hours_enabled=True,
        service_hours_id=1,
        outside_service_hours_strategy="leave_message",
        leave_message_prompt="请留言",
    )
    monkeypatch.setattr(
        "app.services.channel_service.ServiceHoursRepository.get_by_id",
        AsyncMock(return_value=_service_hours(id=1, tenant_id=7)),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.is_within_service_hours",
        lambda *_args, **_kwargs: False,
    )

    result = await ChannelService.check_human_service_gate(AsyncMock(), channel, config)

    assert result["can_start_conversation"] is False
    assert result["reason"] == "outside_service_hours"
    assert result["outside_service_hours_strategy"] == "leave_message"
    assert result["leave_message_prompt"] == "请留言"
    assert ConversationService._availability_is_leave_message(result) is True


@pytest.mark.asyncio
async def test_resolve_human_handoff_target_uses_queue_returning_agent_for_group(monkeypatch):
    db = AsyncMock()
    r = AsyncMock()
    channel = SimpleNamespace(id=10, tenant_id=7, config={})
    group = SimpleNamespace(
        id=8,
        tenant_id=7,
        members=[
            SimpleNamespace(
                employee_id=21,
                employee=SimpleNamespace(is_active=True, max_concurrent=5),
            ),
            SimpleNamespace(
                employee_id=22,
                employee=SimpleNamespace(is_active=True, max_concurrent=5),
            ),
        ],
    )
    select_agent = AsyncMock(return_value=22)
    fallback_find_agent = AsyncMock(return_value=21)

    monkeypatch.setattr(
        "app.services.channel_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.check_human_service_gate",
        AsyncMock(return_value={"can_start_conversation": True, "reason": "available"}),
    )
    monkeypatch.setattr(
        "app.repositories.employee_group_repository.EmployeeGroupRepository.get_by_id",
        AsyncMock(return_value=group),
    )
    monkeypatch.setattr(
        "app.services.queue_service.QueueTaskService.select_immediate_online_chat_agent",
        select_agent,
    )
    monkeypatch.setattr(
        "app.services.channel_service.AgentStatusService.find_available_agent",
        fallback_find_agent,
    )

    result = await ChannelService.resolve_human_handoff_target(
        db,
        r,
        10,
        handoff_payload={"handoff": {"agent_group_id": 8}},
        visitor_id=20,
    )

    select_agent.assert_awaited_once_with(
        db,
        r,
        7,
        queue_type="employee_group",
        queue_id=8,
        visitor_id=20,
    )
    fallback_find_agent.assert_not_awaited()
    assert result["agent_id"] == 22
    assert result["group_id"] == 8


def test_no_available_agent_is_not_leave_message():
    availability = {
        "can_start_conversation": False,
        "reason": "no_available_agent",
        "outside_service_hours_strategy": "leave_message",
    }

    assert ConversationService._availability_is_leave_message(availability) is False


@pytest.mark.asyncio
async def test_create_visitor_session_binds_channel_context(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=3,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )

    result = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(visitor_name="Ada"),
    )

    payload = decode_access_token(result["visitor_session_token"])
    assert result["visitor_external_id"].startswith("v_")
    assert result["visitor_secret"].startswith("vs_")
    assert result["expires_in"] > 0
    assert payload["typ"] == "visitor_session"
    assert payload["tenant_id"] == 7
    assert payload["channel_id"] == 10
    assert payload["channel_key"] == channel.channel_key
    assert payload["channel_key_version"] == 3
    assert payload["visitor_external_id"] == result["visitor_external_id"]


@pytest.mark.asyncio
async def test_create_visitor_session_renews_only_with_server_minted_secret(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=3,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )
    issued = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(),
    )

    renewed = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(
            visitor_external_id=issued["visitor_external_id"],
            visitor_secret=issued["visitor_secret"],
        ),
    )

    assert renewed["visitor_external_id"] == issued["visitor_external_id"]
    assert renewed["visitor_secret"] is None


@pytest.mark.asyncio
async def test_create_visitor_session_rejects_client_supplied_id_without_secret(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=3,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )

    with pytest.raises(UnauthorizedError):
        await ChannelService.create_visitor_session(
            AsyncMock(),
            channel.channel_key,
            VisitorSessionRequest(visitor_external_id="visitor-1"),
        )


@pytest.mark.asyncio
async def test_create_visitor_session_rejects_invalid_visitor_secret(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=3,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )

    with pytest.raises(UnauthorizedError):
        await ChannelService.create_visitor_session(
            AsyncMock(),
            channel.channel_key,
            VisitorSessionRequest(
                visitor_external_id="visitor-1",
                visitor_secret="vs_invalid",
            ),
        )


@pytest.mark.asyncio
async def test_validate_visitor_session_rejects_rotated_key(monkeypatch):
    token = create_visitor_session_token({
        "tenant_id": 7,
        "channel_id": 10,
        "channel_key": "ch_abcdefghijklmnopqrstuvwxyzabcdef",
        "channel_key_version": 1,
        "visitor_external_id": "visitor-1",
    })
    monkeypatch.setattr(
        "app.services.channel_service.ChannelRepository.get_by_id",
        AsyncMock(return_value=SimpleNamespace(
            id=10,
            tenant_id=7,
            channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
            channel_key_version=2,
            public_access_enabled=True,
        )),
    )

    with pytest.raises(UnauthorizedError):
        await ChannelService.validate_visitor_session_token(AsyncMock(), token)


@pytest.mark.asyncio
async def test_create_visitor_session_uses_context_identity(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=1,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.WebSdkContextService.resolve_visitor_identity",
        AsyncMock(return_value=VisitorIdentityResolution(
            visitor_external_id="mall_user_1",
            visitor_name="Ada",
            warnings=["CUSTOMER_MATCH_CONFLICT:email_phone"],
        )),
    )

    response = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(contextToken="odctx_test"),
    )

    assert response["visitor_external_id"] == "mall_user_1"
    assert response["visitor_secret"]
    assert response["context_warnings"] == ["CUSTOMER_MATCH_CONFLICT:email_phone"]
    payload = decode_access_token(response["visitor_session_token"])
    assert payload["visitor_external_id"] == "mall_user_1"
    assert payload["visitor_name"] == "Ada"


@pytest.mark.asyncio
async def test_create_visitor_session_prefers_context_over_stale_visitor_id(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=1,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.WebSdkContextService.resolve_visitor_identity",
        AsyncMock(return_value=VisitorIdentityResolution(
            visitor_external_id="mall_user_1",
            visitor_name="Ada",
        )),
    )

    anonymous = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(),
    )
    assert anonymous["visitor_external_id"].startswith("v_")

    upgraded = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(
            visitor_external_id=anonymous["visitor_external_id"],
            visitor_secret=anonymous["visitor_secret"],
            contextToken="odctx_test",
        ),
    )

    assert upgraded["visitor_external_id"] == "mall_user_1"
    assert upgraded["visitor_secret"]
    assert upgraded["visitor_secret"] != anonymous["visitor_secret"]
    payload = decode_access_token(upgraded["visitor_session_token"])
    assert payload["visitor_external_id"] == "mall_user_1"
    assert payload["visitor_name"] == "Ada"


@pytest.mark.asyncio
async def test_create_visitor_session_keeps_secret_when_context_matches_stored_id(monkeypatch):
    channel = SimpleNamespace(
        id=10,
        tenant_id=7,
        channel_key="ch_abcdefghijklmnopqrstuvwxyzabcdef",
        channel_key_version=1,
        public_access_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.channel_service.ChannelService.get_public_channel_by_key",
        AsyncMock(return_value=channel),
    )
    monkeypatch.setattr(
        "app.services.channel_service.WebSdkContextService.resolve_visitor_identity",
        AsyncMock(return_value=VisitorIdentityResolution(
            visitor_external_id="mall_user_1",
            visitor_name="Ada",
        )),
    )

    issued = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(contextToken="odctx_test"),
    )
    assert issued["visitor_external_id"] == "mall_user_1"
    assert issued["visitor_secret"]

    renewed = await ChannelService.create_visitor_session(
        AsyncMock(),
        channel.channel_key,
        VisitorSessionRequest(
            visitor_external_id=issued["visitor_external_id"],
            visitor_secret=issued["visitor_secret"],
            contextToken="odctx_test",
        ),
    )

    assert renewed["visitor_external_id"] == "mall_user_1"
    assert renewed["visitor_secret"] is None
    payload = decode_access_token(renewed["visitor_session_token"])
    assert payload["visitor_external_id"] == "mall_user_1"
    assert payload["visitor_name"] == "Ada"
