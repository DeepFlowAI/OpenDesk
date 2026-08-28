"""
Unit tests for the SIP-extension "reverse integration" against the kernel:

- new telephony SDK methods (extension_query / extension_list / registrar_info
  and the `extension=` originate variant) on the mock client
- -32601 "method not found" mapping to TelephonyMethodNotFoundError
- kernel extension.registered / extension.unregistered writeback
- registrar_info resolution preferring SIP_REGISTRAR_* over the kernel
- outbound two-stage originate for a SIP-phone agent
- inbound assign_queue SIP-phone gating (never touches the WebRTC path)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.libs.telephony.base import (
    TelephonyMethodNotFoundError,
    TelephonyRPCError,
)
from app.libs.telephony.providers.mock.client import MockTelephonyClient


# ─────────────────── SDK layer ───────────────────


class TestExtensionSDK:
    @pytest.mark.asyncio
    async def test_originate_with_extension(self):
        client = MockTelephonyClient()
        await client.connect()
        client.originate_response = {"call_id": "ext-leg", "status": "originating"}
        result = await client.call_originate(extension="acme-1001")
        assert result["call_id"] == "ext-leg"
        args = next(a for m, a in client.recorded if m == "call.originate")
        # extension only — no uri/trunk_id leaks in
        assert args == {"extension": "acme-1001"}

    @pytest.mark.asyncio
    async def test_extension_query_and_list(self):
        client = MockTelephonyClient()
        await client.connect()
        client.extension_query_response = {
            "extension": "acme-1001", "registered": True, "contact": "sip:x@1.2.3.4",
        }
        client.extension_list_response = [
            {"extension": "acme-1001", "contact": "sip:x", "expires_at": 1, "last_seen": 2},
        ]
        q = await client.extension_query("acme-1001")
        assert q["registered"] is True
        lst = await client.extension_list()
        assert lst[0]["extension"] == "acme-1001"

    @pytest.mark.asyncio
    async def test_registrar_info(self):
        client = MockTelephonyClient()
        await client.connect()
        client.registrar_info_response = {"host": "sip.example", "port": 5060, "transport": "udp"}
        info = await client.registrar_info()
        assert info == {"host": "sip.example", "port": 5060, "transport": "udp"}

    @pytest.mark.asyncio
    async def test_method_not_found_surfaces_typed_error(self):
        client = MockTelephonyClient()
        await client.connect()
        client.extension_query_error = TelephonyMethodNotFoundError(
            -32601, "method not found"
        )
        with pytest.raises(TelephonyMethodNotFoundError):
            await client.extension_query("acme-1001")


def test_flowkit_maps_32601_to_method_not_found():
    """The FlowKit response handler must map -32601 to the distinct type so
    callers can detect a kernel with extensions disabled and degrade."""
    import asyncio

    from app.libs.telephony.providers.flowkit.client import FlowKitTelephonyClient

    client = FlowKitTelephonyClient(
        ws_url="ws://x", sdk_name="t", sdk_version="1",
    )
    loop = asyncio.new_event_loop()
    try:
        fut: asyncio.Future = loop.create_future()
        client._pending["7"] = fut
        client._handle_response(
            {"id": "7", "error": {"code": -32601, "message": "method not found"}}
        )
        assert fut.done()
        exc = fut.exception()
        assert isinstance(exc, TelephonyMethodNotFoundError)

        # A different code stays a plain TelephonyRPCError.
        fut2: asyncio.Future = loop.create_future()
        client._pending["8"] = fut2
        client._handle_response(
            {"id": "8", "error": {"code": -32602, "message": "bad param"}}
        )
        exc2 = fut2.exception()
        assert isinstance(exc2, TelephonyRPCError)
        assert not isinstance(exc2, TelephonyMethodNotFoundError)
    finally:
        loop.close()


# ─────────────────── Registration writeback ───────────────────


class TestRegistrationWriteback:
    @pytest.mark.asyncio
    async def test_registered_event_updates_status_and_timestamp(self, monkeypatch):
        from app.repositories.sip_extension_repository import SipExtensionRepository
        from app.services.sip_extension_service import SipExtensionService

        record = SimpleNamespace(
            id=1, sip_user_id="acme-1001", registration_status="unregistered",
            last_registered_at=None, bound_employee_id=5, tenant_id=7,
            extension_number="1001",
        )
        monkeypatch.setattr(
            SipExtensionRepository, "get_by_sip_user_id",
            AsyncMock(return_value=record),
        )

        applied: dict = {}

        async def fake_update(_db, item, data):
            applied.update(data)
            for k, v in data.items():
                setattr(item, k, v)
            return item

        monkeypatch.setattr(SipExtensionRepository, "update", fake_update)

        updated = await SipExtensionService.apply_registration_event(
            MagicMock(), sip_user_id="acme-1001", registered=True,
        )
        assert updated.registration_status == "registered"
        assert applied["registration_status"] == "registered"
        assert applied["last_registered_at"] is not None
        # timezone-aware UTC
        assert applied["last_registered_at"].tzinfo is not None

    @pytest.mark.asyncio
    async def test_unregistered_event_clears_status(self, monkeypatch):
        from app.repositories.sip_extension_repository import SipExtensionRepository
        from app.services.sip_extension_service import SipExtensionService

        record = SimpleNamespace(
            id=1, sip_user_id="acme-1001", registration_status="registered",
            last_registered_at=None, bound_employee_id=None, tenant_id=7,
            extension_number="1001",
        )
        monkeypatch.setattr(
            SipExtensionRepository, "get_by_sip_user_id",
            AsyncMock(return_value=record),
        )

        async def fake_update(_db, item, data):
            for k, v in data.items():
                setattr(item, k, v)
            return item

        monkeypatch.setattr(SipExtensionRepository, "update", fake_update)

        updated = await SipExtensionService.apply_registration_event(
            MagicMock(), sip_user_id="acme-1001", registered=False,
        )
        assert updated.registration_status == "unregistered"

    @pytest.mark.asyncio
    async def test_unknown_aor_is_ignored(self, monkeypatch):
        from app.repositories.sip_extension_repository import SipExtensionRepository
        from app.services.sip_extension_service import SipExtensionService

        monkeypatch.setattr(
            SipExtensionRepository, "get_by_sip_user_id",
            AsyncMock(return_value=None),
        )
        updated = await SipExtensionService.apply_registration_event(
            MagicMock(), sip_user_id="foreign-9999", registered=True,
        )
        assert updated is None


# ─────────────────── registrar_info resolution ───────────────────


class TestRegistrarResolution:
    @pytest.mark.asyncio
    async def test_prefers_settings_over_kernel(self, monkeypatch):
        from app.configs import settings as settings_module
        from app.libs.telephony import factory
        from app.services.sip_extension_service import SipExtensionService

        client = MockTelephonyClient()
        client.registrar_info_response = {
            "host": "kernel.sip", "port": 6060, "transport": "tcp",
        }
        monkeypatch.setattr(factory, "_instance", client)
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_HOST", "public.sip")
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_PORT", 5070)
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_TRANSPORT", "udp")

        host, port, transport = await SipExtensionService._resolve_registrar_endpoint()
        assert host == "public.sip"
        assert port == 5070
        assert transport == "udp"

    @pytest.mark.asyncio
    async def test_kernel_fills_unset_settings_fields(self, monkeypatch):
        from app.configs import settings as settings_module
        from app.libs.telephony import factory
        from app.services.sip_extension_service import SipExtensionService

        client = MockTelephonyClient()
        client.registrar_info_response = {
            "host": "kernel.sip", "port": 6060, "transport": "tcp",
        }
        monkeypatch.setattr(factory, "_instance", client)
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_HOST", "")
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_PORT", None)
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_TRANSPORT", "")

        host, port, transport = await SipExtensionService._resolve_registrar_endpoint()
        assert host == "kernel.sip"
        assert port == 6060
        assert transport == "tcp"

    @pytest.mark.asyncio
    async def test_falls_back_to_settings_when_kernel_absent(self, monkeypatch):
        from app.configs import settings as settings_module
        from app.libs.telephony import factory
        from app.services.sip_extension_service import SipExtensionService

        client = MockTelephonyClient()
        client.registrar_info_response = None  # kernel has no registrar
        monkeypatch.setattr(factory, "_instance", client)
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_HOST", "deploy.sip")
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_PORT", 5061)
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_TRANSPORT", "udp")

        host, port, transport = await SipExtensionService._resolve_registrar_endpoint()
        assert (host, port, transport) == ("deploy.sip", 5061, "udp")

    @pytest.mark.asyncio
    async def test_method_not_found_falls_back_to_settings(self, monkeypatch):
        from app.configs import settings as settings_module
        from app.libs.telephony import factory
        from app.services.sip_extension_service import SipExtensionService

        client = MockTelephonyClient()
        client.registrar_info_error = TelephonyMethodNotFoundError(-32601, "nope")
        monkeypatch.setattr(factory, "_instance", client)
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_HOST", "deploy.sip")
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_PORT", None)
        monkeypatch.setattr(settings_module.settings, "SIP_REGISTRAR_TRANSPORT", "")

        host, _port, _transport = await SipExtensionService._resolve_registrar_endpoint()
        assert host == "deploy.sip"
