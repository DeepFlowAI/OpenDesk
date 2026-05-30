"""
Unit tests for the telephony abstraction — mock client + factory.

The FlowKit provider itself is intentionally NOT tested here: it depends on
a real WebSocket counterpart and runs against the production kernel. See
the dev workflow §4.5.2 exclusion rule.
"""
import asyncio

import pytest

from app.libs.telephony.base import (
    BaseTelephonyClient,
    CallEvent,
)
from app.libs.telephony.factory import get_telephony_client, reset_telephony_client
from app.libs.telephony.providers.mock.client import MockTelephonyClient


class TestMockTelephonyClient:

    @pytest.mark.asyncio
    async def test_connect_marks_ready(self):
        client = MockTelephonyClient()
        assert client.is_ready is False
        await client.connect()
        assert client.is_ready is True
        await client.wait_until_ready(timeout=1.0)

    @pytest.mark.asyncio
    async def test_event_dispatch(self):
        client = MockTelephonyClient()
        await client.connect()
        seen: list[CallEvent] = []

        async def handler(e: CallEvent) -> None:
            seen.append(e)

        client.on_event("call.incoming", handler)
        await client.emit_event("call.incoming", {"call_id": "c1", "from": "sip:123@x"})
        assert len(seen) == 1
        assert seen[0].method == "call.incoming"
        assert seen[0].data["call_id"] == "c1"

    @pytest.mark.asyncio
    async def test_multiple_handlers_all_called(self):
        client = MockTelephonyClient()
        await client.connect()
        seen: list[str] = []

        async def h1(e: CallEvent) -> None:
            seen.append("h1")

        async def h2(e: CallEvent) -> None:
            seen.append("h2")

        client.on_event("call.dtmf", h1)
        client.on_event("call.dtmf", h2)
        await client.emit_event("call.dtmf", {"call_id": "c1", "digit": "1"})
        assert sorted(seen) == ["h1", "h2"]

    @pytest.mark.asyncio
    async def test_off_event_stops_dispatch(self):
        client = MockTelephonyClient()
        await client.connect()
        seen: list[str] = []

        async def h(e: CallEvent) -> None:
            seen.append("x")

        client.on_event("call.hangup", h)
        client.off_event("call.hangup", h)
        await client.emit_event("call.hangup", {"call_id": "c1"})
        assert seen == []

    @pytest.mark.asyncio
    async def test_rpc_records(self):
        client = MockTelephonyClient()
        await client.connect()
        await client.call_answer("c1")
        await client.call_say("c1", "hello", voice="zh", barge_in=True)
        await client.call_bridge("c1", "c2")
        methods = [m for m, _ in client.recorded]
        assert "call.answer" in methods
        assert "call.say" in methods
        assert "call.bridge" in methods
        # call.say returns a play_id
        say_args = next(args for m, args in client.recorded if m == "call.say")
        assert say_args["text"] == "hello"
        assert say_args["voice"] == "zh"
        assert say_args["barge_in"] is True

    @pytest.mark.asyncio
    async def test_call_list_returns_response(self):
        client = MockTelephonyClient()
        await client.connect()
        client.call_list_response = [{"call_id": "c1", "state": "ringing"}]
        result = await client.call_list()
        assert result == [{"call_id": "c1", "state": "ringing"}]

    @pytest.mark.asyncio
    async def test_call_originate_with_trunk_id(self):
        client = MockTelephonyClient()
        await client.connect()
        client.originate_response = {
            "call_id": "out-1",
            "conversation_id": "conv-1",
            "status": "originating",
        }
        result = await client.call_originate(
            "13800138000",
            caller_id="+8602112345678",
            trunk_id="trunk_sh_main",
            timeout_ms=30000,
        )
        assert result["call_id"] == "out-1"
        args = next(a for m, a in client.recorded if m == "call.originate")
        assert args == {
            "uri": "13800138000",
            "caller_id": "+8602112345678",
            "trunk_id": "trunk_sh_main",
            "timeout_ms": 30000,
        }

    @pytest.mark.asyncio
    async def test_call_originate_omits_optional_keys(self):
        client = MockTelephonyClient()
        await client.connect()
        await client.call_originate("13800138000")
        args = next(a for m, a in client.recorded if m == "call.originate")
        # caller_id / trunk_id / timeout_ms / headers must NOT appear when unset
        assert args == {"uri": "13800138000"}


class TestTelephonyFactory:

    def setup_method(self):
        reset_telephony_client()

    def teardown_method(self):
        reset_telephony_client()

    def test_factory_returns_mock_by_default(self, monkeypatch):
        from app.configs import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "TELEPHONY_PROVIDER", "mock")
        client = get_telephony_client()
        assert isinstance(client, MockTelephonyClient)
        assert isinstance(client, BaseTelephonyClient)

    def test_factory_singleton(self, monkeypatch):
        from app.configs import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "TELEPHONY_PROVIDER", "mock")
        c1 = get_telephony_client()
        c2 = get_telephony_client()
        assert c1 is c2

    def test_factory_raises_on_unknown_provider(self, monkeypatch):
        from app.configs import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "TELEPHONY_PROVIDER", "nonexistent")
        with pytest.raises(ValueError, match="Unsupported telephony provider"):
            get_telephony_client()
