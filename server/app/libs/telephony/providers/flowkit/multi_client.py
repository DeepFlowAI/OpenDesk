"""
Multi-kernel FlowKit client — fan-in events / fan-out RPCs across blue/green.

Used when TELEPHONY_WS_URLS lists more than one WebSocket URL. Each URL gets
its own FlowKitTelephonyClient (independent reconnect). Call-scoped RPCs are
routed by a call_id → kernel index map (process L1 + Redis for multi-API).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.libs.telephony.base import (
    BaseTelephonyClient,
    CallEvent,
    EventHandler,
    ReconnectHandler,
    TelephonyNotConnectedError,
    TelephonyRPCError,
)
from app.libs.telephony.providers.flowkit.client import FlowKitTelephonyClient

logger = logging.getLogger(__name__)

_KERNEL_MAP_TTL_SEC = 6 * 60 * 60
_CALL_NOT_FOUND_CODES = {-32002, -32602}


def _kernel_map_key(call_id: str) -> str:
    return f"cc:call:kernel:{call_id}"


def _get_redis():
    try:
        from app.db.redis import redis_client

        if redis_client is None:
            return None
        return redis_client.client
    except Exception:  # noqa: BLE001
        return None


class MultiKernelTelephonyClient(BaseTelephonyClient):
    """Aggregate N FlowKitTelephonyClient instances behind one BaseTelephonyClient."""

    def __init__(
        self,
        *,
        ws_urls: list[str],
        sdk_name: str,
        sdk_version: str,
        rpc_timeout: float = 30.0,
    ) -> None:
        if not ws_urls:
            raise ValueError("ws_urls must be non-empty")
        self._clients: list[FlowKitTelephonyClient] = [
            FlowKitTelephonyClient(
                ws_url=url,
                sdk_name=sdk_name,
                sdk_version=sdk_version,
                rpc_timeout=rpc_timeout,
            )
            for url in ws_urls
        ]
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._reconnect_handlers: list[ReconnectHandler] = []
        self._call_kernel: dict[str, int] = {}
        # Index of the kernel currently receiving new inbound / registrations
        # (Kamailio's active color). Drifts on call.incoming / extension.registered
        # so originates follow the cutover instead of sticking to URL order.
        self._primary_index: int = 0
        self._wired = False

    # ───────────── Lifecycle ─────────────

    def _ensure_wired(self) -> None:
        if self._wired:
            return
        for idx, client in enumerate(self._clients):
            for method in (
                "call.incoming",
                "call.dtmf",
                "call.play_end",
                "call.speech_end",
                "call.speech_partial",
                "call.user_text",
                "call.assistant_text",
                "call.bridge_transcript",
                "call.bridged",
                "call.hangup",
                "call.recording.completed",
                "call.ringing",
                "call.answered",
                "call.early_media",
                "call.external_agent.connected",
                "call.external_agent.handoff",
                "call.external_agent.failed",
                "call.external_agent.ended",
                "webrtc.ice",
                "extension.registered",
                "extension.unregistered",
            ):
                client.on_event(method, self._make_event_forwarder(idx))
            client.on_reconnected(self._make_reconnect_forwarder())
            client.set_peer_serving_probe(self._make_peer_serving_probe(idx))
        self._wired = True

    def _make_peer_serving_probe(self, kernel_index: int) -> Callable[[], bool]:
        """Is any kernel other than this one connected right now?

        A blue/green pair spends every deployment with one side down, so each
        client asks this before deciding how loudly to report that it cannot
        reach its kernel.
        """

        def _serving() -> bool:
            return any(
                client.is_ready
                for idx, client in enumerate(self._clients)
                if idx != kernel_index
            )

        return _serving

    def _make_event_forwarder(self, kernel_index: int) -> EventHandler:
        async def _forward(event: CallEvent) -> None:
            call_id = event.data.get("call_id")
            if call_id:
                await self._remember_kernel(str(call_id), kernel_index)
            # New inbound and phone re-REGISTER only hit Kamailio's active
            # color — treat that as the originate primary so blue/green
            # cutover stops sending new calls at the draining kernel.
            if event.method in ("call.incoming", "extension.registered"):
                if self._primary_index != kernel_index:
                    logger.info(
                        "Multi-kernel primary drifted %d → %d (via %s)",
                        self._primary_index,
                        kernel_index,
                        event.method,
                    )
                    self._primary_index = kernel_index
            for handler in list(self._handlers.get(event.method, [])):
                try:
                    await handler(event)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Multi-kernel event handler crashed: method=%s", event.method
                    )

        return _forward

    def _make_reconnect_forwarder(self) -> ReconnectHandler:
        async def _forward() -> None:
            for handler in list(self._reconnect_handlers):
                try:
                    await handler()
                except Exception:  # noqa: BLE001
                    logger.exception("Multi-kernel reconnect handler crashed")

        return _forward

    async def connect(self) -> None:
        self._ensure_wired()
        for client in self._clients:
            await client.connect()

    async def disconnect(self) -> None:
        for client in self._clients:
            await client.disconnect()

    async def wait_until_ready(self, timeout: float = 30.0) -> None:
        import asyncio

        async def _one(c: FlowKitTelephonyClient) -> None:
            await c.wait_until_ready(timeout=timeout)

        await asyncio.wait_for(
            asyncio.gather(*(_one(c) for c in self._clients), return_exceptions=True),
            timeout=timeout,
        )
        if not self.is_ready:
            raise TelephonyNotConnectedError("No FlowKit kernel ready")

    @property
    def is_ready(self) -> bool:
        return any(c.is_ready for c in self._clients)

    def on_event(self, method: str, handler: EventHandler) -> None:
        self._ensure_wired()
        self._handlers[method].append(handler)

    def off_event(self, method: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(method)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            pass

    def on_reconnected(self, handler: ReconnectHandler) -> None:
        self._ensure_wired()
        self._reconnect_handlers.append(handler)

    # ───────────── Kernel routing ─────────────

    def _primary(self) -> FlowKitTelephonyClient:
        idx = self._primary_index
        if 0 <= idx < len(self._clients) and self._clients[idx].is_ready:
            return self._clients[idx]
        for c in self._clients:
            if c.is_ready:
                return c
        # Prefer drifted index even if not ready so callers get a clear error.
        if 0 <= idx < len(self._clients):
            return self._clients[idx]
        return self._clients[0]

    async def _remember_kernel(self, call_id: str, index: int) -> None:
        self._call_kernel[call_id] = index
        r = _get_redis()
        if r is None:
            return
        try:
            await r.set(_kernel_map_key(call_id), str(index), ex=_KERNEL_MAP_TTL_SEC)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to persist call→kernel map call_id=%s", call_id)

    async def _lookup_kernel(self, call_id: str) -> int | None:
        if call_id in self._call_kernel:
            return self._call_kernel[call_id]
        r = _get_redis()
        if r is None:
            return None
        try:
            raw = await r.get(_kernel_map_key(call_id))
        except Exception:  # noqa: BLE001
            return None
        if raw is None:
            return None
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            return None
        if 0 <= idx < len(self._clients):
            self._call_kernel[call_id] = idx
            return idx
        return None

    async def _client_for(self, call_id: str) -> FlowKitTelephonyClient:
        idx = await self._lookup_kernel(call_id)
        if idx is not None:
            return self._clients[idx]
        return self._primary()

    async def _call_on_kernel(
        self,
        call_id: str,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Invoke a call-scoped method, falling back across kernels on not-found."""
        preferred = await self._client_for(call_id)
        order = [preferred] + [c for c in self._clients if c is not preferred]
        last_exc: Exception | None = None
        for client in order:
            if not client.is_ready:
                continue
            try:
                result = await getattr(client, method_name)(*args, **kwargs)
                # Learn mapping from whichever client succeeded.
                idx = self._clients.index(client)
                await self._remember_kernel(call_id, idx)
                return result
            except TelephonyRPCError as exc:
                last_exc = exc
                if exc.code in _CALL_NOT_FOUND_CODES or "not found" in str(exc).lower():
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise TelephonyNotConnectedError("No FlowKit kernel ready")

    # ───────────── RPC surface ─────────────

    async def call_answer(self, call_id: str) -> None:
        await self._call_on_kernel(call_id, "call_answer", call_id)

    async def call_hangup(self, call_id: str, reason: str | None = None) -> None:
        await self._call_on_kernel(call_id, "call_hangup", call_id, reason=reason)

    async def call_say(
        self,
        call_id: str,
        text: str,
        *,
        voice: str | None = None,
        barge_in: bool | None = None,
    ) -> str:
        return await self._call_on_kernel(
            call_id, "call_say", call_id, text, voice=voice, barge_in=barge_in
        )

    async def call_listen(self, call_id: str, *, timeout_ms: int | None = None) -> None:
        await self._call_on_kernel(call_id, "call_listen", call_id, timeout_ms=timeout_ms)

    async def call_stop(self, call_id: str, *, target: str = "all") -> None:
        await self._call_on_kernel(call_id, "call_stop", call_id, target=target)

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
        return await self._call_on_kernel(
            call_id,
            "call_play",
            call_id,
            text=text,
            audio_url=audio_url,
            audio=audio,
            loop=loop,
            interval_ms=interval_ms,
            voice=voice,
        )

    async def call_dtmf(
        self, call_id: str, digits: str, *, duration_ms: int | None = None
    ) -> None:
        await self._call_on_kernel(
            call_id, "call_dtmf", call_id, digits, duration_ms=duration_ms
        )

    async def call_bridge(
        self,
        call_id: str,
        other_call_id: str,
        transcribe: bool = True,
        *,
        keepalive_on_peer_hangup: bool = False,
    ) -> None:
        await self._call_on_kernel(
            call_id,
            "call_bridge",
            call_id,
            other_call_id,
            transcribe=transcribe,
            keepalive_on_peer_hangup=keepalive_on_peer_hangup,
        )
        # Both legs live on the same kernel.
        idx = await self._lookup_kernel(call_id)
        if idx is not None:
            await self._remember_kernel(other_call_id, idx)

    async def call_connect_external_agent(self, call_id: str, **kwargs: Any) -> None:
        await self._call_on_kernel(call_id, "call_connect_external_agent", call_id, **kwargs)

    async def call_converse_external_agent(self, call_id: str, **kwargs: Any) -> None:
        await self._call_on_kernel(call_id, "call_converse_external_agent", call_id, **kwargs)

    async def call_unbridge(self, call_id: str, other_call_id: str) -> None:
        await self._call_on_kernel(call_id, "call_unbridge", call_id, other_call_id)

    async def room_create(self, *, leg_call_ids: list[str] | None = None) -> dict:
        # All legs of a live call sit on one kernel. Prefer that kernel over
        # primary — during blue/green drain primary can drift while the SIP /
        # WebRTC legs still live on the other color, and room.create on the
        # wrong kernel fails with call-not-found (三方合并失败).
        idx: int | None = None
        for cid in leg_call_ids or []:
            idx = await self._lookup_kernel(cid)
            if idx is not None:
                break
        if idx is None:
            idx = self._primary_index
        client = self._clients[idx]
        result = await client.room_create(leg_call_ids=leg_call_ids)
        for cid in leg_call_ids or []:
            await self._remember_kernel(cid, idx)
        room_id = result.get("room_id")
        if isinstance(room_id, str) and room_id:
            await self._remember_kernel(f"room:{room_id}", idx)
        return result

    async def room_add_leg(self, room_id: str, call_id: str) -> dict:
        return await self._call_on_kernel(call_id, "room_add_leg", room_id, call_id)

    async def room_remove_leg(self, room_id: str, call_id: str) -> dict:
        return await self._call_on_kernel(call_id, "room_remove_leg", room_id, call_id)

    async def room_replace_leg(
        self, room_id: str, old_call_id: str, new_call_id: str
    ) -> dict:
        result = await self._call_on_kernel(
            old_call_id, "room_replace_leg", room_id, old_call_id, new_call_id
        )
        idx = await self._lookup_kernel(old_call_id)
        if idx is not None:
            await self._remember_kernel(new_call_id, idx)
        return result

    async def room_set_mix_gain(
        self, room_id: str, *, listener_call_id: str, speaker_call_id: str, gain: float
    ) -> dict:
        return await self._call_on_kernel(
            listener_call_id,
            "room_set_mix_gain",
            room_id,
            listener_call_id=listener_call_id,
            speaker_call_id=speaker_call_id,
            gain=gain,
        )

    async def room_close(self, room_id: str, *, reason: str | None = None) -> dict:
        idx = await self._lookup_kernel(f"room:{room_id}")
        client = self._clients[idx] if idx is not None else self._primary()
        return await client.room_close(room_id, reason=reason)

    async def call_hold(self, call_id: str) -> None:
        await self._call_on_kernel(call_id, "call_hold", call_id)

    async def call_unhold(self, call_id: str) -> None:
        await self._call_on_kernel(call_id, "call_unhold", call_id)

    async def call_mute(self, call_id: str) -> None:
        await self._call_on_kernel(call_id, "call_mute", call_id)

    async def call_unmute(self, call_id: str) -> None:
        await self._call_on_kernel(call_id, "call_unmute", call_id)

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
        preferred = self._primary()
        # Prefer the active-color primary, but fall through to any other ready
        # kernel (blue/green cutover: primary may still point at a drained
        # color). Extension dial additionally retries on "not registered".
        order = [preferred]
        order.extend(c for c in self._clients if c is not preferred)
        last_exc: Exception | None = None
        for client in order:
            if not client.is_ready:
                continue
            try:
                result = await client.call_originate(
                    uri,
                    extension=extension,
                    caller_id=caller_id,
                    trunk_id=trunk_id,
                    timeout_ms=timeout_ms,
                    headers=headers,
                )
            except TelephonyRPCError as exc:
                last_exc = exc
                if extension and "not registered" in str(exc).lower():
                    continue
                raise
            call_id = result.get("call_id")
            if call_id:
                idx = self._clients.index(client)
                await self._remember_kernel(str(call_id), idx)
                if client is not preferred:
                    self._primary_index = idx
            return result
        if last_exc is not None:
            raise last_exc
        raise TelephonyNotConnectedError("No FlowKit kernel ready")

    async def extension_query(self, extension: str) -> dict:
        # Prefer primary; if not registered, try other kernels (phone may have
        # re-registered onto the active color).
        last: dict | None = None
        last_exc: Exception | None = None
        preferred = self._primary()
        for client in [preferred] + [c for c in self._clients if c is not preferred]:
            if not client.is_ready:
                continue
            try:
                result = await client.extension_query(extension)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
            last = result
            if result.get("registered"):
                return result
        if last is not None:
            return last
        if last_exc is not None:
            raise last_exc
        raise TelephonyNotConnectedError("No FlowKit kernel ready")

    async def extension_list(self) -> list[dict]:
        seen: dict[str, dict] = {}
        for client in self._clients:
            if not client.is_ready:
                continue
            try:
                for row in await client.extension_list():
                    ext = row.get("extension")
                    if ext:
                        seen[str(ext)] = row
            except Exception:  # noqa: BLE001
                logger.warning("extension_list failed on a kernel", exc_info=True)
        return list(seen.values())

    async def registrar_info(self) -> dict | None:
        return await self._primary().registrar_info()

    async def call_list(self) -> list[dict]:
        merged: list[dict] = []
        for idx, client in enumerate(self._clients):
            if not client.is_ready:
                continue
            try:
                calls = await client.call_list()
            except Exception:  # noqa: BLE001
                logger.warning("call_list failed on kernel %d", idx, exc_info=True)
                continue
            for call in calls:
                call = dict(call)
                call["_kernel_index"] = idx
                cid = call.get("call_id")
                if cid:
                    await self._remember_kernel(str(cid), idx)
                merged.append(call)
        return merged

    async def webrtc_offer(self, sdp: str, call_id: str | None = None) -> dict:
        if call_id:
            # Pass affinity as a positional arg — `_call_on_kernel`'s first
            # parameter is also named `call_id`, so `call_id=` would TypeError.
            result = await self._call_on_kernel(call_id, "webrtc_offer", sdp, call_id)
            new_id = result.get("call_id") if isinstance(result, dict) else None
            if new_id:
                idx = await self._lookup_kernel(call_id)
                if idx is None:
                    preferred = await self._client_for(call_id)
                    idx = self._clients.index(preferred)
                await self._remember_kernel(str(new_id), idx)
            return result
        client = self._primary()
        result = await client.webrtc_offer(sdp, call_id=None)
        new_id = result.get("call_id")
        if new_id:
            await self._remember_kernel(str(new_id), self._clients.index(client))
        return result

    async def webrtc_ice(self, call_id: str, candidate: dict) -> None:
        await self._call_on_kernel(call_id, "webrtc_ice", call_id, candidate)
