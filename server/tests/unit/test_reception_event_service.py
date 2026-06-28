"""
Unit tests for ReceptionEventService — the runtime reception-event recorder.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.enums import ReceptionEventReason, ReceptionEventType
from app.services.reception_event_service import ReceptionEventService

OCCURRED_AT = datetime(2026, 6, 27, 8, 0, 0, tzinfo=timezone.utc)


def _latest(event_type: str, to_agent_id: int | None):
    return SimpleNamespace(event_type=event_type, to_agent_id=to_agent_id)


class TestReceptionEventService:

    @pytest.mark.asyncio
    async def test_record_first_assignment_creates_event(self):
        mock_db = AsyncMock()
        with patch("app.services.reception_event_service.ReceptionEventRepository") as repo:
            repo.get_latest = AsyncMock(return_value=None)
            repo.create = AsyncMock(return_value=SimpleNamespace(id=1))

            result = await ReceptionEventService.record(
                mock_db,
                tenant_id=1,
                conversation_id=100,
                event_type=ReceptionEventType.ASSIGNED.value,
                occurred_at=OCCURRED_AT,
                agent_id=5,
                group_id=7,
                to_agent_id=5,
                reason=ReceptionEventReason.FIRST_HUMAN.value,
            )

        assert result is not None
        repo.create.assert_awaited_once()
        payload = repo.create.await_args.args[1]
        assert payload["event_type"] == "assigned"
        assert payload["to_agent_id"] == 5
        assert payload["reason"] == "first_human"
        assert payload["occurred_at"] == OCCURRED_AT

    @pytest.mark.asyncio
    async def test_record_assignment_dedupes_same_owner(self):
        mock_db = AsyncMock()
        with patch("app.services.reception_event_service.ReceptionEventRepository") as repo:
            repo.get_latest = AsyncMock(return_value=_latest("assigned", 5))
            repo.create = AsyncMock()

            result = await ReceptionEventService.record(
                mock_db,
                tenant_id=1,
                conversation_id=100,
                event_type=ReceptionEventType.ASSIGNED.value,
                occurred_at=OCCURRED_AT,
                agent_id=5,
                to_agent_id=5,
            )

        assert result is None
        repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_record_assignment_to_new_owner_creates_event(self):
        mock_db = AsyncMock()
        with patch("app.services.reception_event_service.ReceptionEventRepository") as repo:
            repo.get_latest = AsyncMock(return_value=_latest("assigned", 5))
            repo.create = AsyncMock(return_value=SimpleNamespace(id=2))

            result = await ReceptionEventService.record(
                mock_db,
                tenant_id=1,
                conversation_id=100,
                event_type=ReceptionEventType.TRANSFERRED.value,
                occurred_at=OCCURRED_AT,
                agent_id=9,
                from_agent_id=5,
                to_agent_id=9,
                reason=ReceptionEventReason.TRANSFER.value,
            )

        assert result is not None
        repo.create.assert_awaited_once()
        payload = repo.create.await_args.args[1]
        assert payload["from_agent_id"] == 5
        assert payload["to_agent_id"] == 9

    @pytest.mark.asyncio
    async def test_record_ended_skips_dedupe(self):
        mock_db = AsyncMock()
        with patch("app.services.reception_event_service.ReceptionEventRepository") as repo:
            repo.get_latest = AsyncMock(return_value=_latest("assigned", 5))
            repo.create = AsyncMock(return_value=SimpleNamespace(id=3))

            result = await ReceptionEventService.record(
                mock_db,
                tenant_id=1,
                conversation_id=100,
                event_type=ReceptionEventType.ENDED.value,
                occurred_at=OCCURRED_AT,
                agent_id=5,
                from_agent_id=5,
            )

        assert result is not None
        repo.get_latest.assert_not_awaited()
        repo.create.assert_awaited_once()
