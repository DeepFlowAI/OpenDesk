"""Redis-backed failed-attempt counters for credential endpoints.

Every helper fails open: when Redis is not configured or errors out, callers
are never blocked, so a Redis outage cannot lock everyone out of login.
"""
import logging

logger = logging.getLogger(__name__)


def _redis():
    """Return the Redis client, or None when Redis is not initialized."""
    from app.db.redis import redis_client

    try:
        return redis_client.client
    except RuntimeError:
        return None


async def failure_count(key: str) -> int:
    redis = _redis()
    if redis is None:
        return 0
    try:
        value = await redis.get(key)
    except Exception:  # noqa: BLE001
        logger.warning("login throttle: failed to read counter key=%s", key, exc_info=True)
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def record_failure(key: str, window_seconds: int) -> None:
    redis = _redis()
    if redis is None:
        return
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
    except Exception:  # noqa: BLE001
        logger.warning("login throttle: failed to record failure key=%s", key, exc_info=True)


async def clear_failures(*keys: str) -> None:
    redis = _redis()
    if redis is None or not keys:
        return
    try:
        await redis.delete(*keys)
    except Exception:  # noqa: BLE001
        logger.warning("login throttle: failed to clear counters keys=%s", keys, exc_info=True)
