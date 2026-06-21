from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.enums import ConversationStatus, MessageContentType
from app.schemas.visitor_timeout_close import VisitorTimeoutClosePayload
from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService


def _conversation(**overrides):
    data = {
        "id": 100,
        "tenant_id": 1,
        "status": ConversationStatus.ACTIVE.value,
        "agent_id": 20,
        "visitor": SimpleNamespace(level="normal"),
        "started_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _enabled_payload(**overrides) -> VisitorTimeoutClosePayload:
    payload = VisitorTimeoutCloseService.default_payload().model_copy(
        update={
            "enabled": True,
            "first_normal_minutes": 10,
            "close_normal_minutes": 20,
        }
    )
    if overrides:
        payload = payload.model_copy(update=overrides)
    return payload


def test_default_payload_is_disabled_until_configured():
    payload = VisitorTimeoutCloseService.default_payload()

    assert payload.enabled is False
    assert payload.first_normal_minutes == 110
    assert payload.close_normal_minutes == 120
    assert payload.notify_agent is True
    assert payload.notify_visitor is True


def test_payload_validation_requires_close_after_first_and_target():
    with pytest.raises(ValidationError):
        VisitorTimeoutClosePayload(
            first_normal_minutes=30,
            close_normal_minutes=30,
        )

    with pytest.raises(ValidationError):
        VisitorTimeoutClosePayload(
            notify_agent=False,
            notify_visitor=False,
        )


def test_vip_order_is_required_only_when_vip_rule_enabled():
    payload = VisitorTimeoutClosePayload(
        vip_enabled=False,
        first_vip_minutes=120,
        close_vip_minutes=110,
    )
    assert payload.vip_enabled is False

    with pytest.raises(ValidationError):
        VisitorTimeoutClosePayload(
            vip_enabled=True,
            first_vip_minutes=120,
            close_vip_minutes=110,
        )


@pytest.mark.asyncio
async def test_reset_on_visitor_message_upserts_next_check(monkeypatch):
    captured: dict = {}
    anchor_at = datetime.now(timezone.utc)

    async def setting_or_default(_db, _tenant_id):
        return _enabled_payload(first_normal_minutes=5, close_normal_minutes=8), 4

    async def upsert_for_conversation(_db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        VisitorTimeoutCloseService,
        "_setting_or_default",
        staticmethod(setting_or_default),
    )
    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.VisitorTimeoutCloseStateRepository.upsert_for_conversation",
        upsert_for_conversation,
    )

    message = SimpleNamespace(
        id=55,
        content_type=MessageContentType.TEXT.value,
        created_at=anchor_at,
    )
    result = await VisitorTimeoutCloseService.reset_on_visitor_message(
        AsyncMock(),
        _conversation(),
        message,
    )

    assert result is not None
    assert captured["tenant_id"] == 1
    assert captured["conversation_id"] == 100
    assert captured["anchor_at"] == anchor_at
    assert captured["anchor_message_id"] == 55
    assert captured["first_reminded_at"] is None
    assert captured["next_check_at"] == anchor_at + timedelta(minutes=5)
    assert captured["config_version"] == 4


@pytest.mark.asyncio
async def test_process_state_sends_first_reminder(monkeypatch):
    called: dict = {}
    now = datetime.now(timezone.utc)
    state = SimpleNamespace(
        tenant_id=1,
        conversation_id=100,
        anchor_at=now - timedelta(minutes=11),
        anchor_message_id=None,
        first_reminded_at=None,
    )
    conversation = _conversation()

    async def setting_or_default(_db, _tenant_id):
        return _enabled_payload(first_normal_minutes=10, close_normal_minutes=20), 3

    async def send_reminder(_db, state_arg, conversation_arg, payload, version, timeout_minutes, now_arg):
        called["state"] = state_arg
        called["conversation"] = conversation_arg
        called["version"] = version
        called["timeout_minutes"] = timeout_minutes
        called["now"] = now_arg

    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        VisitorTimeoutCloseService,
        "_setting_or_default",
        staticmethod(setting_or_default),
    )
    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.MessageRepository.get_latest_by_sender",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        VisitorTimeoutCloseService,
        "_send_reminder",
        staticmethod(send_reminder),
    )

    outcome = await VisitorTimeoutCloseService.process_state(AsyncMock(), state, now=now)

    assert outcome == "reminded"
    assert called["state"] is state
    assert called["conversation"] is conversation
    assert called["version"] == 3
    assert called["timeout_minutes"] == 10


@pytest.mark.asyncio
async def test_process_state_auto_closes_after_close_threshold(monkeypatch):
    called: dict = {}
    now = datetime.now(timezone.utc)
    state = SimpleNamespace(
        tenant_id=1,
        conversation_id=100,
        anchor_at=now - timedelta(minutes=21),
        anchor_message_id=None,
        first_reminded_at=now - timedelta(minutes=10),
    )
    conversation = _conversation()

    async def setting_or_default(_db, _tenant_id):
        return _enabled_payload(first_normal_minutes=10, close_normal_minutes=20), 6

    async def auto_close(_db, state_arg, conversation_arg, payload, version, timeout_minutes, now_arg, redis):
        called["state"] = state_arg
        called["conversation"] = conversation_arg
        called["version"] = version
        called["timeout_minutes"] = timeout_minutes
        called["now"] = now_arg
        called["redis"] = redis

    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        VisitorTimeoutCloseService,
        "_setting_or_default",
        staticmethod(setting_or_default),
    )
    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.MessageRepository.get_latest_by_sender",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        VisitorTimeoutCloseService,
        "_auto_close",
        staticmethod(auto_close),
    )

    outcome = await VisitorTimeoutCloseService.process_state(AsyncMock(), state, now=now)

    assert outcome == "closed"
    assert called["state"] is state
    assert called["conversation"] is conversation
    assert called["version"] == 6
    assert called["timeout_minutes"] == 20


@pytest.mark.asyncio
async def test_process_state_clears_next_check_when_config_disabled(monkeypatch):
    captured: dict = {}
    now = datetime.now(timezone.utc)
    state = SimpleNamespace(
        tenant_id=1,
        conversation_id=100,
        anchor_at=now - timedelta(minutes=30),
        anchor_message_id=None,
        first_reminded_at=None,
    )

    async def setting_or_default(_db, _tenant_id):
        return VisitorTimeoutCloseService.default_payload(), 2

    async def update(_db, state_arg, data, *, commit=True):
        captured["state"] = state_arg
        captured["data"] = data
        captured["commit"] = commit
        return state_arg

    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.ConversationRepository.get_by_id",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        VisitorTimeoutCloseService,
        "_setting_or_default",
        staticmethod(setting_or_default),
    )
    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.VisitorTimeoutCloseStateRepository.update",
        update,
    )

    outcome = await VisitorTimeoutCloseService.process_state(AsyncMock(), state, now=now)

    assert outcome == "skipped"
    assert captured["state"] is state
    assert captured["data"] == {"next_check_at": None, "config_version": 2}


@pytest.mark.asyncio
async def test_process_due_states_claims_one_state_at_a_time(monkeypatch):
    now = datetime.now(timezone.utc)
    states = [
        SimpleNamespace(id=1),
        SimpleNamespace(id=2),
    ]
    claimed: list[dict] = []
    processed: list[object] = []

    async def claim_due(_db, *, now: datetime, lease_until: datetime):
        claimed.append({"now": now, "lease_until": lease_until})
        return states.pop(0) if states else None

    async def process_state(_db, state, _redis, *, now: datetime):
        processed.append(state)
        return "reminded" if state.id == 1 else "closed"

    monkeypatch.setattr(
        "app.services.visitor_timeout_close_service.VisitorTimeoutCloseStateRepository.claim_due",
        claim_due,
    )
    monkeypatch.setattr(
        VisitorTimeoutCloseService,
        "process_state",
        staticmethod(process_state),
    )

    result = await VisitorTimeoutCloseService.process_due_states(AsyncMock(), limit=10, now=now)

    assert result == {"checked": 2, "reminded": 1, "closed": 1, "skipped": 0}
    assert processed == [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    assert len(claimed) == 3
    assert all(item["now"] == now for item in claimed)
    assert all(item["lease_until"] == now + timedelta(seconds=300) for item in claimed)
