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
    OpenAgentAgentTool,
    OpenAgentClientError,
    OpenAgentConnectionResult,
    OpenAgentFeedbackResult,
    OpenAgentKnowledgeBaseListResult,
    OpenAgentKnowledgeBaseSummary,
    OpenAgentQaDirectory,
    OpenAgentQaDirectoryListResult,
    OpenAgentQaResult,
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
            raise OpenAgentClientError(
                message or "OpenAgent agent detail failed",
                status_code=response.status_code,
                code=self._extract_error_code(response),
            )

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
            ai_disclaimer=self._parse_agent_ai_disclaimer(payload),
            attachment_handoff_tool_id=self._parse_attachment_handoff_tool_id(payload),
        )

    async def get_agent_tool(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
        tool_id: int,
    ) -> OpenAgentAgentTool:
        """Get one OpenAgent tool used to validate attachment handoff configuration."""
        url = self._build_agent_tool_url(base_url, agent_id, tool_id)
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise OpenAgentClientError(f"OpenAgent agent tool lookup failed: {exc}") from exc

        if not 200 <= response.status_code < 300:
            message = self._extract_error_message(response)
            raise OpenAgentClientError(
                message or "OpenAgent agent tool lookup failed",
                status_code=response.status_code,
                code=self._extract_error_code(response),
            )

        payload = self._parse_json_object(response)
        try:
            parsed_id = int(payload["id"])
            parsed_agent_id = int(payload["agent_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenAgentClientError("OpenAgent returned an invalid agent tool") from exc
        name = payload.get("name")
        tool_type = payload.get("tool_type")
        if not isinstance(name, str) or not isinstance(tool_type, str):
            raise OpenAgentClientError("OpenAgent returned an invalid agent tool")
        return OpenAgentAgentTool(
            id=parsed_id,
            agent_id=parsed_agent_id,
            name=name,
            tool_type=tool_type,
            is_enabled=payload.get("is_enabled") is True,
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

    async def submit_feedback(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
        conversation_id: int,
        step_id: int,
        payload: dict[str, Any],
    ) -> OpenAgentFeedbackResult:
        url = self._build_step_feedback_url(base_url, agent_id, conversation_id, step_id)
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise OpenAgentClientError(f"OpenAgent feedback submit failed: {exc}") from exc

        if not 200 <= response.status_code < 300:
            message = self._extract_error_message(response)
            if response.status_code in {401, 403}:
                message = message or "OpenAgent API key is invalid or unauthorized"
            raise OpenAgentClientError(message or "OpenAgent feedback submit failed")

        data = self._parse_json_object(response)
        feedback = data.get("feedback") if isinstance(data.get("feedback"), dict) else data
        raw_comment = feedback.get("feedback_comment", feedback.get("comment"))
        raw_updated_at = feedback.get("feedback_updated_at") or feedback.get("updated_at")
        return OpenAgentFeedbackResult(
            step_id=self._safe_int(feedback.get("step_id"), step_id),
            rating=str(feedback.get("feedback_rating") or feedback.get("rating") or payload.get("rating") or ""),
            comment=raw_comment if isinstance(raw_comment, str) or raw_comment is None else payload.get("comment"),
            updated_at=raw_updated_at if isinstance(raw_updated_at, str) else None,
        )

    async def list_knowledge_bases(
        self,
        base_url: str,
        api_key: str,
        page: int = 1,
        per_page: int = 100,
    ) -> OpenAgentKnowledgeBaseListResult:
        """List one page of knowledge bases through the saved API key."""
        url = self._build_knowledge_bases_url(base_url)
        response = await self._request(
            "GET",
            url,
            api_key,
            operation="knowledge base list",
            params={"page": page, "per_page": per_page},
        )
        payload = self._parse_json_object(response)
        raw_items = payload.get("items")
        items: list[OpenAgentKnowledgeBaseSummary] = []
        if isinstance(raw_items, list):
            for raw in raw_items:
                parsed = self._parse_knowledge_base(raw)
                if parsed:
                    items.append(parsed)
        return OpenAgentKnowledgeBaseListResult(
            items=items,
            total=self._safe_int(payload.get("total"), len(items)),
            page=self._safe_int(payload.get("page"), page),
            per_page=self._safe_int(payload.get("per_page"), per_page),
            pages=self._safe_int(payload.get("pages"), 1),
        )

    async def list_qa_directories(
        self,
        base_url: str,
        api_key: str,
        knowledge_base_id: int,
    ) -> OpenAgentQaDirectoryListResult:
        """List QA directories for one knowledge base."""
        url = self._build_qa_directories_url(base_url, knowledge_base_id)
        response = await self._request(
            "GET",
            url,
            api_key,
            operation="QA directory list",
        )
        payload = self._parse_json_object(response)
        raw_items = payload.get("items")
        items: list[OpenAgentQaDirectory] = []
        if isinstance(raw_items, list):
            for raw in raw_items:
                parsed = self._parse_qa_directory(raw)
                if parsed:
                    items.append(parsed)
        return OpenAgentQaDirectoryListResult(
            items=items,
            total_qa_count=self._safe_int(payload.get("total_qa_count"), 0),
        )

    async def create_qa(
        self,
        base_url: str,
        api_key: str,
        knowledge_base_id: int,
        payload: dict[str, Any],
    ) -> OpenAgentQaResult:
        """Create a QA item and return its initial processing state."""
        url = self._build_qas_url(base_url, knowledge_base_id)
        response = await self._request(
            "POST",
            url,
            api_key,
            operation="QA create",
            json=payload,
        )
        data = self._parse_json_object(response)
        try:
            return OpenAgentQaResult(
                id=int(data["id"]),
                knowledge_base_id=int(data["knowledge_base_id"]),
                directory_id=int(data["directory_id"]),
                directory_path=self._string_list(data.get("directory_path")),
                question=str(data["question"]),
                answer_markdown=str(data["answer_markdown"]),
                enabled=bool(data.get("enabled", True)),
                access_keywords=self._string_list(data.get("access_keywords")),
                process_status=str(data.get("process_status") or "processing"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenAgentClientError("OpenAgent returned an unexpected QA response") from exc

    async def _request(
        self,
        method: str,
        url: str,
        api_key: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(method, url, headers=headers, params=params, json=json)
        except httpx.RequestError as exc:
            raise OpenAgentClientError(f"OpenAgent {operation} failed: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise OpenAgentClientError(
                self._extract_error_message(response) or f"OpenAgent {operation} failed",
                status_code=response.status_code,
                code=self._extract_error_code(response),
            )
        return response

    @staticmethod
    def _build_agents_url(base_url: str) -> str:
        parsed = urlparse(base_url)
        suffix = "/agents" if parsed.path.rstrip("/").endswith("/api/v1") else "/api/v1/agents"
        return f"{base_url}{suffix}"

    @staticmethod
    def _api_v1_url(base_url: str, path: str) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        if parsed.path.rstrip("/").endswith("/api/v1"):
            return f"{base}/{path.lstrip('/')}"
        return f"{base}/api/v1/{path.lstrip('/')}"

    @staticmethod
    def _build_knowledge_bases_url(base_url: str) -> str:
        return HTTPOpenAgentClient._api_v1_url(base_url, "knowledge-bases")

    @staticmethod
    def _build_qa_directories_url(base_url: str, knowledge_base_id: int) -> str:
        return HTTPOpenAgentClient._api_v1_url(
            base_url,
            f"knowledge-bases/{knowledge_base_id}/qa-directories",
        )

    @staticmethod
    def _build_qas_url(base_url: str, knowledge_base_id: int) -> str:
        return HTTPOpenAgentClient._api_v1_url(
            base_url,
            f"knowledge-bases/{knowledge_base_id}/qas",
        )

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
    def _build_agent_tool_url(base_url: str, agent_id: int, tool_id: int) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/api/v1"):
            return f"{base}/agents/{agent_id}/tools/{tool_id}"
        return f"{base}/api/v1/agents/{agent_id}/tools/{tool_id}"

    @staticmethod
    def _build_step_feedback_url(base_url: str, agent_id: int, conversation_id: int, step_id: int) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        path = f"/agents/{agent_id}/conversations/{conversation_id}/steps/{step_id}/feedback"
        if parsed.path.rstrip("/").endswith("/api/v1"):
            return f"{base}{path}"
        return f"{base}/api/v1{path}"

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
    def _extract_error_code(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict) and isinstance(payload.get("code"), str):
            return payload["code"]
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
    def _parse_attachment_handoff_tool_id(raw: dict[str, Any]) -> int | None:
        engine_config = raw.get("engine_config")
        if not isinstance(engine_config, dict):
            return None
        value = engine_config.get("attachment_handoff_tool_id")
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _parse_knowledge_base(raw: Any) -> OpenAgentKnowledgeBaseSummary | None:
        if not isinstance(raw, dict):
            return None
        try:
            knowledge_base_id = int(raw["id"])
        except (KeyError, TypeError, ValueError):
            return None
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        description = raw.get("description")
        status = raw.get("status")
        return OpenAgentKnowledgeBaseSummary(
            id=knowledge_base_id,
            name=name,
            description=description if isinstance(description, str) else None,
            status=status if isinstance(status, str) else "active",
        )

    @staticmethod
    def _parse_qa_directory(raw: Any) -> OpenAgentQaDirectory | None:
        if not isinstance(raw, dict):
            return None
        try:
            directory_id = int(raw["id"])
        except (KeyError, TypeError, ValueError):
            return None
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        raw_parent_id = raw.get("parent_id")
        parent_id = None if raw_parent_id is None else HTTPOpenAgentClient._safe_int(raw_parent_id, 0) or None
        return OpenAgentQaDirectory(
            id=directory_id,
            parent_id=parent_id,
            name=name,
            sort_order=HTTPOpenAgentClient._safe_int(raw.get("sort_order"), 0),
            depth=HTTPOpenAgentClient._safe_int(raw.get("depth"), 1),
            path=HTTPOpenAgentClient._string_list(raw.get("path")),
        )

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

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
    def _parse_agent_ai_disclaimer(raw: dict[str, Any]) -> dict[str, Any] | None:
        engine_config = raw.get("engine_config")
        if not isinstance(engine_config, dict):
            return None
        conversation_settings = engine_config.get("conversation_settings")
        if not isinstance(conversation_settings, dict):
            return None
        disclaimer = conversation_settings.get("ai_disclaimer")
        if not isinstance(disclaimer, dict):
            return None

        content = disclaimer.get("content")
        return {
            "enabled": bool(disclaimer.get("enabled")),
            "content": content.strip() if isinstance(content, str) else "",
        }

    @staticmethod
    def _safe_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
