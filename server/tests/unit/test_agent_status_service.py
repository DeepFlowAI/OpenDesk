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
