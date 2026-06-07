"""
Unit tests for call record service.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.call_record_service import CallRecordService


def _dt() -> datetime:
    return datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_get_by_id_includes_related_tickets(monkeypatch):
    row = SimpleNamespace(
        id=7,
        call_id="call_001",
        conversation_id=None,
        root_call_id=None,
        direction="inbound",
        state="completed",
        from_number="13800138000",
        to_number="4008009000",
        voice_flow_id=None,
        voice_flow_version_id=None,
        employee_group_id=None,
        agent_id=None,
        user_id=None,
        started_at=_dt(),
        answered_at=_dt(),
        ended_at=_dt(),
        ring_duration_ms=1000,
        talk_duration_ms=2000,
        hangup_reason=None,
        recording_url=None,
        recording_duration_ms=None,
        extra_metadata={},
    )
    tickets = [SimpleNamespace(id=21, ticket_number="TK202605290021")]

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_id",
        AsyncMock(return_value=row),
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
        AsyncMock(return_value=tickets),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.QueueHistoryService.summaries_for_refs",
        AsyncMock(
            return_value={
                "call_001": {
                    "last_assigned_queue": None,
                    "queue_duration_seconds": None,
                }
            }
        ),
    )

    result = await CallRecordService.get_by_id(AsyncMock(), record_id=7, tenant_id=1)

    assert result["related_tickets"] == [
        {"id": 21, "ticket_number": "TK202605290021"},
    ]


@pytest.mark.asyncio
async def test_bind_queue_records_queue_summary_metadata(monkeypatch):
    row = SimpleNamespace(
        call_id="call_001",
        extra_metadata={},
    )
    updates = []

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.services.call_record_service._queue_record_brief",
        AsyncMock(
            return_value={
                "queue_type": "employee_group",
                "queue_id": 9,
                "name": "Support Team",
            }
        ),
    )

    async def fake_update(_db, _row, patch):
        updates.append(patch)
        for key, value in patch.items():
            setattr(_row, key, value)
        return _row

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.update",
        fake_update,
    )

    await CallRecordService.bind_queue(
        AsyncMock(),
        1,
        "call_001",
        "employee_group",
        9,
    )

    patch = updates[0]
    assert patch["state"] == "queued"
    assert patch["employee_group_id"] == 9
    summary = patch["extra_metadata"]["queue_summary"]
    assert summary["last_assigned_queue"]["name"] == "Support Team"
    assert "queued_at" not in summary
    assert "queue_duration_seconds" not in summary


@pytest.mark.asyncio
async def test_mark_answered_does_not_record_queue_duration_metadata(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 5, 29, 10, 0, 30)

    row = SimpleNamespace(
        call_id="call_001",
        started_at=datetime(2026, 5, 29, 10, 0),
        extra_metadata={
            "queue_summary": {
                "last_assigned_queue": {
                    "queue_type": "employee_group",
                    "queue_id": 9,
                    "name": "Support Team",
                },
                "queued_at": datetime(2026, 5, 29, 10, 0, 10).isoformat(),
                "queue_duration_seconds": None,
            }
        },
    )
    updates = []

    monkeypatch.setattr("app.services.call_record_service.datetime", FrozenDatetime)
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_call_id",
        AsyncMock(return_value=row),
    )

    async def fake_update(_db, _row, patch):
        updates.append(patch)
        for key, value in patch.items():
            setattr(_row, key, value)
        return _row

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.update",
        fake_update,
    )

    await CallRecordService.mark_answered(AsyncMock(), 1, "call_001", agent_id=3)

    patch = updates[0]
    assert patch["state"] == "in_progress"
    assert patch["agent_id"] == 3
    assert patch["ring_duration_ms"] == 30_000
    assert "extra_metadata" not in patch


@pytest.mark.asyncio
async def test_get_by_id_uses_call_record_queue_metadata(monkeypatch):
    row = SimpleNamespace(
        id=7,
        call_id="call_001",
        conversation_id=None,
        root_call_id=None,
        direction="inbound",
        state="completed",
        from_number="13800138000",
        to_number="4008009000",
        voice_flow_id=None,
        voice_flow_version_id=None,
        employee_group_id=9,
        agent_id=None,
        user_id=None,
        started_at=_dt(),
        answered_at=_dt() + timedelta(seconds=12),
        ended_at=_dt() + timedelta(seconds=30),
        ring_duration_ms=1000,
        talk_duration_ms=2000,
        hangup_reason=None,
        recording_url=None,
        recording_duration_ms=None,
        extra_metadata={
            "queue_summary": {
                "last_assigned_queue": {
                    "queue_type": "employee_group",
                    "queue_id": 9,
                    "name": "Support Team",
                },
                "queued_at": _dt().isoformat(),
                "queue_duration_seconds": 12,
            }
        },
    )

    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordRepository.get_by_id",
        AsyncMock(return_value=row),
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
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.call_record_service.QueueHistoryService.summaries_for_refs",
        AsyncMock(return_value={"call_001": {"last_assigned_queue": None, "queue_duration_seconds": None}}),
    )

    result = await CallRecordService.get_by_id(AsyncMock(), record_id=7, tenant_id=1)

    assert result["last_assigned_queue"] == {
        "queue_type": "employee_group",
        "queue_id": 9,
        "name": "Support Team",
    }
    assert result["queue_duration_seconds"] is None
