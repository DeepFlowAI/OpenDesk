"""SMS channel client contract."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SmsSendResult:
    """Normalized result of a single-send submission to the channel."""

    success: bool
    biz_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class SmsDeliveryReceipt:
    """Normalized delivery receipt parsed from a provider callback payload."""

    biz_id: str
    success: bool
    phone: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BaseSmsClient(ABC):
    """Provider-agnostic single-send SMS client."""

    @abstractmethod
    async def send_sms(
        self,
        *,
        phone: str,
        sign_name: str,
        template_code: str,
        template_params: dict[str, str],
    ) -> SmsSendResult:
        """Submit one SMS to the channel. ``success`` means the channel accepted the request."""

    @abstractmethod
    def parse_delivery_receipt(self, payload: dict[str, Any]) -> SmsDeliveryReceipt:
        """Parse a provider callback payload into a normalized delivery receipt."""
