"""Per-user receivers that capture call event subscription deliveries for testing.

Each employee gets an unguessable webhook token. Deliveries posted to that token
are stored in Redis so the owner can inspect them; receivers of different users
never share state. Everything expires after a day without use.
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.core.exceptions import ForbiddenError
from app.schemas.call_event_tester import (
    CallEventTesterEvent,
    CallEventTesterEventListResponse,
    CallEventTesterReceiverResponse,
)

KEY_PREFIX = "call-event-tester"
TTL_SECONDS = 24 * 60 * 60
MAX_EVENTS = 500
MAX_BODY_BYTES = 256 * 1024
WEBHOOK_PATH_TEMPLATE = "/api/v1/public/call-center/event-tester/{token}/webhook"


def _owner_key(tenant_id: int, employee_id: int) -> str:
    return f"{KEY_PREFIX}:owner:{tenant_id}:{employee_id}"


def _receiver_key(token: str) -> str:
    return f"{KEY_PREFIX}:receiver:{token}"


def _events_key(token: str) -> str:
    return f"{KEY_PREFIX}:events:{token}"


def _seq_key(token: str) -> str:
    return f"{KEY_PREFIX}:seq:{token}"


def _ids_key(token: str) -> str:
    return f"{KEY_PREFIX}:ids:{token}"


def _token_keys(token: str) -> list[str]:
    return [_receiver_key(token), _events_key(token), _seq_key(token), _ids_key(token)]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CallEventTesterService:
    @staticmethod
    def _require_employee(employee_id: int | None) -> int:
        if employee_id is None:
            raise ForbiddenError("A signed-in employee is required")
        return int(employee_id)

    @staticmethod
    async def _touch(redis: aioredis.Redis, owner_key: str, token: str) -> None:
        pipe = redis.pipeline()
        pipe.expire(owner_key, TTL_SECONDS)
        for key in _token_keys(token):
            pipe.expire(key, TTL_SECONDS)
        await pipe.execute()

    @staticmethod
    def _to_response(token: str, meta: dict) -> CallEventTesterReceiverResponse:
        return CallEventTesterReceiverResponse(
            token=token,
            webhook_path=WEBHOOK_PATH_TEMPLATE.format(token=token),
            has_secret=bool(meta.get("secret_sha256")),
            created_at=meta["created_at"],
            expires_in_seconds=TTL_SECONDS,
        )

    @staticmethod
    async def _create(
        redis: aioredis.Redis, tenant_id: int, employee_id: int
    ) -> tuple[str, dict]:
        token = secrets.token_urlsafe(24)
        meta = {
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "secret_sha256": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        pipe = redis.pipeline()
        pipe.set(_receiver_key(token), json.dumps(meta), ex=TTL_SECONDS)
        pipe.set(_owner_key(tenant_id, employee_id), token, ex=TTL_SECONDS)
        await pipe.execute()
        return token, meta

    @staticmethod
    async def _load_owned(
        redis: aioredis.Redis, tenant_id: int, employee_id: int
    ) -> tuple[str, dict]:
        """Return the caller's receiver, creating one when missing or expired."""
        owner_key = _owner_key(tenant_id, employee_id)
        token = await redis.get(owner_key)
        if token:
            raw = await redis.get(_receiver_key(token))
            if raw:
                await CallEventTesterService._touch(redis, owner_key, token)
                return token, json.loads(raw)
        return await CallEventTesterService._create(redis, tenant_id, employee_id)

    @staticmethod
    async def get_receiver(
        redis: aioredis.Redis, tenant_id: int, employee_id: int | None
    ) -> CallEventTesterReceiverResponse:
        employee = CallEventTesterService._require_employee(employee_id)
        token, meta = await CallEventTesterService._load_owned(redis, tenant_id, employee)
        return CallEventTesterService._to_response(token, meta)

    @staticmethod
    async def rotate_receiver(
        redis: aioredis.Redis, tenant_id: int, employee_id: int | None
    ) -> CallEventTesterReceiverResponse:
        employee = CallEventTesterService._require_employee(employee_id)
        old_token = await redis.get(_owner_key(tenant_id, employee))
        if old_token:
            await redis.delete(*_token_keys(old_token))
        token, meta = await CallEventTesterService._create(redis, tenant_id, employee)
        return CallEventTesterService._to_response(token, meta)

    @staticmethod
    async def set_secret(
        redis: aioredis.Redis,
        tenant_id: int,
        employee_id: int | None,
        secret: str | None,
    ) -> CallEventTesterReceiverResponse:
        employee = CallEventTesterService._require_employee(employee_id)
        token, meta = await CallEventTesterService._load_owned(redis, tenant_id, employee)
        cleaned = (secret or "").strip()
        meta["secret_sha256"] = _sha256(cleaned) if cleaned else None
        await redis.set(_receiver_key(token), json.dumps(meta), ex=TTL_SECONDS)
        return CallEventTesterService._to_response(token, meta)

    @staticmethod
    async def list_events(
        redis: aioredis.Redis,
        tenant_id: int,
        employee_id: int | None,
        after: int = 0,
    ) -> CallEventTesterEventListResponse:
        employee = CallEventTesterService._require_employee(employee_id)
        token, _ = await CallEventTesterService._load_owned(redis, tenant_id, employee)
        raw_items = await redis.lrange(_events_key(token), 0, MAX_EVENTS - 1)
        last_seq = int(await redis.get(_seq_key(token)) or 0)
        items = [CallEventTesterEvent(**json.loads(raw)) for raw in raw_items]
        items = sorted((item for item in items if item.seq > after), key=lambda e: e.seq)
        return CallEventTesterEventListResponse(items=items, last_seq=last_seq)

    @staticmethod
    async def clear_events(
        redis: aioredis.Redis, tenant_id: int, employee_id: int | None
    ) -> None:
        employee = CallEventTesterService._require_employee(employee_id)
        token, _ = await CallEventTesterService._load_owned(redis, tenant_id, employee)
        # Keep the sequence counter so pollers using `after` never miss new events.
        await redis.delete(_events_key(token), _ids_key(token))

    @staticmethod
    async def receive(
        redis: aioredis.Redis,
        token: str,
        *,
        body: bytes,
        authorization: str | None,
        delivery_id: str | None,
        user_agent: str | None,
    ) -> int:
        """Store one delivery and return the HTTP status to answer with."""
        raw_meta = await redis.get(_receiver_key(token))
        if not raw_meta:
            return 404
        if len(body) > MAX_BODY_BYTES:
            return 413
        meta = json.loads(raw_meta)

        expected = meta.get("secret_sha256")
        presented = (authorization or "").strip()
        if presented.lower().startswith("bearer "):
            presented = presented[7:].strip()
        secret_ok = bool(expected) and hmac.compare_digest(_sha256(presented), expected)

        text = body.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except ValueError:
            payload = text

        rejected = bool(expected) and not secret_ok
        duplicate = False
        event_id = payload.get("id") if isinstance(payload, dict) else None
        # Only accepted deliveries count, so a retry after a 401 is not flagged.
        if not rejected and isinstance(event_id, str) and event_id:
            duplicate = (await redis.sadd(_ids_key(token), event_id)) == 0

        seq = await redis.incr(_seq_key(token))
        event = CallEventTesterEvent(
            seq=seq,
            received_at=datetime.now(timezone.utc).isoformat(),
            delivery_id=delivery_id,
            user_agent=user_agent,
            secret_checked=bool(expected),
            secret_ok=secret_ok,
            duplicate=duplicate,
            body=payload,
        )
        pipe = redis.pipeline()
        pipe.lpush(_events_key(token), event.model_dump_json())
        pipe.ltrim(_events_key(token), 0, MAX_EVENTS - 1)
        for key in _token_keys(token):
            pipe.expire(key, TTL_SECONDS)
        await pipe.execute()

        if rejected:
            return 401
        return 204
