"""
HTTP VoiceSpeed client provider.
"""
from urllib.parse import urlparse

import httpx

from app.libs.voice_speed.base import BaseVoiceSpeedClient, VoiceSpeedConnectionResult


class HTTPVoiceSpeedClient(BaseVoiceSpeedClient):
    timeout_seconds = 10.0

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
