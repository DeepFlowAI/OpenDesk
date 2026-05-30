"""
FlowKit Catalog sync — pushes OpenDesk's SipTrunk table to FlowKit
Catalog and keeps the lease alive via heartbeat.

Lifecycle (driven by the orchestrator):
  - start()  : initial PUT /snapshot + spawn heartbeat task
  - reload() : re-PUT /snapshot when admin CRUDs a trunk (call after commit)
  - stop()   : cancel heartbeat task + DELETE /registrars/{id}

Wire-protocol shape (FlowKit):
  PUT /api/v1/telecom/registrars/{provider_id}/snapshot
  {
    "revision":             <monotonic int>,
    "lease_ttl_sec":        90,
    "stale_acceptable_sec": 30,
    "trunks": [
      {
        "id":             "<sip_trunk.id>",
        "trunk_types":    ["inbound", "outbound"],
        "status":         "enabled",
        "peer_endpoints": [{"ip": "203.0.113.10", "port": 5060}],
        "outbound":       { server, port, user, pass, realm, callee_prefix }
      },
      ...
    ]
  }

Inbound-only trunks (outbound_profile=NULL) ship without "outbound" key
and with trunk_types limited to ["inbound"]. Outbound-only or dual trunks
attach the outbound block built from the JSONB column.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.libs.telephony.base import CallEvent
from app.libs.telephony.providers.flowkit.telecom_client import (
    FlowKitTelecomClient,
    TelecomAPIError,
)
from app.models.sip_trunk import SipTrunk


logger = logging.getLogger(__name__)


class CatalogSyncService:
    """Background catalog-sync loop bound to one FlowKitTelecomClient."""

    # Watchdog wakeup interval. Heartbeat is the primary safety; watchdog is
    # a paranoia layer for the BaseException-kills-task edge case.
    _WATCHDOG_INTERVAL_SEC = 60

    def __init__(
        self,
        *,
        telecom_client: FlowKitTelecomClient,
        lease_ttl_sec: int,
        stale_acceptable_sec: int,
    ) -> None:
        self._client = telecom_client
        self._lease_ttl_sec = lease_ttl_sec
        self._stale_acceptable_sec = stale_acceptable_sec
        self._heartbeat_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        # Revision uses unix-seconds; monotonically increasing across reloads
        # and survives process restarts (clocks don't go backwards in practice).
        self._revision = 0
        self._started = False
        # ── Health / observability state ──
        # Updated on every heartbeat success / failure / push_snapshot result
        # and surfaced via health_snapshot() to the /health endpoint.
        self._last_heartbeat_at: float | None = None
        self._last_heartbeat_error: str | None = None
        self._last_snapshot_at: float | None = None
        self._last_snapshot_error: str | None = None
        self._heartbeat_restart_count = 0

    async def start(self) -> None:
        if self._started:
            return
        await self.push_snapshot()
        self._heartbeat_task = self._spawn_heartbeat()
        self._watchdog_task = asyncio.create_task(
            self._watchdog_loop(), name="telecom-watchdog"
        )
        self._started = True
        logger.info("Catalog sync started: provider_id=%s", self._client.provider_id)

    async def stop(self) -> None:
        if not self._started:
            return
        # Stop watchdog FIRST so it doesn't try to restart heartbeat mid-teardown.
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        try:
            await self._client.delete()
        except TelecomAPIError as exc:
            # 404 on already-gone provider is fine
            if exc.status != 404:
                logger.warning("Catalog DELETE failed: %s", exc)
        except Exception:  # noqa: BLE001
            logger.exception("Catalog DELETE crashed")
        finally:
            await self._client.aclose()
            self._started = False
            logger.info("Catalog sync stopped")

    def _spawn_heartbeat(self) -> asyncio.Task:
        return asyncio.create_task(self._heartbeat_loop(), name="telecom-heartbeat")

    async def push_snapshot(self) -> None:
        """Build a snapshot from the SipTrunk table and PUT it to FlowKit."""

        trunks = await self._build_wire_trunks()
        self._revision = max(self._revision + 1, int(time.time()))
        try:
            resp = await self._client.put_snapshot(
                revision=self._revision,
                lease_ttl_sec=self._lease_ttl_sec,
                stale_acceptable_sec=self._stale_acceptable_sec,
                trunks=trunks,
            )
            self._last_snapshot_at = time.time()
            self._last_snapshot_error = None
            logger.info(
                "Catalog snapshot pushed: revision=%s trunks=%d",
                resp.get("revision"), resp.get("trunk_count", len(trunks)),
            )
        except TelecomAPIError as exc:
            self._last_snapshot_error = str(exc)
            logger.error("Catalog snapshot rejected: %s", exc)
            raise

    async def reload(self) -> None:
        """Public reload entry-point — call after admin CRUD on trunks."""

        if not self._started:
            return
        await self.push_snapshot()

    # ── Internals ──

    async def _build_wire_trunks(self) -> list[dict]:
        """Translate SipTrunk rows into the wire shape FlowKit's Catalog
        expects. The outbound block is DERIVED from peer_endpoints[0] —
        same IP/port handles both inbound INVITEs and outbound INVITEs
        on this carrier link. Per-call caller_id and callee_prefix come
        from the PhoneNumber row at originate time, NOT from the trunk."""

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(SipTrunk))).scalars().all()
        wire: list[dict] = []
        for t in rows:
            endpoints = list(t.peer_endpoints or [])
            trunk: dict[str, Any] = {
                "id": t.id,
                "trunk_types": list(t.trunk_types or []),
                "status": t.status or "enabled",
                "peer_endpoints": endpoints,
            }
            if "outbound" in trunk["trunk_types"]:
                if endpoints:
                    pe = endpoints[0]
                    trunk["outbound"] = {
                        "server": pe.get("ip", ""),
                        "port": int(pe.get("port") or 5060),
                    }
                else:
                    trunk["trunk_types"] = [
                        tt for tt in trunk["trunk_types"] if tt != "outbound"
                    ]
                    logger.warning(
                        "Trunk %s declared outbound but has no peer_endpoints; "
                        "demoted to inbound-only in FlowKit snapshot.", t.id,
                    )
            wire.append(trunk)
        return wire

    async def _heartbeat_loop(self) -> None:
        # Beat at lease/3, clamped to [10, 60] seconds.
        interval = max(10, min(60, self._lease_ttl_sec // 3))
        while True:
            try:
                await asyncio.sleep(interval)
                await self._client.heartbeat(lease_ttl_sec=self._lease_ttl_sec)
                self._last_heartbeat_at = time.time()
                self._last_heartbeat_error = None
            except asyncio.CancelledError:
                raise
            except TelecomAPIError as exc:
                self._last_heartbeat_error = f"{exc.status}: {exc}"
                # 404 means FlowKit has us evicted (sweeper) — re-PUT snapshot
                # to register again rather than just retrying heartbeat.
                if exc.status == 404:
                    logger.warning("Heartbeat got 404; re-pushing snapshot")
                    try:
                        await self.push_snapshot()
                    except Exception:  # noqa: BLE001
                        logger.exception("Re-push after 404 failed")
                else:
                    logger.warning("Heartbeat failed: %s", exc)
            except Exception as exc:  # noqa: BLE001
                self._last_heartbeat_error = repr(exc)
                logger.exception("Heartbeat crashed")

    async def _watchdog_loop(self) -> None:
        """Paranoia layer: detect heartbeat task death and respawn.

        The heartbeat loop catches every `Exception`, so this only fires when:
          - a `BaseException` (KeyboardInterrupt / SystemExit / GeneratorExit)
            killed the loop, OR
          - the task got cancelled outside of stop() somehow.

        Either way: log loudly + restart so FlowKit doesn't sweep us.
        """
        while True:
            try:
                await asyncio.sleep(self._WATCHDOG_INTERVAL_SEC)
                task = self._heartbeat_task
                if task is None or not task.done():
                    continue
                # Task died. Inspect the exception for the log, then respawn.
                exc: BaseException | None = None
                try:
                    exc = task.exception()
                except (asyncio.CancelledError, asyncio.InvalidStateError):
                    exc = None
                logger.error(
                    "Heartbeat task died unexpectedly (%s); respawning. "
                    "Restart #%d.",
                    repr(exc) if exc else "no exception",
                    self._heartbeat_restart_count + 1,
                )
                self._heartbeat_restart_count += 1
                self._last_heartbeat_error = (
                    f"task-died: {exc!r}" if exc else "task-died"
                )
                self._heartbeat_task = self._spawn_heartbeat()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Watchdog crashed; will retry next tick")

    # ── Observability ──

    def health_snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe dict for /health (or /metrics later).

        Fields:
          provider_id            : our FlowKit Provider name
          started                : sync currently running
          last_heartbeat_age_sec : seconds since the last successful heartbeat
                                    (None if never succeeded since start)
          last_heartbeat_error   : last error message, cleared on next success
          last_snapshot_age_sec  : seconds since the last successful PUT snapshot
          last_snapshot_error    : last snapshot push error
          heartbeat_restart_count: how many times the watchdog respawned hb
          heartbeat_task_alive   : True if the asyncio task is currently running
        """
        now = time.time()
        task = self._heartbeat_task
        return {
            "provider_id": self._client.provider_id,
            "started": self._started,
            "last_heartbeat_age_sec": (
                None if self._last_heartbeat_at is None
                else round(now - self._last_heartbeat_at, 1)
            ),
            "last_heartbeat_error": self._last_heartbeat_error,
            "last_snapshot_age_sec": (
                None if self._last_snapshot_at is None
                else round(now - self._last_snapshot_at, 1)
            ),
            "last_snapshot_error": self._last_snapshot_error,
            "heartbeat_restart_count": self._heartbeat_restart_count,
            "heartbeat_task_alive": (task is not None and not task.done()),
        }

    # ── Event handlers (orchestrator wires these to telephony.on_event) ──

    async def on_trunk_registered(self, event: CallEvent) -> None:
        logger.info(
            "telecom.trunk.registered trunk_id=%s provider_id=%s revision=%s",
            event.data.get("trunk_id"),
            event.data.get("provider_id"),
            event.data.get("revision"),
        )

    async def on_trunk_deregistered(self, event: CallEvent) -> None:
        reason = event.data.get("reason")
        log_fn = logger.warning if reason == "lease_expired" else logger.info
        log_fn(
            "telecom.trunk.deregistered trunk_id=%s reason=%s",
            event.data.get("trunk_id"), reason,
        )

    async def on_lease_stale(self, event: CallEvent) -> None:
        logger.warning(
            "telecom.lease.stale provider_id=%s stale_until=%s",
            event.data.get("provider_id"),
            event.data.get("stale_until"),
        )


