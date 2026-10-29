"""Unit tests for stale call-finalization retry discovery."""
from unittest.mock import AsyncMock

import pytest

from app.services.call_finalization_retry_service import (
    CallFinalizationRetryService,
)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_run_tick_retries_each_candidate_in_a_short_session(monkeypatch):
    sessions = [object(), object(), object()]
    opened = []

    def session_factory():
        session = sessions[len(opened)]
        opened.append(session)
        return _SessionContext(session)

    list_candidates = AsyncMock(return_value=[11, 12])
    retry = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(
        "app.services.call_finalization_retry_service.AsyncSessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        "app.services.call_finalization_retry_service."
        "CallRecordRepository.list_finalization_retry_candidate_ids",
        list_candidates,
    )
    monkeypatch.setattr(
        "app.services.call_finalization_retry_service."
        "CallRecordService.retry_finalization",
        retry,
    )

    stats = await CallFinalizationRetryService.run_tick()

    assert stats == {"checked": 2, "completed": 1, "failed": 1}
    assert len(opened) == 3
    assert list_candidates.await_args.args[0] is opened[0]
    assert retry.await_args_list[0].args[0] is opened[1]
    assert retry.await_args_list[1].args[0] is opened[2]
    assert retry.await_args_list[0].kwargs["call_record_id"] == 11
    assert retry.await_args_list[1].kwargs["call_record_id"] == 12
