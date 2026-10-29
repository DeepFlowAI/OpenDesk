"""Unit checks for the target call-record persistence model."""
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import BigInteger, DateTime

from app.models.call_record import CallRecord
from app.models.call_record_access_scope import CallRecordAccessScope
from app.models.call_recording import CallRecording
from app.repositories.call_record_repository import CallRecordRepository


TARGET_CALL_RECORD_COLUMNS = {
    "id",
    "public_id",
    "tenant_id",
    "call_id",
    "conversation_id",
    "root_call_id",
    "direction",
    "call_source",
    "custom_business_info",
    "external_context",
    "customer_number",
    "service_number",
    "user_id",
    "voice_flow_id",
    "voice_flow_version_id",
    "initiator_agent_id",
    "initiator_agent_ref_id",
    "initiator_agent_name_snapshot",
    "last_serving_agent_id",
    "last_queue_type",
    "last_queue_id",
    "lifecycle_status",
    "started_at",
    "customer_connected_at",
    "first_agent_connected_at",
    "human_service_requested_at",
    "first_agent_wait_started_at",
    "first_agent_offer_started_at",
    "bot_handoff_requested_at",
    "bot_handoff_succeeded_at",
    "ended_at",
    "human_service_ended_at",
    "finalization_status",
    "ended_event_id",
    "result_rule_version",
    "finalized_at",
    "actual_reception_type",
    "call_result",
    "hangup_party",
    "hangup_reason_code",
    "hangup_stage",
    "short_abandon_threshold_ms",
    "total_duration_ms",
    "customer_ring_duration_ms",
    "agent_wait_duration_ms",
    "customer_agent_talk_duration_ms",
    "satisfaction_result",
    "satisfaction_trigger_source",
    "satisfaction_primary_option_id",
    "satisfaction_primary_option_label",
    "satisfaction_answer_count",
    "satisfaction_duration_ms",
    "satisfaction_projected_at",
    "recording_status",
    "created_at",
    "updated_at",
}

REMOVED_COLUMNS = {
    "from_number",
    "to_number",
    "state",
    "employee_group_id",
    "agent_id",
    "answered_at",
    "ring_duration_ms",
    "talk_duration_ms",
    "device_type",
    "device_identifier",
    "hangup_reason",
    "recording_url",
    "recording_duration_ms",
    "extra_metadata",
}


def test_call_record_has_only_target_columns() -> None:
    columns = set(CallRecord.__table__.columns.keys())

    assert columns == TARGET_CALL_RECORD_COLUMNS
    assert columns.isdisjoint(REMOVED_COLUMNS)


def test_call_record_uses_bigint_durations_and_timezone_aware_datetimes() -> None:
    for column_name in (
        "id",
        "total_duration_ms",
        "customer_ring_duration_ms",
        "agent_wait_duration_ms",
        "customer_agent_talk_duration_ms",
        "satisfaction_duration_ms",
        "short_abandon_threshold_ms",
    ):
        assert isinstance(CallRecord.__table__.columns[column_name].type, BigInteger)

    for column_name in (
        "started_at",
        "customer_connected_at",
        "first_agent_connected_at",
        "human_service_requested_at",
        "first_agent_wait_started_at",
        "first_agent_offer_started_at",
        "bot_handoff_requested_at",
        "bot_handoff_succeeded_at",
        "ended_at",
        "human_service_ended_at",
        "satisfaction_projected_at",
        "finalized_at",
        "created_at",
        "updated_at",
    ):
        column_type = CallRecord.__table__.columns[column_name].type
        assert isinstance(column_type, DateTime)
        assert column_type.timezone is True


def test_call_record_related_models_have_expected_unique_constraints() -> None:
    access_constraints = {
        constraint.name for constraint in CallRecordAccessScope.__table__.constraints
    }
    recording_constraints = {
        constraint.name for constraint in CallRecording.__table__.constraints
    }

    assert "uq_cras_record_subject_reason" in access_constraints
    assert "uq_cras_source_subject_reason" in access_constraints
    assert "uq_call_recordings_tenant_recording" in recording_constraints


@pytest.mark.asyncio
async def test_repository_create_can_participate_in_caller_transaction() -> None:
    db = AsyncMock()
    db.add = Mock()

    row = await CallRecordRepository.create(
        db,
        {
            "tenant_id": 1,
            "call_id": "call-1",
            "root_call_id": "call-1",
            "direction": "inbound",
            "call_source": "inbound",
        },
        commit=False,
    )

    assert isinstance(row, CallRecord)
    db.add.assert_called_once_with(row)
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()
