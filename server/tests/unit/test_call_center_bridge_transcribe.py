"""
Unit tests for the per-tenant live-transcription toggle at the bridge sites.

When a tenant's `bridge_asr_enabled` is False, OpenDesk must tell FlowKit NOT to
run live ASR by passing `transcribe=False` to `call_bridge`. When True (the
historical behavior), it passes `transcribe=True`.

These are true unit tests: the tenant setting read is stubbed, so no DB is hit.
"""
from unittest.mock import AsyncMock

import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center.nodes import AssignQueueExecutor, ExecutionContext
from app.services.system_settings_service import SystemSettingsService


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_bridge_to_agent_passes_transcribe_from_tenant_setting(monkeypatch, enabled):
    monkeypatch.setattr(
        SystemSettingsService,
        "is_bridge_asr_enabled_managed",
        AsyncMock(return_value=enabled),
    )

    tel = MockTelephonyClient()
    await tel.connect()
    ctx = ExecutionContext(call_id="call-1", tenant_id=7, telephony=tel, variables={})

    await AssignQueueExecutor()._bridge_to_agent(
        ctx, webrtc_call_id="webrtc-1", employee_id=42, redis=None,
    )

    bridge = next(p for m, p in tel.recorded if m == "call.bridge")
    assert bridge["call_id"] == "call-1"
    assert bridge["other_call_id"] == "webrtc-1"
    assert bridge["transcribe"] is enabled


@pytest.mark.asyncio
async def test_flowkit_client_omits_transcribe_when_true():
    """FlowKit RPC stays backward-compatible: send `transcribe` only when False."""
    from app.libs.telephony.providers.flowkit.client import FlowKitTelephonyClient

    client = FlowKitTelephonyClient(ws_url="ws://x", sdk_name="t", sdk_version="0")
    sent: list[tuple[str, dict]] = []

    async def fake_rpc(method, params):
        sent.append((method, params))
        return {}

    client._rpc = fake_rpc  # type: ignore[assignment]

    await client.call_bridge("c1", "c2", transcribe=True)
    assert sent[-1] == ("call.bridge", {"call_id": "c1", "other_call_id": "c2"})

    await client.call_bridge("c1", "c2", transcribe=False)
    assert sent[-1] == (
        "call.bridge",
        {"call_id": "c1", "other_call_id": "c2", "transcribe": False},
    )
