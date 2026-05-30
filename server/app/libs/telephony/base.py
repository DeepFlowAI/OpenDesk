"""
Base interfaces for the call-center Telephony abstraction.

A "telephony client" owns the control plane to a media kernel. The kernel
handles SIP, RTP, WebRTC, TTS, ASR; this client just sends RPC commands
("answer this call", "play that prompt") and receives events ("call.dtmf",
"call.hangup").

Implementations live in `providers/`. Service-layer code MUST depend only
on `BaseTelephonyClient` and acquire instances via `get_telephony_client()`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


# ───────────────────── Errors ─────────────────────


class TelephonyError(Exception):
    """Base for all telephony-related errors raised by clients."""


class TelephonyRPCError(TelephonyError):
    """Server returned a JSON-RPC error response."""

    def __init__(self, code: int, message: str, data: dict | None = None):
        super().__init__(f"RPC {code}: {message}")
        self.code = code
        self.data = data


class TelephonyNotConnectedError(TelephonyError):
    """Raised when calling an RPC before the client is connected."""


# ───────────────────── Events ─────────────────────


@dataclass(frozen=True)
class CallEvent:
    """A notification pushed by the kernel.

    `method` mirrors the JSON-RPC notification method (e.g. "call.incoming",
    "call.dtmf", "webrtc.ice"). `data` is the raw `params` dict.
    """

    method: str
    data: dict


EventHandler = Callable[[CallEvent], Awaitable[None]]
ReconnectHandler = Callable[[], Awaitable[None]]


# ───────────────────── Base client ─────────────────────


class BaseTelephonyClient(ABC):
    """Contract every telephony provider must implement."""

    # ── Lifecycle ──

    @abstractmethod
    async def connect(self) -> None:
        """Open the control channel and complete handshake."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the control channel and stop background tasks."""

    @abstractmethod
    async def wait_until_ready(self, timeout: float = 30.0) -> None:
        """Block until the client is ready to send RPCs (i.e. hello complete)."""

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """True if the control channel is open and handshake completed."""

    # ── Event subscription ──

    @abstractmethod
    def on_event(self, method: str, handler: EventHandler) -> None:
        """Register a handler for kernel-pushed notifications.

        Multiple handlers for the same method are supported and invoked
        concurrently. `method` matches the JSON-RPC notification method
        verbatim (e.g. "call.incoming").
        """

    @abstractmethod
    def off_event(self, method: str, handler: EventHandler) -> None:
        """Unregister a previously-registered handler."""

    @abstractmethod
    def on_reconnected(self, handler: ReconnectHandler) -> None:
        """Register a handler invoked after a successful reconnect.

        Orchestrators typically use this to re-issue `call_list()` and
        recover state for active calls that may have moved during the
        disconnect window.
        """

    # ── Call control ──

    @abstractmethod
    async def call_answer(self, call_id: str) -> None: ...

    @abstractmethod
    async def call_hangup(self, call_id: str, reason: str | None = None) -> None: ...

    @abstractmethod
    async def call_say(
        self,
        call_id: str,
        text: str,
        *,
        voice: str | None = None,
        barge_in: bool | None = None,
    ) -> str:
        """Speak `text` on the call. Returns `play_id`."""

    @abstractmethod
    async def call_listen(self, call_id: str, *, timeout_ms: int | None = None) -> None: ...

    @abstractmethod
    async def call_stop(self, call_id: str, *, target: str = "all") -> None:
        """Stop play/listen/both on the call. `target` ∈ {play, listen, all}."""

    @abstractmethod
    async def call_dtmf(
        self,
        call_id: str,
        digits: str,
        *,
        duration_ms: int | None = None,
    ) -> None: ...

    @abstractmethod
    async def call_bridge(self, call_id: str, other_call_id: str) -> None: ...

    @abstractmethod
    async def call_unbridge(self, call_id: str, other_call_id: str) -> None: ...

    @abstractmethod
    async def call_hold(self, call_id: str) -> None: ...

    @abstractmethod
    async def call_unhold(self, call_id: str) -> None: ...

    @abstractmethod
    async def call_originate(
        self,
        uri: str,
        *,
        caller_id: str | None = None,
        trunk_id: str | None = None,
        timeout_ms: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        """Start an outbound call. Returns `{call_id, conversation_id, status}`.

        - `uri`: destination (e.g. "13800138000" or "sip:1001@host:5060")
        - `caller_id`: SIP From user-part (outbound DID); omitted → trunk default
        - `trunk_id`: which Trunk to route through; omitted → kernel default
          (system_outbound for single-trunk deployments)

        Errors mapped to TelephonyRPCError:
        - `-32602 trunk_id not found` / `trunk not ready for outbound`
        - `-32008 originate concurrent limit reached`
        """

    @abstractmethod
    async def call_list(self) -> list[dict]:
        """Return all active calls. Used to recover after orchestrator restart."""

    # ── WebRTC signaling (agent browser) ──

    @abstractmethod
    async def webrtc_offer(self, sdp: str, call_id: str | None = None) -> dict:
        """Forward a browser SDP offer; returns `{call_id, sdp}` (answer)."""

    @abstractmethod
    async def webrtc_ice(self, call_id: str, candidate: dict) -> None: ...
