from types import SimpleNamespace

import pytest

from app.services.call_center.orchestration.events import EventHandlersMixin


class _Harness(EventHandlersMixin):
    def __init__(self) -> None:
        self.telephony = SimpleNamespace()


class _ProbeClient:
    calls_by_url: dict[str, list[dict] | Exception] = {}
    disconnected: list[str] = []

    def __init__(self, *, ws_url: str, **_kwargs) -> None:
        self.url = ws_url

    async def _open_and_handshake(self) -> None:
        value = self.calls_by_url[self.url]
        if isinstance(value, Exception):
            raise value

    async def call_list(self) -> list[dict]:
        value = self.calls_by_url[self.url]
        assert not isinstance(value, Exception)
        return value

    def _start_recv_loop(self) -> None:
        return None

    async def disconnect(self) -> None:
        self.disconnected.append(self.url)


@pytest.mark.asyncio
async def test_reconcile_collects_calls_from_both_colors(monkeypatch):
    monkeypatch.setattr(
        "app.configs.settings.settings.TELEPHONY_RECONCILE_WS_URLS",
        "ws://blue/ws,ws://green/ws",
    )
    monkeypatch.setattr(
        "app.libs.telephony.providers.flowkit.client.FlowKitTelephonyClient",
        _ProbeClient,
        raising=False,
    )
    _ProbeClient.calls_by_url = {
        "ws://blue/ws": [{"call_id": "old-call"}],
        "ws://green/ws": [{"call_id": "new-call"}],
    }
    _ProbeClient.disconnected = []

    active, complete = await _Harness()._reconcile_active_call_ids()

    assert active == {"old-call", "new-call"}
    assert complete is True
    assert _ProbeClient.disconnected == ["ws://blue/ws", "ws://green/ws"]


@pytest.mark.asyncio
async def test_reconcile_marks_snapshot_incomplete_when_one_color_fails(monkeypatch):
    monkeypatch.setattr(
        "app.configs.settings.settings.TELEPHONY_RECONCILE_WS_URLS",
        "ws://blue/ws,ws://green/ws",
    )
    monkeypatch.setattr(
        "app.libs.telephony.providers.flowkit.client.FlowKitTelephonyClient",
        _ProbeClient,
        raising=False,
    )
    _ProbeClient.calls_by_url = {
        "ws://blue/ws": TimeoutError("handshake timed out"),
        "ws://green/ws": [{"call_id": "new-call"}],
    }
    _ProbeClient.disconnected = []

    active, complete = await _Harness()._reconcile_active_call_ids()

    assert active == {"new-call"}
    assert complete is False
    assert _ProbeClient.disconnected == ["ws://blue/ws", "ws://green/ws"]


@pytest.mark.asyncio
async def test_stopped_color_is_a_complete_empty_snapshot(monkeypatch):
    monkeypatch.setattr(
        "app.configs.settings.settings.TELEPHONY_RECONCILE_WS_URLS",
        "ws://blue/ws,ws://green/ws",
    )
    monkeypatch.setattr(
        "app.libs.telephony.providers.flowkit.client.FlowKitTelephonyClient",
        _ProbeClient,
    )
    _ProbeClient.calls_by_url = {
        "ws://blue/ws": ConnectionRefusedError(111, "Connection refused"),
        "ws://green/ws": [{"call_id": "active-call"}],
    }
    _ProbeClient.disconnected = []

    active, complete = await _Harness()._reconcile_active_call_ids()

    assert active == {"active-call"}
    assert complete is True
