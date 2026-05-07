import pytest_asyncio
import fakeredis.aioredis
from httpx import AsyncClient, ASGITransport
from app.main import _fastapi_app
from app.db.session import engine
from app.db.deps import get_redis


_fake_redis = None


async def _get_fake_redis():
    global _fake_redis
    if _fake_redis is None:
        _fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return _fake_redis


@pytest_asyncio.fixture
async def client():
    _fastapi_app.dependency_overrides[get_redis] = _get_fake_redis
    transport = ASGITransport(app=_fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    _fastapi_app.dependency_overrides.pop(get_redis, None)
    await engine.dispose()
