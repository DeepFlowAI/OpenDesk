"""Unit tests for publishing call facts to call event subscription rules."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import call_event_publisher as publisher_module
from app.services.call_event_publisher import CallEventPublisher
from app.services.call_event_rule_cache import CachedCallEventRule


NOW = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)


class FakeSession:
    def __init__(self, *, max_sequence: int | None = 9) -> None:
        self.savepoints = 0
        self.rolled_back = 0
        self.max_sequence = max_sequence

    @asynccontextmanager
    async def _nested(self):
        self.savepoints += 1
        try:
            yield
        except Exception:
            self.rolled_back += 1
            raise

    def begin_nested(self):
        return self._nested()

    async def get(self, model, ident):
        return None

    async def execute(self, statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.max_sequence)


def _record(**overrides):
    values = {
        "id": 5,
        "public_id": uuid4(),
        "tenant_id": 7,
        "call_id": "media-call-1",
        "direction": "inbound",
        "call_source": "inbound",
        "lifecycle_status": "active",
        "customer_number": "13800000000",
        "service_number": "4000000000",
        "user_id": None,
        "initiator_agent_id": None,
        "initiator_agent_name_snapshot": None,
        "last_serving_agent_id": None,
        "last_queue_type": None,
        "last_queue_id": None,
        "started_at": NOW,
        "customer_connected_at": None,
        "ended_at": None,
        "external_context": {"order": "A-1"},
        "custom_business_info": {"level": "vip"},
        "finalization_status": "completed",
        "call_result": "agent_answered",
        "hangup_party": "customer",
        "hangup_reason_code": "normal",
        "actual_reception_type": "agent",
        "total_duration_ms": 60_000,
        "customer_ring_duration_ms": 1_000,
        "agent_wait_duration_ms": 2_000,
        "customer_agent_talk_duration_ms": 50_000,
        "recording_status": "completed",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _event(**overrides):
    values = {
        "event_id": "flowkit:queue-entered:1",
        "event_type": "queue_entered",
        "occurred_at": NOW,
        "sequence_no": 3,
        "actor_type": "system",
        "actor_id": None,
        "target_type": "employee_group",
        "target_id": "11",
        "target_name_snapshot": "Sales",
        "queue_type": "employee_group",
        "queue_id": 11,
        "queue_name_snapshot": "Sales",
        "duration_ms": None,
        "details": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _rule(rule_id=1, *, events, directions=("inbound",), sources=("inbound",)):
    return CachedCallEventRule(
        id=rule_id,
        event_types=frozenset(events),
        directions=frozenset(directions),
        call_sources=frozenset(sources),
    )


@pytest.fixture
def wiring(monkeypatch):
    state = SimpleNamespace(
        rules=(_rule(events={"call.queue.entered", "call.ended", "call.created"}),),
        cached=True,
        subscriptions=[SimpleNamespace(id=21, tenant_id=7, is_active=True)],
    )

    async def lookup(tenant_id):
        return "v1", state.rules if state.cached else None

    async def load(db, tenant_id, version):
        return state.rules

    async def deliverable(db, *, tenant_id, rule_ids):
        state.deliverable_rule_ids = rule_ids
        return state.subscriptions

    enqueue = AsyncMock(return_value=[uuid4()])
    monkeypatch.setattr(publisher_module.CallEventRuleCache, "lookup", lookup)
    monkeypatch.setattr(publisher_module.CallEventRuleCache, "load", load)
    monkeypatch.setattr(
        publisher_module.CallEventSubscriptionRepository,
        "list_deliverable_subscriptions",
        deliverable,
    )
    monkeypatch.setattr(
        publisher_module.EventDeliveryService,
        "enqueue_resolved_in_transaction",
        enqueue,
    )
    state.enqueue = enqueue
    return state


@pytest.mark.asyncio
async def test_matching_rule_enqueues_whitelisted_queue_event(wiring):
    db = FakeSession()
    record = _record()

    await CallEventPublisher.publish_trajectory_event(
        db, record, _event(), event_type="queue_entered"
    )

    kwargs = wiring.enqueue.await_args.kwargs
    assert kwargs["event_type"] == "call.queue.entered"
    assert kwargs["source_module"] == "opendesk://call-center"
    assert kwargs["subject"] == f"call/{record.public_id}"
    payload = kwargs["payload"]
    assert payload["sequence"] == 3
    assert payload["event"]["queue"] == {"type": "employee_group", "name": "Sales"}
    call = payload["call"]
    assert call["public_id"] == str(record.public_id)
    assert call["external_context"] == {"order": "A-1"}
    assert "custom_business_info" not in call
    for forbidden in ("id", "tenant_id", "call_id", "user_id", "last_queue_id"):
        assert forbidden not in call
    assert wiring.deliverable_rule_ids == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rule",
    [
        _rule(events={"call.created"}),
        _rule(events={"call.queue.entered"}, directions=("outbound",)),
        _rule(events={"call.queue.entered"}, sources=("agent_dial",)),
    ],
)
async def test_unmatched_rule_skips_without_savepoint(wiring, rule):
    wiring.rules = (rule,)
    db = FakeSession()

    await CallEventPublisher.publish_trajectory_event(
        db, _record(), _event(), event_type="queue_entered"
    )

    assert db.savepoints == 0
    wiring.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_unmapped_trajectory_event_is_ignored(wiring):
    db = FakeSession()

    await CallEventPublisher.publish_trajectory_event(
        db, _record(), _event(event_type="hold_started"), event_type="hold_started"
    )

    assert db.savepoints == 0
    wiring.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_rolls_back_savepoint_and_never_raises(wiring, caplog):
    wiring.enqueue.side_effect = RuntimeError("boom 13800000000")
    db = FakeSession()

    await CallEventPublisher.publish_trajectory_event(
        db, _record(), _event(), event_type="queue_entered"
    )

    assert db.savepoints == 1
    assert db.rolled_back == 1
    assert "call event publish failed" in caplog.text
    assert "13800000000" not in caplog.text


@pytest.mark.asyncio
async def test_cache_miss_loads_rules_inside_savepoint(wiring):
    wiring.cached = False
    db = FakeSession()

    await CallEventPublisher.publish_trajectory_event(
        db, _record(), _event(), event_type="queue_entered"
    )

    assert db.savepoints == 1
    wiring.enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_deliverable_subscription_skips(wiring):
    wiring.subscriptions = []
    db = FakeSession()

    await CallEventPublisher.publish_trajectory_event(
        db, _record(), _event(), event_type="queue_entered"
    )

    wiring.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_once_per_call_event_id_is_stable(wiring):
    record = _record()
    for event_id in ("flowkit:created:a", "flowkit:created:b"):
        await CallEventPublisher.publish_trajectory_event(
            FakeSession(),
            record,
            _event(event_id=event_id, event_type="call_created"),
            event_type="call_created",
        )

    first, second = wiring.enqueue.await_args_list
    assert first.kwargs["event_id"] == second.kwargs["event_id"]
    assert first.kwargs["event_id"] == CallEventPublisher.event_id(
        "call.created", str(record.public_id)
    )


@pytest.mark.asyncio
async def test_call_ended_adds_final_fields(wiring):
    record = _record(lifecycle_status="ended", ended_at=NOW)

    await CallEventPublisher.publish_call_ended(FakeSession(max_sequence=12), record)

    kwargs = wiring.enqueue.await_args.kwargs
    assert kwargs["event_type"] == "call.ended"
    payload = kwargs["payload"]
    assert payload["sequence"] == 12
    assert payload["call"]["custom_business_info"] == {"level": "vip"}
    assert payload["call"]["call_result"] == "agent_answered"
    assert payload["call"]["customer_agent_talk_duration_ms"] == 50_000


@pytest.mark.asyncio
async def test_recording_event_carries_temporary_link(wiring, monkeypatch):
    wiring.rules = (_rule(events={"call.recording.completed"}),)
    record = _record()
    recording = SimpleNamespace(
        public_id=uuid4(),
        call_record_id=record.id,
        recording_id="media-rec-1",
        storage_key="tenant/7/recordings/a.wav",
        phase="llm",
        status="partial",
        started_at=NOW,
        ended_at=NOW,
        duration_ms=1_000,
    )
    monkeypatch.setattr(
        publisher_module.CallRecordingRepository,
        "get_by_recording_id",
        AsyncMock(return_value=recording),
    )
    storage = SimpleNamespace(get_temporary_url=AsyncMock(return_value="https://signed"))
    monkeypatch.setattr(
        "app.libs.storage.factory.create_storage_client", lambda: storage
    )

    await CallEventPublisher.publish_trajectory_event(
        FakeSession(),
        record,
        _event(event_type="recording_partial", details={"recording_id": "media-rec-1"}),
        event_type="recording_partial",
    )

    storage.get_temporary_url.assert_awaited_once_with(
        "tenant/7/recordings/a.wav", expires_seconds=3600
    )
    kwargs = wiring.enqueue.await_args.kwargs
    assert kwargs["event_type"] == "call.recording.completed"
    assert kwargs["event_id"] == CallEventPublisher.event_id(
        "call.recording.completed", str(recording.public_id)
    )
    body = kwargs["payload"]["event"]["recording"]
    assert body["public_id"] == str(recording.public_id)
    assert body["phase"] == "bot"
    assert body["status"] == "partial"
    assert body["download_url"] == "https://signed"
    assert body["download_url_expires_at"] is not None
    assert "storage_key" not in body
    assert "recording_id" not in body


@pytest.mark.asyncio
async def test_synthetic_recording_end_without_artifact_is_skipped(wiring, monkeypatch):
    wiring.rules = (_rule(events={"call.recording.completed"}),)
    lookup = AsyncMock()
    monkeypatch.setattr(
        publisher_module.CallRecordingRepository, "get_by_recording_id", lookup
    )

    await CallEventPublisher.publish_trajectory_event(
        FakeSession(),
        _record(),
        _event(event_type="recording_partial", details={"synthesized_from_event_id": "x"}),
        event_type="recording_partial",
    )

    lookup.assert_not_awaited()
    wiring.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_recording_has_no_link(wiring, monkeypatch):
    wiring.rules = (_rule(events={"call.recording.failed"}),)
    record = _record()
    recording = SimpleNamespace(
        public_id=uuid4(),
        call_record_id=record.id,
        storage_key=None,
        phase="bridged",
        status="failed",
        started_at=NOW,
        ended_at=None,
        duration_ms=None,
    )
    monkeypatch.setattr(
        publisher_module.CallRecordingRepository,
        "get_by_recording_id",
        AsyncMock(return_value=recording),
    )

    await CallEventPublisher.publish_trajectory_event(
        FakeSession(),
        record,
        _event(event_type="recording_failed", details={"recording_id": "r"}),
        event_type="recording_failed",
    )

    body = wiring.enqueue.await_args.kwargs["payload"]["event"]["recording"]
    assert body["phase"] == "human"
    assert body["download_url"] is None
    assert body["failure_reason"] == "recording_failed"


@pytest.mark.asyncio
async def test_transfer_to_external_hides_number(wiring):
    wiring.rules = (_rule(events={"call.transfer.completed"}),)

    await CallEventPublisher.publish_trajectory_event(
        FakeSession(),
        _record(),
        _event(
            event_type="transfer_completed",
            actor_id="3",
            target_type="external_number",
            target_id=None,
            target_name_snapshot="13900000000",
            queue_type=None,
            queue_name_snapshot=None,
        ),
        event_type="transfer_completed",
    )

    body = wiring.enqueue.await_args.kwargs["payload"]["event"]
    assert body["transfer_type"] == "external"
    assert body["target"] == {"type": "external"}
