import pytest

from app.services.call_center.nodes import AssignQueueExecutor, ExecutionContext


class _MissingRedisClient:
    @property
    def client(self):
        raise RuntimeError("Redis not initialized")


@pytest.mark.asyncio
async def test_assign_queue_requires_redis(monkeypatch):
    monkeypatch.setattr("app.db.redis.redis_client", _MissingRedisClient())
    ctx = ExecutionContext(
        call_id="call-1",
        tenant_id=7,
        variables={},
        telephony=object(),
    )

    with pytest.raises(RuntimeError, match="requires Redis"):
        await AssignQueueExecutor().execute(
            ctx,
            {
                "id": "assign-queue-1",
                "type": "assign_queue",
                "data": {"employee_group_id": 9, "timeout_seconds": 30},
            },
        )
