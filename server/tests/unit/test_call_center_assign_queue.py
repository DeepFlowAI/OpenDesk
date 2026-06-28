from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.call_center.assign_queue import AssignQueueCandidate, AssignQueueSelector
from app.services.call_center.nodes import AssignQueueExecutor, ExecutionContext
from app.services.call_center.queue import QueuePicker
from app.services.cc_agent_resource_service import CcAgentResourceService


class _MissingRedisClient:
    @property
    def client(self):
        raise RuntimeError("Redis not initialized")


class _ScalarResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items


class _FakeDb:
    def __init__(self, employees):
        self.employees = employees

    async def execute(self, _query):
        return _ScalarResult(self.employees)


@pytest.mark.asyncio
async def test_assign_queue_requires_redis(monkeypatch):
    monkeypatch.setattr("app.db.redis.redis_client", _MissingRedisClient())
    ctx = ExecutionContext(
        call_id="call-1",
        tenant_id=7,
        variables={},
        telephony=object(),
    )

    with pytest.raises(RuntimeError, match="requires Redis"):
        await AssignQueueExecutor().execute(
            ctx,
            {
                "id": "assign-queue-1",
                "type": "assign_queue",
                "data": {"employee_group_id": 9, "timeout_seconds": 30},
            },
        )


@pytest.mark.asyncio
async def test_queue_picker_prioritizes_preferred_ready_agent(monkeypatch):
    picker = QueuePicker()
    employees = [
        SimpleNamespace(id=1, display_name="Agent 1", nickname=None, name="Agent 1", username="a1"),
        SimpleNamespace(id=2, display_name="Agent 2", nickname=None, name="Agent 2", username="a2"),
    ]
    db = _FakeDb(employees)
    reserve = AsyncMock(return_value={"resource_state": "ringing"})
    next_index = AsyncMock(side_effect=AssertionError("preferred hit should not advance queue pointer"))
    monkeypatch.setattr(CcAgentResourceService, "ensure_from_visible", AsyncMock())
    monkeypatch.setattr(CcAgentResourceService, "reserve_inbound", reserve)
    monkeypatch.setattr(CcAgentResourceService, "next_queue_index", next_index)

    pick = await picker.pick_ready_agent_for_queue(
        db,
        tenant_id=7,
        queue_type="employee_group",
        queue_id=9,
        r=object(),
        call_id="call-1",
        offer_id="offer-1",
        ttl_seconds=30,
        preferred_employee_id=2,
    )

    assert pick["employee_id"] == 2
    reserve.assert_awaited_once()
    assert reserve.await_args.kwargs["call_id"] == "call-1"
    assert reserve.await_args.args[2] == 2
    next_index.assert_not_awaited()


def _candidate(
    queue_id: int,
    *,
    waiting: int,
    tail: int,
    available: int,
    gate: bool = True,
    order: int = 0,
    limit_reason: str | None = None,
) -> AssignQueueCandidate:
    return AssignQueueCandidate(
        queue_type="employee_group",
        queue_id=queue_id,
        order=order,
        waiting_count=waiting,
        tail_wait_seconds=tail,
        available_agent_count=available,
        gate_passed=gate,
        limit_reason=limit_reason,
    )


@pytest.mark.asyncio
async def test_assign_queue_selector_uses_legacy_employee_group(monkeypatch):
    async def fake_build(_db, _r, _tenant_id, *, queue_type, queue_id, order):
        assert queue_type == "employee_group"
        assert queue_id == 9
        return _candidate(queue_id, waiting=0, tail=0, available=1, order=order)

    monkeypatch.setattr(AssignQueueSelector, "_build_candidate", fake_build)

    selection = await AssignQueueSelector.select(
        object(),
        object(),
        7,
        {"employee_group_id": 9, "timeout_seconds": 30},
    )

    assert selection.candidate is not None
    assert selection.candidate.queue_id == 9


@pytest.mark.asyncio
async def test_assign_queue_selector_resolves_user_field_target(monkeypatch):
    async def fake_targets(_db, _tenant_id, *, call_id, field_id):
        assert call_id == "call-1"
        assert field_id == 5
        return [{"queue_type": "employee_group", "queue_id": 9}]

    async def fake_build(_db, _r, _tenant_id, *, queue_type, queue_id, order):
        assert queue_type == "employee_group"
        assert queue_id == 9
        return _candidate(queue_id, waiting=0, tail=0, available=1, order=order)

    monkeypatch.setattr(AssignQueueSelector, "_targets_from_user_field", fake_targets)
    monkeypatch.setattr(AssignQueueSelector, "_build_candidate", fake_build)

    selection = await AssignQueueSelector.select(
        object(),
        object(),
        7,
        {"queue_targets": [{"queue_type": "user_field", "queue_id": 5}]},
        call_id="call-1",
    )

    assert selection.candidate is not None
    assert selection.candidate.queue_id == 9


@pytest.mark.asyncio
async def test_assign_queue_selector_skips_unresolved_user_field(monkeypatch):
    async def fake_targets(_db, _tenant_id, *, call_id, field_id):
        assert call_id == "call-1"
        assert field_id == 5
        return []

    async def fake_build(_db, _r, _tenant_id, *, queue_type, queue_id, order):
        raise AssertionError("unresolved user_field target should not be built")

    monkeypatch.setattr(AssignQueueSelector, "_targets_from_user_field", fake_targets)
    monkeypatch.setattr(AssignQueueSelector, "_build_candidate", fake_build)

    selection = await AssignQueueSelector.select(
        object(),
        object(),
        7,
        {"queue_targets": [{"queue_type": "user_field", "queue_id": 5}]},
        call_id="call-1",
    )

    assert selection.candidate is None
    assert selection.failure_status == "no_available_queue"


@pytest.mark.asyncio
async def test_assign_queue_selector_least_waiting_tiebreaks_available(monkeypatch):
    async def fake_build(_db, _r, _tenant_id, *, queue_type, queue_id, order):
        data = {
            1: _candidate(1, waiting=2, tail=5, available=0, order=order),
            2: _candidate(2, waiting=2, tail=10, available=2, order=order),
            3: _candidate(3, waiting=4, tail=0, available=3, order=order),
        }
        return data[queue_id]

    monkeypatch.setattr(AssignQueueSelector, "_build_candidate", fake_build)

    selection = await AssignQueueSelector.select(
        object(),
        object(),
        7,
        {
            "target_strategy": "least_waiting_count",
            "queue_targets": [
                {"queue_type": "employee_group", "queue_id": 1},
                {"queue_type": "employee_group", "queue_id": 2},
                {"queue_type": "employee_group", "queue_id": 3},
            ],
        },
    )

    assert selection.candidate is not None
    assert selection.candidate.queue_id == 2


@pytest.mark.asyncio
async def test_assign_queue_selector_reports_mixed_limit(monkeypatch):
    async def fake_build(_db, _r, _tenant_id, *, queue_type, queue_id, order):
        reason = "max_waiting_count" if queue_id == 1 else "max_wait_seconds"
        return _candidate(
            queue_id,
            waiting=10,
            tail=120,
            available=0,
            gate=False,
            order=order,
            limit_reason=reason,
        )

    monkeypatch.setattr(AssignQueueSelector, "_build_candidate", fake_build)

    selection = await AssignQueueSelector.select(
        object(),
        object(),
        7,
        {
            "queue_targets": [
                {"queue_type": "employee_group", "queue_id": 1},
                {"queue_type": "employee_group", "queue_id": 2},
            ],
        },
    )

    assert selection.candidate is None
    assert selection.failure_status == "queue_limit_reached"
    assert selection.limit_reason == "mixed_limit"
