"""Server-authoritative single-controller lease for an agent's call surfaces."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.core.exceptions import BusinessError, ForbiddenError
from app.schemas.embedded_call import EmbeddedCallControlResponse


logger = logging.getLogger(__name__)

CONTROL_LEASE_SECONDS = 15

_COMPARE_EXPIRE = """
local current = redis.call('GET', KEYS[1])
if not current then return 0 end
local parsed = cjson.decode(current)
if parsed['lease_token'] ~= ARGV[1] then return 0 end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

_COMPARE_DELETE = """
local current = redis.call('GET', KEYS[1])
if not current then return 0 end
local parsed = cjson.decode(current)
if parsed['lease_token'] ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""


class EmbeddedCallControlService:
    @staticmethod
    def _key(tenant_id: int, employee_id: int) -> str:
        return f"embedded-call:control:{tenant_id}:{employee_id}"

    @staticmethod
    def _decode(value: str | bytes | None) -> dict | None:
        if value is None:
            return None
        raw = value.decode("utf-8") if isinstance(value, bytes) else value
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _validate_instance(session: dict, instance_id: str) -> None:
        if (
            session.get("typ") == "embedded_call_session"
            and session.get("instance_id") != instance_id
        ):
            raise ForbiddenError("Embedded call instance does not match session")

    @staticmethod
    def _new_value(session: dict, instance_id: str, surface: str) -> dict:
        return {
            "tenant_id": int(session["tenant_id"]),
            "employee_id": int(session["user_id"]),
            "integration_id": session.get("integration_id"),
            "instance_id": instance_id,
            "surface": surface,
            "lease_token": f"eclease_{secrets.token_urlsafe(24)}",
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _response(value: dict | None, *, is_owner: bool) -> EmbeddedCallControlResponse:
        return EmbeddedCallControlResponse(
            is_owner=is_owner,
            owner_instance_id=value.get("instance_id") if value else None,
            owner_surface=value.get("surface") if value else None,
            lease_token=value.get("lease_token") if is_owner and value else None,
            expires_in=CONTROL_LEASE_SECONDS,
        )

    @staticmethod
    async def acquire(
        redis: aioredis.Redis,
        *,
        session: dict,
        instance_id: str,
        surface: str,
    ) -> EmbeddedCallControlResponse:
        EmbeddedCallControlService._validate_instance(session, instance_id)
        key = EmbeddedCallControlService._key(
            int(session["tenant_id"]), int(session["user_id"])
        )
        value = EmbeddedCallControlService._new_value(session, instance_id, surface)
        claimed = await redis.set(
            key,
            json.dumps(value, separators=(",", ":")),
            ex=CONTROL_LEASE_SECONDS,
            nx=True,
        )
        if claimed:
            return EmbeddedCallControlService._response(value, is_owner=True)
        owner = EmbeddedCallControlService._decode(await redis.get(key))
        if owner and owner.get("instance_id") == instance_id:
            renewed = await redis.eval(
                _COMPARE_EXPIRE,
                1,
                key,
                owner.get("lease_token"),
                CONTROL_LEASE_SECONDS,
            )
            if renewed:
                return EmbeddedCallControlService._response(owner, is_owner=True)
        return EmbeddedCallControlService._response(owner, is_owner=False)

    @staticmethod
    async def heartbeat(
        redis: aioredis.Redis,
        *,
        session: dict,
        instance_id: str,
        lease_token: str,
    ) -> EmbeddedCallControlResponse:
        EmbeddedCallControlService._validate_instance(session, instance_id)
        key = EmbeddedCallControlService._key(
            int(session["tenant_id"]), int(session["user_id"])
        )
        renewed = await redis.eval(
            _COMPARE_EXPIRE, 1, key, lease_token, CONTROL_LEASE_SECONDS
        )
        if renewed:
            owner = EmbeddedCallControlService._decode(await redis.get(key))
            return EmbeddedCallControlService._response(owner, is_owner=True)
        owner = EmbeddedCallControlService._decode(await redis.get(key))
        return EmbeddedCallControlService._response(owner, is_owner=False)

    @staticmethod
    async def takeover(
        redis: aioredis.Redis,
        *,
        session: dict,
        instance_id: str,
        surface: str,
    ) -> EmbeddedCallControlResponse:
        EmbeddedCallControlService._validate_instance(session, instance_id)
        key = EmbeddedCallControlService._key(
            int(session["tenant_id"]), int(session["user_id"])
        )
        previous = EmbeddedCallControlService._decode(await redis.get(key))
        value = EmbeddedCallControlService._new_value(session, instance_id, surface)
        await redis.set(
            key,
            json.dumps(value, separators=(",", ":")),
            ex=CONTROL_LEASE_SECONDS,
        )
        logger.info(
            "call control takeover: tenant=%s employee=%s previous_instance=%s "
            "new_instance=%s",
            session["tenant_id"],
            session["user_id"],
            previous.get("instance_id") if previous else None,
            instance_id,
        )
        return EmbeddedCallControlService._response(value, is_owner=True)

    @staticmethod
    async def release(
        redis: aioredis.Redis,
        *,
        session: dict,
        instance_id: str,
        lease_token: str,
    ) -> EmbeddedCallControlResponse:
        EmbeddedCallControlService._validate_instance(session, instance_id)
        key = EmbeddedCallControlService._key(
            int(session["tenant_id"]), int(session["user_id"])
        )
        await redis.eval(_COMPARE_DELETE, 1, key, lease_token)
        owner = EmbeddedCallControlService._decode(await redis.get(key))
        return EmbeddedCallControlService._response(owner, is_owner=False)

    @staticmethod
    async def assert_owner(redis: aioredis.Redis, *, session: dict) -> None:
        key = EmbeddedCallControlService._key(
            int(session["tenant_id"]), int(session["user_id"])
        )
        owner = EmbeddedCallControlService._decode(await redis.get(key))
        if owner is None or owner.get("instance_id") != session.get("instance_id"):
            raise BusinessError(
                "This call is controlled in another window",
                status_code=409,
                code="EMBED_CONTROL_NOT_OWNER",
            )
