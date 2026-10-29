"""ACW writes follow finalization's parent-before-child lock order."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.call_agent_fact_repository import CallAgentFactRepository
from app.repositories.call_record_repository import CallRecordRepository
from app.services.call_agent_fact_service import CallAgentFactService


@pytest.mark.asyncio
async def test_acw_locks_parent_before_reading_or_writing_child_facts(monkeypatch):
    row = SimpleNamespace(id=12)
    steps = []

    async def lock(*args):
        steps.append('parent_lock')
        return row

    async def segment(*args):
        steps.append('segment')
        return 8

    async def snapshot(*args):
        steps.append('snapshot')
        return 'Agent'

    async def write(*args):
        steps.append('write')

    monkeypatch.setattr(CallRecordRepository, 'get_by_call_id', AsyncMock(return_value=row))
    monkeypatch.setattr(CallRecordRepository, 'lock_by_id', lock)
    monkeypatch.setattr(CallAgentFactRepository, 'latest_segment_id', segment)
    monkeypatch.setattr('app.services.call_agent_fact_service._agent_snapshot', snapshot)
    monkeypatch.setattr(CallAgentFactRepository, 'start_after_call_work', write)
    assert await CallAgentFactService.start_after_call_work(
        AsyncMock(), tenant_id=1, call_id='call-1', agent_id=4,
    )
    assert steps == ['parent_lock', 'segment', 'snapshot', 'write']


@pytest.mark.asyncio
async def test_duplicate_acw_start_cannot_reset_start_or_reopen_closed_fact():
    db = AsyncMock()
    await CallAgentFactRepository.start_after_call_work(db, {
        'tenant_id': 1, 'call_record_id': 12, 'agent_id': 4,
        'started_at': datetime.now(timezone.utc), 'result_reliable': False,
    })
    sql = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert 'ON CONFLICT ON CONSTRAINT uq_call_agent_acw_call_agent DO NOTHING' in sql
