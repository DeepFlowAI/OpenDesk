"""MultiKernelTelephonyClient routing / fan-in."""
from __future__ import annotations

import asyncio
import logging
from unittest import mock

import fakeredis.aioredis
import pytest

from app.libs.telephony.providers.flowkit import client as _flowkit_client

from app.libs.telephony.base import CallEvent
from app.libs.telephony.factory import _flowkit_ws_urls, get_telephony_client, reset_telephony_client
from app.libs.telephony.providers.flowkit.multi_client import MultiKernelTelephonyClient
from app.libs.telephony.providers.mock.client import MockTelephonyClient


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_telephony_client()
    yield
    reset_telephony_client()


def _multi(monkeypatch) -> tuple[MultiKernelTelephonyClient, MockTelephonyClient, MockTelephonyClient]:
    monkeypatch.setattr(
        "app.libs.telephony.providers.flowkit.multi_client._get_redis",
        lambda: None,
    )
    multi = MultiKernelTelephonyClient(
        ws_urls=["ws://k0/ws", "ws://k1/ws"],
        sdk_name="test",
        sdk_version="0",
    )
    k0 = MockTelephonyClient()
    k1 = MockTelephonyClient()
    multi._clients = [k0, k1]  # type: ignore[assignment]
    multi._wired = False
    return multi, k0, k1


@pytest.mark.asyncio
async def test_events_from_either_kernel_forwarded(monkeypatch):
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()
    seen: list[str] = []

    async def handler(event: CallEvent) -> None:
        seen.append(event.data["call_id"])

    multi.on_event("call.incoming", handler)
    await k0.emit_event("call.incoming", {"call_id": "c0", "transport": "sip"})
    await k1.emit_event("call.incoming", {"call_id": "c1", "transport": "sip"})

    assert seen == ["c0", "c1"]
    assert multi._call_kernel["c0"] == 0
    assert multi._call_kernel["c1"] == 1


@pytest.mark.asyncio
async def test_rpc_routes_to_mapped_kernel(monkeypatch):
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()
    multi._call_kernel["c1"] = 1

    await multi.call_answer("c1")

    assert ("call.answer", {"call_id": "c1"}) in k1.recorded
    assert ("call.answer", {"call_id": "c1"}) not in k0.recorded


@pytest.mark.asyncio
async def test_room_create_routes_to_leg_kernel_not_primary(monkeypatch):
    """Conference merge must hit the kernel that owns the call legs."""
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()
    # Legs live on k1, but primary is still k0 (no drift yet).
    assert multi._primary_index == 0
    multi._call_kernel["sip-1"] = 1
    multi._call_kernel["webrtc-1"] = 1
    k1.room_create_response = {"room_id": "room-k1", "legs": []}

    result = await multi.room_create(leg_call_ids=["sip-1", "webrtc-1", "party-1"])

    assert result["room_id"] == "room-k1"
    assert ("room.create", {
        "leg_call_ids": ["sip-1", "webrtc-1", "party-1"],
    }) in k1.recorded
    assert "room.create" not in {r[0] for r in k0.recorded}
    assert multi._call_kernel["room:room-k1"] == 1


@pytest.mark.asyncio
async def test_webrtc_offer_with_affinity_routes_and_maps_new_leg(monkeypatch):
    """Consult accept pins a new WebRTC leg to the customer's kernel."""
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()
    multi._call_kernel["sip-customer"] = 1
    k1.webrtc_offer_response = {"call_id": "webrtc-target", "sdp": "v=0"}

    result = await multi.webrtc_offer("v=0-offer", call_id="sip-customer")

    assert result["call_id"] == "webrtc-target"
    assert multi._call_kernel["webrtc-target"] == 1
    assert any(r[0] == "webrtc.offer" for r in k1.recorded)
    assert not any(r[0] == "webrtc.offer" for r in k0.recorded)


@pytest.mark.asyncio
async def test_originate_uses_primary_and_maps(monkeypatch):
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()
    # Mark k1 ready-only primary by disconnecting k0 after connect.
    await k0.disconnect()
    k1.originate_response = {"call_id": "out-1", "status": "ringing"}

    result = await multi.call_originate("13800138000")
    assert result["call_id"] == "out-1"
    assert multi._call_kernel["out-1"] == 1


@pytest.mark.asyncio
async def test_primary_drifts_on_incoming_from_other_kernel(monkeypatch):
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()
    assert multi._primary_index == 0

    await k1.emit_event("call.incoming", {"call_id": "c-new", "transport": "sip"})
    assert multi._primary_index == 1

    k1.originate_response = {"call_id": "out-new", "status": "ringing"}
    result = await multi.call_originate("13800138000")
    assert result["call_id"] == "out-new"
    assert multi._call_kernel["out-new"] == 1
    assert any(r[0] == "call.originate" for r in k1.recorded)
    assert not any(r[0] == "call.originate" for r in k0.recorded)


@pytest.mark.asyncio
async def test_primary_drifts_on_extension_registered(monkeypatch):
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()
    await k1.emit_event("extension.registered", {"extension": "1001"})
    assert multi._primary_index == 1


@pytest.mark.asyncio
async def test_call_list_aggregates(monkeypatch):
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()
    k0.call_list_response = [{"call_id": "a"}]
    k1.call_list_response = [{"call_id": "b"}]

    calls = await multi.call_list()
    ids = {c["call_id"] for c in calls}
    assert ids == {"a", "b"}
    assert multi._call_kernel["a"] == 0
    assert multi._call_kernel["b"] == 1


@pytest.mark.asyncio
async def test_kernel_map_persists_to_redis(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        "app.libs.telephony.providers.flowkit.multi_client._get_redis",
        lambda: fake,
    )
    multi = MultiKernelTelephonyClient(
        ws_urls=["ws://k0/ws", "ws://k1/ws"],
        sdk_name="test",
        sdk_version="0",
    )
    multi._clients = [MockTelephonyClient(), MockTelephonyClient()]  # type: ignore[assignment]
    multi._wired = False
    await multi.connect()
    await multi._remember_kernel("c-redis", 1)
    assert await fake.get("cc:call:kernel:c-redis") == "1"
    multi._call_kernel.clear()
    assert await multi._lookup_kernel("c-redis") == 1


def test_factory_single_url_unchanged(monkeypatch):
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_PROVIDER", "flowkit")
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_WS_URL", "ws://one/ws")
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_WS_URLS", "")
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_SDK_NAME", "t")
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_SDK_VERSION", "1")
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_RPC_TIMEOUT", 5.0)

    client = get_telephony_client()
    from app.libs.telephony.providers.flowkit.client import FlowKitTelephonyClient

    assert isinstance(client, FlowKitTelephonyClient)


def test_factory_multi_urls(monkeypatch):
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_PROVIDER", "flowkit")
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_WS_URL", "")
    monkeypatch.setattr(
        "app.libs.telephony.factory.settings.TELEPHONY_WS_URLS",
        "ws://a/ws, ws://b/ws",
    )
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_SDK_NAME", "t")
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_SDK_VERSION", "1")
    monkeypatch.setattr("app.libs.telephony.factory.settings.TELEPHONY_RPC_TIMEOUT", 5.0)

    client = get_telephony_client()
    assert isinstance(client, MultiKernelTelephonyClient)
    assert len(client._clients) == 2


def test_flowkit_ws_urls_prefers_urls_list(monkeypatch):
    monkeypatch.setattr(
        "app.libs.telephony.factory.settings.TELEPHONY_WS_URLS",
        "ws://a/ws,ws://b/ws",
    )
    monkeypatch.setattr(
        "app.libs.telephony.factory.settings.TELEPHONY_WS_URL",
        "ws://ignored/ws",
    )
    assert _flowkit_ws_urls() == ["ws://a/ws", "ws://b/ws"]


# ─────────── Blue/green: one kernel down is not an incident ───────────


@pytest.mark.asyncio
async def test_each_kernel_can_tell_whether_a_sibling_serves(monkeypatch):
    multi, k0, k1 = _multi(monkeypatch)
    await multi.connect()

    assert k0.peer_serving_probe is not None and k1.peer_serving_probe is not None
    assert k0.peer_serving_probe() is True

    await k1.disconnect()
    assert k0.peer_serving_probe() is False
    assert k1.peer_serving_probe() is True


async def _one_failed_reconnect(client, caplog) -> logging.LogRecord:
    """Drive a single failing reconnect attempt and return what it logged."""

    async def _refused() -> None:
        client._closing = True  # stop the retry loop after this attempt
        raise ConnectionRefusedError(111, "Connection refused")

    client._open_and_handshake = _refused  # type: ignore[method-assign]
    with caplog.at_level(logging.INFO, logger=_flowkit_client.logger.name):
        with mock.patch.object(asyncio, "sleep", _skip_backoff):
            await client._reconnect_loop()
    records = [r for r in caplog.records if "reconnect failed" in r.getMessage()]
    assert len(records) == 1
    return records[0]


async def _skip_backoff(_delay, result=None):
    return result


def _client(url: str):
    return _flowkit_client.FlowKitTelephonyClient(
        ws_url=url, sdk_name="test", sdk_version="0"
    )


@pytest.mark.asyncio
async def test_unreachable_kernel_is_not_an_error_while_a_sibling_serves(caplog):
    """Blue/green takes one kernel down on every release, and this retry runs
    every 30s for as long as it stays down. Calls keep flowing through the
    sibling, so paging someone would be crying wolf."""
    client = _client("ws://green/ws")
    client.set_peer_serving_probe(lambda: True)

    record = await _one_failed_reconnect(client, caplog)

    assert record.levelno == logging.INFO


@pytest.mark.asyncio
async def test_last_kernel_down_still_warns(caplog):
    """No kernel left means no telephony — that one really is worth an alert."""
    client = _client("ws://green/ws")
    client.set_peer_serving_probe(lambda: False)

    record = await _one_failed_reconnect(client, caplog)

    assert record.levelno == logging.WARNING


@pytest.mark.asyncio
async def test_single_kernel_deployment_still_warns(caplog):
    """Nobody wired a probe, so there is no sibling to fall back on."""
    record = await _one_failed_reconnect(_client("ws://only/ws"), caplog)

    assert record.levelno == logging.WARNING
