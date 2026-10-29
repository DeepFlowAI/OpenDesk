"""
Abstract base class for VoiceSpeed clients.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse


class VoiceSpeedClientError(Exception):
    """Raised when VoiceSpeed API calls fail."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class VoiceSpeedConnectionResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class VoiceSpeedAgentSummary:
    id: str
    name: str
    description: str | None
    status: str


@dataclass(frozen=True)
class VoiceSpeedAgentListResult:
    items: list[VoiceSpeedAgentSummary]


@dataclass(frozen=True)
class VoiceSpeedCallTranscriptMessage:
    role: str
    content: str
    interrupted: bool = False
    heard_content: str | None = None


@dataclass(frozen=True)
class VoiceSpeedCallTranscript:
    call_id: str
    agent_id: str
    agent_name: str
    handoff_at: str | None
    messages: list[VoiceSpeedCallTranscriptMessage]


@dataclass(frozen=True)
class VoiceSpeedRealtimeSession:
    """Short-lived realtime session minted for one phone call.

    `audio_in` / `audio_out` describe the PCM codec/sample-rate the media
    kernel must pump in each direction (e.g. {"codec": "pcm16",
    "sample_rate": 16000, "channels": 1}).
    """

    session_id: str
    ws_url: str
    token: str
    expires_at: str | None
    audio_in: dict
    audio_out: dict


class BaseVoiceSpeedClient(ABC):

    @staticmethod
    def build_turn_url(base_url: str, agent_id: str) -> str:
        """URL of an agent's streaming text-turn endpoint (v2 flowkit-中枢架构).

        flowkit owns the call leg and POSTs each transcribed utterance here,
        consuming the reply as an SSE ``data: {"type":"delta","text":...}``
        stream (``/turn/stream``) so TTS can start mid-reply. The non-streaming
        ``/turn`` returns plain JSON, which flowkit's SSE reader can't parse —
        it must be the ``/stream`` variant. Mirrors the same base-path rules as
        the realtime-sessions endpoint.
        """
        path = urlparse(base_url).path.rstrip("/")
        base = base_url.rstrip("/")
        suffix = f"agents/{agent_id}/turn/stream"
        if path.endswith("/api/v1/openapi"):
            return f"{base}/{suffix}"
        if path.endswith("/api/v1"):
            return f"{base}/openapi/{suffix}"
        return f"{base}/api/v1/openapi/{suffix}"

    @abstractmethod
    async def test_connection(self, base_url: str, api_key: str) -> VoiceSpeedConnectionResult:
        """Test whether VoiceSpeed accepts the provided API key."""
        ...

    @abstractmethod
    async def list_agents(
        self,
        base_url: str,
        api_key: str,
        status: str = "enabled",
    ) -> VoiceSpeedAgentListResult:
        """List VoiceSpeed agents available to the provided API key."""
        ...

    @abstractmethod
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
        """Exchange the API key for a one-time realtime session token.

        `external_id` is the business call id VoiceSpeed echoes back on its
        side; `trace_id` / `traceparent` continue the W3C trace so the whole
        call shares one trace across services.
        """
        ...

    async def get_performance_settings(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
    ) -> dict:
        """Fetch agent dialog-timing knobs for FlowKit (empty dict = no override).

        Default no-op so mock/test clients need not implement it.
        """
        return {}

    async def preset_call_variables(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
        call_id: str,
        variables: dict[str, str],
    ) -> None:
        """Store `{{name}}` values for one call before its first dialog turn.

        Raises VoiceSpeedClientError on any failure. Clients that cannot preset
        variables inherit this default, which always fails.
        """
        raise VoiceSpeedClientError("Call variable preset is not supported")

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
        """Resolve how the agent opens this call: ``{"greeting", "opening"}``
        plus an optional ``voice_spk_id``, passed as-is to converse. ``fallback_greeting`` is used when the agent
        has no opening configured. ``user_identifier`` (the customer's number)
        is shown on the agent's session record.

        Default returns the fallback so mock/test clients need not implement it.
        """
        return {"greeting": fallback_greeting, "opening": ""}

    async def get_call_transcript(
        self,
        base_url: str,
        api_key: str,
        agent_id: str,
        call_id: str,
    ) -> VoiceSpeedCallTranscript:
        """Read the robot-stage transcript for one VoiceSpeed call.

        Raises VoiceSpeedClientError on any failure, including 404. Default
        always fails so mock clients that do not implement it stay explicit.
        """
        raise VoiceSpeedClientError("Call transcript is not supported")
