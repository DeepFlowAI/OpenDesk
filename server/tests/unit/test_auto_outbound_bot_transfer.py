"""Bot/IVR auto-outbound calls bridged to an agent are treated as agent-handled."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.auto_outbound_repository import AutoOutboundRepository
from app.services.call_wrapup_service import resolve_effective_wrapup_seconds


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_wrapup_seconds_lookup_includes_records_with_agent():
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=45)

    seconds = await resolve_effective_wrapup_seconds(db, 1, "call-1")

    assert seconds == 45
    sql = _sql(db.scalar.await_args.args[0])
    assert "auto_outbound_call_records.reception_type = " in sql
    assert "auto_outbound_call_records.agent_id IS NOT NULL" in sql


@pytest.mark.asyncio
async def test_task_stats_counts_bot_transfers():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[[], []])

    await AutoOutboundRepository.task_stats(db, 1, [1])

    sql = _sql(db.execute.await_args_list[1].args[0])
    transfer_filter = sql.split("AS transfer_count")[0]
    # The transferred marker must not be gated on reception_type = 'agent'.
    assert ") OR (auto_outbound_call_records.reception_result ->> " in transfer_filter
