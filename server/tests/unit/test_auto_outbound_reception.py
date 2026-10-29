"""Unit tests for auto-outbound reception strategies (Wave B2)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.models.auto_outbound import AutoOutboundCallRecord, AutoOutboundTarget, AutoOutboundTask
from app.services.auto_outbound.engine import AutoOutboundDialEngine, DialSessionContext
from app.services.auto_outbound.reception import (
    AgentReception,
    BotReception,
    IvrReception,
    ReceptionDispatcher,
    TaskReceptionSnap,
    count_pacing_agents_for_queue,
    count_ready_agents_for_queue,
)
from app.services.auto_outbound.simulator import CallSimulator, SimulationProfile


def _snap(**overrides) -> TaskReceptionSnap:
    data = dict(
        id=1,
        tenant_id=1,
        execution_mode="ivr",
        voice_flow_id=10,
        transfer_queue_id=20,
        voicespeed_agent_id="vs-1",
        voicespeed_agent_name="Bot",
        intent_result_field_key="intent",
        queue_id=30,
        abandon_prompt="hangup",
        fields=[
            {"key": "intent", "name": "意向", "field_type": "single_select", "enabled": True},
            {"key": "note", "name": "备注", "field_type": "single_line_text", "enabled": True},
        ],
        wrapup_seconds=60,
    )
    data.update(overrides)
    return TaskReceptionSnap(**data)


def _ctx(**overrides) -> DialSessionContext:
    data = dict(
        tenant_id=1,
        task_id=1,
        target_id=10,
        record_id=100,
        phone_number="13800138000",
        answered=True,
        call_id="call-1",
    )
    data.update(overrides)
    return DialSessionContext(**data)


class _SessionCM:
    def __init__(self, db=None):
        self.db = db or MagicMock()
        self.db.commit = AsyncMock()
        self.db.refresh = AsyncMock()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *args):
        return False


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def _event_defaults(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundEventService.emit_call_event",
        AsyncMock(return_value=[]),
    )


@pytest.mark.asyncio
async def test_queue_agent_counts_use_realtime_resource_ownership(redis, monkeypatch):
    from app.services.auto_outbound import frequency as freq

    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [
        (1, "ready"),
        (2, "ready"),
        (3, "busy"),
        (4, "busy"),
    ]
    db.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AsyncSessionLocal",
        lambda: _SessionCM(db),
    )
    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        AsyncMock(return_value=True),
    )
    snapshots = {
        1: {"resource_state": "idle", "visible_status": "ready"},
        2: {
            "resource_state": "ringing",
            "visible_status": "busy",
            "current_call_id": "inbound-call",
        },
        3: {
            "resource_state": "in_call",
            "visible_status": "busy",
            "current_call_id": "auto-call",
        },
        4: {
            "resource_state": "in_call",
            "visible_status": "busy",
            "current_call_id": "other-auto-call",
        },
    }
    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.get_snapshot",
        AsyncMock(side_effect=lambda _r, _tenant, employee_id: snapshots[employee_id]),
    )
    await freq.set_session_mapping(
        "auto-call",
        {"tenant_id": 1, "queue_id": 30, "task_id": 10, "target_id": 100},
        redis=redis,
    )
    await freq.set_session_mapping(
        "other-auto-call",
        {"tenant_id": 1, "queue_id": 31, "task_id": 11, "target_id": 101},
        redis=redis,
    )

    assert await count_ready_agents_for_queue(1, 30, redis=redis) == 1
    assert await count_pacing_agents_for_queue(1, 30, redis=redis) == 2


@pytest.mark.asyncio
async def test_no_idle_agent_log_throttles_identical_blocked_signature(
    redis, monkeypatch, caplog
):
    import logging

    import app.services.auto_outbound.reception as reception_mod
    from app.services.auto_outbound.reception import _count_queue_agent_capacity

    reception_mod._no_idle_log_state.clear()

    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [(1, "ready"), (2, "ready")]
    db.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AsyncSessionLocal",
        lambda: _SessionCM(db),
    )
    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.get_snapshot",
        AsyncMock(return_value={"resource_state": "idle"}),
    )

    with caplog.at_level(logging.INFO, logger="app.services.auto_outbound.reception"):
        await _count_queue_agent_capacity(1, 30, redis=redis)
        await _count_queue_agent_capacity(1, 30, redis=redis)
        await _count_queue_agent_capacity(1, 30, redis=redis)

    messages = [
        r.message
        for r in caplog.records
        if "auto_outbound no idle agent" in r.message
    ]
    assert len(messages) == 1
    assert "1:ready/disconnected,2:ready/disconnected" in messages[0]


@pytest.mark.asyncio
async def test_no_idle_agent_log_emits_immediately_on_signature_change(
    redis, monkeypatch, caplog
):
    import logging

    import app.services.auto_outbound.reception as reception_mod
    from app.services.auto_outbound.reception import _count_queue_agent_capacity

    reception_mod._no_idle_log_state.clear()

    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [(1, "ready")]
    db.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AsyncSessionLocal",
        lambda: _SessionCM(db),
    )

    connected = AsyncMock(side_effect=[False, False])
    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        connected,
    )
    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.get_snapshot",
        AsyncMock(return_value={"resource_state": "idle"}),
    )

    with caplog.at_level(logging.INFO, logger="app.services.auto_outbound.reception"):
        await _count_queue_agent_capacity(1, 30, redis=redis)

        # Same agent now busy/disconnected signature would differ if status
        # from DB changes — swap the DB row status for the second probe.
        result.all.return_value = [(1, "busy")]
        await _count_queue_agent_capacity(1, 30, redis=redis)

    messages = [
        r.message
        for r in caplog.records
        if "auto_outbound no idle agent" in r.message
    ]
    assert len(messages) == 2
    assert "1:ready/disconnected" in messages[0]
    assert "1:busy/disconnected" in messages[1]


@pytest.mark.asyncio
async def test_dispatcher_routes_by_mode(monkeypatch):
    ivr = AsyncMock()
    bot = AsyncMock()
    agent = AsyncMock()
    dispatcher = ReceptionDispatcher(
        strategies={"ivr": ivr, "bot": bot, "agent": agent},
    )
    snap = _snap(execution_mode="bot")
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._load_task_snap",
        AsyncMock(return_value=snap),
    )
    await dispatcher.on_answered(_ctx())
    bot.handle.assert_awaited_once()
    ivr.handle.assert_not_awaited()
    agent.handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_ivr_degraded_writes_reception_result(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    updates = []

    async def _update(record_id, data):
        updates.append((record_id, data))

    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", _update
    )
    await IvrReception().handle("sim-1", _ctx(), _snap())
    assert any(u[1].get("reception_type") == "ivr" for u in updates)
    result_updates = [u[1] for u in updates if "reception_result" in u[1]]
    assert result_updates
    assert result_updates[0]["reception_result"]["degraded"] is True


@pytest.mark.asyncio
async def test_ivr_uses_published_queue_targets(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._degrade_media",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", AsyncMock()
    )
    graph = {
        "nodes": [
            {
                "id": "queue",
                "type": "assign_queue",
                "data": {
                    "queue_targets": [
                        {"queue_type": "employee_group", "queue_id": 31},
                        {"queue_type": "employee_group", "queue_id": 32},
                    ]
                },
            }
        ]
    }
    reception = IvrReception()
    monkeypatch.setattr(
        reception,
        "_load_published_graph",
        AsyncMock(return_value=(graph, 7)),
    )
    run_workflow = AsyncMock()
    monkeypatch.setattr(reception, "_run_workflow", run_workflow)
    ctx = _ctx()
    task = _snap(transfer_queue_id=20)

    await reception.handle("call-1", ctx, task)
    await asyncio.sleep(0)

    run_workflow.assert_awaited_once_with("call-1", ctx, task, graph, 7)
    assert graph["nodes"][0]["data"]["queue_targets"] == [
        {"queue_type": "employee_group", "queue_id": 31},
        {"queue_type": "employee_group", "queue_id": 32},
    ]


@pytest.mark.asyncio
async def test_bot_intent_writes_target_field(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", AsyncMock()
    )
    merge = AsyncMock()
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._merge_target_field_values", merge
    )
    await BotReception().handle("sim-1", _ctx(), _snap(intent_result_field_key="intent"))
    merge.assert_awaited_once()
    assert merge.await_args.args[1] == {"intent": "simulated_intent"}


@pytest.mark.asyncio
async def test_bot_skips_intent_when_field_key_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", AsyncMock()
    )
    merge = AsyncMock()
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._merge_target_field_values", merge
    )
    await BotReception().handle(
        "sim-1", _ctx(), _snap(intent_result_field_key=None)
    )
    merge.assert_not_awaited()


class _FakeBotWorkflow:
    """Captures initial variables and mimics the VoiceSpeed node's preset outcome."""

    instances: list["_FakeBotWorkflow"] = []
    preset_status: str | None = "passed"

    def __init__(self, *, initial_variables, **_kwargs):
        self.ctx = SimpleNamespace(variables=dict(initial_variables))
        self.done = asyncio.Event()
        self.ended_reason = "voicespeed_ended"
        _FakeBotWorkflow.instances.append(self)

    async def start(self):
        if self.preset_status and "sys._voicespeed_call_variables" in self.ctx.variables:
            self.ctx.variables["sys._voicespeed_call_variables_status"] = self.preset_status
        self.done.set()

    def bridged_agent_info(self):
        return None


async def _run_bot_with_target(monkeypatch, field_values, *, preset_status="passed"):
    _FakeBotWorkflow.instances = []
    _FakeBotWorkflow.preset_status = preset_status
    monkeypatch.setattr(
        "app.services.call_center.workflow.VoiceFlowWorkflow", _FakeBotWorkflow
    )

    def _no_orchestrator():
        raise RuntimeError("no orchestrator in unit tests")

    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator", _no_orchestrator
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._get_telephony", AsyncMock(return_value=object())
    )
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=object())
    session.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.services.auto_outbound.reception.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AutoOutboundRepository.get_target",
        AsyncMock(return_value=SimpleNamespace(field_values=field_values)),
    )
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(
        "app.services.auto_outbound.reception.resolve_tenant_timezone",
        AsyncMock(return_value=ZoneInfo("Asia/Shanghai")),
    )
    update = AsyncMock()
    monkeypatch.setattr("app.services.auto_outbound.reception._update_record", update)
    snap = _snap(
        execution_mode="bot",
        intent_result_field_key=None,
        fields=[
            {"key": "field_1", "name": "customer_name", "field_type": "single_line_text", "enabled": True},
            {"key": "field_2", "name": "备注", "field_type": "single_line_text", "enabled": True},
        ],
    )
    await BotReception()._run_bot("call-1", _ctx(), snap)
    return _FakeBotWorkflow.instances[0], update


@pytest.mark.asyncio
async def test_bot_injects_call_variables_and_records_snapshot(monkeypatch):
    workflow, update = await _run_bot_with_target(
        monkeypatch, {"field_1": "张三", "field_2": "VIP"}
    )
    assert workflow.ctx.variables["sys._voicespeed_call_variables"] == {"customer_name": "张三"}
    payload = update.await_args.args[1]
    assert payload["call_variables"] == {
        "status": "passed",
        "items": [{"name": "customer_name", "value": "张三", "truncated": False}],
    }


@pytest.mark.asyncio
async def test_bot_records_failed_call_variables(monkeypatch):
    _workflow, update = await _run_bot_with_target(
        monkeypatch, {"field_1": "张三"}, preset_status="failed"
    )
    assert update.await_args.args[1]["call_variables"]["status"] == "failed"


@pytest.mark.asyncio
async def test_bot_skips_call_variables_when_node_never_presets(monkeypatch):
    _workflow, update = await _run_bot_with_target(
        monkeypatch, {"field_1": "张三"}, preset_status=None
    )
    assert "call_variables" not in update.await_args.args[1]


@pytest.mark.asyncio
async def test_agent_abandon_hangup(monkeypatch, redis):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    updates = []

    async def _update(record_id, data):
        updates.append(data)

    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", _update
    )
    hangup = AsyncMock()
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._safe_hangup", hangup
    )
    picker = MagicMock()
    picker.pick_ready_agent_for_queue = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AsyncSessionLocal",
        lambda: _SessionCM(),
    )

    strategy = AgentReception(redis=redis, picker=picker)
    await strategy.handle(
        "sim-1",
        _ctx(),
        _snap(execution_mode="agent", abandon_prompt="hangup"),
    )
    assert any(u.get("reception_result", {}).get("abandoned") for u in updates)
    hangup.assert_awaited()


@pytest.mark.asyncio
async def test_agent_abandon_play_wait_falls_back(monkeypatch, redis):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", AsyncMock()
    )
    say = AsyncMock(return_value=False)
    hangup = AsyncMock()
    monkeypatch.setattr("app.services.auto_outbound.reception._safe_say", say)
    monkeypatch.setattr("app.services.auto_outbound.reception._safe_hangup", hangup)
    picker = MagicMock()
    picker.pick_ready_agent_for_queue = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AsyncSessionLocal",
        lambda: _SessionCM(),
    )

    strategy = AgentReception(redis=redis, picker=picker)
    await strategy.handle(
        "sim-1",
        _ctx(),
        _snap(execution_mode="agent", abandon_prompt="play_wait"),
    )
    say.assert_awaited()
    hangup.assert_awaited()


@pytest.mark.asyncio
async def test_agent_degraded_assigns_ready_agent(monkeypatch, redis):
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    updates = []

    async def _update(record_id, data):
        updates.append(data)

    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", _update
    )
    picker = MagicMock()
    picker.pick_ready_agent_for_queue = AsyncMock(
        return_value={"employee_id": 77, "name": "A"}
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AsyncSessionLocal",
        lambda: _SessionCM(),
    )
    strategy = AgentReception(redis=redis, picker=picker)
    await strategy.handle("sim-1", _ctx(), _snap(execution_mode="agent"))
    assert any(u.get("agent_id") == 77 for u in updates)


@pytest.mark.asyncio
async def test_simulator_agent_abandon_e2e(monkeypatch, redis):
    """answered → AgentReception no ready agent → abandoned record persisted."""
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.settings.AUTO_OUTBOUND_SIMULATION_ENABLED",
        True,
    )

    task = AutoOutboundTask(
        id=1,
        tenant_id=1,
        name="t",
        template_name="tpl",
        fields=[],
        status="active",
        execution_mode="agent",
        queue_id=30,
        pacing_mode="progressive",
        abandon_prompt="hangup",
        start_date=datetime(2026, 8, 1).date(),
        end_date=datetime(2026, 8, 31).date(),
        daily_time_windows=[{"start": "00:00", "end": "23:59"}],
        max_concurrency=5,
        wrapup_seconds=60,
    )
    target = AutoOutboundTarget(
        id=10,
        tenant_id=1,
        task_id=1,
        phone_number="13800138000",
        status="calling",
        field_values={},
        call_count=1,
        answered_count=0,
        retry_counts={},
    )
    record = AutoOutboundCallRecord(
        id=100,
        tenant_id=1,
        task_id=1,
        target_id=10,
        phone_number="13800138000",
        attempt_no=1,
        started_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
        duration_ms=0,
    )
    record_updates: list[dict] = []

    async def get_record(db, record_id):
        return record

    async def update_record(db, item, data):
        for k, v in data.items():
            setattr(item, k, v)
        record_updates.append(dict(data))
        return item

    async def mark_answered_once(db, *, record_id, target_id, answered_at, **_kwargs):
        if record.answered_at is not None or record.ended_at is not None:
            return False
        record.answered_at = answered_at
        target.answered_count = int(target.answered_count or 0) + 1
        return True

    async def finalize_record_once(
        db,
        *,
        record_id,
        ended_at,
        duration_ms,
        terminal_state,
        fail_reason,
        **_kwargs,
    ):
        if record.ended_at is not None:
            return None
        persisted_terminal = (
            "answered" if record.answered_at is not None else terminal_state
        )
        record.ended_at = ended_at
        record.duration_ms = duration_ms
        record.terminal_state = persisted_terminal
        record.fail_reason = None if persisted_terminal == "answered" else fail_reason
        return persisted_terminal

    async def get_target(db, target_id):
        return target

    async def update_target(db, item, data, **_kwargs):
        for k, v in data.items():
            setattr(item, k, v)
        return item

    async def get_task(db, task_id):
        return task

    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_record",
        get_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_record",
        update_record,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.mark_answered_once",
        mark_answered_once,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.finalize_record_once",
        finalize_record_once,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_target",
        get_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.update_target",
        update_target,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.get_task",
        get_task,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository._maybe_complete_task_locked",
        AsyncMock(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._load_task_snap",
        AsyncMock(
            return_value=_snap(execution_mode="agent", abandon_prompt="hangup")
        ),
    )
    picker = MagicMock()
    picker.pick_ready_agent_for_queue = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.auto_outbound.reception.AsyncSessionLocal",
        lambda: _SessionCM(),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AsyncSessionLocal",
        lambda: _SessionCM(),
    )
    # Patch repository.maybe_complete used inside handle_call_ended
    monkeypatch.setattr(
        "app.services.auto_outbound.engine.AutoOutboundRepository.count_targets_by_status",
        AsyncMock(return_value=1),
    )

    reception = ReceptionDispatcher(
        redis=redis,
        strategies={
            "agent": AgentReception(redis=redis, picker=picker),
            "ivr": IvrReception(),
            "bot": BotReception(),
        },
    )
    sim = CallSimulator(
        profile=SimulationProfile(
            answer_rate=1.0,
            min_ring_seconds=0.01,
            max_ring_seconds=0.01,
            min_talk_seconds=0.01,
            max_talk_seconds=0.01,
        )
    )
    engine = AutoOutboundDialEngine(
        redis=redis,
        session_factory=lambda: _SessionCM(),
        reception=reception,
        simulator=sim,
    )
    await engine._store_session(
        "sim-e2e",
        DialSessionContext(
            tenant_id=1,
            task_id=1,
            target_id=10,
            record_id=100,
            phone_number="13800138000",
            call_id="sim-e2e",
        ),
    )
    await engine.handle_call_answered("sim-e2e")
    # Allow agent reception task to finish
    import asyncio

    await asyncio.sleep(0.05)

    abandoned = [
        u for u in record_updates if (u.get("reception_result") or {}).get("abandoned")
    ]
    assert abandoned, f"expected abandon update, got {record_updates}"
    assert record.reception_result and record.reception_result.get("abandoned") is True


def _fake_assign_workflow_cls(*, bridged: bool):
    """Stand-in VoiceFlowWorkflow whose bridge outcome is fixed up front."""

    class _FakeWorkflow:
        def __init__(self, **_kwargs):
            self.done = asyncio.Event()
            self.ended_reason = "bridged" if bridged else "timeout"
            self.ctx = SimpleNamespace(variables={})

        async def start(self):
            self.done.set()

        def bridged_agent_info(self):
            if not bridged:
                return None
            return {"tenant_id": 1, "employee_id": 42}

    return _FakeWorkflow


def _patch_assign_workflow_deps(monkeypatch, orch, *, bridged: bool):
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator", lambda: orch
    )
    monkeypatch.setattr(
        "app.services.call_center.workflow.VoiceFlowWorkflow",
        _fake_assign_workflow_cls(bridged=bridged),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._get_telephony", AsyncMock()
    )


@pytest.mark.asyncio
async def test_assign_workflow_stays_registered_after_bridge(monkeypatch, redis):
    """Once bridged, the workflow must stay in the orchestrator registry: the
    customer leg's hangup settles the agent via the bridged-agent path, which
    looks the workflow up there."""
    orch = SimpleNamespace(_workflows={})
    _patch_assign_workflow_deps(monkeypatch, orch, bridged=True)
    updates = []
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record",
        AsyncMock(side_effect=lambda record_id, data: updates.append(data)),
    )

    strategy = AgentReception(redis=redis, picker=MagicMock())
    await strategy._run_assign_workflow("call-1", _ctx(), _snap(execution_mode="agent"))

    assert "call-1" in orch._workflows
    assert any(u.get("reception_result", {}).get("assigned") for u in updates)


@pytest.mark.asyncio
async def test_assign_workflow_popped_when_not_bridged(monkeypatch, redis):
    """Without a bridge the workflow hung the call up itself, so the registry
    entry is removed and the target is treated as abandoned."""
    orch = SimpleNamespace(_workflows={})
    _patch_assign_workflow_deps(monkeypatch, orch, bridged=False)
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", AsyncMock()
    )
    abandon = AsyncMock()
    monkeypatch.setattr(AgentReception, "_abandon", abandon)

    strategy = AgentReception(redis=redis, picker=MagicMock())
    await strategy._run_assign_workflow("call-1", _ctx(), _snap(execution_mode="agent"))

    assert "call-1" not in orch._workflows
    abandon.assert_awaited_once()


@pytest.mark.asyncio
async def test_assign_workflow_disables_transfer_prompt(monkeypatch, redis):
    """The inline assign graph built by _run_assign_workflow carries
    queue_prompt_text="" so the callee hears no transfer TTS before the agent."""
    orch = SimpleNamespace(_workflows={})
    captured: dict = {}

    class _FakeWorkflow:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.done = asyncio.Event()
            self.ended_reason = "timeout"

        async def start(self):
            self.done.set()

        def bridged_agent_info(self):
            return None

    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator", lambda: orch
    )
    monkeypatch.setattr(
        "app.services.call_center.workflow.VoiceFlowWorkflow", _FakeWorkflow
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._get_telephony", AsyncMock()
    )
    monkeypatch.setattr(
        "app.services.auto_outbound.reception._update_record", AsyncMock()
    )
    monkeypatch.setattr(AgentReception, "_abandon", AsyncMock())

    strategy = AgentReception(redis=redis, picker=MagicMock())
    await strategy._run_assign_workflow("call-1", _ctx(), _snap(execution_mode="agent"))

    assign_node = next(
        n for n in captured["graph"]["nodes"] if n["type"] == "assign_queue"
    )
    assert assign_node["data"]["queue_prompt_text"] == ""
