"""Unit tests for the direct HTTPS webhook provider."""
import asyncio
import socket
from unittest.mock import AsyncMock

import httpx
import pytest

from app.libs.webhook.base import WebhookUrlError
from app.libs.webhook.providers.http import HttpWebhookClient


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/path",
        "https://user:password@hooks.example.com/path",
        "https://hooks.example.com/path#fragment",
        "https://localhost/path",
        "https://service.local/path",
    ],
)
def test_validate_shape_rejects_unsafe_url(url: str) -> None:
    with pytest.raises(WebhookUrlError):
        HttpWebhookClient._validate_shape(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hook",
        "https://10.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/hook",
        "https://192.0.2.1/hook",
    ],
)
async def test_validate_url_rejects_non_public_literal(url: str) -> None:
    with pytest.raises(WebhookUrlError):
        await HttpWebhookClient().validate_url(url)


@pytest.mark.asyncio
async def test_validate_url_rejects_hostname_if_any_dns_answer_is_private(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(*_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.2", 443)),
        ]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(WebhookUrlError):
        await HttpWebhookClient().validate_url("https://hooks.example.com/path")


@pytest.mark.asyncio
async def test_send_does_not_follow_redirect_and_does_not_expose_body(monkeypatch) -> None:
    client = HttpWebhookClient()
    monkeypatch.setattr(client, "validate_url", AsyncMock())

    class FakeResponse:
        status_code = 302
        text = "sensitive response body"

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await client.send(
        url="https://hooks.example.com/path",
        body=b'{"secret":"do-not-log"}',
        headers={"Authorization": "Bearer hidden"},
        timeout_seconds=5,
    )

    assert result.success is False
    assert result.http_status == 302
    assert result.error_type == "http_status"
    assert result.error_message == "Endpoint returned HTTP 302"
    assert "sensitive" not in result.error_message


@pytest.mark.asyncio
async def test_send_reuses_client_until_closed(monkeypatch) -> None:
    created = 0
    posts = 0
    closed = 0

    class FakeResponse:
        status_code = 204

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            nonlocal created
            created += 1

        async def post(self, *_args, **_kwargs):
            nonlocal posts
            posts += 1
            return FakeResponse()

        async def aclose(self):
            nonlocal closed
            closed += 1

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = HttpWebhookClient()
    monkeypatch.setattr(client, "validate_url", AsyncMock())

    for _index in range(2):
        result = await client.send(
            url="https://hooks.example.com/path",
            body=b"{}",
            headers={},
            timeout_seconds=5,
        )
        assert result.success is True
    await client.aclose()

    assert created == 1
    assert posts == 2
    assert closed == 1


@pytest.mark.asyncio
async def test_send_enforces_total_request_deadline(monkeypatch) -> None:
    class SlowAsyncClient:
        async def post(self, *_args, **_kwargs):
            await asyncio.Event().wait()

        async def aclose(self):
            return None

    client = HttpWebhookClient()
    client._client = SlowAsyncClient()
    monkeypatch.setattr(client, "validate_url", AsyncMock())

    result = await client.send(
        url="https://hooks.example.com/path",
        body=b"{}",
        headers={},
        timeout_seconds=0.01,
    )

    assert result.success is False
    assert result.error_type == "timeout"
