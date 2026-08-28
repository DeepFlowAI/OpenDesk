from collections.abc import AsyncGenerator
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from app.core.exceptions import ForbiddenError
from app.db.session import AsyncSessionLocal
from app.schemas.permission import EffectivePrincipal
from app.services.permission_service import PermissionService


_EMBEDDED_CALL_ALLOWED_METHODS_BY_PATH: dict[str, frozenset[str]] = {
    "/api/v1/call-center/agent-status/me": frozenset({"GET", "PUT"}),
    "/api/v1/call-center/agents/consultable": frozenset({"GET"}),
    "/api/v1/call-center/transfer-queues": frozenset({"GET"}),
    "/api/v1/call-center/agents/me/devices": frozenset({"GET"}),
    "/api/v1/call-center/agents/me/current-device": frozenset({"GET", "PUT"}),
    "/api/v1/call-center/agents/me/outbound-numbers": frozenset({"GET"}),
    "/api/v1/call-center/agents/me/webrtc-session": frozenset(
        {"GET", "POST", "DELETE"}
    ),
    "/api/v1/call-center/agents/me/webrtc/offer": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/webrtc/ice": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/dial": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/dial/cancel": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/dial-webrtc/offer": frozenset({"POST"}),
    "/api/v1/call-center/embed/commands/dial": frozenset({"POST"}),
    "/api/v1/call-center/embed/control/acquire": frozenset({"POST"}),
    "/api/v1/call-center/embed/control/heartbeat": frozenset({"POST"}),
    "/api/v1/call-center/embed/control/takeover": frozenset({"POST"}),
    "/api/v1/call-center/embed/control/release": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/satisfaction": frozenset({"GET"}),
    "/api/v1/call-center/agents/me/current-call/satisfaction/invite": frozenset(
        {"POST"}
    ),
    "/api/v1/call-center/agents/me/current-call/hangup": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/hold": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/unhold": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/dtmf": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/mute": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/transfer": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/consult": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/consult/end": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/conference/add": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/conference/merge": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/conference/remove": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/conference/leave": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/conference/end-all": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/media-reconnect": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/accept": frozenset({"POST"}),
    "/api/v1/call-center/agents/me/current-call/reject": frozenset({"POST"}),
}
_EMBEDDED_CALL_COMMAND_PATH_PREFIX = "/api/v1/call-center/embed/commands/"


def embedded_call_http_access_allowed(method: str, path: str) -> bool:
    """Return whether an embedded session may call one HTTP endpoint."""
    normalized_method = method.upper()
    exact_methods = _EMBEDDED_CALL_ALLOWED_METHODS_BY_PATH.get(path)
    if exact_methods is not None:
        return normalized_method in exact_methods
    if normalized_method != "GET" or not path.startswith(
        _EMBEDDED_CALL_COMMAND_PATH_PREFIX
    ):
        return False
    command_id = path.removeprefix(_EMBEDDED_CALL_COMMAND_PATH_PREFIX)
    return bool(command_id) and "/" not in command_id


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_redis() -> aioredis.Redis:
    from app.db.redis import redis_client
    return redis_client.client


async def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
) -> dict:
    """Extract user payload from JWT Bearer token.

    Normalizes the payload so all consumers can use ``user["user_id"]``
    and ``user["tenant_id"]`` regardless of the raw JWT claim names.
    """
    from app.core.security import decode_access_token
    from app.core.exceptions import UnauthorizedError

    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")
    token = authorization[7:]
    payload = decode_access_token(token)
    if not payload:
        raise UnauthorizedError("Invalid or expired token")

    # JWT stores user id in "sub" as a string — normalize to int "user_id"
    if "sub" in payload and "user_id" not in payload:
        payload["user_id"] = int(payload["sub"])

    # Ensure tenant_id is always the integer PK.
    # Old tokens may contain a string slug — force re-login in that case.
    if "tenant_id" in payload:
        try:
            payload["tenant_id"] = int(payload["tenant_id"])
        except (ValueError, TypeError):
            raise UnauthorizedError("Token contains invalid tenant_id, please re-login")

    is_embedded_call = payload.get("typ") == "embedded_call_session"
    if is_embedded_call and not embedded_call_http_access_allowed(
        request.method, request.url.path
    ):
        raise ForbiddenError("Embedded call session cannot access this endpoint")

    async with AsyncSessionLocal() as db:
        if is_embedded_call:
            from app.db.redis import redis_client
            from app.services.embedded_call_integration_service import (
                EmbeddedCallIntegrationService,
            )

            await EmbeddedCallIntegrationService.validate_session_payload(
                db, redis_client.client, payload
            )
        else:
            from app.services.employee_session_service import EmployeeSessionService

            await EmployeeSessionService.validate_payload(db, payload)

    return payload


async def get_optional_current_user(authorization: str | None = Header(None)) -> dict | None:
    """Best-effort JWT decode for optional auth (e.g. client telemetry)."""
    from app.core.security import decode_access_token

    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_access_token(authorization[7:])
    if not payload:
        return None
    if payload.get("typ") == "embedded_call_session":
        return None
    if "sub" in payload and "user_id" not in payload:
        try:
            payload["user_id"] = int(payload["sub"])
        except (ValueError, TypeError):
            return None
    if "tenant_id" in payload:
        try:
            payload["tenant_id"] = int(payload["tenant_id"])
        except (ValueError, TypeError):
            return None
    return payload


async def get_current_principal(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EffectivePrincipal:
    return await PermissionService.get_current_principal(db, current_user)


async def get_current_principal_short_session(
    current_user: dict = Depends(get_current_user),
) -> EffectivePrincipal:
    async with AsyncSessionLocal() as db:
        return await PermissionService.get_current_principal(db, current_user)


def require_permission(permission: str):
    async def dependency(
        principal: EffectivePrincipal = Depends(get_current_principal),
    ) -> EffectivePrincipal:
        if not principal.has_permission(permission):
            raise ForbiddenError("Permission denied")
        return principal

    return dependency


def require_permission_short_session(permission: str):
    async def dependency(
        principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    ) -> EffectivePrincipal:
        if not principal.has_permission(permission):
            raise ForbiddenError("Permission denied")
        return principal

    return dependency


async def require_active_call_controller(
    current_user: dict = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Require the active lease for embedded call mutations.

    Regular OpenDesk sessions retain their existing authorization path; the
    workspace also participates in the lease through its UI. Embedded sessions
    are always enforced server-side because an observer iframe must not be able
    to bypass its disabled controls with direct API requests.
    """
    if current_user.get("typ") == "embedded_call_session":
        from app.services.embedded_call_control_service import (
            EmbeddedCallControlService,
        )

        await EmbeddedCallControlService.assert_owner(redis, session=current_user)
    return current_user


def require_any_permission(permissions: list[str]):
    async def dependency(
        principal: EffectivePrincipal = Depends(get_current_principal),
    ) -> EffectivePrincipal:
        if not principal.has_any_permission(permissions):
            raise ForbiddenError("Permission denied")
        return principal

    return dependency


def require_all_permissions(permissions: list[str]):
    async def dependency(
        principal: EffectivePrincipal = Depends(get_current_principal),
    ) -> EffectivePrincipal:
        if not principal.has_all_permissions(permissions):
            raise ForbiddenError("Permission denied")
        return principal

    return dependency


def require_all_permissions_short_session(permissions: list[str]):
    """Require all permissions without retaining a request-scoped DB session."""

    async def dependency(
        principal: EffectivePrincipal = Depends(get_current_principal_short_session),
    ) -> EffectivePrincipal:
        if not principal.has_all_permissions(permissions):
            raise ForbiddenError("Permission denied")
        return principal

    return dependency


require_admin_access = require_permission("admin.access")
