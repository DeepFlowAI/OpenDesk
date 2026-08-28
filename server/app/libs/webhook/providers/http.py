"""Direct HTTPS webhook provider with SSRF defenses."""
import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlparse

import httpx

from app.libs.webhook.base import BaseWebhookClient, WebhookSendResult, WebhookUrlError

DNS_TIMEOUT_SECONDS = 5.0


class HttpWebhookClient(BaseWebhookClient):
    """Send webhooks directly to publicly routable HTTPS endpoints."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
            )
        return self._client

    @staticmethod
    def _validate_shape(url: str) -> tuple[str, int]:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise WebhookUrlError("Endpoint must be a valid HTTPS URL")
        if parsed.username or parsed.password:
            raise WebhookUrlError("Endpoint must not contain credentials")
        if parsed.fragment:
            raise WebhookUrlError("Endpoint must not contain a fragment")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            raise WebhookUrlError("Endpoint host is not publicly routable")
        try:
            port = parsed.port or 443
        except ValueError as exc:
            raise WebhookUrlError("Endpoint port is invalid") from exc
        return hostname, port

    @staticmethod
    def _ensure_public_ip(address: str) -> None:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as exc:
            raise WebhookUrlError("Endpoint resolved to an invalid address", error_type="dns") from exc
        if not ip.is_global:
            raise WebhookUrlError("Endpoint resolves to a non-public address")

    async def validate_url(self, url: str) -> None:
        hostname, port = self._validate_shape(url)
        try:
            literal = ipaddress.ip_address(hostname.split("%", 1)[0])
        except ValueError:
            literal = None
        if literal is not None:
            self._ensure_public_ip(str(literal))
            return

        loop = asyncio.get_running_loop()
        try:
            addresses = await asyncio.wait_for(
                loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM),
                timeout=DNS_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise WebhookUrlError("Endpoint DNS resolution timed out", error_type="dns") from exc
        except socket.gaierror as exc:
            raise WebhookUrlError("Endpoint DNS resolution failed", error_type="dns") from exc
        if not addresses:
            raise WebhookUrlError("Endpoint DNS returned no addresses", error_type="dns")
        for address in {entry[4][0] for entry in addresses}:
            self._ensure_public_ip(address)

    async def send(
        self,
        *,
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> WebhookSendResult:
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout_seconds):
                await self.validate_url(url)
                response = await self._http_client().post(
                    url,
                    content=body,
                    headers=headers,
                    timeout=timeout_seconds,
                )
        except WebhookUrlError as exc:
            return self._failure(started, exc.error_type, str(exc))
        except (TimeoutError, httpx.TimeoutException):
            return self._failure(started, "timeout", "Endpoint request timed out")
        except httpx.ConnectError as exc:
            message = str(exc).lower()
            error_type = "tls" if "ssl" in message or "certificate" in message else "network"
            return self._failure(started, error_type, "Endpoint connection failed")
        except httpx.RequestError:
            return self._failure(started, "network", "Endpoint request failed")

        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        if 200 <= response.status_code < 300:
            return WebhookSendResult(
                success=True,
                http_status=response.status_code,
                duration_ms=duration_ms,
            )
        return WebhookSendResult(
            success=False,
            http_status=response.status_code,
            duration_ms=duration_ms,
            error_type="http_status",
            error_message=f"Endpoint returned HTTP {response.status_code}",
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _failure(started: float, error_type: str, message: str) -> WebhookSendResult:
        return WebhookSendResult(
            success=False,
            http_status=None,
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
            error_type=error_type,
            error_message=message[:255],
        )
