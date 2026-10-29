"""A PG after_call_work left behind after Redis already ended wrap-up heals on read."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.services import cc_agent_status_service as status_mod
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService


def _install(monkeypatch, pg_status: str):
    row = SimpleNamespace(
        employee_id=42, status=pg_status, reason=None,
        status_changed_at=None, updated_at=None,
    )
    monkeypatch.setattr(
        status_mod.AgentStatusRepository, "get_for_employee", AsyncMock(return_value=row)
    )

    async def _reconcile(_db, _r, _tenant_id, _employee_id, *, snapshot, chosen_status):
        return snapshot

    monkeypatch.setattr(CcAgentStatusService, "reconcile_agent", staticmethod(_reconcile))
    monkeypatch.setattr(status_mod, "_consult_fields", AsyncMock(return_value={}))
    monkeypatch.setattr(
        status_mod.CallRecordRepository, "get_by_call_id", AsyncMock(return_value=None)
    )
    writes: list[str] = []

    async def _sync_pg(_db, _tenant_id, _employee_id, status, reason=None):
        writes.append(status)
        return {}

    monkeypatch.setattr(CcAgentStatusService, "sync_pg_status", staticmethod(_sync_pg))
    return writes


@pytest.mark.asyncio
async def test_stale_pg_after_call_work_shows_redis_status_and_heals(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await CcAgentResourceService.mark_after_call_work(fake, 1, 42, call_id="c1", wrap_up_seconds=30)
    await CcAgentResourceService.set_visible_status(fake, 1, 42, "ready")
    writes = _install(monkeypatch, "after_call_work")

    result = await CcAgentStatusService.get_for_employee(AsyncMock(), 1, 42, fake)

    assert result["status"] == "ready"
    assert writes == ["ready"]


@pytest.mark.asyncio
async def test_live_after_call_work_is_kept(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await CcAgentResourceService.mark_after_call_work(fake, 1, 42, call_id="c1", wrap_up_seconds=30)
    writes = _install(monkeypatch, "after_call_work")

    result = await CcAgentStatusService.get_for_employee(AsyncMock(), 1, 42, fake)

    assert result["status"] == "after_call_work"
    assert writes == []
