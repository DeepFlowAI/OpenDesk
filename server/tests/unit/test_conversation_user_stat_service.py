"""
Unit tests for workspace user statistic settings and counts.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.conversation_user_statistics import (
    ConversationUserStatFieldSettingsPayload,
    ConversationUserStatFieldSettingsResponse,
)
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_user_stat_service import ConversationUserStatService


def _principal(permissions: list[str]) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=1,
        permissions=permissions,
        data_scopes={"session_record": "self", "call_record": "self", "ticket": "self"},
        group_ids=[2],
    )


@pytest.mark.asyncio
async def test_get_settings_returns_default_when_not_configured(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.ConversationUserStatRepository.get_settings_by_tenant",
        AsyncMock(return_value=None),
    )

    result = await ConversationUserStatService.get_settings(AsyncMock(), tenant_id=1)

    assert result.configured is False
    assert result.show_session_count is True
    assert result.show_call_count is True
    assert result.show_unresolved_ticket_count is True
    assert result.show_total_ticket_count is True


@pytest.mark.asyncio
async def test_save_settings_persists_actor_snapshot(monkeypatch):
    captured: dict = {}

    async def save_settings(_db, tenant_id: int, data: dict):
        captured["tenant_id"] = tenant_id
        captured["data"] = data
        return SimpleNamespace(id=3, tenant_id=tenant_id, configured=True, updated_at=None, **data)

    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.ConversationUserStatRepository.save_settings",
        save_settings,
    )

    payload = ConversationUserStatFieldSettingsPayload(
        show_session_count=False,
        show_call_count=True,
        show_unresolved_ticket_count=True,
        show_total_ticket_count=False,
    )
    result = await ConversationUserStatService.save_settings(
        AsyncMock(),
        tenant_id=1,
        current_user={"user_id": 10, "display_name": "Agent One"},
        payload=payload,
    )

    assert captured["tenant_id"] == 1
    assert captured["data"]["updated_by_id"] == 10
    assert captured["data"]["updated_by_name"] == "Agent One"
    assert result.show_session_count is False
    assert result.show_total_ticket_count is False


@pytest.mark.asyncio
async def test_get_statistics_returns_empty_for_unlinked_user(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.ConversationService.get_agent_conversation",
        AsyncMock(return_value={"visitor": None}),
    )

    result = await ConversationUserStatService.get_statistics(
        AsyncMock(),
        conversation_id=100,
        principal=_principal(["chat.workspace.use", "chat.session_record.view"]),
    )

    assert result.conversation_id == 100
    assert result.user_id is None
    assert result.items == []


@pytest.mark.asyncio
async def test_get_statistics_only_returns_permitted_enabled_items(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.ConversationService.get_agent_conversation",
        AsyncMock(return_value={"visitor": SimpleNamespace(id=20)}),
    )
    monkeypatch.setattr(
        ConversationUserStatService,
        "get_settings",
        AsyncMock(
            return_value=ConversationUserStatFieldSettingsResponse(
                configured=False,
                show_session_count=True,
                show_call_count=True,
                show_unresolved_ticket_count=True,
                show_total_ticket_count=True,
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.DataScopeService.get_group_peer_employee_ids",
        AsyncMock(return_value=[10, 11]),
    )
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.DataScopeService.build_session_record_predicate",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.ConversationUserStatRepository.count_sessions",
        AsyncMock(return_value=7),
    )

    result = await ConversationUserStatService.get_statistics(
        AsyncMock(),
        conversation_id=100,
        principal=_principal(["chat.workspace.use", "chat.session_record.view"]),
    )

    assert [item.key for item in result.items] == ["sessions"]
    assert result.items[0].value == 7


@pytest.mark.asyncio
async def test_get_statistics_respects_split_ticket_settings(monkeypatch):
    captured: list[bool] = []

    async def count_tickets(_db, _tenant_id, _user_id, *, unresolved_only: bool = False, scope_predicate=None):
        captured.append(unresolved_only)
        return 5

    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.ConversationService.get_agent_conversation",
        AsyncMock(return_value={"visitor": SimpleNamespace(id=20)}),
    )
    monkeypatch.setattr(
        ConversationUserStatService,
        "get_settings",
        AsyncMock(
            return_value=ConversationUserStatFieldSettingsResponse(
                configured=True,
                show_session_count=False,
                show_call_count=False,
                show_unresolved_ticket_count=False,
                show_total_ticket_count=True,
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.DataScopeService.get_group_peer_employee_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.DataScopeService.build_ticket_predicate",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.conversation_user_stat_service.ConversationUserStatRepository.count_tickets",
        count_tickets,
    )

    result = await ConversationUserStatService.get_statistics(
        AsyncMock(),
        conversation_id=100,
        principal=_principal(["chat.workspace.use", "ticket.workspace.view"]),
    )

    assert captured == [False]
    assert [item.key for item in result.items] == ["tickets"]
    assert result.items[0].unresolved_value is None
    assert result.items[0].total_value == 5


@pytest.mark.asyncio
async def test_safe_count_rolls_back_and_returns_none_on_failure():
    db = SimpleNamespace(rollback=AsyncMock())

    async def fail():
        raise RuntimeError("boom")

    result = await ConversationUserStatService._safe_count(db, fail)

    assert result is None
    db.rollback.assert_awaited_once()
