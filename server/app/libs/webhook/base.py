"""Provider-neutral webhook delivery contract."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


class WebhookUrlError(ValueError):
    """Raised when a webhook endpoint is unsafe or cannot be resolved safely."""

    def __init__(self, message: str, *, error_type: str = "url_unsafe") -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class WebhookSendResult:
    """Safe delivery result without response body contents."""

    success: bool
    http_status: int | None
    duration_ms: int
    error_type: str | None = None
    error_message: str | None = None


class BaseWebhookClient(ABC):
    """Abstract client for validating and delivering signed webhook requests."""

    @abstractmethod
    async def validate_url(self, url: str) -> None:
        """Validate scheme, host and every currently resolved address."""
        ...

    @abstractmethod
    async def send(
        self,
        *,
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> WebhookSendResult:
        """Send one HTTPS POST without following redirects."""
        ...

    async def aclose(self) -> None:
        """Release pooled network resources held by this client."""
