"""
In-process mock telephony client.

Used by:
- Local dev when no FlowKit kernel is reachable
- Unit tests of the orchestrator and node executors

The mock records every RPC call into `recorded` so tests can assert on
control-plane behavior without needing a real WS server.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from typing import Any

from app.libs.telephony.base import (
    BaseTelephonyClient,
    CallEvent,
    EventHandler,
    ReconnectHandler,
    TelephonyRPCError,
)


class MockTelephonyClient(BaseTelephonyClient):

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._reconnect_handlers: list[ReconnectHandler] = []
        self._ready = asyncio.Event()
        self.recorded: list[tuple[str, dict[str, Any]]] = []
        # Test injection slot: tests can preset webrtc.offer answer SDP / call_id
        self.webrtc_offer_response: dict = {"call_id": "mock-webrtc-call", "sdp": "v=0\r\n"}
        # Test injection slots for simulating FlowKit RPC errors (e.g. -32002
        # "call not found" when a leg is already gone). `bridge_error` is raised
        # by call_bridge; `hangup_errors` maps a call_id → exception for call_hangup.
        self.bridge_error: Exception | None = None
        self.hangup_errors: dict[str, Exception] = {}
        self.call_list_response: list[dict] = []
        self.originate_response: dict = {
            "call_id": "mock-out-call",
            "conversation_id": "mock-conv",
            "status": "originating",
        }
        # Test injection slots for the SIP-extension RPCs. Set `*_error` to an
        # exception (e.g. TelephonyMethodNotFoundError) to simulate a kernel
        # with extensions disabled.
        self.extension_query_response: dict = {"extension": "", "registered": False}
        self.extension_query_error: Exception | None = None
        self.extension_list_response: list[dict] = []
        self.extension_list_error: Exception | None = None
        self.registrar_info_response: dict | None = None
        self.registrar_info_error: Exception | None = None
        # Test injection slots for the multi-party room RPCs. Set `room_error`
        # to an exception (e.g. TelephonyMethodNotFoundError) to simulate a
        # kernel with rooms disabled. `room_create_response` seeds the room_id.
        self.room_create_response: dict = {"room_id": "mock-room", "legs": []}
        self.room_error: Exception | None = None
        # Tracks which legs are in each room so the mock can reject re-adding a
        # leg already in the room — the real kernel raises RPC -32003 "leg
        # already in room", which a record-only mock would silently pass.
        self._room_legs: dict[str, set[str]] = {}
        # `call.play` returns a play_id; `play_error` simulates a rejected play
        # (e.g. unsupported audio container) so callers can prove they degrade.
        self.play_response: dict = {"play_id": "mock-play", "status": "playing"}
        self.play_error: Exception | None = None

    # ── Lifecycle ──

    async def connect(self) -> None:
        self._ready.set()

    async def disconnect(self) -> None:
        self._ready.clear()

    async def wait_until_ready(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    # ── Event subscription ──

    def on_event(self, method: str, handler: EventHandler) -> None:
        self._handlers[method].append(handler)

    def off_event(self, method: str, handler: EventHandler) -> None:
        try:
            self._handlers[method].remove(handler)
        except ValueError:
            pass

    def on_reconnected(self, handler: ReconnectHandler) -> None:
        self._reconnect_handlers.append(handler)

    async def emit_event(self, method: str, data: dict) -> None:
        """Test helper — dispatch a fake event to all handlers concurrently."""

        event = CallEvent(method=method, data=data)
        await asyncio.gather(*(h(event) for h in self._handlers.get(method, [])))

    # ── Call control ──

    async def call_answer(self, call_id: str) -> None:
        self.recorded.append(("call.answer", {"call_id": call_id}))

    async def call_hangup(self, call_id: str, reason: str | None = None) -> None:
        self.recorded.append(("call.hangup", {"call_id": call_id, "reason": reason}))
        err = self.hangup_errors.get(call_id)
        if err is not None:
            raise err

    async def call_say(
        self, call_id: str, text: str, *, voice: str | None = None, barge_in: bool | None = None,
    ) -> str:
        play_id = uuid.uuid4().hex
        self.recorded.append((
            "call.say",
            {"call_id": call_id, "text": text, "voice": voice, "barge_in": barge_in, "play_id": play_id},
        ))
        return play_id

    async def call_listen(self, call_id: str, *, timeout_ms: int | None = None) -> None:
        self.recorded.append(("call.listen", {"call_id": call_id, "timeout_ms": timeout_ms}))

    async def call_stop(self, call_id: str, *, target: str = "all") -> None:
        self.recorded.append(("call.stop", {"call_id": call_id, "target": target}))

    async def call_play(
        self,
        call_id: str,
        *,
        text: str | None = None,
        audio_url: str | None = None,
        loop: bool = False,
        interval_ms: int | None = None,
        voice: str | None = None,
    ) -> dict:
        self.recorded.append((
            "call.play",
            {
                "call_id": call_id,
                "text": text,
                "audio_url": audio_url,
                "loop": loop,
                "interval_ms": interval_ms,
                "voice": voice,
            },
        ))
        if self.play_error is not None:
            raise self.play_error
        return self.play_response

    async def call_dtmf(
        self, call_id: str, digits: str, *, duration_ms: int | None = None,
    ) -> None:
        self.recorded.append(("call.dtmf", {"call_id": call_id, "digits": digits, "duration_ms": duration_ms}))

    async def call_bridge(
        self, call_id: str, other_call_id: str, transcribe: bool = True
    ) -> None:
        self.recorded.append((
            "call.bridge",
            {"call_id": call_id, "other_call_id": other_call_id, "transcribe": transcribe},
        ))
        if self.bridge_error is not None:
            raise self.bridge_error

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
        self.recorded.append((
            "call.connect_external_agent",
            {
                "call_id": call_id,
                "provider": provider,
                "ws_url": ws_url,
                "token": token,
                "audio_in_rate": audio_in_rate,
                "audio_out_rate": audio_out_rate,
                "traceparent": traceparent,
                "trace_call_id": trace_call_id,
            },
        ))

    async def call_converse_external_agent(
        self,
        call_id: str,
        *,
        provider: str,
        turn_url: str,
        token: str,
        greeting: str | None = None,
        voice_spk_id: str | None = None,
        traceparent: str | None = None,
        trace_call_id: str | None = None,
    ) -> None:
        self.recorded.append((
            "call.converse_external_agent",
            {
                "call_id": call_id,
                "provider": provider,
                "turn_url": turn_url,
                "token": token,
                "greeting": greeting,
                "voice_spk_id": voice_spk_id,
                "traceparent": traceparent,
                "trace_call_id": trace_call_id,
            },
        ))
        if self.bridge_error is not None:
            raise self.bridge_error

    async def call_unbridge(self, call_id: str, other_call_id: str) -> None:
        self.recorded.append(("call.unbridge", {"call_id": call_id, "other_call_id": other_call_id}))

    # ── Multi-party rooms ──

    async def room_create(self, *, leg_call_ids: list[str] | None = None) -> dict:
        self.recorded.append(("room.create", {"leg_call_ids": leg_call_ids}))
        if self.room_error is not None:
            raise self.room_error
        room_id = self.room_create_response.get("room_id", "mock-room")
        self._room_legs[room_id] = set(leg_call_ids or [])
        return self.room_create_response

    async def room_add_leg(self, room_id: str, call_id: str) -> dict:
        self.recorded.append(("room.add_leg", {"room_id": room_id, "call_id": call_id}))
        if self.room_error is not None:
            raise self.room_error
        legs = self._room_legs.setdefault(room_id, set())
        if call_id in legs:
            raise TelephonyRPCError(-32003, "call state invalid: leg already in room")
        legs.add(call_id)
        return {"room_id": room_id}

    async def room_remove_leg(self, room_id: str, call_id: str) -> dict:
        self.recorded.append(("room.remove_leg", {"room_id": room_id, "call_id": call_id}))
        if self.room_error is not None:
            raise self.room_error
        self._room_legs.setdefault(room_id, set()).discard(call_id)
        return {"room_id": room_id}

    async def room_replace_leg(
        self, room_id: str, old_call_id: str, new_call_id: str
    ) -> dict:
        self.recorded.append((
            "room.replace_leg",
            {"room_id": room_id, "old_call_id": old_call_id, "new_call_id": new_call_id},
        ))
        if self.room_error is not None:
            raise self.room_error
        legs = self._room_legs.setdefault(room_id, set())
        if new_call_id in legs:
            raise TelephonyRPCError(-32003, "call state invalid: leg already in room")
        legs.discard(old_call_id)
        legs.add(new_call_id)
        return {"room_id": room_id}

    async def room_set_mix_gain(
        self, room_id: str, *, listener_call_id: str, speaker_call_id: str, gain: float
    ) -> dict:
        self.recorded.append((
            "room.set_mix_gain",
            {
                "room_id": room_id,
                "listener_call_id": listener_call_id,
                "speaker_call_id": speaker_call_id,
                "gain": gain,
            },
        ))
        if self.room_error is not None:
            raise self.room_error
        return {"room_id": room_id}

    async def room_close(self, room_id: str, *, reason: str | None = None) -> dict:
        self.recorded.append(("room.close", {"room_id": room_id, "reason": reason}))
        if self.room_error is not None:
            raise self.room_error
        return {"room_id": room_id}

    async def call_hold(self, call_id: str) -> None:
        self.recorded.append(("call.hold", {"call_id": call_id}))

    async def call_unhold(self, call_id: str) -> None:
        self.recorded.append(("call.unhold", {"call_id": call_id}))

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
        params: dict[str, Any] = {}
        if uri:
            params["uri"] = uri
        if extension:
            params["extension"] = extension
        if caller_id:
            params["caller_id"] = caller_id
        if trunk_id:
            params["trunk_id"] = trunk_id
        if timeout_ms is not None:
            params["timeout_ms"] = timeout_ms
        if headers:
            params["headers"] = headers
        self.recorded.append(("call.originate", params))
        return self.originate_response

    async def extension_query(self, extension: str) -> dict:
        self.recorded.append(("extension.query", {"extension": extension}))
        if self.extension_query_error is not None:
            raise self.extension_query_error
        return self.extension_query_response

    async def extension_list(self) -> list[dict]:
        self.recorded.append(("extension.list", {}))
        if self.extension_list_error is not None:
            raise self.extension_list_error
        return self.extension_list_response

    async def registrar_info(self) -> dict | None:
        self.recorded.append(("system.registrar_info", {}))
        if self.registrar_info_error is not None:
            raise self.registrar_info_error
        return self.registrar_info_response

    async def call_list(self) -> list[dict]:
        self.recorded.append(("call.list", {}))
        return self.call_list_response

    async def webrtc_offer(self, sdp: str, call_id: str | None = None) -> dict:
        self.recorded.append(("webrtc.offer", {"sdp": sdp, "call_id": call_id}))
        return self.webrtc_offer_response

    async def webrtc_ice(self, call_id: str, candidate: dict) -> None:
        self.recorded.append(("webrtc.ice", {"call_id": call_id, "candidate": candidate}))
