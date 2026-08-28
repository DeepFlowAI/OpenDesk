"""
Unit tests for libs/sms: factory dispatch, mock provider and Aliyun provider
(SDK layer is stubbed — no real Aliyun call is ever made).
"""
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.libs.sms.base import SmsDeliveryReceipt
from app.libs.sms.providers.mock import MockSmsClient


class TestSmsFactory:

    def test_mock_provider_returns_mock_client(self, monkeypatch):
        from app.libs.sms import factory

        monkeypatch.setattr("app.libs.sms.factory.settings.SMS_PROVIDER", "mock")
        factory.reset_sms_client()
        client = factory.get_sms_client()
        assert isinstance(client, MockSmsClient)
        factory.reset_sms_client()

    def test_unknown_provider_raises(self, monkeypatch):
        from app.libs.sms import factory

        monkeypatch.setattr("app.libs.sms.factory.settings.SMS_PROVIDER", "unknown")
        factory.reset_sms_client()
        with pytest.raises(ValueError):
            factory.get_sms_client()
        factory.reset_sms_client()


class TestMockSmsClient:

    @pytest.mark.asyncio
    async def test_send_sms_returns_success_with_mock_biz_id(self):
        client = MockSmsClient()
        result = await client.send_sms(
            phone="13800138000",
            sign_name="深流客服",
            template_code="SMS_1",
            template_params={"name": "王先生"},
        )
        assert result.success is True
        assert result.biz_id and result.biz_id.startswith("MOCK-")

    def test_parse_delivery_receipt(self):
        client = MockSmsClient()
        receipt = client.parse_delivery_receipt(
            {"biz_id": "MOCK-1", "success": False, "error_message": "空号"}
        )
        assert isinstance(receipt, SmsDeliveryReceipt)
        assert receipt.biz_id == "MOCK-1"
        assert receipt.success is False
        assert receipt.error_message == "空号"


def _install_fake_aliyun_sdk(monkeypatch, response_body=None, raise_exc=None):
    """Register stub alibabacloud modules in sys.modules."""
    captured: dict = {}

    class FakeSendSmsRequest:
        def __init__(self, phone_numbers, sign_name, template_code, template_param):
            captured["request"] = {
                "phone_numbers": phone_numbers,
                "sign_name": sign_name,
                "template_code": template_code,
                "template_param": template_param,
            }

    class FakeClient:
        def __init__(self, config):
            captured["config"] = config

        def send_sms(self, request):
            if raise_exc is not None:
                raise raise_exc
            return SimpleNamespace(body=response_body)

    models_module = types.ModuleType("alibabacloud_dysmsapi20170525.models")
    models_module.SendSmsRequest = FakeSendSmsRequest
    client_module = types.ModuleType("alibabacloud_dysmsapi20170525.client")
    client_module.Client = FakeClient
    package_module = types.ModuleType("alibabacloud_dysmsapi20170525")
    package_module.models = models_module
    openapi_module = types.ModuleType("alibabacloud_tea_openapi")
    openapi_models_module = types.ModuleType("alibabacloud_tea_openapi.models")
    openapi_models_module.Config = MagicMock()
    openapi_module.models = openapi_models_module

    monkeypatch.setitem(sys.modules, "alibabacloud_dysmsapi20170525", package_module)
    monkeypatch.setitem(sys.modules, "alibabacloud_dysmsapi20170525.models", models_module)
    monkeypatch.setitem(sys.modules, "alibabacloud_dysmsapi20170525.client", client_module)
    monkeypatch.setitem(sys.modules, "alibabacloud_tea_openapi", openapi_module)
    monkeypatch.setitem(sys.modules, "alibabacloud_tea_openapi.models", openapi_models_module)
    return captured


class TestAliyunSmsClient:

    @pytest.mark.asyncio
    async def test_send_sms_maps_params_and_parses_ok(self, monkeypatch):
        from app.libs.sms.providers.aliyun import AliyunSmsClient

        captured = _install_fake_aliyun_sdk(
            monkeypatch,
            response_body=SimpleNamespace(code="OK", biz_id="9006197469364984401", message="OK"),
        )
        client = AliyunSmsClient(access_key_id="ak", access_key_secret="sk", endpoint="ep")
        result = await client.send_sms(
            phone="13800138000",
            sign_name="深流客服",
            template_code="SMS_1000001",
            template_params={"name": "王先生"},
        )

        assert result.success is True
        assert result.biz_id == "9006197469364984401"
        request = captured["request"]
        assert request["phone_numbers"] == "13800138000"
        assert request["sign_name"] == "深流客服"
        assert request["template_code"] == "SMS_1000001"
        assert '"name"' in request["template_param"]

    @pytest.mark.asyncio
    async def test_send_sms_business_error_code(self, monkeypatch):
        from app.libs.sms.providers.aliyun import AliyunSmsClient

        _install_fake_aliyun_sdk(
            monkeypatch,
            response_body=SimpleNamespace(
                code="isv.INSUFFICIENT_BALANCE", biz_id=None, message="余额不足"
            ),
        )
        client = AliyunSmsClient(access_key_id="ak", access_key_secret="sk", endpoint="ep")
        result = await client.send_sms(
            phone="13800138000", sign_name="s", template_code="SMS_1", template_params={}
        )

        assert result.success is False
        assert result.error_code == "isv.INSUFFICIENT_BALANCE"
        assert result.error_message == "余额不足"

    @pytest.mark.asyncio
    async def test_send_sms_sdk_exception_is_caught(self, monkeypatch):
        from app.libs.sms.providers.aliyun import AliyunSmsClient

        _install_fake_aliyun_sdk(monkeypatch, raise_exc=RuntimeError("network down"))
        client = AliyunSmsClient(access_key_id="ak", access_key_secret="sk", endpoint="ep")
        result = await client.send_sms(
            phone="13800138000", sign_name="s", template_code="SMS_1", template_params={}
        )

        assert result.success is False
        assert result.error_code == "SDK_ERROR"
        assert "network down" in (result.error_message or "")

    def test_parse_delivery_receipt_aliyun_fields(self, monkeypatch):
        from app.libs.sms.providers.aliyun import AliyunSmsClient

        client = AliyunSmsClient(access_key_id="ak", access_key_secret="sk", endpoint="ep")
        receipt = client.parse_delivery_receipt(
            {
                "biz_id": "90061",
                "phone": "13800138000",
                "success": False,
                "err_code": "DELIVRD_FAIL",
                "err_msg": "空号",
            }
        )
        assert receipt.biz_id == "90061"
        assert receipt.success is False
        assert receipt.error_code == "DELIVRD_FAIL"
