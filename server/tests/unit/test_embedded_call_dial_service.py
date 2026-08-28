"""Unit tests for embedded outbound dial commands."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import BusinessError, NotFoundError
from app.schemas.call_center import DialOutboundResponse
from app.schemas.embedded_call import EmbeddedCallDialRequest
from app.services.embedded_call_dial_service import EmbeddedCallDialService


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        del ex
        if nx and key in self.values:
            return False
        if xx and key not in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += self.values.pop(key, None) is not None
        return removed


def embedded_session(**overrides: object) -> dict:
    payload = {
        "typ": "embedded_call_session",
        "tenant_id": 7,
        "user_id": 19,
        "integration_id": 41,
        "instance_id": "instance-123",
    }
    payload.update(overrides)
    return payload


def controlled_redis() -> FakeRedis:
    redis = FakeRedis()
    redis.values["embedded-call:control:7:19"] = json.dumps(
        {"instance_id": "instance-123", "lease_token": "eclease_test"}
    )
    return redis


def dial_request(**overrides: object) -> EmbeddedCallDialRequest:
    data = {
        "number": "+8613800138000",
        "outbound_number_id": "outbound-1",
        "idempotency_key": "crm-record-88",
        "external_context": {
            "record_type": "customer",
            "record_id": "88",
            "display_name": "Ada",
            "attributes": {"tier": "gold"},
        },
        "custom_business_info": "Renewal due next week",
    }
    data.update(overrides)
    return EmbeddedCallDialRequest(**data)


@pytest.mark.asyncio
async def test_same_idempotency_key_dials_only_once() -> None:
    redis = controlled_redis()
    dial = AsyncMock(
        return_value=DialOutboundResponse(
            call_id="call-123", conversation_id="conversation-1", status="originating"
        )
    )
    with (
        patch(
            "app.services.embedded_call_dial_service.get_telephony_client",
            return_value=object(),
        ),
        patch(
            "app.services.embedded_call_dial_service.OutboundDialService.dial_managed",
            dial,
        ),
    ):
        first = await EmbeddedCallDialService.dial(
            redis, session=embedded_session(), data=dial_request()
        )
        second = await EmbeddedCallDialService.dial(
            redis, session=embedded_session(), data=dial_request()
        )

    assert first == second
    assert first.call_id == "call-123"
    assert first.status == "accepted"
    dial.assert_awaited_once()
    assert dial.await_args.kwargs["call_source"] == "embedded_call"
    assert dial.await_args.kwargs["external_context"]["record_id"] == "88"


@pytest.mark.asyncio
async def test_business_info_over_utf8_limit_does_not_dial() -> None:
    redis = controlled_redis()
    dial = AsyncMock()
    with patch(
        "app.services.embedded_call_dial_service.OutboundDialService.dial_managed",
        dial,
    ):
        with pytest.raises(BusinessError) as exc_info:
            await EmbeddedCallDialService.dial(
                redis,
                session=embedded_session(),
                data=dial_request(custom_business_info="通" * 11000),
            )

    assert exc_info.value.code == "EMBED_CUSTOM_BUSINESS_INFO_TOO_LARGE"
    dial.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_external_context_has_stable_error_code() -> None:
    redis = controlled_redis()
    with pytest.raises(BusinessError) as exc_info:
        await EmbeddedCallDialService.dial(
            redis,
            session=embedded_session(),
            data=dial_request(external_context={"attributes": ["invalid"]}),
        )
    assert exc_info.value.code == "EMBED_EXTERNAL_CONTEXT_INVALID"
    assert not any("dial-command" in key or "dial-idem" in key for key in redis.values)


@pytest.mark.asyncio
async def test_command_query_is_scoped_to_session_owner() -> None:
    redis = controlled_redis()
    dial = AsyncMock(
        return_value=DialOutboundResponse(
            call_id="call-123", conversation_id=None, status="originating"
        )
    )
    with (
        patch(
            "app.services.embedded_call_dial_service.get_telephony_client",
            return_value=object(),
        ),
        patch(
            "app.services.embedded_call_dial_service.OutboundDialService.dial_managed",
            dial,
        ),
    ):
        created = await EmbeddedCallDialService.dial(
            redis, session=embedded_session(), data=dial_request()
        )

    found = await EmbeddedCallDialService.get_command(
        redis, session=embedded_session(), command_id=created.command_id
    )
    assert found == created
    with pytest.raises(NotFoundError):
        await EmbeddedCallDialService.get_command(
            redis,
            session=embedded_session(user_id=20),
            command_id=created.command_id,
        )
