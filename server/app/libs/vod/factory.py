"""Factory for VOD clients, driven by settings.VOD_PROVIDER."""
import logging
import threading

from app.configs.settings import settings
from app.libs.vod.base import BaseVodClient

logger = logging.getLogger(__name__)

_instance: BaseVodClient | None = None
_lock = threading.Lock()


def get_vod_client() -> BaseVodClient:
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        provider = settings.VOD_PROVIDER
        match provider:
            case "aliyun":
                from app.libs.vod.providers.aliyun import AliyunVodClient

                _instance = AliyunVodClient(
                    access_key_id=settings.ALIYUN_VOD_ACCESS_KEY_ID,
                    access_key_secret=settings.ALIYUN_VOD_ACCESS_KEY_SECRET,
                    endpoint=settings.ALIYUN_VOD_ENDPOINT,
                    template_group_id=settings.ALIYUN_VOD_TEMPLATE_GROUP_ID,
                )
            case "mock":
                from app.libs.vod.providers.mock import MockVodClient

                _instance = MockVodClient()
            case _:
                raise ValueError(f"Unsupported VOD provider: {provider}")
        logger.info("VOD client initialized: provider=%s", provider)
    return _instance


def reset_vod_client() -> None:
    """Reset the cached client (used by tests)."""
    global _instance
    with _lock:
        _instance = None
