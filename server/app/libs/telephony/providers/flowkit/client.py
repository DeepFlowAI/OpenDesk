"""
FlowKit telephony client — WebSocket + JSON-RPC 2.0.

Key behavior:
  * `connect()` opens the WS, spawns the recv loop, sends `system.hello`,
    then sets `_ready`. RPCs called before this block.
  * `_recv_loop()` parses every frame:
      - frames with `id` → resolve the pending future
      - frames with `method` and no `id` → dispatch via `on_event` handlers
        (concurrently via `asyncio.create_task` so a slow handler doesn't
        stall the receive pump)
  * On WS close / error, `_reconnect_loop()` retries with exponential backoff
    (1s → 30s), re-runs hello, then invokes any `on_reconnected` handlers.
    Orchestrators use this to call `call_list()` and resync call state.

We don't bake in business semantics here — `call.incoming`, queue routing,
agent assignment all live in the orchestrator.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from itertools import count
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from app.libs.telephony.base import (
    BaseTelephonyClient,
    CallEvent,
    EventHandler,
    ReconnectHandler,
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

    # ───────────── Lifecycle ─────────────

    async def connect(self) -> None:
        if self._ws is not None and not self._ws.closed:
            return
        self._closing = False
        await self._open_and_handshake()
        self._recv_task = asyncio.create_task(self._recv_loop(), name="flowkit-recv")

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
        # Fail any in-flight RPCs
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(TelephonyNotConnectedError("Client disconnected"))
        self._pending.clear()

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

    async def _open_and_handshake(self) -> None:
        self._ws = await websockets.connect(self._ws_url, ping_interval=20, ping_timeout=20)
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
        await self._ws.send(json.dumps(hello))
        raw = await self._ws.recv()
        msg = json.loads(raw)
        if "error" in msg:
            err = msg["error"]
            raise TelephonyRPCError(err.get("code", -1), err.get("message", "hello failed"))
        self._hello_result = msg.get("result", {})
        self._ready.set()
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
            if not self._closing:
                self._reconnect_task = asyncio.create_task(
                    self._reconnect_loop(), name="flowkit-reconnect"
                )

    def _handle_response(self, msg: dict) -> None:
        rpc_id = str(msg["id"])
        fut = self._pending.pop(rpc_id, None)
        if fut is None or fut.done():
            return
        if "error" in msg:
            err = msg["error"]
            fut.set_exception(
                TelephonyRPCError(err.get("code", -1), err.get("message", ""), err.get("data"))
            )
        else:
            fut.set_result(msg.get("result", {}))

    def _dispatch_event(self, method: str, data: dict) -> None:
        handlers = self._handlers.get(method)
        if not handlers:
            return
        event = CallEvent(method=method, data=data)
        for handler in handlers:
            asyncio.create_task(_safe_call(handler, event), name=f"evt:{method}")

    async def _reconnect_loop(self) -> None:
        delay = 1.0
        while not self._closing:
            await asyncio.sleep(delay)
            try:
                await self._open_and_handshake()
                self._recv_task = asyncio.create_task(self._recv_loop(), name="flowkit-recv")
                logger.info("FlowKit reconnected")
                # Notify subscribers (orchestrator uses this to call call.list)
                for h in list(self._reconnect_handlers):
                    asyncio.create_task(_safe_call0(h), name="on-reconnect")
                return
            except Exception:  # noqa: BLE001
                logger.exception("FlowKit reconnect failed, retrying in %ss", delay)
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

    async def call_listen(self, call_id: str, *, timeout_ms: int | None = None) -> None:
        params: dict = {"call_id": call_id}
        if timeout_ms is not None:
            params["timeout_ms"] = timeout_ms
        await self._rpc("call.listen", params)

    async def call_stop(self, call_id: str, *, target: str = "all") -> None:
        await self._rpc("call.stop", {"call_id": call_id, "target": target})

    async def call_dtmf(
        self, call_id: str, digits: str, *, duration_ms: int | None = None,
    ) -> None:
        params: dict = {"call_id": call_id, "digits": digits}
        if duration_ms is not None:
            params["duration_ms"] = duration_ms
        await self._rpc("call.dtmf", params)

    async def call_bridge(self, call_id: str, other_call_id: str) -> None:
        await self._rpc("call.bridge", {"call_id": call_id, "other_call_id": other_call_id})

    async def call_unbridge(self, call_id: str, other_call_id: str) -> None:
        await self._rpc("call.unbridge", {"call_id": call_id, "other_call_id": other_call_id})

    async def call_hold(self, call_id: str) -> None:
        await self._rpc("call.hold", {"call_id": call_id})

    async def call_unhold(self, call_id: str) -> None:
        await self._rpc("call.unhold", {"call_id": call_id})

    async def call_originate(
        self,
        uri: str,
        *,
        caller_id: str | None = None,
        trunk_id: str | None = None,
        timeout_ms: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        params: dict[str, Any] = {"uri": uri}
        if caller_id:
            params["caller_id"] = caller_id
        if trunk_id:
            params["trunk_id"] = trunk_id
        if timeout_ms is not None:
            params["timeout_ms"] = timeout_ms
        if headers:
            params["headers"] = headers
        return await self._rpc("call.originate", params)

    async def call_list(self) -> list[dict]:
        result = await self._rpc("call.list", {})
        return result.get("calls", [])

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
