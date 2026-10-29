"""
HTTP VoiceSpeed client provider.
"""
from urllib.parse import quote, urlparse

import httpx

from app.libs.voice_speed.base import (
    BaseVoiceSpeedClient,
    VoiceSpeedAgentListResult,
    VoiceSpeedAgentSummary,
    VoiceSpeedCallTranscript,
    VoiceSpeedCallTranscriptMessage,
    VoiceSpeedClientError,
    VoiceSpeedConnectionResult,
    VoiceSpeedRealtimeSession,
)


class HTTPVoiceSpeedClient(BaseVoiceSpeedClient):
    timeout_seconds = 10.0
    # Short timeout for the agent-list proxy so a slow VoiceSpeed never stalls
    # the editor's agent picker.
    list_timeout_seconds = 3.0

    async def test_connection(self, base_url: str, api_key: str) -> VoiceSpeedConnectionResult:
        """Call a lightweight read-only OpenAPI endpoint to verify connectivity."""
        url = self._build_agents_url(base_url)
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers, params={"page": 1, "per_page": 1})
        except httpx.RequestError:
            return VoiceSpeedConnectionResult(False, "无法连接 VoiceSpeed，请检查服务地址和网络")

        if 200 <= response.status_code < 300:
            return VoiceSpeedConnectionResult(True, "VoiceSpeed 连接成功")

        message = self._extract_error_message(response)
        return VoiceSpeedConnectionResult(False, self._map_error_message(response.status_code, message))

    async def list_agents(
        self,
        base_url: str,
        api_key: str,
        status: str = "enabled",
    ) -> VoiceSpeedAgentListResult:
        """List agents through the VoiceSpeed OpenAPI, keeping only safe fields."""
        url = self._build_agents_url(base_url)
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self.list_timeout_seconds) as client:
                response = await client.get(url, headers=headers, params={"status": status})
        except httpx.RequestError as exc:
            raise VoiceSpeedClientError("无法连接 VoiceSpeed，请检查服务地址和网络") from exc

        if not 200 <= response.status_code < 300:
            message = self._extract_error_message(response)
            raise VoiceSpeedClientError(
                self._map_error_message(response.status_code, message),
                status_code=response.status_code,
            )

        return VoiceSpeedAgentListResult(items=self._parse_agents(response))

    async def mint_realtime_session(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
        *,
        external_id: str,
        trace_id: str | None = None,
        traceparent: str | None = None,
    ) -> VoiceSpeedRealtimeSession:
        """POST to the realtime-sessions endpoint and return the minted token."""
        url = self._build_realtime_sessions_url(base_url, agent_id)
        headers = {"Authorization": f"Bearer {api_key}"}
        if traceparent:
            headers["traceparent"] = traceparent
        body: dict = {"external_id": external_id}
        if trace_id:
            body["trace_id"] = trace_id

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=body)
        except httpx.RequestError as exc:
            raise VoiceSpeedClientError("无法连接 VoiceSpeed，请检查服务地址和网络") from exc

        if not 200 <= response.status_code < 300:
            message = self._extract_error_message(response)
            raise VoiceSpeedClientError(
                self._map_error_message(response.status_code, message),
                status_code=response.status_code,
            )

        return self._parse_realtime_session(response)

    async def get_performance_settings(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
    ) -> dict:
        """GET agent performance-settings; empty/missing knobs → {}."""
        url = self._build_performance_settings_url(base_url, agent_id)
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.list_timeout_seconds) as client:
                response = await client.get(url, headers=headers)
        except httpx.RequestError:
            return {}
        if not 200 <= response.status_code < 300:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {k: v for k, v in payload.items() if v is not None}

    async def preset_call_variables(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
        call_id: str,
        variables: dict[str, str],
    ) -> None:
        """PUT the call's variable values; VoiceSpeed reads them on the first turn."""
        url = self._build_call_variables_url(base_url, agent_id, call_id)
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.list_timeout_seconds) as client:
                response = await client.put(url, headers=headers, json={"variables": variables})
        except httpx.RequestError as exc:
            raise VoiceSpeedClientError("无法连接 VoiceSpeed，请检查服务地址和网络") from exc

        if not 200 <= response.status_code < 300:
            raise VoiceSpeedClientError(
                self._extract_error_message(response) or "VoiceSpeed 通话变量传入失败",
                status_code=response.status_code,
            )

    async def get_call_opening(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
        *,
        session_id: str,
        fallback_greeting: str,
        user_identifier: str | None = None,
    ) -> dict:
        """POST call-opening; any failure (including a VoiceSpeed without this
        endpoint) falls back to speaking ``fallback_greeting``."""
        fallback = {"greeting": fallback_greeting, "opening": ""}
        url = self._build_call_opening_url(base_url, agent_id)
        headers = {"Authorization": f"Bearer {api_key}"}
        body = {"session_id": session_id, "fallback_greeting": fallback_greeting}
        if user_identifier:
            body["user_identifier"] = user_identifier
        try:
            async with httpx.AsyncClient(timeout=self.list_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=body)
        except httpx.RequestError:
            return fallback
        if not 200 <= response.status_code < 300:
            return fallback
        try:
            payload = response.json()
        except ValueError:
            return fallback
        if not isinstance(payload, dict):
            return fallback
        return {
            "greeting": str(payload.get("greeting") or ""),
            "opening": str(payload.get("opening") or ""),
            "voice_spk_id": str(payload.get("voice_spk_id") or ""),
        }

    async def get_call_transcript(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
        call_id: str,
    ) -> VoiceSpeedCallTranscript:
        """GET the robot-stage transcript. 3s timeout so a slow VoiceSpeed
        never blocks the ringing screen-pop."""
        url = self._build_call_transcript_url(base_url, agent_id, call_id)
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.list_timeout_seconds) as client:
                response = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise VoiceSpeedClientError("无法连接 VoiceSpeed，请检查服务地址和网络") from exc

        if not 200 <= response.status_code < 300:
            message = self._extract_error_message(response)
            raise VoiceSpeedClientError(
                self._map_error_message(response.status_code, message),
                status_code=response.status_code,
            )
        return self._parse_call_transcript(response, call_id)

    @staticmethod
    def _parse_call_transcript(
        response: httpx.Response, fallback_call_id: str
    ) -> VoiceSpeedCallTranscript:
        try:
            payload = response.json()
        except ValueError as exc:
            raise VoiceSpeedClientError("VoiceSpeed 返回了无法解析的响应") from exc
        if not isinstance(payload, dict):
            raise VoiceSpeedClientError("VoiceSpeed 返回了无法解析的响应")

        agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
        handoff = payload.get("handoff") if isinstance(payload.get("handoff"), dict) else None
        handoff_at = None
        if handoff:
            raw = handoff.get("handoff_at")
            handoff_at = str(raw) if raw else None

        messages: list[VoiceSpeedCallTranscriptMessage] = []
        raw_messages = payload.get("messages")
        if isinstance(raw_messages, list):
            for raw in raw_messages:
                if not isinstance(raw, dict):
                    continue
                role = str(raw.get("role") or "")
                content = raw.get("content")
                if role not in {"user", "assistant"} or not isinstance(content, str):
                    continue
                heard = raw.get("heard_content")
                messages.append(
                    VoiceSpeedCallTranscriptMessage(
                        role=role,
                        content=content,
                        interrupted=bool(raw.get("interrupted")),
                        heard_content=heard if isinstance(heard, str) else None,
                    )
                )

        return VoiceSpeedCallTranscript(
            call_id=str(payload.get("call_id") or fallback_call_id),
            agent_id=str(agent.get("id") or ""),
            agent_name=str(agent.get("name") or ""),
            handoff_at=handoff_at,
            messages=messages,
        )

    @staticmethod
    def _parse_realtime_session(response: httpx.Response) -> VoiceSpeedRealtimeSession:
        try:
            payload = response.json()
        except ValueError as exc:
            raise VoiceSpeedClientError("VoiceSpeed 返回了无法解析的响应") from exc
        if not isinstance(payload, dict):
            raise VoiceSpeedClientError("VoiceSpeed 返回了无法解析的响应")

        ws_url = payload.get("ws_url")
        token = payload.get("token")
        if not ws_url or not token:
            raise VoiceSpeedClientError("VoiceSpeed 实时会话响应缺少 ws_url 或 token")

        audio_in = payload.get("audio_in") if isinstance(payload.get("audio_in"), dict) else {}
        audio_out = payload.get("audio_out") if isinstance(payload.get("audio_out"), dict) else {}
        expires_at = payload.get("expires_at")
        return VoiceSpeedRealtimeSession(
            session_id=str(payload.get("session_id") or ""),
            ws_url=str(ws_url),
            token=str(token),
            expires_at=str(expires_at) if expires_at else None,
            audio_in=audio_in,
            audio_out=audio_out,
        )

    @staticmethod
    def _parse_agents(response: httpx.Response) -> list[VoiceSpeedAgentSummary]:
        try:
            payload = response.json()
        except ValueError:
            return []

        raw_items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            return []

        agents: list[VoiceSpeedAgentSummary] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            raw_id = raw.get("id")
            name = raw.get("name")
            if raw_id is None or name is None:
                continue
            description = raw.get("description")
            agents.append(
                VoiceSpeedAgentSummary(
                    id=str(raw_id),
                    name=str(name),
                    description=str(description) if description is not None else None,
                    status=str(raw.get("status") or ""),
                )
            )
        return agents

    @staticmethod
    def _build_agents_url(base_url: str) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        path = parsed.path.rstrip("/")
        if path.endswith("/api/v1/openapi"):
            return f"{base}/agents"
        if path.endswith("/api/v1"):
            return f"{base}/openapi/agents"
        return f"{base}/api/v1/openapi/agents"

    @staticmethod
    def _build_realtime_sessions_url(base_url: str, agent_id: str) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        path = parsed.path.rstrip("/")
        suffix = f"agents/{agent_id}/realtime-sessions"
        if path.endswith("/api/v1/openapi"):
            return f"{base}/{suffix}"
        if path.endswith("/api/v1"):
            return f"{base}/openapi/{suffix}"
        return f"{base}/api/v1/openapi/{suffix}"

    @staticmethod
    def _build_performance_settings_url(base_url: str, agent_id: str) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        path = parsed.path.rstrip("/")
        suffix = f"agents/{agent_id}/performance-settings"
        if path.endswith("/api/v1/openapi"):
            return f"{base}/{suffix}"
        if path.endswith("/api/v1"):
            return f"{base}/openapi/{suffix}"
        return f"{base}/api/v1/openapi/{suffix}"

    @staticmethod
    def _build_call_variables_url(base_url: str, agent_id: str, call_id: str) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        path = parsed.path.rstrip("/")
        suffix = f"agents/{quote(agent_id, safe='')}/calls/{quote(call_id, safe='')}/variables"
        if path.endswith("/api/v1/openapi"):
            return f"{base}/{suffix}"
        if path.endswith("/api/v1"):
            return f"{base}/openapi/{suffix}"
        return f"{base}/api/v1/openapi/{suffix}"

    @staticmethod
    def _build_call_opening_url(base_url: str, agent_id: str) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        path = parsed.path.rstrip("/")
        suffix = f"agents/{quote(agent_id, safe='')}/call-opening"
        if path.endswith("/api/v1/openapi"):
            return f"{base}/{suffix}"
        if path.endswith("/api/v1"):
            return f"{base}/openapi/{suffix}"
        return f"{base}/api/v1/openapi/{suffix}"

    @staticmethod
    def _build_call_transcript_url(base_url: str, agent_id: str, call_id: str) -> str:
        parsed = urlparse(base_url)
        base = base_url.rstrip("/")
        path = parsed.path.rstrip("/")
        suffix = (
            f"agents/{quote(agent_id, safe='')}/calls/{quote(call_id, safe='')}/transcript"
        )
        if path.endswith("/api/v1/openapi"):
            return f"{base}/{suffix}"
        if path.endswith("/api/v1"):
            return f"{base}/openapi/{suffix}"
        return f"{base}/api/v1/openapi/{suffix}"

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
    def _map_error_message(status_code: int, message: str | None) -> str:
        normalized = (message or "").lower()
        if status_code == 401:
            return "VoiceSpeed API 密钥无效或已失效"
        if status_code == 403:
            return "VoiceSpeed API 密钥缺少配置管理权限，请在 VoiceSpeed 中为该密钥勾选 config 权限范围"
        if status_code in {402, 423} or "tenant" in normalized or "租户" in normalized:
            return "VoiceSpeed 租户不可用，请检查 VoiceSpeed 租户状态"
        if status_code in {404, 502, 503, 504}:
            return "无法连接 VoiceSpeed，请检查服务地址和网络"
        return message or "无法连接 VoiceSpeed，请检查服务地址和网络"
