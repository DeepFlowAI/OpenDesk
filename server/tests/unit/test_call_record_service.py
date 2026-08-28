"""Unit tests for target call-record reads and queue projection."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.services.call_record_service import CallRecordService


NOW = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)


def _record(**overrides):
    data = {
        "id": 7,
        "public_id": uuid4(),
        "tenant_id": 1,
        "call_id": "call-001",
        "conversation_id": "conv-001",
        "root_call_id": "call-001",
        "direction": "inbound",
        "call_source": "inbound",
        "custom_business_info": None,
        "external_context": None,
        "customer_number": "13800138000",
        "service_number": "4008009000",
        "voice_flow_id": None,
        "voice_flow_version_id": None,
        "initiator_agent_id": None,
        "last_serving_agent_id": None,
        "last_queue_type": None,
        "last_queue_id": None,
        "user_id": None,
        "lifecycle_status": "ended",
        "finalization_status": "completed",
        "result_rule_version": 1,
        "finalized_at": NOW,
        "actual_reception_type": "agent",
        "call_result": "agent_answered",
        "hangup_party": "customer",
        "hangup_reason_code": "normal_clearing",
        "started_at": NOW,
        "customer_connected_at": NOW,
        "first_agent_connected_at": NOW,
        "ended_at": NOW,
        "human_service_ended_at": NOW,
        "total_duration_ms": 30_000,
        "customer_ring_duration_ms": 1_000,
        "agent_wait_duration_ms": 2_000,
        "customer_agent_talk_duration_ms": 20_000,
        "satisfaction_result": "not_surveyed",
        "satisfaction_trigger_source": None,
        "satisfaction_primary_option_id": None,
        "satisfaction_primary_option_label": None,
        "satisfaction_answer_count": 0,
        "satisfaction_duration_ms": None,
        "recording_status": "completed",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_get_by_public_id_returns_tickets_and_temporary_recording_url(monkeypatch):
    row = _record(last_queue_type="employee_group", last_queue_id=9)
    recording = SimpleNamespace(
        recording_id="rec-1",
        call_leg_id="leg-1",
        phase="bridged",
        status="completed",
        storage_key="recordings/rec-1.wav",
        started_at=NOW,
        ended_at=NOW,
        duration_ms=20_000,
    )
    storage = SimpleNamespace(
        get_temporary_url=AsyncMock(return_value="https://signed.example/rec-1")
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_public_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._employee_name_snapshots",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.UserRepository.list_by_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallUserAssociationService.candidate_users",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.TicketRepository.list_by_call_record_id",
        AsyncMock(return_value=[SimpleNamespace(id=21, ticket_number="TK-21")]),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordingRepository.list_for_call",
        AsyncMock(return_value=[recording]),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._last_queue_brief",
        AsyncMock(
            return_value={
                "queue_type": "employee_group",
                "queue_id": 9,
                "name": "Support",
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.create_storage_client",
        lambda: storage,
    )
    monkeypatch.setattr(
        "app.services.call_satisfaction_projection_service."
        "CallSatisfactionProjectionService.detail",
        AsyncMock(return_value=None),
    )

    result = await CallRecordService.get_by_public_id(
        AsyncMock(),
        row.public_id,
        tenant_id=1,
    )

    assert result["public_id"] == row.public_id
    assert result["related_tickets"] == [{"id": 21, "ticket_number": "TK-21"}]
    assert result["recordings"][0]["access_url"] == "https://signed.example/rec-1"
    assert "storage_key" not in result["recordings"][0]
    storage.get_temporary_url.assert_awaited_once_with(
        "recordings/rec-1.wav",
        expires_seconds=300,
    )


@pytest.mark.asyncio
async def test_get_paginated_forwards_target_filters_and_scope(monkeypatch):
    get_page = AsyncMock(return_value=([], 0))
    scope_predicate = object()
    monkeypatch.setattr(
        "app.services.call_record_service.DataScopeService.build_call_record_predicate",
        lambda _principal: scope_predicate,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_paginated",
        get_page,
    )

    result = await CallRecordService.get_paginated(
        AsyncMock(),
        1,
        call_source="auto_outbound",
        call_result="agent_answered",
        recording_status="completed",
        min_customer_agent_talk_duration_ms=5_000,
        principal=SimpleNamespace(),
    )

    kwargs = get_page.await_args.kwargs
    assert kwargs["call_source"] == "auto_outbound"
    assert kwargs["call_result"] == "agent_answered"
    assert kwargs["recording_status"] == "completed"
    assert kwargs["min_customer_agent_talk_duration_ms"] == 5_000
    assert kwargs["scope_predicate"] is scope_predicate
    assert result["items"] == []


@pytest.mark.asyncio
async def test_get_paginated_includes_auto_outbound_history_context(monkeypatch):
    row = _record(call_source="auto_outbound")
    db = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_paginated",
        AsyncMock(return_value=([row], 1)),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._employee_name_snapshots",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._load_user_map",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._last_queue_brief",
        AsyncMock(return_value=None),
    )
    get_contexts = AsyncMock(
        return_value={
            row.id: {
                "source": "auto_outbound",
                "task_id": 12,
                "record_id": 34,
            }
        }
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallWorkspaceContextService."
        "get_auto_outbound_contexts",
        get_contexts,
    )

    result = await CallRecordService.get_paginated(db, 1)

    assert result["items"][0]["source"] == "auto_outbound"
    assert result["items"][0]["task_id"] == 12
    assert result["items"][0]["record_id"] == 34
    get_contexts.assert_awaited_once_with(
        db,
        tenant_id=1,
        call_records=[row],
    )


@pytest.mark.asyncio
async def test_get_paginated_rejects_invalid_date_and_duration_ranges():
    with pytest.raises(ValidationError, match="later than"):
        await CallRecordService.get_paginated(
            AsyncMock(),
            1,
            start_time=NOW,
            end_time=NOW - timedelta(days=1),
        )

    with pytest.raises(ValidationError, match="90 days"):
        await CallRecordService.get_paginated(
            AsyncMock(),
            1,
            start_time=NOW - timedelta(days=91),
            end_time=NOW,
        )

    with pytest.raises(ValidationError, match="cannot exceed"):
        await CallRecordService.get_paginated(
            AsyncMock(),
            1,
            min_agent_wait_duration_ms=2_000,
            max_agent_wait_duration_ms=1_000,
        )


@pytest.mark.asyncio
async def test_get_filter_options_group_limits_agents_and_queues(monkeypatch):
    principal = SimpleNamespace(user_id=7, group_ids=[3])
    employees = [
        SimpleNamespace(id=7, name="Alice", display_name=None, username="alice"),
        SimpleNamespace(id=8, name=None, display_name="Bob", username="bob"),
    ]
    groups = [SimpleNamespace(id=3, name="Support")]
    list_employees = AsyncMock(return_value=employees)
    list_groups = AsyncMock(return_value=groups)
    monkeypatch.setattr(
        "app.services.call_record_service.DataScopeService.get_scope",
        lambda _principal, _resource: "group",
    )
    monkeypatch.setattr(
        "app.services.call_record_service.DataScopeService.get_group_peer_employee_ids",
        AsyncMock(return_value=[8]),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.EmployeeRepository.list_active_filter_options",
        list_employees,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.EmployeeGroupRepository.list_filter_options",
        list_groups,
    )

    result = await CallRecordService.get_filter_options(
        AsyncMock(),
        tenant_id=1,
        principal=principal,
    )

    assert list_employees.await_args.args[2] == [7, 8]
    assert list_groups.await_args.args[2] == [3]
    assert result["agents"] == [
        {"id": 7, "name": "Alice"},
        {"id": 8, "name": "Bob"},
    ]
    assert result["queues"] == [
        {"queue_type": "employee_group", "queue_id": 3, "name": "Support"},
        {"queue_type": "employee", "queue_id": 7, "name": "Alice"},
        {"queue_type": "employee", "queue_id": 8, "name": "Bob"},
    ]


@pytest.mark.asyncio
async def test_get_filter_options_self_returns_no_cross_agent_options(monkeypatch):
    list_employees = AsyncMock()
    list_groups = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.DataScopeService.get_scope",
        lambda _principal, _resource: "self",
    )
    monkeypatch.setattr(
        "app.services.call_record_service.EmployeeRepository.list_active_filter_options",
        list_employees,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.EmployeeGroupRepository.list_filter_options",
        list_groups,
    )

    result = await CallRecordService.get_filter_options(
        AsyncMock(),
        tenant_id=1,
        principal=SimpleNamespace(),
    )

    assert result == {"agents": [], "queues": []}
    list_employees.assert_not_awaited()
    list_groups.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_filter_options_all_uses_unrestricted_tenant_options(monkeypatch):
    list_employees = AsyncMock(return_value=[])
    list_groups = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.call_record_service.DataScopeService.get_scope",
        lambda _principal, _resource: "all",
    )
    monkeypatch.setattr(
        "app.services.call_record_service.EmployeeRepository.list_active_filter_options",
        list_employees,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.EmployeeGroupRepository.list_filter_options",
        list_groups,
    )

    await CallRecordService.get_filter_options(
        AsyncMock(),
        tenant_id=1,
        principal=SimpleNamespace(),
    )

    assert list_employees.await_args.args[2] is None
    assert list_groups.await_args.args[2] is None


@pytest.mark.asyncio
async def test_bind_queue_projects_summary_event_and_access_scope(monkeypatch):
    row = _record(lifecycle_status="active")
    update = AsyncMock(return_value=row)
    append = AsyncMock()
    add_scope = AsyncMock()
    db = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.update",
        update,
    )
    monkeypatch.setattr(
        "app.services.call_record_service._queue_record_brief",
        AsyncMock(return_value={"name": "Support"}),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.append_event",
        append,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordAccessScopeRepository.add",
        add_scope,
    )

    await CallRecordService.bind_queue(db, 1, row.call_id, "employee_group", 9)

    assert update.await_args.args[2] == {
        "last_queue_type": "employee_group",
        "last_queue_id": 9,
    }
    assert append.await_args.kwargs["payload"].event_type == "queue_entered"
    assert add_scope.await_args.kwargs["subject_type"] == "employee_group"
    assert add_scope.await_args.kwargs["reason"] == "queued"
    db.commit.assert_awaited_once()
