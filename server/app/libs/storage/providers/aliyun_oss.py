"""
Alibaba Cloud OSS storage implementation.
"""
import logging
from functools import lru_cache

import oss2

from app.configs.settings import settings
from app.libs.storage.base import BaseStorageClient

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_bucket() -> oss2.Bucket:
    auth = oss2.Auth(settings.OSS_ACCESS_KEY, settings.OSS_SECRET_KEY)
    return oss2.Bucket(auth, settings.OSS_URL, settings.OSS_BUCKET)


class AliyunOSSClient(BaseStorageClient):

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload bytes to OSS and return the public URL."""
        bucket = _get_bucket()
        headers = {"Content-Type": content_type}
        bucket.put_object(key, data, headers=headers)
        public_url = f"{settings.OSS_ADDR}/{key}"
        logger.info("Uploaded to OSS: %s", public_url)
        return public_url

    async def delete(self, key: str) -> None:
        """Delete an object from OSS by key."""
        bucket = _get_bucket()
        bucket.delete_object(key)
        logger.info("Deleted from OSS: %s", key)

    async def get_temporary_url(
        self,
        key: str,
        expires_seconds: int = 300,
        download_name: str | None = None,
    ) -> str:
        """Create a short-lived signed URL for object reads."""
        bucket = _get_bucket()
        params = {}
        if download_name:
            params["response-content-disposition"] = f'attachment; filename="{download_name}"'
        return bucket.sign_url("GET", key, expires_seconds, params=params)
