"""
Storage client factory.
"""
from app.configs.settings import settings
from app.libs.storage.base import BaseStorageClient


def create_storage_client() -> BaseStorageClient:
    provider = settings.STORAGE_PROVIDER
    match provider:
        case "aliyun_oss":
            from app.libs.storage.providers.aliyun_oss import AliyunOSSClient
            return AliyunOSSClient()
        case _:
            raise ValueError(f"Unsupported storage provider: {provider}")
