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
    async def copy(self, source_key: str, destination_key: str) -> None:
        """Copy an object within the configured storage bucket."""
        ...

    @abstractmethod
    async def get_temporary_url(
        self,
        key: str,
        expires_seconds: int = 300,
        download_name: str | None = None,
        image_process: str | None = None,
    ) -> str:
        """Return a temporary URL for reading an object."""
        ...

    @abstractmethod
    async def get_presigned_upload_url(
        self,
        key: str,
        content_type: str = "application/octet-stream",
        expires_seconds: int = 900,
    ) -> str:
        """Return a temporary signed URL that lets a client PUT one object directly."""
        ...

    async def upload_private(self, key: str, data: bytes, content_type: str) -> None:
        """Upload with private object ACL; providers must explicitly support this."""
        raise NotImplementedError("Private object uploads are not supported")

    async def read_private(self, key: str, max_bytes: int) -> bytes:
        """Read without a public URL, enforcing the maximum size before buffering.

        Raise FileNotFoundError for a missing object and ValueError for an
        oversized/corrupt object. Other failures are treated as transient I/O.
        """
        raise NotImplementedError("Private object reads are not supported")
