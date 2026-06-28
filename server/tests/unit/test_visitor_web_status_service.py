"""
Unit tests for visitor Web status service.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.core.exceptions import ForbiddenError
from app.services.visitor_web_status_service import (
    CHAT_NAMESPACE,
    VISITOR_WEB_CONNECTION_KEY_TTL_SECONDS,
    VISITOR_WEB_STATUS_EVENT,
    VisitorWebStatusService,
)


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _conversation(
    *,
    conversation_id: int = 123,
    tenant_id: int = 7,
    agent_id: int | None = 42,
    channel_id: int | None = 9,
    channel_type: str | None = "web",
    visitor_external_id: str | None = "visitor-1",
):
    return SimpleNamespace(
        id=conversation_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        channel_id=channel_id,
        channel=SimpleNamespace(channel_type=channel_type) if channel_type is not None else None,
        visitor=(
            SimpleNamespace(id=20, external_id=visitor_external_id)
            if visitor_external_id is not None
            else None
        ),
    )


@pytest.mark.asyncio
async def test_connection_status_stays_online_until_all_sids_disconnect(fake_redis):
    await VisitorWebStatusService.mark_connected(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    )
    await VisitorWebStatusService.mark_connected(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-2",
    )

    assert await VisitorWebStatusService.get_status(fake_redis, 7, 9, "visitor-1") == "online"
    assert await VisitorWebStatusService.mark_disconnected(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    ) == "online"
    assert await VisitorWebStatusService.get_status(fake_redis, 7, 9, "visitor-1") == "online"

    assert await VisitorWebStatusService.mark_disconnected(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-2",
    ) == "offline"
    assert await VisitorWebStatusService.get_status(fake_redis, 7, 9, "visitor-1") == "offline"


@pytest.mark.asyncio
async def test_stale_connection_expires_without_disconnect(monkeypatch, fake_redis):
    monkeypatch.setattr("app.services.visitor_web_status_service.time.time", lambda: 1_000.0)
    await VisitorWebStatusService.mark_connected(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    )

    monkeypatch.setattr("app.services.visitor_web_status_service.time.time", lambda: 1_025.0)

    assert await VisitorWebStatusService.get_status(fake_redis, 7, 9, "visitor-1") == "offline"


@pytest.mark.asyncio
async def test_refresh_connection_reports_offline_to_online_transition(monkeypatch, fake_redis):
    monkeypatch.setattr("app.services.visitor_web_status_service.time.time", lambda: 1_000.0)
    assert await VisitorWebStatusService.refresh_connection(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    ) is True

    monkeypatch.setattr("app.services.visitor_web_status_service.time.time", lambda: 1_008.0)
    assert await VisitorWebStatusService.refresh_connection(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    ) is False

    monkeypatch.setattr("app.services.visitor_web_status_service.time.time", lambda: 1_033.0)
    assert await VisitorWebStatusService.refresh_connection(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    ) is True


@pytest.mark.asyncio
async def test_legacy_set_key_is_cleared_instead_of_read_as_online(fake_redis):
    key = VisitorWebStatusService._key(7, 9, "visitor-1")
    await fake_redis.sadd(key, "legacy-sid")

    assert await VisitorWebStatusService.get_status(fake_redis, 7, 9, "visitor-1") == "offline"
    assert await fake_redis.type(key) == "none"


@pytest.mark.asyncio
async def test_connection_key_gets_ttl(fake_redis):
    key = VisitorWebStatusService._key(7, 9, "visitor-1")

    await VisitorWebStatusService.mark_connected(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    )

    ttl = await fake_redis.ttl(key)
    assert 0 < ttl <= VISITOR_WEB_CONNECTION_KEY_TTL_SECONDS


@pytest.mark.asyncio
async def test_build_status_response_returns_unknown_when_not_displayable(fake_redis):
    response = await VisitorWebStatusService.build_status_response(
        fake_redis,
        _conversation(channel_type="email"),
    )

    assert response["status"] == "unknown"
    assert response["can_display"] is False
    assert isinstance(response["checked_at"], str)
    datetime.fromisoformat(response["checked_at"])


@pytest.mark.asyncio
async def test_build_status_response_reads_redis_for_web_conversation(fake_redis):
    await VisitorWebStatusService.mark_connected(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    )

    response = await VisitorWebStatusService.build_status_response(
        fake_redis,
        _conversation(),
    )

    assert response["conversation_id"] == 123
    assert response["status"] == "online"
    assert response["can_display"] is True


@pytest.mark.asyncio
async def test_get_conversation_status_rejects_other_agent(monkeypatch, fake_redis):
    monkeypatch.setattr(
        "app.services.visitor_web_status_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=_conversation(agent_id=99)),
    )

    with pytest.raises(ForbiddenError):
        await VisitorWebStatusService.get_conversation_status(
            AsyncMock(),
            fake_redis,
            conversation_id=123,
            tenant_id=7,
            agent_id=42,
            roles=["agent"],
        )


@pytest.mark.asyncio
async def test_get_conversation_status_allows_admin(monkeypatch, fake_redis):
    monkeypatch.setattr(
        "app.services.visitor_web_status_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=_conversation(agent_id=99)),
    )

    response = await VisitorWebStatusService.get_conversation_status(
        AsyncMock(),
        fake_redis,
        conversation_id=123,
        tenant_id=7,
        agent_id=42,
        roles=["admin"],
    )

    assert response["status"] == "offline"
    assert response["can_display"] is True


@pytest.mark.asyncio
async def test_emit_status_for_conversation_pushes_agent_room(fake_redis):
    class FakeRealtime:
        def __init__(self):
            self.calls = []

        async def emit(self, event, data, *, room=None, to=None, namespace=None):
            self.calls.append((event, data, room, to, namespace))

    await VisitorWebStatusService.mark_connected(
        fake_redis,
        tenant_id=7,
        channel_id=9,
        visitor_external_id="visitor-1",
        sid="sid-1",
    )
    rt = FakeRealtime()

    await VisitorWebStatusService.emit_status_for_conversation(
        rt,
        fake_redis,
        _conversation(),
    )

    assert rt.calls == [
        (
            VISITOR_WEB_STATUS_EVENT,
            {
                "conversation_id": 123,
                "status": "online",
                "can_display": True,
                "checked_at": rt.calls[0][1]["checked_at"],
            },
            "agent:7:42",
            None,
            CHAT_NAMESPACE,
        )
    ]
