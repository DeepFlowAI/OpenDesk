"""Wrap-up deadline storage, expiry scan, and server-side timeout sweep."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.services import call_wrapup_service as wrapup_module
from app.services import call_wrapup_timeout_service as sweep_module
from app.services.call_wrapup_service import apply_post_call_agent_status
from app.services.call_wrapup_timeout_service import CallWrapupTimeoutService
from app.services.cc_agent_resource_service import CcAgentResourceService


def _fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@asynccontextmanager
async def _fake_session():
    yield AsyncMock()


@pytest.mark.asyncio
async def test_mark_after_call_work_stores_deadline():
    fake = _fake_redis()
    before = datetime.now(timezone.utc).timestamp()
    snap = await CcAgentResourceService.mark_after_call_work(
        fake, 1, 42, call_id="call-1", wrap_up_seconds=30
    )
    assert snap["resource_state"] == "after_call_work"
    assert snap["wrap_up_call_id"] == "call-1"
    assert before + 29 <= snap["wrap_up_until_epoch"] <= before + 31


@pytest.mark.asyncio
async def test_mark_after_call_work_without_seconds_has_no_deadline():
    fake = _fake_redis()
    snap = await CcAgentResourceService.mark_after_call_work(
        fake, 1, 42, call_id="call-1"
    )
    assert snap["resource_state"] == "after_call_work"
    assert snap["wrap_up_until_epoch"] is None
    assert snap["wrap_up_until"] is None


@pytest.mark.asyncio
async def test_status_transition_clears_wrapup_fields():
    fake = _fake_redis()
    await CcAgentResourceService.mark_after_call_work(
        fake, 1, 42, call_id="call-1", wrap_up_seconds=30
    )
    snap = await CcAgentResourceService.set_visible_status(fake, 1, 42, "ready")
    assert snap["resource_state"] == "idle"
    assert snap["wrap_up_until_epoch"] is None
    assert snap["wrap_up_call_id"] is None


@pytest.mark.asyncio
async def test_list_expired_wrapups_returns_only_due_agents():
    fake = _fake_redis()
    # Expired: deadline in the past.
    await CcAgentResourceService.mark_after_call_work(
        fake, 1, 42, call_id="call-old", wrap_up_seconds=1
    )
    key = CcAgentResourceService.key(1, 42)
    await fake.hset(key, "wrap_up_until", "1")
    # Not yet due.
    await CcAgentResourceService.mark_after_call_work(
        fake, 1, 43, call_id="call-new", wrap_up_seconds=300
    )
    # In wrap-up but without a deadline (legacy rows) — never swept.
    await CcAgentResourceService.mark_after_call_work(fake, 1, 44, call_id="call-x")
    # In call — not wrap-up.
    await CcAgentResourceService.reserve_inbound(
        fake, 1, 45, call_id="call-r", offer_id="o1", queue_id=None
    )

    expired = await CcAgentResourceService.list_expired_wrapups(fake)
    assert expired == [(1, 42, "call-old")]


@pytest.mark.asyncio
async def test_apply_post_call_agent_status_zero_goes_ready(monkeypatch):
    fake = _fake_redis()
    emit = AsyncMock(return_value=True)
    monkeypatch.setattr(wrapup_module, "emit_to_agent", emit)
    result = await apply_post_call_agent_status(
        None, fake, 1, 42, call_id="call-1", reason="call_hangup", wrapup_seconds=0
    )
    assert result == "ready"
    snap = await CcAgentResourceService.get_snapshot(fake, 1, 42)
    assert snap["visible_status"] == "ready"
    assert snap["resource_state"] == "idle"
    # No wrap-up entered → no countdown push.
    emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_post_call_agent_status_positive_marks_acw_with_deadline(
    monkeypatch,
):
    fake = _fake_redis()
    emit = AsyncMock(return_value=True)
    monkeypatch.setattr(wrapup_module, "emit_to_agent", emit)
    result = await apply_post_call_agent_status(
        None, fake, 1, 42, call_id="call-1", reason="call_hangup", wrapup_seconds=45
    )
    assert result == "after_call_work"
    snap = await CcAgentResourceService.get_snapshot(fake, 1, 42)
    assert snap["resource_state"] == "after_call_work"
    assert snap["wrap_up_until_epoch"] is not None
    assert snap["wrap_up_call_id"] == "call-1"
    # Entering wrap-up pushes the deadline so clients can count down
    # immediately without waiting for the next status poll.
    emit.assert_awaited_once()
    kwargs = emit.await_args.kwargs
    assert kwargs["tenant_id"] == 1
    assert kwargs["employee_id"] == 42
    assert kwargs["method"] == "cc.wrap_up_started"
    assert kwargs["payload"]["call_id"] == "call-1"
    pushed = datetime.fromisoformat(kwargs["payload"]["wrap_up_until"])
    assert abs(pushed.timestamp() - snap["wrap_up_until_epoch"]) < 1


@pytest.mark.asyncio
async def test_process_expired_flips_ready_syncs_pg_and_notifies(monkeypatch):
    fake = _fake_redis()
    await CcAgentResourceService.mark_after_call_work(
        fake, 1, 42, call_id="call-1", wrap_up_seconds=1
    )
    await fake.hset(CcAgentResourceService.key(1, 42), "wrap_up_until", "1")
    # A second agent still within their wrap-up window must be left alone.
    await CcAgentResourceService.mark_after_call_work(
        fake, 1, 43, call_id="call-2", wrap_up_seconds=300
    )

    sync_pg = AsyncMock()
    emit = AsyncMock(return_value=True)
    monkeypatch.setattr(sweep_module, "AsyncSessionLocal", _fake_session)
    monkeypatch.setattr(
        sweep_module.CcAgentStatusService, "sync_pg_status", sync_pg
    )
    monkeypatch.setattr(sweep_module, "emit_to_agent", emit)

    processed = await CallWrapupTimeoutService.process_expired(fake)
    assert processed == 1

    snap = await CcAgentResourceService.get_snapshot(fake, 1, 42)
    assert snap["visible_status"] == "ready"
    assert snap["wrap_up_until_epoch"] is None
    sync_pg.assert_awaited_once()
    args = sync_pg.await_args.args
    assert args[1:4] == (1, 42, "ready")
    assert sync_pg.await_args.kwargs["reason"] == "wrap_up_timeout"
    emit.assert_awaited_once()
    assert emit.await_args.kwargs["tenant_id"] == 1
    assert emit.await_args.kwargs["employee_id"] == 42
    assert emit.await_args.kwargs["method"] == "cc.wrap_up_timeout"
    assert emit.await_args.kwargs["payload"] == {"call_id": "call-1"}

    # The agent still inside their window is untouched.
    snap2 = await CcAgentResourceService.get_snapshot(fake, 1, 43)
    assert snap2["resource_state"] == "after_call_work"


@pytest.mark.asyncio
async def test_process_expired_skips_agent_reserved_by_new_call(monkeypatch):
    fake = _fake_redis()
    # Agent shows an expired wrap-up in the scan, but a new call reserved them
    # before the flip — the sweep must not clobber the active resource.
    await CcAgentResourceService.reserve_inbound(
        fake, 1, 42, call_id="call-new", offer_id="o1", queue_id=None
    )
    monkeypatch.setattr(
        CcAgentResourceService,
        "list_expired_wrapups",
        AsyncMock(return_value=[(1, 42, "call-old")]),
    )
    sync_pg = AsyncMock()
    emit = AsyncMock(return_value=True)
    monkeypatch.setattr(sweep_module, "AsyncSessionLocal", _fake_session)
    monkeypatch.setattr(
        sweep_module.CcAgentStatusService, "sync_pg_status", sync_pg
    )
    monkeypatch.setattr(sweep_module, "emit_to_agent", emit)

    processed = await CallWrapupTimeoutService.process_expired(fake)
    assert processed == 0
    sync_pg.assert_not_awaited()
    emit.assert_not_awaited()
    snap = await CcAgentResourceService.get_snapshot(fake, 1, 42)
    assert snap["resource_state"] == "reserved"
