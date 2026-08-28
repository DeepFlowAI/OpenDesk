"""Factory for SMS channel clients, driven by settings.SMS_PROVIDER."""
import logging
import threading

from app.configs.settings import settings
from app.libs.sms.base import BaseSmsClient

logger = logging.getLogger(__name__)

_instance: BaseSmsClient | None = None
_lock = threading.Lock()


def get_sms_client() -> BaseSmsClient:
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        provider = settings.SMS_PROVIDER
        match provider:
            case "aliyun":
                from app.libs.sms.providers.aliyun import AliyunSmsClient

                _instance = AliyunSmsClient(
                    access_key_id=settings.ALIYUN_SMS_ACCESS_KEY_ID,
                    access_key_secret=settings.ALIYUN_SMS_ACCESS_KEY_SECRET,
                    endpoint=settings.ALIYUN_SMS_ENDPOINT,
                )
            case "mock":
                from app.libs.sms.providers.mock import MockSmsClient

                _instance = MockSmsClient()
            case _:
                raise ValueError(f"Unsupported SMS provider: {provider}")
        logger.info("SMS client initialized: provider=%s", provider)
    return _instance


def reset_sms_client() -> None:
    """Reset the cached client (used by tests)."""
    global _instance
    with _lock:
        _instance = None
