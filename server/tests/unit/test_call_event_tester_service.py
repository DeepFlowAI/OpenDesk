import json

import fakeredis.aioredis
import pytest

from app.core.exceptions import ForbiddenError
from app.services.call_event_tester_service import (
    MAX_BODY_BYTES,
    CallEventTesterService,
)


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _event(event_id: str, event_type: str = "call.created") -> bytes:
    return json.dumps({"id": event_id, "type": event_type, "data": {"sequence": 1}}).encode()


async def _deliver(redis, token: str, body: bytes, authorization: str | None = None) -> int:
    return await CallEventTesterService.receive(
        redis,
        token,
        body=body,
        authorization=authorization,
        delivery_id="dlv_1",
        user_agent="OpenDesk-Webhook/1.0",
    )


@pytest.mark.asyncio
async def test_same_employee_reuses_receiver_and_users_are_isolated(redis):
    first = await CallEventTesterService.get_receiver(redis, 1, 10)
    again = await CallEventTesterService.get_receiver(redis, 1, 10)
    other = await CallEventTesterService.get_receiver(redis, 1, 11)

    assert first.token == again.token
    assert other.token != first.token
    assert first.webhook_path.endswith(f"/{first.token}/webhook")

    assert await _deliver(redis, first.token, _event("evt_1")) == 204
    mine = await CallEventTesterService.list_events(redis, 1, 10)
    theirs = await CallEventTesterService.list_events(redis, 1, 11)
    assert [e.body["id"] for e in mine.items] == ["evt_1"]
    assert theirs.items == []


@pytest.mark.asyncio
async def test_rotate_invalidates_old_token(redis):
    old = await CallEventTesterService.get_receiver(redis, 1, 10)
    new = await CallEventTesterService.rotate_receiver(redis, 1, 10)

    assert new.token != old.token
    assert await _deliver(redis, old.token, _event("evt_1")) == 404
    assert await _deliver(redis, new.token, _event("evt_1")) == 204


@pytest.mark.asyncio
async def test_secret_mismatch_returns_401_but_is_recorded(redis):
    receiver = await CallEventTesterService.get_receiver(redis, 1, 10)
    updated = await CallEventTesterService.set_secret(redis, 1, 10, "odwhsec_abc")
    assert updated.has_secret is True

    assert await _deliver(redis, receiver.token, _event("evt_1"), "Bearer wrong") == 401
    assert await _deliver(redis, receiver.token, _event("evt_1"), "Bearer odwhsec_abc") == 204

    events = (await CallEventTesterService.list_events(redis, 1, 10)).items
    assert [(e.secret_checked, e.secret_ok, e.duplicate) for e in events] == [
        (True, False, False),
        (True, True, False),
    ]

    cleared = await CallEventTesterService.set_secret(redis, 1, 10, "")
    assert cleared.has_secret is False
    assert await _deliver(redis, receiver.token, _event("evt_3"), None) == 204


@pytest.mark.asyncio
async def test_duplicates_are_flagged_and_after_filters(redis):
    receiver = await CallEventTesterService.get_receiver(redis, 1, 10)
    await _deliver(redis, receiver.token, _event("evt_1"))
    await _deliver(redis, receiver.token, _event("evt_1"))
    await _deliver(redis, receiver.token, b"not json")

    result = await CallEventTesterService.list_events(redis, 1, 10)
    assert [e.seq for e in result.items] == [1, 2, 3]
    assert [e.duplicate for e in result.items] == [False, True, False]
    assert result.items[2].body == "not json"
    assert result.last_seq == 3

    newer = await CallEventTesterService.list_events(redis, 1, 10, after=2)
    assert [e.seq for e in newer.items] == [3]


@pytest.mark.asyncio
async def test_oversized_body_and_clear(redis):
    receiver = await CallEventTesterService.get_receiver(redis, 1, 10)
    assert await _deliver(redis, receiver.token, b"x" * (MAX_BODY_BYTES + 1)) == 413

    await _deliver(redis, receiver.token, _event("evt_1"))
    await CallEventTesterService.clear_events(redis, 1, 10)
    cleared = await CallEventTesterService.list_events(redis, 1, 10)
    assert cleared.items == []
    assert cleared.last_seq == 1

    await _deliver(redis, receiver.token, _event("evt_1"))
    after_clear = await CallEventTesterService.list_events(redis, 1, 10, after=1)
    assert [(e.seq, e.duplicate) for e in after_clear.items] == [(2, False)]


@pytest.mark.asyncio
async def test_requires_employee(redis):
    with pytest.raises(ForbiddenError):
        await CallEventTesterService.get_receiver(redis, 1, None)
