"""
FlowKit telephony client — WebSocket + JSON-RPC 2.0.

Key behavior:
  * `connect()` opens the WS, spawns the recv loop, sends `system.hello`,
    then sets `_ready`. RPCs called before this block. If the initial open
    fails (e.g. FlowKit restarting), a background `_reconnect_loop()` is
    scheduled instead of raising — callers can register handlers and proceed.
  * `_recv_loop()` parses every frame:
      - frames with `id` → resolve the pending future
      - frames with `method` and no `id` → dispatch via `on_event` handlers
        (concurrently via `asyncio.create_task` so a slow handler doesn't
        stall the receive pump)
  * On WS close / error or initial connect failure, `_reconnect_loop()` retries
    with exponential backoff (1s → 30s), re-runs hello, then invokes any
    `on_reconnected` handlers. Orchestrators use this to call `call_list()`
    and resync call state.

We don't bake in business semantics here — `call.incoming`, queue routing,
agent assignment all live in the orchestrator.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import defaultdict
from collections.abc import Callable
from itertools import count
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from app.libs.telephony.base import (
    BaseTelephonyClient,
    CallEvent,
    EventHandler,
    ReconnectHandler,
    TelephonyMethodNotFoundError,
    TelephonyNotConnectedError,
    TelephonyRPCError,
)


logger = logging.getLogger(__name__)


class FlowKitTelephonyClient(BaseTelephonyClient):

    def __init__(
        self,
        *,
        ws_url: str,
        sdk_name: str,
        sdk_version: str,
        rpc_timeout: float = 30.0,
    ) -> None:
        self._ws_url = ws_url
        self._sdk_name = sdk_name
        self._sdk_version = sdk_version
        self._rpc_timeout = rpc_timeout

        self._ws: WebSocketClientProtocol | None = None
        self._id_counter = count(1)
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._reconnect_handlers: list[ReconnectHandler] = []
        self._ready = asyncio.Event()
        self._recv_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._closing = False
        self._hello_result: dict | None = None
        self._peer_serving_probe: Callable[[], bool] | None = None

    # ───────────── Lifecycle ─────────────

    def set_peer_serving_probe(self, probe: Callable[[], bool] | None) -> None:
        """Teach this client how to ask whether another kernel still serves calls.

        Deployments that run a blue/green pair take one kernel down on every
        release, so a connection failure there is routine rather than an
        outage — telephony keeps working through the sibling. Wire this up and
        such failures are logged at INFO; they stay at WARNING only when no
        kernel is left, which is when someone actually needs to be paged.
        """
        self._peer_serving_probe = probe

    def _another_kernel_serving(self) -> bool:
        probe = self._peer_serving_probe
        if probe is None:
            return False
        try:
            return probe()
        except Exception:  # noqa: BLE001
            return False

    async def connect(self) -> None:
        if self._closing:
            return
        if self.is_ready:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._closing = False
        try:
            await self._open_and_handshake()
            self._start_recv_loop()
        except Exception:  # noqa: BLE001
            logger.warning(
                "FlowKit initial connect failed; scheduling reconnect to %s",
                self._ws_url,
                exc_info=True,
            )
            self._ensure_reconnect_loop()

    def _fail_pending(self, exc: BaseException) -> None:
        """Fail all in-flight RPCs. Safe to call from disconnect or recv exit."""
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()

    async def disconnect(self) -> None:
        self._closing = True
        self._ready.clear()
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
        if self._recv_task is not None:
            self._recv_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
        self._ws = None
        self._fail_pending(TelephonyNotConnectedError("Client disconnected"))

    async def wait_until_ready(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    # ───────────── Event subscription ─────────────

    def on_event(self, method: str, handler: EventHandler) -> None:
        self._handlers[method].append(handler)

    def off_event(self, method: str, handler: EventHandler) -> None:
        try:
            self._handlers[method].remove(handler)
        except ValueError:
            pass

    def on_reconnected(self, handler: ReconnectHandler) -> None:
        self._reconnect_handlers.append(handler)

    # ───────────── Internals ─────────────

    def _start_recv_loop(self) -> None:
        if self._recv_task is None or self._recv_task.done():
            self._recv_task = asyncio.create_task(self._recv_loop(), name="flowkit-recv")

    def _ensure_reconnect_loop(self) -> None:
        if self._closing:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(
            self._reconnect_loop(), name="flowkit-reconnect"
        )

    async def _open_and_handshake(self) -> None:
        ws = await websockets.connect(self._ws_url, ping_interval=20, ping_timeout=20)
        try:
            # Send hello inline (recv loop not running yet) so we don't race
            hello = {
                "jsonrpc": "2.0",
                "id": "hello",
                "method": "system.hello",
                "params": {
                    "sdk": self._sdk_name,
                    "version": self._sdk_version,
                    "capabilities": ["events"],
                },
            }
            await ws.send(json.dumps(hello))
            raw = await ws.recv()
            msg = json.loads(raw)
            if "error" in msg:
                err = msg["error"]
                raise TelephonyRPCError(
                    err.get("code", -1), err.get("message", "hello failed")
                )
            self._hello_result = msg.get("result", {})
            self._ws = ws
            self._ready.set()
        except Exception:
            # Connect succeeded but hello failed — don't leak the half-open socket
            # or leave self._ws pointing at a dead connection for the next retry.
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
            raise
        logger.info("FlowKit hello OK: %s", self._hello_result)

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON frame discarded: %r", raw[:200])
                    continue
                if "id" in msg and msg["id"] is not None:
                    self._handle_response(msg)
                elif "method" in msg:
                    self._dispatch_event(msg["method"], msg.get("params") or {})
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed:
            logger.warning("FlowKit WS closed; scheduling reconnect")
        except Exception:  # noqa: BLE001
            logger.exception("FlowKit recv loop crashed")
        finally:
            self._ready.clear()
            self._ws = None
            # Unexpected close must not leave callers blocked until rpc_timeout.
            self._fail_pending(TelephonyNotConnectedError("FlowKit connection closed"))
            self._ensure_reconnect_loop()

    def _handle_response(self, msg: dict) -> None:
        rpc_id = str(msg["id"])
        fut = self._pending.pop(rpc_id, None)
        if fut is None or fut.done():
            return
        if "error" in msg:
            err = msg["error"]
            code = err.get("code", -1)
            # -32601 "method not found" means the kernel lacks this optional
            # capability (e.g. SIP extensions not enabled); surface a distinct
            # type so callers can degrade gracefully.
            err_cls = (
                TelephonyMethodNotFoundError if code == -32601 else TelephonyRPCError
            )
            fut.set_exception(err_cls(code, err.get("message", ""), err.get("data")))
        else:
            fut.set_result(msg.get("result", {}))

    def _dispatch_event(self, method: str, data: dict) -> None:
        handlers = self._handlers.get(method)
        if not handlers:
            return
        event = CallEvent(method=method, data=data)
        for handler in handlers:
            asyncio.create_task(_safe_call(handler, event), name=f"evt:{method}")

    @staticmethod
    def _is_transient_connect_error(exc: BaseException) -> bool:
        """True for expected kernel-down / network blips during reconnect.

        These must not be logged at ERROR — the reconnect loop is designed to
        keep retrying, and ERROR alerts (e.g. errno 111 Connection refused)
        would fire every backoff tick while FlowKit is simply unreachable.
        """
        if isinstance(
            exc,
            (
                ConnectionError,
                TimeoutError,
                asyncio.TimeoutError,
                OSError,
            ),
        ):
            return True
        # websockets wraps many connect failures; treat package errors as
        # transient except InvalidURI (bad config — that is a real ERROR).
        mod = type(exc).__module__ or ""
        if mod.startswith("websockets"):
            return type(exc).__name__ != "InvalidURI"
        return False

    async def _reconnect_loop(self) -> None:
        delay = 1.0
        while not self._closing:
            retry_delay = delay * random.uniform(0.8, 1.2)
            await asyncio.sleep(retry_delay)
            try:
                await self._open_and_handshake()
                self._start_recv_loop()
                logger.info("FlowKit reconnected url=%s", self._ws_url)
                # Notify subscribers (orchestrator uses this to call call.list)
                for h in list(self._reconnect_handlers):
                    asyncio.create_task(_safe_call0(h), name="on-reconnect")
                return
            except Exception as exc:  # noqa: BLE001
                # Match initial-connect policy: connectivity failures are WARNING
                # (with the exception message in the body so alerts stay useful).
                # Unexpected bugs stay ERROR via logger.exception. A kernel that
                # is unreachable while a sibling still carries calls is demoted
                # to INFO — this retry runs every 30s for as long as the kernel
                # stays down, and a blue/green deployment leaves one down by
                # design.
                if self._is_transient_connect_error(exc):
                    served = self._another_kernel_serving()
                    log = logger.info if served else logger.warning
                    log(
                        "FlowKit reconnect failed url=%s err=%s; retrying in %.1fs%s",
                        self._ws_url,
                        exc,
                        retry_delay,
                        " (another kernel is serving calls)" if served else "",
                    )
                else:
                    logger.exception(
                        "FlowKit reconnect failed url=%s; retrying in %.1fs",
                        self._ws_url,
                        retry_delay,
                    )
                delay = min(delay * 2, 30.0)

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict:
        if self._ws is None or not self._ready.is_set():
            raise TelephonyNotConnectedError("FlowKit not connected")
        rpc_id = str(next(self._id_counter))
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[rpc_id] = fut
        frame = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
        await self._ws.send(json.dumps(frame))
        try:
            return await asyncio.wait_for(fut, timeout=self._rpc_timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(rpc_id, None)
            raise TelephonyRPCError(-1, f"RPC {method} timed out after {self._rpc_timeout}s") from exc

    # ───────────── RPC surface ─────────────

    async def call_answer(self, call_id: str) -> None:
        await self._rpc("call.answer", {"call_id": call_id})

    async def call_hangup(self, call_id: str, reason: str | None = None) -> None:
        params: dict = {"call_id": call_id}
        if reason:
            params["reason"] = reason
        await self._rpc("call.hangup", params)

    async def call_say(
        self,
        call_id: str,
        text: str,
        *,
        voice: str | None = None,
        barge_in: bool | None = None,
    ) -> str:
        params: dict = {"call_id": call_id, "text": text}
        if voice:
            params["voice"] = voice
        if barge_in is not None:
            params["barge_in"] = barge_in
        result = await self._rpc("call.say", params)
        return result.get("play_id", "")

    async def call_listen(
        self,
        call_id: str,
        *,
        timeout_ms: int | None = None,
        adaptive_barge_in: bool | None = None,
        performance: dict | None = None,
    ) -> None:
        params: dict = {"call_id": call_id}
        if timeout_ms is not None:
            params["timeout_ms"] = timeout_ms
        if adaptive_barge_in is not None:
            params["adaptive_barge_in"] = adaptive_barge_in
        if performance is not None:
            params["performance"] = performance
        await self._rpc("call.listen", params)

    async def call_stop(self, call_id: str, *, target: str = "all") -> None:
        await self._rpc("call.stop", {"call_id": call_id, "target": target})

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
        params: dict[str, Any] = {"call_id": call_id}
        if text is not None:
            params["text"] = text
        if audio_url is not None:
            params["audio_url"] = audio_url
        if audio is not None:
            params["audio"] = audio
        if loop:
            params["loop"] = True
        if interval_ms is not None:
            params["interval_ms"] = interval_ms
        if voice:
            params["voice"] = voice
        return await self._rpc("call.play", params)

    async def call_dtmf(
        self, call_id: str, digits: str, *, duration_ms: int | None = None,
    ) -> None:
        params: dict = {"call_id": call_id, "digits": digits}
        if duration_ms is not None:
            params["duration_ms"] = duration_ms
        await self._rpc("call.dtmf", params)

    async def call_bridge(
        self,
        call_id: str,
        other_call_id: str,
        transcribe: bool = True,
        *,
        keepalive_on_peer_hangup: bool = False,
        user_call_id: str | None = None,
    ) -> None:
        params: dict[str, Any] = {"call_id": call_id, "other_call_id": other_call_id}
        # Omit when True to stay backward-compatible with kernels that default
        # to transcribing; only send the flag to explicitly disable ASR.
        if not transcribe:
            params["transcribe"] = False
        if keepalive_on_peer_hangup:
            params["keepalive_on_peer_hangup"] = True
        if user_call_id is not None:
            params["user_call_id"] = user_call_id
        await self._rpc("call.bridge", params)

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
        params: dict[str, Any] = {
            "call_id": call_id,
            "provider": provider,
            "ws_url": ws_url,
            "token": token,
            "audio_in_rate": audio_in_rate,
            "audio_out_rate": audio_out_rate,
        }
        if traceparent:
            params["traceparent"] = traceparent
        if trace_call_id:
            params["trace_call_id"] = trace_call_id
        await self._rpc("call.connect_external_agent", params)

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
        """Start a v2 text-turn conversation on the call leg.

        flowkit owns ASR/TTS/barge-in and POSTs each transcribed utterance to
        ``turn_url`` (Bearer ``token``), speaking back the reply; transfer_human
        / hang_up surface as the same external_agent handoff/ended events.
        """
        params: dict[str, Any] = {
            "call_id": call_id,
            "provider": provider,
            "turn_url": turn_url,
            "token": token,
        }
        if greeting:
            params["greeting"] = greeting
        if voice_spk_id:
            params["voice_spk_id"] = voice_spk_id
        if performance:
            params["performance"] = performance
        if traceparent:
            params["traceparent"] = traceparent
        if trace_call_id:
            params["trace_call_id"] = trace_call_id
        await self._rpc("call.converse_external_agent", params)

    async def call_unbridge(self, call_id: str, other_call_id: str) -> None:
        await self._rpc("call.unbridge", {"call_id": call_id, "other_call_id": other_call_id})

    # ── Multi-party rooms ──

    async def room_create(self, *, leg_call_ids: list[str] | None = None) -> dict:
        params: dict[str, Any] = {}
        if leg_call_ids:
            params["leg_call_ids"] = leg_call_ids
        return await self._rpc("room.create", params)

    async def room_add_leg(self, room_id: str, call_id: str) -> dict:
        return await self._rpc("room.add_leg", {"room_id": room_id, "call_id": call_id})

    async def room_remove_leg(self, room_id: str, call_id: str) -> dict:
        return await self._rpc(
            "room.remove_leg", {"room_id": room_id, "call_id": call_id}
        )

    async def room_replace_leg(
        self, room_id: str, old_call_id: str, new_call_id: str
    ) -> dict:
        return await self._rpc(
            "room.replace_leg",
            {"room_id": room_id, "old_call_id": old_call_id, "new_call_id": new_call_id},
        )

    async def room_set_mix_gain(
        self, room_id: str, *, listener_call_id: str, speaker_call_id: str, gain: float
    ) -> dict:
        return await self._rpc(
            "room.set_mix_gain",
            {
                "room_id": room_id,
                "listener_call_id": listener_call_id,
                "speaker_call_id": speaker_call_id,
                "gain": gain,
            },
        )

    async def room_close(self, room_id: str, *, reason: str | None = None) -> dict:
        params: dict[str, Any] = {"room_id": room_id}
        if reason:
            params["reason"] = reason
        return await self._rpc("room.close", params)

    async def call_hold(self, call_id: str) -> None:
        await self._rpc("call.hold", {"call_id": call_id})

    async def call_unhold(self, call_id: str) -> None:
        await self._rpc("call.unhold", {"call_id": call_id})

    async def call_mute(self, call_id: str) -> None:
        await self._rpc("call.mute", {"call_id": call_id})

    async def call_unmute(self, call_id: str) -> None:
        await self._rpc("call.unmute", {"call_id": call_id})

    async def call_originate(
        self,
        uri: str | None = None,
        *,
        extension: str | None = None,
        caller_id: str | None = None,
        trunk_id: str | None = None,
        timeout_ms: int | None = None,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
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
        if request_id:
            params["request_id"] = request_id
        return await self._rpc("call.originate", params)

    async def originate_capacity(self) -> dict | None:
        try:
            return await self._rpc("system.capacity", {})
        except TelephonyMethodNotFoundError:
            return None

    async def extension_query(self, extension: str) -> dict:
        return await self._rpc("extension.query", {"extension": extension})

    async def extension_list(self) -> list[dict]:
        result = await self._rpc("extension.list", {})
        return result.get("extensions", [])

    async def registrar_info(self) -> dict | None:
        result = await self._rpc("system.registrar_info", {})
        # The kernel returns null (→ empty dict here) when no registrar is
        # configured; normalize to None so callers can fall back to settings.
        return result or None

    async def call_list(self) -> list[dict]:
        result = await self._rpc("call.list", {})
        return result.get("calls", [])

    async def call_alive(self, call_id: str) -> bool | None:
        if not self.is_ready:
            return None
        try:
            calls = await self.call_list()
        except Exception:  # noqa: BLE001
            logger.warning("call_alive: call_list failed call_id=%s", call_id, exc_info=True)
            return None
        active_ids = {str(c.get("call_id")) for c in calls if c.get("call_id")}
        return call_id in active_ids

    async def webrtc_offer(self, sdp: str, call_id: str | None = None) -> dict:
        params: dict = {"sdp": sdp}
        if call_id:
            params["call_id"] = call_id
        return await self._rpc("webrtc.offer", params)

    async def webrtc_ice(self, call_id: str, candidate: dict) -> None:
        await self._rpc("webrtc.ice", {"call_id": call_id, "candidate": candidate})


async def _safe_call(handler: EventHandler, event: CallEvent) -> None:
    try:
        await handler(event)
    except Exception:  # noqa: BLE001
        logger.exception("Telephony event handler crashed: method=%s", event.method)


async def _safe_call0(handler: ReconnectHandler) -> None:
    try:
        await handler()
    except Exception:  # noqa: BLE001
        logger.exception("Reconnect handler crashed")
