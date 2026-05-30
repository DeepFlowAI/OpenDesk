"""
Unit tests for call record service.
"""
from datetime import datetime, timezone
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

    result = await CallRecordService.get_by_id(AsyncMock(), record_id=7, tenant_id=1)

    assert result["related_tickets"] == [
        {"id": 21, "ticket_number": "TK202605290021"},
    ]
