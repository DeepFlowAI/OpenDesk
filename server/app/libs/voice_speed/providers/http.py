"""
HTTP VoiceSpeed client provider.
"""
from urllib.parse import urlparse

import httpx

from app.libs.voice_speed.base import (
    BaseVoiceSpeedClient,
    VoiceSpeedAgentListResult,
    VoiceSpeedAgentSummary,
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
