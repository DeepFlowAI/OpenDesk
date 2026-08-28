"""Embedded outbound dial commands with scoped idempotency."""
from __future__ import annotations

import hashlib
import json
import logging
import secrets

import redis.asyncio as aioredis

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.libs.telephony import get_telephony_client
from app.schemas.embedded_call import (
    EmbeddedCallCommandResponse,
    EmbeddedCallDialRequest,
)
from app.services.call_center.outbound_dial_service import OutboundDialService
from app.services.embedded_call_control_service import EmbeddedCallControlService


logger = logging.getLogger(__name__)

COMMAND_TTL_SECONDS = 24 * 60 * 60
MAX_CUSTOM_BUSINESS_INFO_BYTES = 32 * 1024


def _embed_error(code: str, message: str, status_code: int = 400) -> BusinessError:
    return BusinessError(message, status_code=status_code, code=code)


class EmbeddedCallDialService:
    @staticmethod
    def _command_key(command_id: str) -> str:
        return f"embedded-call:dial-command:{command_id}"

    @staticmethod
    def _idempotency_key(payload: dict, idempotency_key: str) -> str:
        scope = ":".join(
            str(payload[name])
            for name in ("tenant_id", "user_id", "integration_id")
        )
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"embedded-call:dial-idem:{scope}:{digest}"

    @staticmethod
    def _encode(state: dict) -> str:
        return json.dumps(state, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _decode(value: str | bytes | None) -> dict | None:
        if value is None:
            return None
        raw = value.decode("utf-8") if isinstance(value, bytes) else value
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _response(state: dict) -> EmbeddedCallCommandResponse:
        return EmbeddedCallCommandResponse(
            command_id=str(state["command_id"]),
            call_id=state.get("call_id"),
            status=str(state["status"]),
        )

    @staticmethod
    def _validate_session(payload: dict) -> None:
        if payload.get("typ") != "embedded_call_session":
            raise ForbiddenError("Embedded call session required")
        required = ("tenant_id", "user_id", "integration_id")
        if any(payload.get(name) is None for name in required):
            raise ForbiddenError("Embedded call session is invalid")

    @staticmethod
    def _validate_external_context(value: dict | None) -> dict | None:
        if value is None:
            return None
        allowed = {"record_type", "record_id", "display_name", "attributes"}
        attributes = value.get("attributes", {})
        if not isinstance(attributes, dict):
            raise _embed_error(
                "EMBED_EXTERNAL_CONTEXT_INVALID", "External context is invalid"
            )
        text_limits = {"record_type": 40, "record_id": 128, "display_name": 128}
        valid = set(value) <= allowed
        valid = valid and len(attributes) <= 10
        for key, limit in text_limits.items():
            field = value.get(key)
            valid = valid and (field is None or isinstance(field, str) and len(field) <= limit)
        for key, item in attributes.items():
            valid = valid and (
                isinstance(key, str)
                and 0 < len(key) <= 64
                and isinstance(item, str)
                and len(item) <= 256
            )
        valid = valid and len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ) <= 4096
        if not valid:
            raise _embed_error(
                "EMBED_EXTERNAL_CONTEXT_INVALID", "External context is invalid"
            )
        return value

    @staticmethod
    async def dial(
        redis: aioredis.Redis,
        *,
        session: dict,
        data: EmbeddedCallDialRequest,
    ) -> EmbeddedCallCommandResponse:
        EmbeddedCallDialService._validate_session(session)
        await EmbeddedCallControlService.assert_owner(redis, session=session)
        custom_size = len((data.custom_business_info or "").encode("utf-8"))
        if custom_size > MAX_CUSTOM_BUSINESS_INFO_BYTES:
            raise _embed_error(
                "EMBED_CUSTOM_BUSINESS_INFO_TOO_LARGE",
                "Custom business information exceeds 32 KiB",
            )
        context = EmbeddedCallDialService._validate_external_context(
            data.external_context
        )

        command_id = f"eccmd_{secrets.token_urlsafe(18)}"
        state = {
            "command_id": command_id,
            "call_id": None,
            "status": "pending",
            "tenant_id": int(session["tenant_id"]),
            "employee_id": int(session["user_id"]),
            "integration_id": int(session["integration_id"]),
        }
        encoded = EmbeddedCallDialService._encode(state)
        idempotency_redis_key = None
        if data.idempotency_key:
            idempotency_redis_key = EmbeddedCallDialService._idempotency_key(
                session, data.idempotency_key
            )
            claimed = await redis.set(
                idempotency_redis_key,
                encoded,
                ex=COMMAND_TTL_SECONDS,
                nx=True,
            )
            if not claimed:
                existing = EmbeddedCallDialService._decode(
                    await redis.get(idempotency_redis_key)
                )
                if existing is None:
                    raise _embed_error(
                        "EMBED_COMMAND_STATE_INVALID",
                        "Embedded dial command state is unavailable",
                        503,
                    )
                return EmbeddedCallDialService._response(existing)

        command_redis_key = EmbeddedCallDialService._command_key(command_id)
        await redis.set(command_redis_key, encoded, ex=COMMAND_TTL_SECONDS)
        logger.info(
            "embedded outbound dial requested: tenant=%s employee=%s integration=%s "
            "has_business_info=%s business_info_bytes=%s",
            state["tenant_id"],
            state["employee_id"],
            state["integration_id"],
            bool(data.custom_business_info),
            custom_size,
        )
        try:
            result = await OutboundDialService.dial_managed(
                get_telephony_client(),
                tenant_pk=state["tenant_id"],
                employee_id=state["employee_id"],
                outbound_phone_number_id=data.outbound_number_id,
                destination=data.number,
                r=redis,
                call_source="embedded_call",
                custom_business_info=data.custom_business_info,
                external_context=context,
            )
        except Exception:
            await redis.delete(command_redis_key)
            if idempotency_redis_key is not None:
                await redis.delete(idempotency_redis_key)
            raise

        state.update(call_id=result.call_id, status="accepted")
        encoded = EmbeddedCallDialService._encode(state)
        await redis.set(command_redis_key, encoded, ex=COMMAND_TTL_SECONDS)
        if idempotency_redis_key is not None:
            await redis.set(
                idempotency_redis_key, encoded, ex=COMMAND_TTL_SECONDS, xx=True
            )
        return EmbeddedCallDialService._response(state)

    @staticmethod
    async def get_command(
        redis: aioredis.Redis,
        *,
        session: dict,
        command_id: str,
    ) -> EmbeddedCallCommandResponse:
        EmbeddedCallDialService._validate_session(session)
        state = EmbeddedCallDialService._decode(
            await redis.get(EmbeddedCallDialService._command_key(command_id))
        )
        if state is None:
            raise NotFoundError("Embedded dial command not found")
        expected = (
            int(session["tenant_id"]),
            int(session["user_id"]),
            int(session["integration_id"]),
        )
        actual = (
            state.get("tenant_id"),
            state.get("employee_id"),
            state.get("integration_id"),
        )
        if actual != expected:
            raise NotFoundError("Embedded dial command not found")
        return EmbeddedCallDialService._response(state)
