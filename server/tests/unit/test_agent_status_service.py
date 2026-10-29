"""
Unit tests for agent status persistence.
"""
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.enums import AgentOnlineStatus
from app.services.agent_status_service import AgentStatusService


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_mark_connected_defaults_new_agent_to_offline(fake_redis):
    await AgentStatusService.mark_connected(fake_redis, tenant_id=7, user_id=42, sid="sid-new")

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.OFFLINE.value


@pytest.mark.asyncio
async def test_mark_connected_preserves_manual_offline_status(fake_redis):
    await AgentStatusService.set_status(
        fake_redis,
        tenant_id=7,
        user_id=42,
        status=AgentOnlineStatus.OFFLINE.value,
    )

    await AgentStatusService.mark_connected(fake_redis, tenant_id=7, user_id=42, sid="sid-1")

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.OFFLINE.value


@pytest.mark.asyncio
async def test_set_status_offline_preserves_current_count(fake_redis, monkeypatch):
    # set_count notifies via AgentRealtimeService, which opens a real DB session
    # to read max_concurrent — incidental to this Redis-state assertion.
    monkeypatch.setattr(AgentStatusService, "_notify_stats_changed", AsyncMock())

    await AgentStatusService.set_count(fake_redis, tenant_id=7, user_id=42, count=2)

    await AgentStatusService.set_status(
        fake_redis,
        tenant_id=7,
        user_id=42,
        status=AgentOnlineStatus.OFFLINE.value,
    )

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.OFFLINE.value
    assert status["current_count"] == 2


@pytest.mark.asyncio
async def test_set_status_refreshes_current_count_when_provided(fake_redis, monkeypatch):
    notify = AsyncMock()
    monkeypatch.setattr(AgentStatusService, "_notify_stats_changed", notify)

    await AgentStatusService.set_status(
        fake_redis,
        tenant_id=7,
        user_id=42,
        status=AgentOnlineStatus.ONLINE.value,
        current_count=3,
    )

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.ONLINE.value
    assert status["current_count"] == 3
    notify.assert_awaited_once_with(fake_redis, 7, 42)


@pytest.mark.asyncio
async def test_mark_connected_preserves_existing_status_without_desired_status(fake_redis):
    await fake_redis.hset("agent:status:7:42", mapping={"status": AgentOnlineStatus.OFFLINE.value})

    await AgentStatusService.mark_connected(fake_redis, tenant_id=7, user_id=42, sid="sid-legacy")

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.OFFLINE.value


@pytest.mark.asyncio
async def test_mark_connected_restores_desired_status_after_transient_disconnect(fake_redis):
    await AgentStatusService.set_status(
        fake_redis,
        tenant_id=7,
        user_id=42,
        status=AgentOnlineStatus.BUSY.value,
    )
    await fake_redis.hset("agent:status:7:42", mapping={"status": AgentOnlineStatus.OFFLINE.value})

    await AgentStatusService.mark_connected(fake_redis, tenant_id=7, user_id=42, sid="sid-2")

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.BUSY.value


@pytest.mark.asyncio
async def test_mark_connected_treats_expired_pending_disconnect_as_offline(fake_redis):
    await fake_redis.hset(
        "agent:status:7:42",
        mapping={
            "status": AgentOnlineStatus.ONLINE.value,
            "desired_status": AgentOnlineStatus.ONLINE.value,
            "pending_offline_until": "1",
        },
    )

    await AgentStatusService.mark_connected(fake_redis, tenant_id=7, user_id=42, sid="sid-late")

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.OFFLINE.value


@pytest.mark.asyncio
async def test_finalized_disconnect_resets_desired_status_to_offline(fake_redis, monkeypatch):
    key = "agent:status:7:42"
    await fake_redis.hset(
        key,
        mapping={
            "connection_sid": "sid-online",
            "pending_offline_until": "1",
            "status": AgentOnlineStatus.ONLINE.value,
            "desired_status": AgentOnlineStatus.ONLINE.value,
            "current_count": 3,
        },
    )

    async def fake_eval(
        _script,
        _numkeys,
        key_arg,
        connection_sid_field,
        sid,
        pending_offline_field,
        offline_status,
        desired_status_field,
    ):
        assert desired_status_field == "desired_status"
        if (
            await fake_redis.hget(key_arg, connection_sid_field) == sid
            and await fake_redis.hexists(key_arg, pending_offline_field)
        ):
            await fake_redis.hdel(key_arg, connection_sid_field, pending_offline_field)
            await fake_redis.hset(key_arg, "status", offline_status)
            await fake_redis.hset(key_arg, desired_status_field, offline_status)
            return 1
        return 0

    monkeypatch.setattr(fake_redis, "eval", fake_eval)
    sync_db = AsyncMock()
    monkeypatch.setattr(AgentStatusService, "_sync_cc_db_status_best_effort", sync_db)

    await AgentStatusService.finalize_disconnect_if_stale(
        fake_redis,
        tenant_id=7,
        user_id=42,
        sid="sid-online",
    )

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.OFFLINE.value
    assert await fake_redis.hget(key, "desired_status") == AgentOnlineStatus.OFFLINE.value
    assert status["current_count"] == 3
    sync_db.assert_awaited_once_with(
        7, 42, AgentOnlineStatus.OFFLINE.value, reason="disconnect_finalize"
    )


@pytest.mark.asyncio
async def test_finalize_disconnect_syncs_cc_db_offline(fake_redis, monkeypatch):
    key = "agent:status:7:42"
    await fake_redis.hset(
        key,
        mapping={
            "connection_sid": "sid-online",
            "pending_offline_until": "1",
            "status": AgentOnlineStatus.ONLINE.value,
            "desired_status": AgentOnlineStatus.ONLINE.value,
        },
    )

    async def fake_eval(
        _script,
        _numkeys,
        key_arg,
        connection_sid_field,
        sid,
        pending_offline_field,
        offline_status,
        desired_status_field,
    ):
        if (
            await fake_redis.hget(key_arg, connection_sid_field) == sid
            and await fake_redis.hexists(key_arg, pending_offline_field)
        ):
            await fake_redis.hdel(key_arg, connection_sid_field, pending_offline_field)
            await fake_redis.hset(key_arg, "status", offline_status)
            await fake_redis.hset(key_arg, desired_status_field, offline_status)
            return 1
        return 0

    monkeypatch.setattr(fake_redis, "eval", fake_eval)
    upsert = AsyncMock()
    monkeypatch.setattr(
        "app.repositories.agent_status_repository.AgentStatusRepository.upsert",
        upsert,
    )

    class _SessionCM:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(
        "app.db.session.AsyncSessionLocal",
        lambda: _SessionCM(),
    )

    changed = await AgentStatusService.finalize_disconnect_if_stale(
        fake_redis, tenant_id=7, user_id=42, sid="sid-online"
    )

    assert changed is True
    upsert.assert_awaited_once()
    args = upsert.await_args.args
    assert args[1:] == (7, 42, "offline", "disconnect_finalize")


@pytest.mark.asyncio
async def test_finalize_stale_disconnect_does_not_touch_cc_db(fake_redis, monkeypatch):
    # Newer connection already replaced the sid — Lua returns 0.
    await fake_redis.hset(
        "agent:status:7:42",
        mapping={
            "connection_sid": "sid-newer",
            "pending_offline_until": "1",
            "status": AgentOnlineStatus.ONLINE.value,
            "desired_status": AgentOnlineStatus.ONLINE.value,
        },
    )

    async def fake_eval(*_args):
        return 0

    monkeypatch.setattr(fake_redis, "eval", fake_eval)
    sync_db = AsyncMock()
    monkeypatch.setattr(AgentStatusService, "_sync_cc_db_status_best_effort", sync_db)

    changed = await AgentStatusService.finalize_disconnect_if_stale(
        fake_redis, tenant_id=7, user_id=42, sid="sid-old"
    )

    assert changed is False
    sync_db.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_connected_restores_cc_db_from_resource_visible_status(
    fake_redis, monkeypatch
):
    """Within-grace reconnect: chat desired_status restores Redis; PG follows
    call-center resource visible_status (ready/busy/...), not chat enums."""
    await AgentStatusService.set_status(
        fake_redis,
        tenant_id=7,
        user_id=42,
        status=AgentOnlineStatus.BUSY.value,
    )
    await fake_redis.hset(
        "agent:status:7:42",
        mapping={
            "status": AgentOnlineStatus.OFFLINE.value,
            "desired_status": AgentOnlineStatus.BUSY.value,
        },
    )

    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.get_snapshot",
        AsyncMock(
            return_value={
                "visible_status": "ready",
                "resource_state": "idle",
            }
        ),
    )
    sync_db = AsyncMock()
    monkeypatch.setattr(AgentStatusService, "_sync_cc_db_status_best_effort", sync_db)

    await AgentStatusService.mark_connected(fake_redis, tenant_id=7, user_id=42, sid="sid-2")

    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.BUSY.value
    sync_db.assert_awaited_once_with(7, 42, "ready", reason="reconnect_restore")


@pytest.mark.asyncio
async def test_mark_connected_offline_desired_does_not_restore_cc_db(
    fake_redis, monkeypatch
):
    await fake_redis.hset(
        "agent:status:7:42",
        mapping={
            "status": AgentOnlineStatus.OFFLINE.value,
            "desired_status": AgentOnlineStatus.OFFLINE.value,
        },
    )
    sync_db = AsyncMock()
    monkeypatch.setattr(AgentStatusService, "_sync_cc_db_status_best_effort", sync_db)
    monkeypatch.setattr(
        "app.services.cc_agent_resource_service.CcAgentResourceService.get_snapshot",
        AsyncMock(return_value={"visible_status": "ready", "resource_state": "idle"}),
    )

    await AgentStatusService.mark_connected(
        fake_redis, tenant_id=7, user_id=42, sid="sid-offline"
    )

    sync_db.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_db_sync_failure_does_not_raise(fake_redis, monkeypatch):
    key = "agent:status:7:42"
    await fake_redis.hset(
        key,
        mapping={
            "connection_sid": "sid-online",
            "pending_offline_until": "1",
            "status": AgentOnlineStatus.ONLINE.value,
            "desired_status": AgentOnlineStatus.ONLINE.value,
        },
    )

    async def fake_eval(
        _script,
        _numkeys,
        key_arg,
        connection_sid_field,
        sid,
        pending_offline_field,
        offline_status,
        desired_status_field,
    ):
        await fake_redis.hdel(key_arg, connection_sid_field, pending_offline_field)
        await fake_redis.hset(key_arg, "status", offline_status)
        await fake_redis.hset(key_arg, desired_status_field, offline_status)
        return 1

    monkeypatch.setattr(fake_redis, "eval", fake_eval)
    monkeypatch.setattr(
        "app.repositories.agent_status_repository.AgentStatusRepository.upsert",
        AsyncMock(side_effect=RuntimeError("db down")),
    )

    class _SessionCM:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr("app.db.session.AsyncSessionLocal", lambda: _SessionCM())

    changed = await AgentStatusService.finalize_disconnect_if_stale(
        fake_redis, tenant_id=7, user_id=42, sid="sid-online"
    )
    assert changed is True
    status = await AgentStatusService.get_status(fake_redis, tenant_id=7, user_id=42)
    assert status["status"] == AgentOnlineStatus.OFFLINE.value


@pytest.mark.asyncio
async def test_get_statuses_bulk_empty_list_returns_empty_dict(fake_redis):
    assert await AgentStatusService.get_statuses_bulk(fake_redis, tenant_id=1, users=[]) == {}


@pytest.mark.asyncio
async def test_get_statuses_bulk_returns_one_entry_per_user(fake_redis):
    await AgentStatusService.set_status(fake_redis, tenant_id=1, user_id=10, status=AgentOnlineStatus.ONLINE.value)
    await AgentStatusService.set_status(fake_redis, tenant_id=1, user_id=11, status=AgentOnlineStatus.BUSY.value)
    # user 12 never set — should fall through to offline default

    result = await AgentStatusService.get_statuses_bulk(
        fake_redis,
        tenant_id=1,
        users=[(10, 5), (11, 3), (12, 5)],
    )
    assert set(result.keys()) == {10, 11, 12}
    assert result[10]["status"] == AgentOnlineStatus.ONLINE.value
    assert result[10]["max_concurrent"] == 5
    assert result[11]["status"] == AgentOnlineStatus.BUSY.value
    assert result[11]["max_concurrent"] == 3
    assert result[12]["status"] == AgentOnlineStatus.OFFLINE.value
    assert result[12]["current_count"] == 0


@pytest.mark.asyncio
async def test_get_statuses_bulk_matches_individual_get_status(fake_redis):
    """Bulk method must produce the same payload shape as ``get_status``."""
    await AgentStatusService.set_status(fake_redis, tenant_id=2, user_id=99, status=AgentOnlineStatus.ONLINE.value)
    await AgentStatusService.set_count(fake_redis, tenant_id=2, user_id=99, count=3)

    single = await AgentStatusService.get_status(fake_redis, tenant_id=2, user_id=99, max_concurrent=8)
    bulk = await AgentStatusService.get_statuses_bulk(fake_redis, tenant_id=2, users=[(99, 8)])
    assert bulk[99] == single


@pytest.mark.asyncio
async def test_trigger_queue_backfill_delegates_to_assign(fake_redis, monkeypatch):
    import app.libs.realtime as realtime
    from app.socketio import chat_handlers

    rt = object()
    backfill = AsyncMock()
    monkeypatch.setattr(realtime, "get_realtime_transport", lambda: rt)
    monkeypatch.setattr(chat_handlers, "_assign_queued_conversations", backfill)

    await AgentStatusService.trigger_queue_backfill(fake_redis, tenant_id=1, user_id=10)

    backfill.assert_awaited_once_with(rt, fake_redis, 1, 10)


@pytest.mark.asyncio
async def test_trigger_queue_backfill_swallows_errors(fake_redis, monkeypatch):
    import app.libs.realtime as realtime
    from app.socketio import chat_handlers

    monkeypatch.setattr(realtime, "get_realtime_transport", lambda: object())
    monkeypatch.setattr(
        chat_handlers,
        "_assign_queued_conversations",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    # Best-effort trigger: a failed backfill must not propagate to the caller.
    await AgentStatusService.trigger_queue_backfill(fake_redis, tenant_id=1, user_id=10)


@pytest.mark.asyncio
async def test_get_statuses_bulk_self_heals_expired_pending_offline(fake_redis):
    # Manually craft a hash with a past-due pending_offline_until marker;
    # bulk should surface offline even though status field still says online.
    await fake_redis.hset(
        "agent:status:5:77",
        mapping={
            "status": AgentOnlineStatus.ONLINE.value,
            "pending_offline_until": "1",  # epoch=1 is definitely in the past
        },
    )
    result = await AgentStatusService.get_statuses_bulk(fake_redis, tenant_id=5, users=[(77, 10)])
    assert result[77]["status"] == AgentOnlineStatus.OFFLINE.value
