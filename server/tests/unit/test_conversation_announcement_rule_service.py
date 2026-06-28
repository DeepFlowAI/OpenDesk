"""
Unit tests for conversation announcement rules.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.conversation_announcement_rule import ConversationAnnouncementRuleCreate
from app.services.conversation_announcement_rule_service import ConversationAnnouncementRuleService


def _rule(
    *,
    rule_id: int,
    priority: int = 1,
    enabled: bool = True,
    time_range_type: str = "permanent",
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    conditions: list[dict] | None = None,
    summary_html: str = "<p>Summary</p>",
    detail_html: str = "<p>Detail</p>",
):
    return SimpleNamespace(
        id=rule_id,
        priority=priority,
        name=f"Announcement {rule_id}",
        enabled=enabled,
        time_range_type=time_range_type,
        start_at=start_at,
        end_at=end_at,
        conditions=conditions or [],
        auto_popup=True,
        background_color="yellow",
        summary_html=summary_html,
        detail_html=detail_html,
        created_at=None,
        updated_at=None,
    )


def test_schema_rejects_invalid_limited_time_range():
    now = datetime.now(timezone.utc)

    with pytest.raises(PydanticValidationError):
        ConversationAnnouncementRuleCreate(
            name="Bad",
            time_range_type="limited",
            start_at=now,
            end_at=now - timedelta(minutes=1),
            summary_html="<p>Summary</p>",
            detail_html="<p>Detail</p>",
        )


def test_schema_rejects_empty_summary_and_detail():
    with pytest.raises(PydanticValidationError):
        ConversationAnnouncementRuleCreate(
            name="Bad",
            summary_html="<p><br></p>",
            detail_html="<p>Detail</p>",
        )

    with pytest.raises(PydanticValidationError):
        ConversationAnnouncementRuleCreate(
            name="Bad",
            summary_html="<p>Summary</p>",
            detail_html="<p><br></p>",
        )


@pytest.mark.asyncio
async def test_match_public_announcement_skips_expired_and_returns_first_active(monkeypatch):
    now = datetime.now(timezone.utc)
    expired = _rule(
        rule_id=1,
        priority=1,
        time_range_type="limited",
        start_at=now - timedelta(days=2),
        end_at=now - timedelta(days=1),
    )
    active = _rule(rule_id=2, priority=2, summary_html="<p>Active summary</p>")
    channel = SimpleNamespace(id=9, tenant_id=5, channel_type="web")

    monkeypatch.setattr(
        "app.services.conversation_announcement_rule_service.ConversationAnnouncementRuleRepository.list_enabled_ordered",
        AsyncMock(return_value=[expired, active]),
    )

    result = await ConversationAnnouncementRuleService.match_public_announcement(AsyncMock(), channel)

    assert result is not None
    assert result["id"] == 2
    assert result["summary_html"] == "<p>Active summary</p>"


@pytest.mark.asyncio
async def test_match_public_announcement_uses_conditions(monkeypatch):
    non_matching = _rule(
        rule_id=1,
        priority=1,
        conditions=[{"condition_type": "web_sdk", "operator": "eq", "value": "100"}],
    )
    matching = _rule(
        rule_id=2,
        priority=2,
        conditions=[{"condition_type": "web_sdk", "operator": "eq", "value": "9"}],
    )
    channel = SimpleNamespace(id=9, tenant_id=5, channel_type="web")

    monkeypatch.setattr(
        "app.services.conversation_announcement_rule_service.ConversationAnnouncementRuleRepository.list_enabled_ordered",
        AsyncMock(return_value=[non_matching, matching]),
    )

    result = await ConversationAnnouncementRuleService.match_public_announcement(AsyncMock(), channel)

    assert result is not None
    assert result["id"] == 2
