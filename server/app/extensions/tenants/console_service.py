"""Tenant console login — issues console tokens for the built-in /tenant UI."""
import logging

from app.configs.settings import settings
from app.core.exceptions import RateLimitedError, ServiceUnavailableError, UnauthorizedError
from app.core.tenant_platform_auth import (
    create_tenant_console_token,
    tenant_console_configured,
    tenant_console_credentials_match,
)

from .schemas import TenantConsoleLoginRequest, TenantConsoleTokenResponse

logger = logging.getLogger(__name__)

LOGIN_FAIL_LIMIT = 10
# Client IPs come from X-Forwarded-For and can be spoofed, so the single console
# account also gets a counter that does not depend on the IP.
LOGIN_GLOBAL_FAIL_LIMIT = 30
LOGIN_FAIL_WINDOW_SECONDS = 900
_FAIL_KEY_PREFIX = "tenant_console:login_fail:"
_GLOBAL_FAIL_KEY = "tenant_console:login_fail_global"


def _redis():
    """Return the Redis client, or None when Redis is not initialized."""
    from app.db.redis import redis_client

    try:
        return redis_client.client
    except RuntimeError:
        return None


async def _read_counter(key: str) -> int:
    redis = _redis()
    if redis is None:
        return 0
    try:
        value = await redis.get(key)
    except Exception:  # noqa: BLE001
        logger.warning("tenant console login: failed to read attempt counter", exc_info=True)
        return 0
    return int(value or 0)


async def _is_locked(client_ip: str) -> bool:
    if await _read_counter(f"{_FAIL_KEY_PREFIX}{client_ip}") >= LOGIN_FAIL_LIMIT:
        return True
    return await _read_counter(_GLOBAL_FAIL_KEY) >= LOGIN_GLOBAL_FAIL_LIMIT


async def _record_failure(client_ip: str) -> None:
    redis = _redis()
    if redis is None:
        return
    for key in (f"{_FAIL_KEY_PREFIX}{client_ip}", _GLOBAL_FAIL_KEY):
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, LOGIN_FAIL_WINDOW_SECONDS)
        except Exception:  # noqa: BLE001
            logger.warning("tenant console login: failed to record attempt", exc_info=True)


async def _clear_failures(client_ip: str) -> None:
    redis = _redis()
    if redis is None:
        return
    try:
        await redis.delete(f"{_FAIL_KEY_PREFIX}{client_ip}", _GLOBAL_FAIL_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("tenant console login: failed to clear attempts", exc_info=True)


class TenantConsoleAuthService:

    @staticmethod
    async def login(data: TenantConsoleLoginRequest, client_ip: str) -> TenantConsoleTokenResponse:
        if not tenant_console_configured():
            raise ServiceUnavailableError(
                "Tenant console is disabled: set TENANT_CONSOLE_PASSWORD",
                code="TENANT_CONSOLE_NOT_CONFIGURED",
            )
        if await _is_locked(client_ip):
            raise RateLimitedError("Too many failed login attempts, try again later")
        if not tenant_console_credentials_match(data.username, data.password):
            await _record_failure(client_ip)
            logger.warning("tenant console login failed: ip=%s", client_ip)
            raise UnauthorizedError("Invalid username or password")
        await _clear_failures(client_ip)
        token, expires_in = create_tenant_console_token()
        logger.info("tenant console login succeeded: ip=%s", client_ip)
        return TenantConsoleTokenResponse(
            access_token=token,
            expires_in=expires_in,
            username=settings.TENANT_CONSOLE_USERNAME.strip(),
        )
