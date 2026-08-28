"""Unit tests for the SMS delivery-receipt callback route."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.configs import settings as settings_module
from app.core.exceptions import register_exception_handlers
from app.routers.v1 import sms_callback
from app.services.sms_service import SmsWorkspaceService

_CALLBACK_URL = "/api/v1/sms/callback/aliyun"
_ALIYUN_ACK = {"code": 0, "msg": "成功"}


def _build_client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(sms_callback.router, prefix="/api/v1")
    return TestClient(app)


def _enable_callback(monkeypatch):
    monkeypatch.setattr(settings_module.settings, "SMS_PROVIDER", "aliyun")
    monkeypatch.setattr(settings_module.settings, "SMS_CALLBACK_TOKEN", "tok")


class TestSmsCallbackProbe:
    def test_get_probe_returns_aliyun_ack(self, monkeypatch):
        _enable_callback(monkeypatch)
        resp = _build_client().get(_CALLBACK_URL, params={"token": "tok"})
        assert resp.status_code == 200
        assert resp.json() == _ALIYUN_ACK

    def test_get_probe_rejects_bad_token(self, monkeypatch):
        _enable_callback(monkeypatch)
        resp = _build_client().get(_CALLBACK_URL, params={"token": "wrong"})
        assert resp.status_code == 404

    def test_get_probe_rejects_when_token_unset(self, monkeypatch):
        monkeypatch.setattr(settings_module.settings, "SMS_CALLBACK_TOKEN", "")
        resp = _build_client().get(_CALLBACK_URL)
        assert resp.status_code == 404


class TestSmsDeliveryCallback:
    def test_post_returns_aliyun_ack_and_applies_receipts(self, monkeypatch):
        _enable_callback(monkeypatch)
        seen = {}

        async def fake_handle(*, provider, payload):
            seen["provider"] = provider
            seen["payload"] = payload
            return 2

        monkeypatch.setattr(SmsWorkspaceService, "handle_delivery_receipts", staticmethod(fake_handle))
        items = [{"biz_id": "1", "success": True}, {"biz_id": "2", "success": False}]
        resp = _build_client().post(_CALLBACK_URL, params={"token": "tok"}, json=items)
        assert resp.status_code == 200
        assert resp.json() == _ALIYUN_ACK
        assert seen == {"provider": "aliyun", "payload": items}

    def test_post_rejects_bad_token(self, monkeypatch):
        _enable_callback(monkeypatch)
        resp = _build_client().post(_CALLBACK_URL, params={"token": "wrong"}, json=[])
        assert resp.status_code == 404

    def test_post_rejects_provider_mismatch(self, monkeypatch):
        _enable_callback(monkeypatch)
        monkeypatch.setattr(settings_module.settings, "SMS_PROVIDER", "mock")
        resp = _build_client().post(_CALLBACK_URL, params={"token": "tok"}, json=[])
        assert resp.status_code == 404
