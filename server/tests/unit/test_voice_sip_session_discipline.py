"""
Session-discipline tests for voice-flow audio assets and SIP extension
admin routes (CLAUDE.md §8).

No managed DB session may stay open while awaiting object-storage upload /
temporary-URL generation or the telephony ``registrar_info`` RPC.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.audio_asset_service as audio_mod
import app.services.sip_extension_service as sip_mod
from app.libs.telephony.base import TelephonyError
from app.repositories.audio_asset_repository import AudioAssetRepository
from app.schemas.permission import EffectivePrincipal
from app.schemas.sip_extension import SipExtensionCreate
from app.services.audio_asset_service import AudioAssetService
from app.services.audit_actor_service import AuditActorService
from app.services.sip_extension_service import SipExtensionService


class SessionTracker:
    active = False
    opens = 0
    closes = 0


class FakeSessionContext:
    async def __aenter__(self):
        assert SessionTracker.active is False
        SessionTracker.active = True
        SessionTracker.opens += 1
        return SimpleNamespace(commit=AsyncMock())

    async def __aexit__(self, *_exc_info):
        SessionTracker.active = False
        SessionTracker.closes += 1


def _reset_tracker() -> None:
    SessionTracker.active = False
    SessionTracker.opens = 0
    SessionTracker.closes = 0


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=7,
        tenant_id=3,
        permissions=["call.admin.extension.manage"],
    )


def _audio_row(**overrides):
    base = dict(
        id=11,
        name="tone.mp3",
        mime_type="audio/mpeg",
        size_bytes=13,
        duration_ms=None,
        created_at=None,
        storage_key="voice-flow/audio/3/abc.mp3",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _sip_record(**overrides):
    base = dict(
        id=5,
        sip_user_id="acme-1001",
        auth_account="acme-1001",
        auth_password_masked="abcd********",
        registration_status="unregistered",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ─────────── Audio assets ───────────


@pytest.mark.asyncio
async def test_managed_upload_closes_db_while_storage_io(monkeypatch):
    """No DB session may be active during object-storage upload or URL fetch."""
    _reset_tracker()
    upload_active: list[bool] = []
    url_active: list[bool] = []

    class _Storage:
        async def upload(self, key, data, content_type=None):
            upload_active.append(SessionTracker.active)

        async def get_temporary_url(self, key, expires_seconds=300):
            url_active.append(SessionTracker.active)
            return "https://cdn.example/preview.mp3"

    monkeypatch.setattr(audio_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(audio_mod, "create_storage_client", lambda: _Storage())
    monkeypatch.setattr(
        AuditActorService,
        "resolve_current_employee",
        AsyncMock(
            return_value={
                "actor_type": "employee",
                "actor_id": 7,
                "actor_name": "Agent",
            }
        ),
    )
    monkeypatch.setattr(
        AudioAssetRepository,
        "create",
        AsyncMock(return_value=_audio_row()),
    )

    result = await AudioAssetService.upload_managed(
        3,
        7,
        filename="tone.mp3",
        content_type="audio/mpeg",
        data=b"ID3" + b"\x00" * 10,
    )

    assert upload_active == [False]
    assert url_active == [False]
    assert result["preview_url"] == "https://cdn.example/preview.mp3"
    assert result["id"] == 11
    assert SessionTracker.opens >= 1
    assert SessionTracker.opens == SessionTracker.closes


@pytest.mark.asyncio
async def test_managed_get_closes_db_while_temporary_url(monkeypatch):
    """No DB session may be active while issuing a temporary preview URL."""
    _reset_tracker()
    url_active: list[bool] = []

    class _Storage:
        async def get_temporary_url(self, key, expires_seconds=300):
            url_active.append(SessionTracker.active)
            assert key == "voice-flow/audio/3/abc.mp3"
            return "https://cdn.example/get.mp3"

    monkeypatch.setattr(audio_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(audio_mod, "create_storage_client", lambda: _Storage())
    monkeypatch.setattr(
        AudioAssetRepository,
        "get_by_id",
        AsyncMock(return_value=_audio_row()),
    )

    result = await AudioAssetService.get_managed(11, 3)

    assert url_active == [False]
    assert result["preview_url"] == "https://cdn.example/get.mp3"
    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_upload_propagates_storage_failure(monkeypatch):
    """Object-storage upload failure aborts before any DB write."""
    _reset_tracker()
    create_mock = AsyncMock()

    class _Storage:
        async def upload(self, key, data, content_type=None):
            assert SessionTracker.active is False
            raise RuntimeError("oss unavailable")

        async def get_temporary_url(self, key, expires_seconds=300):
            raise AssertionError("should not fetch URL after upload failure")

    monkeypatch.setattr(audio_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(audio_mod, "create_storage_client", lambda: _Storage())
    monkeypatch.setattr(AudioAssetRepository, "create", create_mock)

    with pytest.raises(RuntimeError, match="oss unavailable"):
        await AudioAssetService.upload_managed(
            3,
            7,
            filename="tone.mp3",
            content_type="audio/mpeg",
            data=b"ID3" + b"\x00" * 10,
        )

    create_mock.assert_not_awaited()
    assert SessionTracker.opens == SessionTracker.closes == 0


# ─────────── SIP extensions ───────────


@pytest.mark.asyncio
async def test_managed_create_closes_db_while_registrar_rpc(monkeypatch):
    """No DB session may be active during registrar_info RPC after create."""
    _reset_tracker()
    rpc_active: list[bool] = []

    class _Tel:
        async def registrar_info(self):
            rpc_active.append(SessionTracker.active)
            return {"host": "sip.example.com", "port": 5060, "transport": "udp"}

    monkeypatch.setattr(sip_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        SipExtensionService,
        "_create_record",
        AsyncMock(return_value=(_sip_record(), "plain-secret")),
    )
    monkeypatch.setattr(
        "app.libs.telephony.get_telephony_client",
        lambda: _Tel(),
    )

    result = await SipExtensionService.create_managed(
        _principal(),
        SipExtensionCreate(name="Desk", extension_number="1001"),
    )

    assert rpc_active == [False]
    assert result["registration_info"].registration_server == "sip.example.com"
    assert result["registration_info"].auth_password == "plain-secret"
    assert result["record"].sip_user_id == "acme-1001"
    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_create_succeeds_when_registrar_raises(monkeypatch):
    """Telephony failure must not abort create — falls back to settings."""
    _reset_tracker()
    rpc_active: list[bool] = []

    class _Tel:
        async def registrar_info(self):
            rpc_active.append(SessionTracker.active)
            raise TelephonyError("kernel unavailable")

    monkeypatch.setattr(sip_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        SipExtensionService,
        "_create_record",
        AsyncMock(return_value=(_sip_record(), "plain-secret")),
    )
    monkeypatch.setattr(
        "app.libs.telephony.get_telephony_client",
        lambda: _Tel(),
    )
    monkeypatch.setattr(sip_mod.settings, "SIP_REGISTRAR_HOST", "fallback.host")
    monkeypatch.setattr(sip_mod.settings, "SIP_REGISTRAR_PORT", 5070)
    monkeypatch.setattr(sip_mod.settings, "SIP_REGISTRAR_TRANSPORT", "tcp")

    result = await SipExtensionService.create_managed(
        _principal(),
        SipExtensionCreate(name="Desk", extension_number="1001"),
    )

    assert rpc_active == [False]
    info = result["registration_info"]
    assert info.registration_server == "fallback.host"
    assert info.registration_port == 5070
    assert info.transport == "tcp"
    assert info.auth_password == "plain-secret"
    assert SessionTracker.opens == SessionTracker.closes


@pytest.mark.asyncio
async def test_managed_reset_password_closes_db_while_registrar_rpc(monkeypatch):
    """No DB session may be active during registrar_info after password reset."""
    _reset_tracker()
    rpc_active: list[bool] = []

    class _Tel:
        async def registrar_info(self):
            rpc_active.append(SessionTracker.active)
            return {"host": "sip.example.com", "port": 5060, "transport": "udp"}

    monkeypatch.setattr(sip_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        SipExtensionService,
        "_reset_password_record",
        AsyncMock(return_value=(_sip_record(), "new-secret")),
    )
    monkeypatch.setattr(
        "app.libs.telephony.get_telephony_client",
        lambda: _Tel(),
    )

    result = await SipExtensionService.reset_password_managed(_principal(), 5)

    assert rpc_active == [False]
    assert result["registration_info"].auth_password == "new-secret"
    assert SessionTracker.opens == SessionTracker.closes == 1


@pytest.mark.asyncio
async def test_managed_reset_password_succeeds_when_registrar_raises(monkeypatch):
    """Telephony failure must not abort password reset."""
    _reset_tracker()

    class _Tel:
        async def registrar_info(self):
            assert SessionTracker.active is False
            raise RuntimeError("timeout")

    monkeypatch.setattr(sip_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        SipExtensionService,
        "_reset_password_record",
        AsyncMock(return_value=(_sip_record(), "new-secret")),
    )
    monkeypatch.setattr(
        "app.libs.telephony.get_telephony_client",
        lambda: _Tel(),
    )
    monkeypatch.setattr(sip_mod.settings, "SIP_REGISTRAR_HOST", "fallback.host")

    result = await SipExtensionService.reset_password_managed(_principal(), 5)

    assert result["registration_info"].auth_password == "new-secret"
    assert result["registration_info"].registration_server == "fallback.host"
    assert SessionTracker.opens == SessionTracker.closes


@pytest.mark.asyncio
async def test_managed_registration_info_closes_db_while_registrar_rpc(monkeypatch):
    """No DB session may be active during registrar_info for the copy endpoint."""
    _reset_tracker()
    rpc_active: list[bool] = []

    class _Tel:
        async def registrar_info(self):
            rpc_active.append(SessionTracker.active)
            return {"host": "sip.example.com", "port": 5060, "transport": "udp"}

    monkeypatch.setattr(sip_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        SipExtensionService,
        "get_scoped",
        AsyncMock(return_value=_sip_record()),
    )
    monkeypatch.setattr(
        "app.libs.telephony.get_telephony_client",
        lambda: _Tel(),
    )

    info = await SipExtensionService.get_registration_info_managed(_principal(), 5)

    assert rpc_active == [False]
    assert info.registration_server == "sip.example.com"
    assert info.auth_password is None
    assert info.auth_password_masked == "abcd********"
    assert SessionTracker.opens == SessionTracker.closes == 1
