"""VOD client abstraction."""
from app.libs.vod.base import BaseVodClient, VodPlayInfo, VodTranscodeEvent, VodUploadCredential
from app.libs.vod.factory import get_vod_client, reset_vod_client

__all__ = [
    "BaseVodClient",
    "VodPlayInfo",
    "VodTranscodeEvent",
    "VodUploadCredential",
    "get_vod_client",
    "reset_vod_client",
]
