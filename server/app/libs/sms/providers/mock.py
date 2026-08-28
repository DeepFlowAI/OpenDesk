"""Mock SMS client for local development and tests."""
import uuid
from typing import Any

from app.libs.sms.base import BaseSmsClient, SmsDeliveryReceipt, SmsSendResult


class MockSmsClient(BaseSmsClient):
    """Always accepts submissions and echoes a deterministic mock biz id."""

    async def send_sms(
        self,
        *,
        phone: str,
        sign_name: str,
        template_code: str,
        template_params: dict[str, str],
    ) -> SmsSendResult:
        return SmsSendResult(success=True, biz_id=f"MOCK-{uuid.uuid4().hex[:20]}")

    def parse_delivery_receipt(self, payload: dict[str, Any]) -> SmsDeliveryReceipt:
        return SmsDeliveryReceipt(
            biz_id=str(payload.get("biz_id", "")),
            success=bool(payload.get("success", True)),
            phone=payload.get("phone"),
            error_code=payload.get("error_code"),
            error_message=payload.get("error_message"),
            raw=dict(payload),
        )
