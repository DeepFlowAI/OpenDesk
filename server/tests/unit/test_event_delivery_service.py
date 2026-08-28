"""Unit tests for authenticated durable event delivery."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.libs.webhook import WebhookSendResult
from app.models.event_delivery import EVENT_DELIVERY_FAILED, EVENT_DELIVERY_PENDING
from app.repositories.event_delivery_repository import EventDeliveryRepository
from app.repositories.event_subscription_repository import EventSubscriptionRepository
from app.schemas.permission import EffectivePrincipal
from app.services.event_delivery_service import (
    MAX_DELIVERY_ATTEMPTS,
    EventDeliveryService,
)


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=7,
        is_super_admin=True,
        permissions=["admin.access"],
    )


def _snapshot(*, attempt_count: int = 0, is_test: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "public_id": uuid4(),
        "endpoint_url": "https://hooks.example.com/opendesk",
        "secret_ciphertext": "encrypted-secret",
        "source_module": "tickets",
        "event_type": "ticket.updated",
        "event_id": "evt-123",
        "occurred_at": now,
        "payload": {"ticket_id": "ticket-1"},
        "is_test": is_test,
        "attempt_count": attempt_count,
        "first_attempt_at": None,
        "created_at": now,
    }


@pytest.mark.asyncio
async def test_attempt_uses_bearer_secret_header(monkeypatch) -> None:
    captured_headers: dict[str, str] = {}

    class Client:
        async def send(self, **kwargs):
            captured_headers.update(kwargs["headers"])
            return WebhookSendResult(True, 204, 1)

    monkeypatch.setattr(
        "app.services.event_delivery_service.decrypt_secret",
        lambda _value: "odwhsec_test_example",
    )

    await EventDeliveryService._attempt(_snapshot(), client=Client())

    assert captured_headers["Authorization"] == "Bearer odwhsec_test_example"
    assert "X-OpenDesk-Timestamp" not in captured_headers
    assert "X-OpenDesk-Signature" not in captured_headers


def test_build_body_is_stable_and_contains_cloudevents_identity() -> None:
    delivery_id = uuid4()
    occurred_at = datetime(2026, 8, 25, 1, 2, 3, tzinfo=timezone.utc)

    first = EventDeliveryService.build_body(
        delivery_id=delivery_id,
        event_id="evt-1",
        source_module="tickets",
        event_type="ticket.updated",
        occurred_at=occurred_at,
        payload={"b": 2, "a": 1},
        is_test=False,
    )
    second = EventDeliveryService.build_body(
        delivery_id=delivery_id,
        event_id="evt-1",
        source_module="tickets",
        event_type="ticket.updated",
        occurred_at=occurred_at,
        payload={"a": 1, "b": 2},
        is_test=False,
    )

    assert first == second
    assert b'"specversion":"1.0"' in first
    assert b'"id":"evt-1"' in first
    assert f'"deliveryid":"{delivery_id}"'.encode() in first
    assert b'"datacontenttype":"application/json"' in first
    assert b'"time":"2026-08-25T01:02:03Z"' in first
    assert b'"apiversion":"v1"' in first
    assert b'"occurred_at"' not in first
    assert b'"api_version"' not in first
    assert b'"event_id"' not in first
    assert b'"test":false' in first


def test_build_body_omits_empty_optional_subject() -> None:
    body = EventDeliveryService.build_body(
        delivery_id=uuid4(),
        event_id="evt-1",
        source_module="tickets",
        event_type="ticket.updated",
        occurred_at=datetime.now(timezone.utc),
        payload={},
        is_test=False,
    )

    assert b'"subject"' not in body


@pytest.mark.asyncio
async def test_enqueue_in_transaction_does_not_commit_caller_session(monkeypatch) -> None:
    subscription_id = uuid4()
    subscription = SimpleNamespace(
        id=3,
        tenant_id=7,
        public_id=subscription_id,
        endpoint_url="https://hooks.example.com/opendesk",
        secret_ciphertext="encrypted-secret",
        is_active=True,
    )
    db = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    monkeypatch.setattr(
        EventSubscriptionRepository,
        "list_selected_for_tenant",
        AsyncMock(return_value=[subscription]),
    )
    monkeypatch.setattr(
        EventDeliveryRepository,
        "create_many_idempotent",
        AsyncMock(return_value=[uuid4()]),
    )

    result = await EventDeliveryService.enqueue_in_transaction(
        db,
        tenant_id=7,
        subscription_public_ids=[subscription_id],
        source_module="opendesk://engagement/auto-outbound",
        event_type="auto_outbound.task.started",
        event_id="evt-1",
        occurred_at=datetime.now(timezone.utc),
        payload={"task": {"id": 1}},
        api_version="v1",
        subject="auto-outbound-task/1",
    )

    assert len(result) == 1
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_with_no_explicit_subscriptions_does_not_broadcast(monkeypatch) -> None:
    class FailSession:
        def __call__(self):
            raise AssertionError("No session should be opened")

    monkeypatch.setattr(
        "app.services.event_delivery_service.AsyncSessionLocal",
        FailSession(),
    )

    result = await EventDeliveryService.enqueue(
        tenant_id=7,
        subscription_public_ids=[],
        source_module="tickets",
        event_type="ticket.updated",
        event_id="evt-1",
        occurred_at=datetime.now(timezone.utc),
        payload={},
    )

    assert result == []


@pytest.mark.asyncio
async def test_failed_attempt_schedules_first_retry_after_one_minute(monkeypatch) -> None:
    class Client:
        async def send(self, **_kwargs):
            return WebhookSendResult(False, 503, 12, "http_status", "Endpoint returned HTTP 503")

    monkeypatch.setattr(
        "app.services.event_delivery_service.decrypt_secret",
        lambda _value: "secret",
    )
    monkeypatch.setattr(
        "app.services.event_delivery_service.create_webhook_client",
        lambda: Client(),
    )
    before = datetime.now(timezone.utc)

    _result, persisted = await EventDeliveryService._attempt(_snapshot())

    assert persisted["status"] == EVENT_DELIVERY_PENDING
    assert persisted["attempt_count"] == 1
    assert persisted["next_attempt_at"] >= before + timedelta(seconds=59)
    assert persisted["completed_at"] is None


@pytest.mark.asyncio
async def test_eighth_failed_attempt_is_terminal(monkeypatch) -> None:
    class Client:
        async def send(self, **_kwargs):
            return WebhookSendResult(False, None, 5000, "timeout", "Endpoint request timed out")

    monkeypatch.setattr(
        "app.services.event_delivery_service.decrypt_secret",
        lambda _value: "secret",
    )
    monkeypatch.setattr(
        "app.services.event_delivery_service.create_webhook_client",
        lambda: Client(),
    )

    _result, persisted = await EventDeliveryService._attempt(
        _snapshot(attempt_count=MAX_DELIVERY_ATTEMPTS - 1)
    )

    assert persisted["status"] == EVENT_DELIVERY_FAILED
    assert persisted["attempt_count"] == MAX_DELIVERY_ATTEMPTS
    assert persisted["next_attempt_at"] is None
    assert persisted["completed_at"] is not None


@pytest.mark.asyncio
async def test_test_request_has_no_active_session_during_http(monkeypatch) -> None:
    active_sessions = 0

    class FakeSessionContext:
        async def __aenter__(self):
            nonlocal active_sessions
            active_sessions += 1
            return object()

        async def __aexit__(self, *_args):
            nonlocal active_sessions
            active_sessions -= 1

    class FakeSessionFactory:
        def __call__(self):
            return FakeSessionContext()

    public_id = uuid4()
    now = datetime.now(timezone.utc)
    subscription = SimpleNamespace(
        id=1,
        public_id=public_id,
        endpoint_url="https://hooks.example.com/opendesk",
        secret_ciphertext="encrypted-secret",
    )

    async def fake_create_test(_db, *, data, audit_data):
        assert active_sessions == 1
        assert audit_data["subscription_public_id"] == public_id
        return SimpleNamespace(
            public_id=data["public_id"],
            endpoint_url_snapshot=data["endpoint_url_snapshot"],
            secret_ciphertext_snapshot=data["secret_ciphertext_snapshot"],
            source_module=data["source_module"],
            event_type=data["event_type"],
            event_id=data["event_id"],
            occurred_at=data["occurred_at"],
            payload=data["payload"],
            is_test=True,
            attempt_count=0,
            first_attempt_at=None,
            created_at=now,
        )

    async def fake_attempt(_snapshot):
        assert active_sessions == 0
        return (
            WebhookSendResult(True, 204, 20),
            {
                "status": "succeeded",
                "attempt_count": 1,
                "first_attempt_at": now,
                "last_attempt_at": now,
                "last_http_status": 204,
                "last_duration_ms": 20,
                "last_error_type": None,
                "last_error_message": None,
                "claimed_at": None,
                "next_attempt_at": None,
                "completed_at": now,
            },
        )

    async def fake_persist(_db, *, public_id, data, audit_data):
        assert active_sessions == 1
        assert data["status"] == "succeeded"
        assert audit_data["metadata_json"]["http_status"] == 204
        return SimpleNamespace(public_id=public_id)

    monkeypatch.setattr(
        "app.services.event_delivery_service.AsyncSessionLocal",
        FakeSessionFactory(),
    )
    monkeypatch.setattr(
        EventSubscriptionRepository,
        "get_for_tenant",
        AsyncMock(return_value=subscription),
    )
    monkeypatch.setattr(EventDeliveryRepository, "create_test_with_audit", fake_create_test)
    monkeypatch.setattr(EventDeliveryRepository, "persist_attempt_with_audit", fake_persist)
    monkeypatch.setattr(EventDeliveryService, "_attempt", fake_attempt)

    result = await EventDeliveryService.test_subscription_managed(_principal(), public_id)

    assert active_sessions == 0
    assert result["status"] == "succeeded"
    assert result["http_status"] == 204


@pytest.mark.asyncio
async def test_enqueue_safely_isolates_internal_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        EventDeliveryService,
        "enqueue",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    result = await EventDeliveryService.enqueue_safely(
        tenant_id=7,
        subscription_public_ids=[uuid4()],
        source_module="tickets",
        event_type="ticket.updated",
        event_id="evt-1",
        occurred_at=datetime.now(timezone.utc),
        payload={},
    )

    assert result == []


@pytest.mark.asyncio
async def test_run_tick_claims_and_delivers_bounded_slices(monkeypatch) -> None:
    active_sessions = 0
    active_attempts = 0
    max_active_attempts = 0
    snapshots = [_snapshot() for _index in range(3)]

    class FakeSessionContext:
        async def __aenter__(self):
            nonlocal active_sessions
            active_sessions += 1
            return object()

        async def __aexit__(self, *_args):
            nonlocal active_sessions
            active_sessions -= 1

    class FakeSessionFactory:
        def __call__(self):
            return FakeSessionContext()

    class Client:
        def __init__(self) -> None:
            self.closed = 0

        async def aclose(self) -> None:
            self.closed += 1

    client = Client()
    claim_due = AsyncMock(side_effect=[snapshots[:2], snapshots[2:], []])
    persist_attempts = AsyncMock(return_value=2)

    async def fake_attempt(snapshot, *, client: object):
        nonlocal active_attempts, max_active_attempts
        assert active_sessions == 0
        assert client is client_instance
        active_attempts += 1
        max_active_attempts = max(max_active_attempts, active_attempts)
        await asyncio.sleep(0)
        active_attempts -= 1
        return WebhookSendResult(True, 204, 1), {"status": "succeeded"}

    client_instance = client
    monkeypatch.setattr(
        "app.services.event_delivery_service.AsyncSessionLocal",
        FakeSessionFactory(),
    )
    monkeypatch.setattr(
        "app.services.event_delivery_service.create_webhook_client",
        lambda: client,
    )
    monkeypatch.setattr(
        EventDeliveryRepository,
        "sweep_stale",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(EventDeliveryRepository, "claim_due", claim_due)
    monkeypatch.setattr(
        EventDeliveryRepository,
        "persist_attempts",
        persist_attempts,
    )
    monkeypatch.setattr(EventDeliveryService, "_snapshot", lambda item: item)
    monkeypatch.setattr(EventDeliveryService, "_attempt", fake_attempt)
    monkeypatch.setattr(
        "app.services.event_delivery_service.settings.EVENT_DELIVERY_SCAN_BATCH_SIZE",
        3,
    )
    monkeypatch.setattr(
        "app.services.event_delivery_service.settings.EVENT_DELIVERY_CONCURRENCY",
        2,
    )

    result = await EventDeliveryService.run_tick()

    assert result == {
        "claimed": 3,
        "swept": 0,
        "succeeded": 3,
        "failed": 0,
    }
    assert [call.kwargs["limit"] for call in claim_due.await_args_list] == [2, 1]
    assert max_active_attempts == 2
    assert persist_attempts.await_count == 2
    for claim_call, persist_call in zip(
        claim_due.await_args_list,
        persist_attempts.await_args_list,
    ):
        assert persist_call.kwargs["claimed_at"] == claim_call.kwargs["now"]
    assert client.closed == 1
    assert active_sessions == 0


@pytest.mark.asyncio
async def test_cleanup_completed_uses_retention_cutoff_and_batch(monkeypatch) -> None:
    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    class FakeSessionFactory:
        def __call__(self):
            return FakeSessionContext()

    cleanup = AsyncMock(return_value=17)
    monkeypatch.setattr(
        "app.services.event_delivery_service.AsyncSessionLocal",
        FakeSessionFactory(),
    )
    monkeypatch.setattr(
        EventDeliveryRepository,
        "delete_completed_before",
        cleanup,
    )
    monkeypatch.setattr(
        "app.services.event_delivery_service.settings.EVENT_DELIVERY_RETENTION_DAYS",
        30,
    )
    monkeypatch.setattr(
        "app.services.event_delivery_service.settings.EVENT_DELIVERY_CLEANUP_BATCH_SIZE",
        500,
    )
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

    result = await EventDeliveryService.cleanup_completed(now=now)

    assert result == 17
    assert cleanup.await_args.kwargs == {
        "cutoff": now - timedelta(days=30),
        "limit": 500,
    }
