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


class TelephonyMethodNotFoundError(TelephonyRPCError):
    """The kernel does not expose this RPC method.

    Signalled by a JSON-RPC ``-32601 method not found`` response. Callers use
    it to detect a kernel that has an optional capability disabled (e.g. SIP
    extensions not enabled) and degrade gracefully instead of failing hard.
    """


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
    async def call_play(
        self,
        call_id: str,
        *,
        text: str | None = None,
        audio_url: str | None = None,
        audio: str | None = None,
        loop: bool = False,
        interval_ms: int | None = None,
        voice: str | None = None,
    ) -> dict:
        """Play a prompt tone on the call leg. Returns `{play_id, status}`.

        Supply exactly one of `text` (TTS), `audio_url` (a fetchable WAV URL —
        the kernel rejects other container formats) or `audio` (base64 WAV
        bytes, for a tone built in-process that needs no upload or reachable
        URL). `loop=True` with `interval_ms` repeats the prompt on that cadence
        until `call_stop(target="play")`. Used for hold/consult/three-party
        waiting tones on the customer leg; distinct from `call_say`, which is a
        one-shot spoken utterance in the voice-flow path.
        """

    @abstractmethod
    async def call_dtmf(
        self,
        call_id: str,
        digits: str,
        *,
        duration_ms: int | None = None,
    ) -> None: ...

    @abstractmethod
    async def call_bridge(
        self,
        call_id: str,
        other_call_id: str,
        transcribe: bool = True,
        *,
        keepalive_on_peer_hangup: bool = False,
    ) -> None:
        """Bridge two call legs.

        `transcribe` controls whether the media kernel runs live ASR on the
        bridged audio. When False, the kernel is told to skip transcription
        for this call; when True (default), transcription behaves as before.

        `keepalive_on_peer_hangup` keeps the surviving leg alive when the other
        side hangs up (consult A↔B). Default False matches two-party calls
        where either hangup ends both legs.
        """

    @abstractmethod
    async def call_connect_external_agent(
        self,
        call_id: str,
        *,
        provider: str,
        ws_url: str,
        token: str,
        audio_in_rate: int,
        audio_out_rate: int,
        traceparent: str | None = None,
        trace_call_id: str | None = None,
    ) -> None:
        """Bridge a call leg to an external realtime agent over WebSocket.

        The kernel opens a WS to `ws_url` (authenticated with `token`),
        resamples the caller's audio to `audio_in_rate` on the way out and the
        agent's audio to the call leg on the way back, and emits
        `call.external_agent.{connected,handoff,failed,ended}` events. Provider
        is kept generic (no VoiceSpeed business semantics) so other realtime
        agents can reuse this RPC.
        """

    @abstractmethod
    async def call_converse_external_agent(
        self,
        call_id: str,
        *,
        provider: str,
        turn_url: str,
        token: str,
        greeting: str | None = None,
        voice_spk_id: str | None = None,
        performance: dict | None = None,
        traceparent: str | None = None,
        trace_call_id: str | None = None,
    ) -> None:
        """Run a text-turn conversation on a call leg (v2 flowkit-中枢架构).

        Unlike `call_connect_external_agent` (which bridges raw audio), the
        kernel owns ASR/TTS/barge-in here and POSTs each transcribed utterance to
        `turn_url` (Bearer `token`), expecting `{reply, commands, voice_spk_id}`;
        it speaks the reply and emits the same
        `call.external_agent.{connected,handoff,failed,ended}` events. No audio
        leaves the kernel.

        ``performance`` is an optional VoiceSpeed dialog-timing override map
        (endpoint / turn / barge / TTS knobs). Omitted fields keep FlowKit env.
        """

    @abstractmethod
    async def call_unbridge(self, call_id: str, other_call_id: str) -> None: ...

    # ── Multi-party rooms (conference mixer) ──

    @abstractmethod
    async def room_create(self, *, leg_call_ids: list[str] | None = None) -> dict:
        """Create a mixing room. Returns `{room_id, legs}`.

        Any legs passed in `leg_call_ids` are added at creation time; the kernel
        automatically un-bridges those legs from any pairwise bridge and stops
        their TTS/ASR as it moves them into the mixer. Raises
        TelephonyMethodNotFoundError when the kernel has rooms disabled, so
        callers can degrade to a clear "not supported" instead of failing hard.
        """

    @abstractmethod
    async def room_add_leg(self, room_id: str, call_id: str) -> dict:
        """Add a call leg to an existing room."""

    @abstractmethod
    async def room_remove_leg(self, room_id: str, call_id: str) -> dict:
        """Remove a call leg from a room (the leg stays up, just un-mixed)."""

    @abstractmethod
    async def room_replace_leg(
        self, room_id: str, old_call_id: str, new_call_id: str
    ) -> dict:
        """Swap one leg for another inside a room."""

    @abstractmethod
    async def room_set_mix_gain(
        self, room_id: str, *, listener_call_id: str, speaker_call_id: str, gain: float
    ) -> dict:
        """Set how loudly `speaker_call_id` is mixed into `listener_call_id` (0..1)."""

    @abstractmethod
    async def room_close(self, room_id: str, *, reason: str | None = None) -> dict:
        """Close a room, un-mixing every remaining leg."""

    @abstractmethod
    async def call_hold(self, call_id: str) -> None: ...

    @abstractmethod
    async def call_unhold(self, call_id: str) -> None: ...

    @abstractmethod
    async def call_mute(self, call_id: str) -> None:
        """Silence what this leg sends, leaving the rest of the call running.

        Not hold: the party stays in the conversation and keeps hearing the
        other side, so this is accepted while bridged. Needed for an agent on
        a SIP handset, who has no local audio track for a console's mute
        button to switch off.
        """

    @abstractmethod
    async def call_unmute(self, call_id: str) -> None: ...

    @abstractmethod
    async def call_originate(
        self,
        uri: str | None = None,
        *,
        extension: str | None = None,
        caller_id: str | None = None,
        trunk_id: str | None = None,
        timeout_ms: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        """Start an outbound call. Returns `{call_id, conversation_id, status}`.

        - `uri`: destination (e.g. "13800138000" or "sip:1001@host:5060")
        - `extension`: instead of `uri`, dial a registered SIP extension by its
          number/AOR — the kernel resolves the current Contact and rings the
          physical phone directly (no trunk). Raises TelephonyRPCError
          `-32602 extension not registered` when the phone isn't registered.
        - `caller_id`: SIP From user-part (outbound DID); omitted → trunk default
        - `trunk_id`: which Trunk to route through; omitted → kernel default
          (system_outbound for single-trunk deployments)

        Errors mapped to TelephonyRPCError:
        - `-32602 trunk_id not found` / `trunk not ready for outbound`
        - `-32008 originate concurrent limit reached`
        """

    @abstractmethod
    async def extension_query(self, extension: str) -> dict:
        """Look up one registered extension.

        Returns `{extension, registered: bool, contact?}`. Raises
        TelephonyMethodNotFoundError when the kernel has extensions disabled.
        """

    @abstractmethod
    async def extension_list(self) -> list[dict]:
        """List currently registered extensions.

        Returns `[{extension, contact, expires_at, last_seen}]`. Raises
        TelephonyMethodNotFoundError when the kernel has extensions disabled.
        """

    @abstractmethod
    async def registrar_info(self) -> dict | None:
        """Return the SIP registrar endpoint `{host, port, transport}`.

        None when the kernel has no registrar configured. Raises
        TelephonyMethodNotFoundError when the kernel has extensions disabled.
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
