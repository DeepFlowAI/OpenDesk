"""
Unit tests for agent status persistence.
"""
import fakeredis.aioredis
import pytest

from app.enums import AgentOnlineStatus
from app.services.agent_status_service import AgentStatusService


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


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
