"""
FlowKit Telecom Catalog HTTP client.

Lets OpenDesk act as a "Provider" in FlowKit's multi-trunk model: push
the SipTrunk table to FlowKit, keep the lease alive via heartbeat, and
delete cleanly on shutdown.

This is a separate channel from the WebSocket RPC (`client.py`): control
plane (catalog sync) goes over HTTP; data plane (call.* RPC, events)
stays on the WS. They share the same FlowKit port but different paths.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class TelecomAPIError(Exception):
    """FlowKit register API returned a non-2xx response."""

    def __init__(self, status: int, body: dict | str):
        super().__init__(f"telecom api {status}: {body}")
        self.status = status
        self.body = body


class FlowKitTelecomClient:
    """Thin HTTP wrapper over FlowKit's /api/v1/telecom/ register API.

    Owns its own httpx.AsyncClient with a short timeout — these calls are
    on the control path and must not stall the orchestrator.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        provider_id: str,
        timeout: float = 10.0,
    ) -> None:
        if not base_url or not api_key:
            raise ValueError("telecom_client requires base_url and api_key")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._provider_id = provider_id
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── Snapshot / heartbeat / delete ──

    async def put_snapshot(
        self,
        *,
        revision: int,
        lease_ttl_sec: int,
        stale_acceptable_sec: int,
        trunks: list[dict],
    ) -> dict:
        """Replace the FlowKit-side trunk set for this provider.

        Each trunk dict carries the FlowKit wire shape:
          { id, trunk_types[], status, peer_endpoints[], outbound? }
        """
        body = {
            "revision": revision,
            "lease_ttl_sec": lease_ttl_sec,
            "stale_acceptable_sec": stale_acceptable_sec,
            "trunks": trunks,
        }
        return await self._request(
            "PUT",
            f"/api/v1/telecom/registrars/{self._provider_id}/snapshot",
            json_body=body,
        )

    async def heartbeat(self, *, lease_ttl_sec: int | None = None) -> dict:
        body: dict[str, Any] = {}
        if lease_ttl_sec is not None:
            body["lease_ttl_sec"] = lease_ttl_sec
        return await self._request(
            "POST",
            f"/api/v1/telecom/registrars/{self._provider_id}/heartbeat",
            json_body=body,
        )

    async def delete(self) -> None:
        await self._request(
            "DELETE",
            f"/api/v1/telecom/registrars/{self._provider_id}",
            expect_json=False,
        )

    async def get_catalog(self) -> dict:
        return await self._request("GET", "/api/v1/telecom/catalog")

    # ── Internals ──

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        expect_json: bool = True,
    ) -> dict:
        url = self._base_url + path
        headers = {"X-API-Key": self._api_key}
        resp = await self._client.request(method, url, json=json_body, headers=headers)
        if resp.status_code >= 400:
            try:
                body: Any = resp.json()
            except ValueError:
                body = resp.text
            raise TelecomAPIError(resp.status_code, body)
        if not expect_json or not resp.content:
            return {}
        return resp.json()
