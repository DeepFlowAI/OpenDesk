"""Aliyun SMS channel client (SendSms via official SDK, lazily imported)."""
import asyncio
import json
import logging
from typing import Any

from app.libs.sms.base import BaseSmsClient, SmsDeliveryReceipt, SmsSendResult

logger = logging.getLogger(__name__)

ALIYUN_OK_CODE = "OK"


class AliyunSmsClient(BaseSmsClient):
    def __init__(self, *, access_key_id: str, access_key_secret: str, endpoint: str) -> None:
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret
        self._endpoint = endpoint

    def _build_client(self) -> Any:
        # Lazy import so local/dev environments do not need the SDK installed.
        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_tea_openapi.models import Config

        config = Config(
            access_key_id=self._access_key_id,
            access_key_secret=self._access_key_secret,
            endpoint=self._endpoint,
        )
        return Client(config)

    async def send_sms(
        self,
        *,
        phone: str,
        sign_name: str,
        template_code: str,
        template_params: dict[str, str],
    ) -> SmsSendResult:
        from alibabacloud_dysmsapi20170525 import models as dysmsapi_models

        request = dysmsapi_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=sign_name,
            template_code=template_code,
            template_param=json.dumps(template_params, ensure_ascii=False),
        )
        try:
            # The official SDK is synchronous; keep the event loop responsive.
            response = await asyncio.to_thread(self._build_client().send_sms, request)
        except Exception as exc:  # SDK raises TeaException for transport/API errors
            logger.exception("Aliyun SendSms call failed")
            return SmsSendResult(success=False, error_code="SDK_ERROR", error_message=str(exc)[:255])

        body = response.body
        code = getattr(body, "code", None)
        if code == ALIYUN_OK_CODE:
            return SmsSendResult(success=True, biz_id=getattr(body, "biz_id", None))
        return SmsSendResult(
            success=False,
            error_code=code,
            error_message=(getattr(body, "message", None) or "")[:255] or None,
        )

    def parse_delivery_receipt(self, payload: dict[str, Any]) -> SmsDeliveryReceipt:
        # Aliyun delivery reports carry: biz_id, phone, success(bool), err_code, err_msg.
        return SmsDeliveryReceipt(
            biz_id=str(payload.get("biz_id", "")),
            success=bool(payload.get("success")),
            phone=payload.get("phone"),
            error_code=payload.get("err_code"),
            error_message=payload.get("err_msg"),
            raw=dict(payload),
        )
