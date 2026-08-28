"""Unit tests for event-driven call-record projections."""
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.services.call_record_service import CallRecordService, normalize_call_number


NOW = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
MARK_RECEPTION_STARTED = CallRecordService.mark_reception_started


def test_normalize_call_number_removes_sip_address_and_display_separators() -> None:
    assert normalize_call_number("sip:+86 (138) 0013-8000@example.com") == "+8613800138000"
    assert normalize_call_number("tel:400-168-1715;phone-context=cn") == "4001681715"
    assert normalize_call_number(None) is None


@pytest.mark.asyncio
async def test_create_outbound_normalizes_root_identity_and_adds_initiator_scope(
    monkeypatch,
) -> None:
    public_id = uuid4()
    row = SimpleNamespace(
        id=88,
        public_id=public_id,
        tenant_id=3,
        call_id="call-88",
        conversation_id="conv-88",
        root_call_id="call-88",
        direction="outbound",
        call_source="agent_dial",
        customer_number="+8613800138000",
        service_number="4001681715",
        started_at=NOW,
        user_id=None,
    )
    create = AsyncMock(return_value=row)
    append = AsyncMock()
    add_scope = AsyncMock(return_value=True)
    identify = AsyncMock()
    db = AsyncMock()

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.create", create
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.append_event", append
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordAccessScopeRepository.add",
        add_scope,
    )
    monkeypatch.setattr(
        "app.services.call_record_service._best_effort_identify_user", identify
    )
    monkeypatch.setattr(
        "app.services.call_record_service._to_detail",
        lambda value, _name: {"id": value.id, "public_id": str(value.public_id)},
    )

    result = await CallRecordService.create_for_outbound(
        db,
        3,
        call_id="call-88",
        conversation_id="conv-88",
        root_call_id=None,
        from_number="400-168-1715",
        to_number="sip:+86 (138) 0013-8000@example.com",
        agent_id=12,
        call_source="embedded_call",
        custom_business_info="Order 88\nRenewal requested",
        external_context={"record_type": "order", "record_id": "88"},
    )

    data = create.await_args.args[1]
    assert data["root_call_id"] == "call-88"
    assert data["customer_number"] == "+8613800138000"
    assert data["service_number"] == "4001681715"
    assert data["initiator_agent_id"] == 12
    assert data["call_source"] == "embedded_call"
    assert data["custom_business_info"] == "Order 88\nRenewal requested"
    assert data["external_context"] == {"record_type": "order", "record_id": "88"}
    assert UUID(result["public_id"]) == public_id
    assert add_scope.await_args.kwargs["reason"] == "initiator"
    assert add_scope.await_args.kwargs["subject_id"] == 12
    db.commit.assert_awaited_once()
    identify.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_outbound_skips_identify_when_disabled(monkeypatch) -> None:
    public_id = uuid4()
    row = SimpleNamespace(
        id=89,
        public_id=public_id,
        tenant_id=3,
        call_id="call-89",
        conversation_id="conv-89",
        root_call_id="call-89",
        direction="outbound",
        call_source="auto_outbound",
        customer_number="13800138000",
        service_number="0210000",
        started_at=NOW,
        user_id=None,
    )
    identify = AsyncMock()
    db = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.create",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.append_event",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._best_effort_identify_user", identify
    )
    monkeypatch.setattr(
        "app.services.call_record_service._to_detail",
        lambda value, _name: {"id": value.id},
    )

    result = await CallRecordService.create_for_outbound(
        db,
        3,
        call_id="call-89",
        conversation_id="conv-89",
        root_call_id=None,
        from_number="0210000",
        to_number="13800138000",
        call_source="auto_outbound",
        identify_user=False,
    )

    assert result["id"] == 89
    identify.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_outbound_existing_row_skips_identify_when_disabled(
    monkeypatch,
) -> None:
    row = SimpleNamespace(id=90, public_id=uuid4())
    identify = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._best_effort_identify_user", identify
    )
    monkeypatch.setattr(
        "app.services.call_record_service._to_detail",
        lambda value, _name: {"id": value.id},
    )

    result = await CallRecordService.create_for_outbound(
        AsyncMock(),
        3,
        call_id="call-90",
        conversation_id=None,
        root_call_id=None,
        from_number=None,
        to_number="13800138000",
        identify_user=False,
    )

    assert result["id"] == 90
    identify.assert_not_awaited()


@pytest.mark.asyncio
async def test_reception_started_projects_first_and_last_agent(monkeypatch) -> None:
    row = SimpleNamespace(
        id=7,
        tenant_id=3,
        call_id="call-7",
        first_agent_connected_at=None,
    )
    append = AsyncMock()
    db = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.append_event", append
    )
    monkeypatch.setattr(
        "app.services.call_record_service._employee_name_snapshots",
        AsyncMock(return_value={12: "Alice"}),
    )
    await MARK_RECEPTION_STARTED(
        db,
        3,
        "call-7",
        agent_id=12,
        agent_leg_id="leg-12",
    )

    assert append.await_count == 2
    reception_event = append.await_args_list[1].kwargs["payload"]
    assert reception_event.event_type == "reception_started"
    assert reception_event.target_id == "12"
    assert reception_event.occurred_at.tzinfo is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_completed_synchronizes_target_summary(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.services.call_record_service")
    row = SimpleNamespace(
        id=5,
        lifecycle_status="active",
        ended_event_id=None,
        call_id="call-5",
    )
    settlement = {
        "projection_complete": True,
        "result_rule_version": 1,
        "actual_reception_type": "agent",
        "call_result": "agent_answered",
        "hangup_party": "agent",
        "hangup_reason_code": "agent_hangup",
        "hangup_match_strategy": "internal_reason",
        "hangup_match_score": 1.0,
        "hangup_match_margin": 0.0,
        "hangup_classification_version": 1,
        "sip_status": None,
        "sip_reason": None,
        "sip_warning": None,
        "sip_reason_hdr": None,
        "total_duration_ms": 60_000,
        "customer_ring_duration_ms": 10_000,
        "agent_wait_duration_ms": 5_000,
        "customer_agent_talk_duration_ms": 40_000,
    }
    update = AsyncMock(return_value=row)
    db = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.update", update
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.append_event",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.reconcile_open_intervals",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.build_settlement_details",
        AsyncMock(return_value=settlement),
    )
    monkeypatch.setattr(
        "app.services.call_satisfaction_projection_service."
        "CallSatisfactionProjectionService.project",
        AsyncMock(return_value=True),
    )

    await CallRecordService.mark_completed(
        db,
        3,
        "call-5",
        hangup_reason="agent_hangup",
        hangup_party="agent",
    )

    patch = update.await_args.args[2]
    assert patch["lifecycle_status"] == "ended"
    assert patch["finalization_status"] == "completed"
    assert patch["call_result"] == "agent_answered"
    assert patch["customer_agent_talk_duration_ms"] == 40_000
    assert db.commit.await_count == 1
    classified = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "call_hangup_classified"
    )
    assert classified.hangup_call_id == "call-5"
    assert classified.hangup_reason_code == "agent_hangup"
    assert classified.hangup_match_strategy == "internal_reason"


@pytest.mark.asyncio
async def test_save_recording_upserts_artifact_and_refreshes_summary(monkeypatch) -> None:
    row = SimpleNamespace(
        id=9,
        tenant_id=3,
        call_id="call-9",
        recording_status="none",
    )
    recordings = [
        SimpleNamespace(status="completed"),
        SimpleNamespace(status="failed"),
    ]
    upsert = AsyncMock()
    update = AsyncMock(return_value=row)
    db = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.find_by_media_call_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordingRepository.upsert", upsert
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordingRepository.list_for_call",
        AsyncMock(return_value=recordings),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.update", update
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallTrajectoryService.append_event",
        AsyncMock(),
    )

    saved = await CallRecordService.save_recording(
        db,
        call_id="call-9",
        recording_id="rec-9",
        storage_key="recordings/rec-9.wav",
        source_event_id="flowkit:recording:rec-9",
        status="completed",
        duration_ms=42_000,
    )

    assert saved is True
    artifact = upsert.await_args.args[1]
    assert artifact["recording_id"] == "rec-9"
    assert artifact["storage_key"] == "recordings/rec-9.wav"
    assert update.await_args.args[2] == {"recording_status": "partial"}
    db.commit.assert_awaited_once()
