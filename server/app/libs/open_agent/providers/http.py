"""
HTTP OpenAgent client provider.
"""
from urllib.parse import urlparse

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.libs.open_agent.base import (
    BaseOpenAgentClient,
    OpenAgentAgentListResult,
    OpenAgentAgentSummary,
    OpenAgentClientError,
    OpenAgentConnectionResult,
)


class HTTPOpenAgentClient(BaseOpenAgentClient):
    timeout_seconds = 10.0

    async def test_connection(self, base_url: str, api_key: str) -> OpenAgentConnectionResult:
        """Call a lightweight read-only endpoint to verify connectivity."""
        url = self._build_agents_url(base_url)
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers, params={"page": 1, "per_page": 1})
        except httpx.RequestError as exc:
            return OpenAgentConnectionResult(False, f"OpenAgent connection failed: {exc}")

        if 200 <= response.status_code < 300:
            return OpenAgentConnectionResult(True, "Connection successful")

        message = self._extract_error_message(response)
        if response.status_code in {401, 403}:
            message = message or "OpenAgent API key is invalid or unauthorized"
        return OpenAgentConnectionResult(False, message or "OpenAgent connection test failed")

    async def list_agents(
        self,
        base_url: str,
        api_key: str,
        status_filter: str = "active",
        page: int = 1,
        per_page: int = 100,
    ) -> OpenAgentAgentListResult:
        """List agents through the configured OpenAgent HTTP API."""
        url = self._build_agents_url(base_url)
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {
            "status_filter": status_filter,
            "page": page,
            "per_page": per_page,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.RequestError as exc:
            raise OpenAgentClientError(f"OpenAgent agent list failed: {exc}") from exc

        if not 200 <= response.status_code < 300:
            message = self._extract_error_message(response)
            if response.status_code in {401, 403}:
                message = message or "OpenAgent API key is invalid or unauthorized"
            raise OpenAgentClientError(message or "OpenAgent agent list failed")

        payload = self._parse_json_object(response)
        raw_items = payload.get("items")
        items: list[OpenAgentAgentSummary] = []
        if isinstance(raw_items, list):
            for raw in raw_items:
                parsed = self._parse_agent(raw)
                if parsed:
                    items.append(parsed)

        return OpenAgentAgentListResult(
            items=items,
            total=self._safe_int(payload.get("total"), len(items)),
            page=self._safe_int(payload.get("page"), page),
            per_page=self._safe_int(payload.get("per_page"), per_page),
            pages=self._safe_int(payload.get("pages"), 1),
        )

    async def stream_chat(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """Proxy OpenAgent chat SSE without buffering the whole response."""
        url = self._build_chat_url(base_url, agent_id)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream",
        }

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if not 200 <= response.status_code < 300:
                        message = await self._extract_stream_error_message(response)
                        if response.status_code in {401, 403}:
                            message = message or "OpenAgent API key is invalid or unauthorized"
                        raise OpenAgentClientError(message or "OpenAgent chat failed")

                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
        except httpx.RequestError as exc:
            raise OpenAgentClientError(f"OpenAgent chat failed: {exc}") from exc

    async def stream_tool_result(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
        conversation_id: int,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """Proxy OpenAgent tool-results SSE without buffering the whole response."""
        url = self._build_tool_results_url(base_url, agent_id, conversation_id)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream",
        }

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if not 200 <= response.status_code < 300:
                        message = await self._extract_stream_error_message(response)
                        if response.status_code in {401, 403}:
                            message = message or "OpenAgent API key is invalid or unauthorized"
                        raise OpenAgentClientError(message or "OpenAgent tool result failed")

                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
        except httpx.RequestError as exc:
            raise OpenAgentClientError(f"OpenAgent tool result failed: {exc}") from exc

    @staticmethod
    def _build_agents_url(base_url: str) -> str:
        parsed = urlparse(base_url)
        suffix = "/agents" if parsed.path.rstrip("/").endswith("/api/v1") else "/api/v1/agents"
        return f"{base_url}{suffix}"

    @staticmethod
    def _build_chat_url(base_url: str, agent_id: int) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        if parsed.path.rstrip("/").endswith("/api/v1"):
            return f"{base}/agents/{agent_id}/chat"
        return f"{base}/api/v1/agents/{agent_id}/chat"

    @staticmethod
    def _build_tool_results_url(base_url: str, agent_id: int, conversation_id: int) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        if parsed.path.rstrip("/").endswith("/api/v1"):
            return f"{base}/agents/{agent_id}/conversations/{conversation_id}/tool-results"
        return f"{base}/api/v1/agents/{agent_id}/conversations/{conversation_id}/tool-results"

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return response.text[:200] if response.text else None

        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("detail") or payload.get("error")
            if isinstance(message, str):
                return message
        return None

    @staticmethod
    def _parse_json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenAgentClientError("OpenAgent returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise OpenAgentClientError("OpenAgent returned an unexpected response")
        return payload

    @staticmethod
    async def _extract_stream_error_message(response: httpx.Response) -> str | None:
        try:
            body = await response.aread()
        except httpx.HTTPError:
            return None
        if not body:
            return None
        text = body.decode("utf-8", errors="replace")
        try:
            payload = response.json()
        except ValueError:
            return text[:200]
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("detail") or payload.get("error")
            if isinstance(message, str):
                return message
        return text[:200]

    @staticmethod
    def _parse_agent(raw: Any) -> OpenAgentAgentSummary | None:
        if not isinstance(raw, dict):
            return None
        try:
            agent_id = int(raw["id"])
        except (KeyError, TypeError, ValueError):
            return None
        name = raw.get("name")
        status = raw.get("status")
        if not isinstance(name, str) or not isinstance(status, str):
            return None
        description = raw.get("description")
        return OpenAgentAgentSummary(
            id=agent_id,
            name=name,
            description=description if isinstance(description, str) else None,
            status=status,
        )

    @staticmethod
    def _safe_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
