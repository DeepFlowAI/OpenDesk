"""
HTTP OpenAgent client provider.
"""
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx

from app.libs.open_agent.base import (
    BaseOpenAgentClient,
    OpenAgentAgentDetail,
    OpenAgentAgentListResult,
    OpenAgentAgentSummary,
    OpenAgentClientError,
    OpenAgentConnectionResult,
)


# Streaming SSE proxy timeout: bound connect/write/pool so a hung upstream
# cannot exhaust connections, but leave read unbounded so long-lived event
# streams are not cut off mid-response.
_STREAM_TIMEOUT = httpx.Timeout(None, connect=10.0, write=10.0, pool=10.0)


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

    async def get_agent(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
    ) -> OpenAgentAgentDetail:
        """Get one agent through the configured OpenAgent HTTP API."""
        url = self._build_agent_detail_url(base_url, agent_id)
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise OpenAgentClientError(f"OpenAgent agent detail failed: {exc}") from exc

        if not 200 <= response.status_code < 300:
            message = self._extract_error_message(response)
            if response.status_code in {401, 403}:
                message = message or "OpenAgent API key is invalid or unauthorized"
            raise OpenAgentClientError(message or "OpenAgent agent detail failed")

        payload = self._parse_json_object(response)
        parsed = self._parse_agent(payload)
        if not parsed:
            raise OpenAgentClientError("OpenAgent returned an unexpected agent detail response")

        return OpenAgentAgentDetail(
            id=parsed.id,
            name=parsed.name,
            description=parsed.description,
            status=parsed.status,
            welcome_message=self._parse_agent_welcome_message(payload),
            faq=self._parse_agent_faq(payload),
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
            async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
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
            async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
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
    def _build_agent_detail_url(base_url: str, agent_id: int) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        if parsed.path.rstrip("/").endswith("/api/v1"):
            return f"{base}/agents/{agent_id}"
        return f"{base}/api/v1/agents/{agent_id}"

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
    def _parse_agent_welcome_message(raw: dict[str, Any]) -> dict[str, Any] | None:
        engine_config = raw.get("engine_config")
        if not isinstance(engine_config, dict):
            return None
        conversation_settings = engine_config.get("conversation_settings")
        if not isinstance(conversation_settings, dict):
            return None
        welcome = conversation_settings.get("welcome_message")
        if not isinstance(welcome, dict):
            return None

        blocks: list[dict[str, Any]] = []
        raw_blocks = welcome.get("blocks")
        if isinstance(raw_blocks, list):
            for raw_block in raw_blocks:
                if not isinstance(raw_block, dict):
                    continue
                if raw_block.get("type") == "markdown":
                    blocks.append(
                        {
                            "type": "markdown",
                            "content": raw_block.get("content")
                            if isinstance(raw_block.get("content"), str)
                            else "",
                        }
                    )
                elif raw_block.get("type") == "embed":
                    blocks.append(
                        {
                            "type": "embed",
                            "embed_code": raw_block.get("embed_code")
                            if isinstance(raw_block.get("embed_code"), str)
                            else "",
                            "height": HTTPOpenAgentClient._safe_int(raw_block.get("height"), 360),
                        }
                    )

        return {
            "enabled": bool(welcome.get("enabled")),
            "blocks": blocks,
        }

    @staticmethod
    def _parse_agent_faq(raw: dict[str, Any]) -> dict[str, Any] | None:
        engine_config = raw.get("engine_config")
        if not isinstance(engine_config, dict):
            return None
        conversation_settings = engine_config.get("conversation_settings")
        if not isinstance(conversation_settings, dict):
            return None
        faq = conversation_settings.get("faq")
        if not isinstance(faq, dict):
            return None

        categories: list[dict[str, Any]] = []
        raw_categories = faq.get("categories")
        if isinstance(raw_categories, list):
            for raw_category in raw_categories:
                if not isinstance(raw_category, dict):
                    continue
                name = raw_category.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue

                questions: list[dict[str, str]] = []
                raw_questions = raw_category.get("questions")
                if isinstance(raw_questions, list):
                    for raw_question in raw_questions:
                        if not isinstance(raw_question, dict):
                            continue
                        text = raw_question.get("text")
                        if isinstance(text, str) and text.strip():
                            questions.append({"text": text.strip()})

                if questions:
                    categories.append({"name": name.strip(), "questions": questions})

        title = faq.get("title")
        return {
            "enabled": bool(faq.get("enabled")),
            "title": title.strip() if isinstance(title, str) and title.strip() else "常见问题",
            "categories": categories,
        }

    @staticmethod
    def _safe_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
