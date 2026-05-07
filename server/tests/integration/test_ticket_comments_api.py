"""
Integration tests for the ticket comments API.

Uses the real `/auth/login` flow to fetch a JWT that already encodes the
correct integer tenant PK and user id, instead of hand-crafting tokens with
the public tenant slug — that way the tests don't drift from production
auth behaviour.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.configs.settings import settings
from app.core.security import create_access_token, decode_access_token


TENANT_HEADERS = {"X-API-Key": settings.TENANT_API_KEY}


def _auth_header_from_token(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _spoofed_token(tenant_id: int, user_id: int, roles: list[str] | None = None) -> str:
    """Forge a token for a different ``user_id`` while keeping the real tenant PK.

    Used to assert ``author_id`` propagation without registering a second
    employee per test.
    """
    return create_access_token(
        {"sub": str(user_id), "tenant_id": tenant_id, "roles": roles or ["admin"]}
    )


async def _bootstrap_tenant(client: AsyncClient) -> dict:
    """Create a tenant + login → returns auth context for the new admin.

    Returns:
        ``{tenant_pk, tenant_slug, admin_id, admin_username, token, headers}``
    """
    suffix = uuid.uuid4().hex[:8]
    username = f"admin_{suffix}"
    password = "Passw0rd123"

    create_resp = await client.post(
        "/api/v1/tenants",
        headers=TENANT_HEADERS,
        json={
            "name": f"tenant_{suffix}",
            "admin_username": username,
            "admin_password": password,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    tenant_slug = create_resp.json()["id"]

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant_slug, "username": username, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    payload = login_resp.json()
    token = payload["access_token"]
    decoded = decode_access_token(token) or {}

    return {
        "tenant_pk": int(decoded["tenant_id"]),
        "tenant_slug": tenant_slug,
        "admin_id": payload["user"]["id"],
        "admin_username": username,
        "token": token,
        "headers": _auth_header_from_token(token),
    }


async def _create_ticket(client: AsyncClient, headers: dict) -> int:
    resp = await client.post(
        "/api/v1/tickets",
        headers=headers,
        json={"title": "T", "status": "open", "priority": "medium"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestTicketCommentsAPI:

    @pytest.mark.asyncio
    async def test_create_comment_with_body_returns_201(self, client: AsyncClient):
        ctx = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx["headers"])

        resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx["headers"],
            json={"body": "<p>hello <strong>world</strong></p>"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["ticket_id"] == ticket_id
        assert data["tenant_id"] == ctx["tenant_pk"]
        assert data["body"] == "<p>hello <strong>world</strong></p>"
        assert data["body_format"] == "html"
        assert data["attachments"] is None
        assert data["author_id"] == ctx["admin_id"]

    @pytest.mark.asyncio
    async def test_create_comment_with_attachments_only_returns_201(
        self, client: AsyncClient
    ):
        ctx = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx["headers"])

        resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx["headers"],
            json={
                "body": None,
                "attachments": [
                    {
                        "url": "https://example.com/a.pdf",
                        "name": "a.pdf",
                        "size": 1234,
                        "content_type": "application/pdf",
                    }
                ],
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["body"] is None
        assert isinstance(data["attachments"], list)
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["url"] == "https://example.com/a.pdf"
        assert data["attachments"][0]["name"] == "a.pdf"
        assert data["attachments"][0]["size"] == 1234
        assert data["attachments"][0]["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_create_comment_empty_body_and_attachments_returns_400(
        self, client: AsyncClient
    ):
        ctx = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx["headers"])

        resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx["headers"],
            json={"body": "   ", "attachments": []},
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_create_comment_too_many_attachments_returns_400(
        self, client: AsyncClient
    ):
        ctx = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx["headers"])

        attachments = [
            {"url": f"https://x/{i}.bin", "name": f"{i}.bin"} for i in range(11)
        ]
        resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx["headers"],
            json={"body": None, "attachments": attachments},
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_list_comments_returns_paginated_descending(
        self, client: AsyncClient
    ):
        ctx = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx["headers"])

        for i in range(3):
            resp = await client.post(
                f"/api/v1/tickets/{ticket_id}/comments",
                headers=ctx["headers"],
                json={"body": f"<p>msg {i}</p>"},
            )
            assert resp.status_code == 201, resp.text

        list_resp = await client.get(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx["headers"],
        )
        assert list_resp.status_code == 200, list_resp.text
        data = list_resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        ids = [item["id"] for item in data["items"]]
        assert ids == sorted(ids, reverse=True)

    @pytest.mark.asyncio
    async def test_list_comments_includes_author_name_from_employee(
        self, client: AsyncClient
    ):
        ctx = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx["headers"])

        resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx["headers"],
            json={"body": "<p>hello</p>"},
        )
        assert resp.status_code == 201, resp.text

        list_resp = await client.get(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx["headers"],
        )
        assert list_resp.status_code == 200, list_resp.text
        item = list_resp.json()["items"][0]
        assert isinstance(item["author_name"], str) and item["author_name"]
        # Default display falls back to username when no nickname/name is set.
        assert item["author_name"] == ctx["admin_username"]

    @pytest.mark.asyncio
    async def test_create_comment_records_explicit_author_id(
        self, client: AsyncClient
    ):
        """Tokens with a different ``sub`` should propagate as ``author_id``."""
        ctx = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx["headers"])

        spoof_token = _spoofed_token(ctx["tenant_pk"], user_id=99999)
        resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=_auth_header_from_token(spoof_token),
            json={"body": "<p>hi</p>"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["author_id"] == 99999

    @pytest.mark.asyncio
    async def test_create_comment_cross_tenant_returns_404(self, client: AsyncClient):
        ctx_a = await _bootstrap_tenant(client)
        ctx_b = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx_a["headers"])

        resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx_b["headers"],
            json={"body": "hi"},
        )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_list_comments_cross_tenant_returns_404(self, client: AsyncClient):
        ctx_a = await _bootstrap_tenant(client)
        ctx_b = await _bootstrap_tenant(client)
        ticket_id = await _create_ticket(client, ctx_a["headers"])

        resp = await client.get(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=ctx_b["headers"],
        )
        assert resp.status_code == 404, resp.text
