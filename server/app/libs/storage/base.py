"""
Abstract base class for storage clients.
"""
from abc import ABC, abstractmethod


class BaseStorageClient(ABC):

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload data and return the public URL."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete an object by key."""
        ...

    @abstractmethod
    async def get_temporary_url(
        self,
        key: str,
        expires_seconds: int = 300,
        download_name: str | None = None,
    ) -> str:
        """Return a temporary URL for reading an object."""
        ...
