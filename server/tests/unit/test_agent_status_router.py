"""
Unit tests for the agent status REST router backfill behaviour.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.enums import AgentOnlineStatus
from app.routers.v1 import conversations as conversations_router
from app.schemas.agent_status import AgentStatusUpdate


async def _invoke_update_status(monkeypatch, status: str) -> SimpleNamespace:
    set_status = AsyncMock()
    backfill = AsyncMock()
    count_active = AsyncMock(return_value=2)
    get_status = AsyncMock(return_value={
        "user_id": 10,
        "status": status,
        "current_count": 2,
        "max_concurrent": 5,
    })
    monkeypatch.setattr(conversations_router.AgentStatusService, "set_status", set_status)
    monkeypatch.setattr(conversations_router.AgentStatusService, "trigger_queue_backfill", backfill)
    monkeypatch.setattr(conversations_router.AgentStatusService, "get_status", get_status)

    from app.repositories.employee_repository import EmployeeRepository

    monkeypatch.setattr(
        EmployeeRepository,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(max_concurrent=5)),
    )

    from app.repositories.conversation_repository import ConversationRepository

    monkeypatch.setattr(ConversationRepository, "count_active_by_agent", count_active)
    r = SimpleNamespace()
    db = SimpleNamespace()
    await conversations_router.update_agent_status(
        AgentStatusUpdate(status=status),
        r=r,
        db=db,
        user={"tenant_id": 1, "user_id": 10},
    )
    return SimpleNamespace(
        backfill=backfill,
        count_active=count_active,
        db=db,
        r=r,
        set_status=set_status,
    )


@pytest.mark.asyncio
async def test_update_status_online_triggers_backfill(monkeypatch):
    ctx = await _invoke_update_status(monkeypatch, AgentOnlineStatus.ONLINE.value)
    ctx.count_active.assert_awaited_once_with(ctx.db, 1, 10)
    ctx.set_status.assert_awaited_once_with(
        ctx.r,
        1,
        10,
        AgentOnlineStatus.ONLINE.value,
        current_count=2,
    )
    ctx.backfill.assert_awaited_once()
    # Backfill receives the Redis client plus the agent's tenant and user ids.
    assert ctx.backfill.await_args.args[1:] == (1, 10)


@pytest.mark.asyncio
async def test_update_status_busy_does_not_trigger_backfill(monkeypatch):
    ctx = await _invoke_update_status(monkeypatch, AgentOnlineStatus.BUSY.value)
    ctx.set_status.assert_awaited_once_with(
        ctx.r,
        1,
        10,
        AgentOnlineStatus.BUSY.value,
        current_count=2,
    )
    ctx.backfill.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_status_offline_does_not_trigger_backfill(monkeypatch):
    ctx = await _invoke_update_status(monkeypatch, AgentOnlineStatus.OFFLINE.value)
    ctx.set_status.assert_awaited_once_with(
        ctx.r,
        1,
        10,
        AgentOnlineStatus.OFFLINE.value,
        current_count=2,
    )
    ctx.backfill.assert_not_awaited()
