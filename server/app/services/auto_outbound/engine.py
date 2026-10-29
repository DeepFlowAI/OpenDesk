"""
Auto-outbound dial engine (Wave B1).

Scans active tasks, claims due targets, originates calls (or simulates them),
and finalizes target/task state from telephony events.

Reception (IVR / bot / agent) is intentionally not implemented here — see
``ReceptionDispatcher`` for the Wave B2 mount point on answer.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from app.configs.settings import settings
from app.db.session import AsyncSessionLocal
from app.models.auto_outbound import AutoOutboundTarget, AutoOutboundTask
from app.models.phone_number import PhoneNumber
from app.repositories.auto_outbound_repository import AutoOutboundRepository
from app.services.auto_outbound import frequency as freq
from app.services.auto_outbound.outcome_mapping import (
    AutoOutboundTerminalState,
    map_outcome,
)
from app.services.auto_outbound.tenant_time import resolve_tenant_timezone
from app.services.auto_outbound_task_service import is_out_of_daily_window
from app.services.auto_outbound_event_service import AutoOutboundEventService

logger = logging.getLogger(__name__)

# Machine-readable auto-pause reason codes stored on
# auto_outbound_tasks.auto_pause_reason. The frontend maps codes to localized
# copy; legacy rows may hold free-form Chinese copy and are rendered as-is.
AUTO_PAUSE_REASON_DIAL_UNAVAILABLE = "dial_service_unavailable"
AUTO_PAUSE_REASON_QUEUE_FINISHED = "queue_finished"

# Stale calling targets without a live Redis session are swept to redial_pending.
STALE_CALLING_THRESHOLD = timedelta(minutes=30)
STALE_CALLING_REDIAL_DELAY = timedelta(minutes=5)
# Real telephony post-answer hold when no reception dispatcher is mounted.
DEFAULT_POST_ANSWER_HANGUP_SECONDS = 30.0
# Cap a single originate so one tick cannot stall the worker.
ORIGINATE_TIMEOUT_SECONDS = 10.0
ORIGINATE_FAILURE_RETRY_DELAY = timedelta(minutes=10)

# Terminal states that may be retried per task.retry_policy.
_RETRIABLE = frozenset(
    {
        AutoOutboundTerminalState.NO_ANSWER.value,
        AutoOutboundTerminalState.BUSY.value,
        AutoOutboundTerminalState.POWER_OFF.value,
    }
)


@dataclass(frozen=True)
class DialSessionContext:
    """Context stashed in Redis under auto_outbound:session:{call_id}."""

    tenant_id: int
    task_id: int
    target_id: int
    record_id: int
    phone_number: str
    queue_id: int | None = None
    answered: bool = False
    call_id: str | None = None
    attempt_id: str | None = None
    trunk_key: str | None = None


class ReceptionDispatcher(Protocol):
    """
    Wave B2 mount point.

    Invoked after a call is answered and the auto-outbound record has been
    marked answered. Implementations should start IVR / VoiceSpeed / agent
    bridging without holding a DB session across media I/O.
    """

    async def on_answered(self, ctx: DialSessionContext) -> None: ...


class PacingResolver(Protocol):
    """
    Resolve both the claim batch and the shared reception-queue capacity.

    ``resolve_claim_limit`` remains supported for older resolver implementations.
    """

    async def resolve_claim_limit(self, task_snap: dict, *, batch_size: int) -> int: ...

    async def resolve(self, task_snap: dict, *, batch_size: int) -> Any: ...


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    parts = str(value or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def next_daily_window_start(
    daily_time_windows: list[dict] | list[Any] | None,
    *,
    now: datetime | None = None,
    tz: ZoneInfo | None = None,
) -> datetime:
    """
    Earliest configured window start on the next tenant (or local) calendar day.

    Used when a number hits its daily frequency limit so it is deferred past
    midnight into the next callable window.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(tz) if tz is not None else current.astimezone()
    tomorrow = local.date() + timedelta(days=1)

    starts: list[tuple[int, int]] = []
    for window in daily_time_windows or []:
        if isinstance(window, dict):
            start_raw = window.get("start")
        else:
            start_raw = getattr(window, "start", None)
        parsed = _parse_hhmm(str(start_raw or ""))
        if parsed is not None:
            starts.append(parsed)
    if not starts:
        return datetime.combine(tomorrow, time(0, 0), tzinfo=local.tzinfo)
    hour, minute = min(starts)
    return datetime.combine(tomorrow, time(hour, minute), tzinfo=local.tzinfo)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_uncertain_originate_error(exc: BaseException) -> bool:
    """True when FlowKit may already have started SIP despite a local failure."""
    from app.libs.telephony.base import TelephonyNotConnectedError, TelephonyRPCError

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, TelephonyNotConnectedError)):
        return True
    if isinstance(exc, TelephonyRPCError):
        return False
    return True


def _local_today(now: datetime | None = None, *, tz: ZoneInfo | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if tz is not None:
        return current.astimezone(tz).date()
    return current.astimezone().date()


def _is_simulation_enabled() -> bool:
    """Simulation is gated only by settings — injecting a simulator must not override."""
    return bool(settings.AUTO_OUTBOUND_SIMULATION_ENABLED)


class AutoOutboundDialEngine:
    def __init__(
        self,
        *,
        redis: Any | None = None,
        session_factory=AsyncSessionLocal,
        telephony_factory=None,
        reception: ReceptionDispatcher | None = None,
        pacing_resolver: PacingResolver | None = None,
        simulator=None,
    ) -> None:
        self._redis = redis
        self._session_factory = session_factory
        self._telephony_factory = telephony_factory
        # Wave B2: set to an IVR/bot/agent dispatcher; None → hang up after
        # a short simulated talk window (or immediately when ring path ends).
        self._reception: ReceptionDispatcher | None = reception
        # Wave B2: agent-mode dial slots; None → claim up to batch_size (B1).
        self._pacing_resolver: PacingResolver | None = pacing_resolver
        self._simulator = simulator
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._stop_event = asyncio.Event()

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="auto-outbound-dial-worker")
        logger.info("Auto outbound dial worker started")

    async def stop(self) -> None:
        self._stopping = True
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None
        if self._simulator is not None and hasattr(self._simulator, "drain"):
            await self._simulator.drain()
        logger.info("Auto outbound dial worker stopped")

    async def _run_loop(self) -> None:
        interval = max(1, int(settings.AUTO_OUTBOUND_DIAL_SCAN_INTERVAL_SECONDS))
        while not self._stopping:
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Auto outbound dial scan failed")
            if self._stopping:
                break
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                pass

    # ── redis helpers ──────────────────────────────────────────────────────

    def _r(self) -> Any:
        if self._redis is not None:
            return self._redis
        return freq._default_redis()

    async def has_session(self, call_id: str) -> bool:
        return await freq.get_session_mapping(call_id, redis=self._r()) is not None

    async def _load_session(self, call_id: str) -> DialSessionContext | None:
        data = await freq.get_session_mapping(call_id, redis=self._r())
        if not data:
            return None
        try:
            return DialSessionContext(
                tenant_id=int(data["tenant_id"]),
                task_id=int(data["task_id"]),
                target_id=int(data["target_id"]),
                record_id=int(data["record_id"]),
                phone_number=str(data.get("phone_number") or ""),
                queue_id=int(data["queue_id"]) if data.get("queue_id") else None,
                answered=bool(data.get("answered", False)),
                call_id=str(data["call_id"]) if data.get("call_id") else call_id,
                attempt_id=str(data["attempt_id"]) if data.get("attempt_id") else None,
                trunk_key=str(data["trunk_key"]) if data.get("trunk_key") else None,
            )
        except (KeyError, TypeError, ValueError):
            return None

    async def _store_session(self, call_id: str, ctx: DialSessionContext) -> None:
        await freq.set_session_mapping(
            call_id,
            {
                "tenant_id": ctx.tenant_id,
                "task_id": ctx.task_id,
                "target_id": ctx.target_id,
                "record_id": ctx.record_id,
                "phone_number": ctx.phone_number,
                "queue_id": ctx.queue_id,
                "answered": ctx.answered,
                "call_id": call_id,
                "attempt_id": ctx.attempt_id,
                "trunk_key": ctx.trunk_key,
            },
            redis=self._r(),
        )

    async def bind_session_from_attempt(self, call_id: str, request_id: str | None) -> bool:
        """Attach a pending attempt session to call_id when events arrive first."""
        if await self.has_session(call_id):
            return False
        if not request_id:
            return False
        data = await freq.get_session_by_attempt(request_id, redis=self._r())
        if not data:
            return False
        ctx = await self._load_session(call_id)
        if ctx is None:
            try:
                ctx = DialSessionContext(
                    tenant_id=int(data["tenant_id"]),
                    task_id=int(data["task_id"]),
                    target_id=int(data["target_id"]),
                    record_id=int(data["record_id"]),
                    phone_number=str(data.get("phone_number") or ""),
                    answered=bool(data.get("answered", False)),
                    call_id=call_id,
                    queue_id=int(data["queue_id"]) if data.get("queue_id") else None,
                    attempt_id=str(data.get("attempt_id") or request_id),
                    trunk_key=str(data["trunk_key"]) if data.get("trunk_key") else None,
                )
            except (KeyError, TypeError, ValueError):
                return False
        await self._store_session(call_id, ctx)
        return True

    async def _release_inflight(self, ctx: DialSessionContext) -> None:
        await self._release_dial_slot(
            task_id=ctx.task_id,
            tenant_id=ctx.tenant_id,
            queue_id=ctx.queue_id,
            target_id=ctx.target_id,
        )
        await freq.release_tenant_trunk(
            tenant_id=ctx.tenant_id, trunk_key=ctx.trunk_key, redis=self._r()
        )

    async def _reconcile_attempt(self, attempt_id: str) -> str | None:
        if _is_simulation_enabled():
            return None
        try:
            if self._telephony_factory is not None:
                telephony = self._telephony_factory()
            else:
                from app.libs.telephony.factory import get_telephony_client

                telephony = get_telephony_client()
            calls = await telephony.call_list()
        except Exception:  # noqa: BLE001
            logger.warning("auto_outbound reconcile call_list failed attempt=%s", attempt_id, exc_info=True)
            return None
        for row in calls or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("request_id") or "") == attempt_id and row.get("call_id"):
                return str(row["call_id"])
        return None

    # ── scan / claim / dial ────────────────────────────────────────────────

    async def scan_once(self, *, now: datetime | None = None) -> dict[str, int]:
        """
        One worker tick. Returns counters for tests / logging.

        Holds DB sessions only around claim / persist steps — never across
        telephony originate awaits (CLAUDE.md §8).
        """
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        batch_size = max(1, int(settings.AUTO_OUTBOUND_DIAL_BATCH_SIZE))
        stats = {
            "tasks": 0,
            "claimed": 0,
            "dialed": 0,
            "skipped": 0,
            "completed_tasks": 0,
            "swept_stale": 0,
        }

        async with self._session_factory() as db:
            active = await AutoOutboundRepository.list_active_tasks(db)
            # Paused tasks join the scan only for the end_date expiry check.
            paused = await AutoOutboundRepository.list_paused_tasks(db)
            # Materialize lightweight snapshots so we can close the session
            # before per-target dial I/O.
            task_rows = [
                {
                    "id": t.id,
                    "tenant_id": t.tenant_id,
                    "status": t.status,
                    "start_date": t.start_date,
                    "end_date": t.end_date,
                    "daily_time_windows": list(t.daily_time_windows or []),
                    "caller_number_id": t.caller_number_id,
                    "max_concurrency": int(t.max_concurrency or 1),
                    "daily_per_number_limit": int(t.daily_per_number_limit or 1),
                    "retry_policy": dict(t.retry_policy or {}),
                    "execution_mode": t.execution_mode,
                    "queue_id": t.queue_id,
                    "pacing_mode": t.pacing_mode,
                    "dial_ratio": t.dial_ratio,
                    "dial_intensity": float(t.dial_intensity) if t.dial_intensity is not None else None,
                    "abandon_rate_limit": float(t.abandon_rate_limit)
                    if t.abandon_rate_limit is not None
                    else None,
                    "wrapup_seconds": int(t.wrapup_seconds or 60),
                }
                for t in [*active, *paused]
            ]

        # Resolve tenant timezones once per unique tenant (not per target).
        tenant_ids = {int(s["tenant_id"]) for s in task_rows}
        tz_by_tenant: dict[int, ZoneInfo] = {}
        if tenant_ids:
            async with self._session_factory() as db:
                for tid in tenant_ids:
                    tz_by_tenant[tid] = await resolve_tenant_timezone(db, tid)

        # Recover calling targets stuck without a live Redis session.
        try:
            stats["swept_stale"] = await self._sweep_stale_calling(
                now=current.astimezone(timezone.utc)
            )
        except Exception:  # noqa: BLE001
            logger.exception("auto_outbound stale calling sweep failed")

        for snap in task_rows:
            if self._stopping:
                break
            stats["tasks"] += 1
            task_id = int(snap["id"])
            tenant_id = int(snap["tenant_id"])
            tz = tz_by_tenant.get(tenant_id) or ZoneInfo("Asia/Shanghai")
            today = _local_today(current, tz=tz)
            local_now = current.astimezone(tz)

            # Past end_date → stop dialing; complete when nothing is in-flight.
            if snap["end_date"] < today:
                await self._maybe_complete_expired_task(task_id, tenant_id=tenant_id)
                stats["completed_tasks"] += 1
                continue
            # Paused tasks are only scanned for the expiry completion above.
            if snap["status"] != "active":
                continue
            if snap["start_date"] > today:
                continue
            # Pass tenant-local now so hour/minute window checks use tenant TZ.
            if is_out_of_daily_window(snap["daily_time_windows"], now=local_now):
                stats["skipped"] += 1
                continue

            claim_limit = batch_size
            queue_capacity: int | None = None
            if self._pacing_resolver is not None:
                try:
                    resolve = getattr(self._pacing_resolver, "resolve", None)
                    if resolve is not None:
                        resolution = await resolve(snap, batch_size=batch_size)
                        claim_limit = int(resolution.claim_limit)
                        queue_capacity = resolution.queue_capacity
                    else:
                        claim_limit = await self._pacing_resolver.resolve_claim_limit(
                            snap, batch_size=batch_size
                        )
                except Exception:  # noqa: BLE001
                    if snap.get("execution_mode") == "agent":
                        logger.exception(
                            "auto_outbound pacing resolve failed task=%s — skipping agent dial",
                            task_id,
                        )
                        claim_limit = 0
                    else:
                        logger.exception(
                            "auto_outbound pacing resolve failed task=%s — using batch_size",
                            task_id,
                        )
                        claim_limit = batch_size
            claim_limit = max(0, min(int(claim_limit), batch_size))
            if claim_limit <= 0:
                stats["skipped"] += 1
                continue

            async with self._session_factory() as db:
                claimed = await AutoOutboundRepository.claim_due_targets(
                    db, task_id=task_id, now=current.astimezone(timezone.utc), limit=claim_limit
                )
            stats["claimed"] += len(claimed)

            next_claim_index = 0
            try:
                while next_claim_index < len(claimed) and not self._stopping:
                    if not await self._is_task_active(task_id):
                        logger.info(
                            "Stopped auto outbound claim batch for inactive task=%s remaining=%s",
                            task_id,
                            len(claimed) - next_claim_index,
                        )
                        break
                    target, previous_status = claimed[next_claim_index]
                    # This claim is now owned by the processing path. Exclude it
                    # from tail restoration even if processing raises after dial.
                    next_claim_index += 1
                    dialed = await self._process_claimed_target(
                        snap,
                        target_id=target.id,
                        phone_number=target.phone_number,
                        call_count=int(target.call_count or 0),
                        previous_status=previous_status,
                        now=current,
                        tz=tz,
                        queue_capacity=queue_capacity,
                    )
                    if dialed:
                        stats["dialed"] += 1
                    else:
                        stats["skipped"] += 1
            finally:
                unprocessed = claimed[next_claim_index:]
                if unprocessed:
                    async with self._session_factory() as db:
                        restored = await AutoOutboundRepository.restore_claimed_targets(
                            db,
                            [(target.id, previous_status) for target, previous_status in unprocessed],
                        )
                    logger.info(
                        "Restored unprocessed auto outbound claims task=%s restored=%s claimed=%s",
                        task_id,
                        restored,
                        len(unprocessed),
                    )

            await self._maybe_pause_task_when_queue_finished(task_id, tenant_id=tenant_id)

        return stats

    async def _sweep_stale_calling(self, *, now: datetime) -> int:
        """
        Move calling targets with no live Redis session and stale updated_at
        back to redial_pending so they are not stuck forever.
        """
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cutoff = now - STALE_CALLING_THRESHOLD
        async with self._session_factory() as db:
            stale_rows = await AutoOutboundRepository.list_stale_calling_targets(
                db, updated_before=cutoff
            )
        stale = list(stale_rows) if isinstance(stale_rows, (list, tuple)) else []

        swept = 0
        for target in stale:
            if await freq.has_session_for_target(target.id, redis=self._r()):
                continue
            next_at = now + STALE_CALLING_REDIAL_DELAY
            async with self._session_factory() as db:
                row = await AutoOutboundRepository.get_target(db, target.id)
                if row is None or row.status != "calling":
                    continue
                await AutoOutboundRepository.update_target(
                    db,
                    row,
                    {
                        "status": "redial_pending",
                        "next_call_at": next_at,
                        "last_call_result": AutoOutboundTerminalState.FAILED.value,
                    },
                    commit=False,
                )
                open_record = await AutoOutboundRepository.get_open_record_for_target(
                    db, target_id=target.id
                )
                if open_record is not None and open_record.terminal_state is None:
                    persisted_terminal = await AutoOutboundRepository.finalize_record_once(
                        db,
                        record_id=open_record.id,
                        ended_at=now,
                        terminal_state=AutoOutboundTerminalState.FAILED.value,
                        fail_reason="swept_stale_calling",
                        duration_ms=int(open_record.duration_ms or 0),
                        commit=False,
                    )
                    if persisted_terminal is not None:
                        await db.refresh(open_record)
                        task = await AutoOutboundRepository.get_task(db, target.task_id)
                        if task is not None:
                            await AutoOutboundEventService.emit_call_event(
                                db,
                                task=task,
                                target=row,
                                record=open_record,
                                event_type="auto_outbound.call.ended",
                                occurred_at=now,
                            )
                await db.commit()
            swept += 1
            logger.warning(
                "auto_outbound swept stale calling target_id=%s task_id=%s",
                target.id,
                target.task_id,
            )
        return swept

    async def _process_claimed_target(
        self,
        task_snap: dict,
        *,
        target_id: int,
        phone_number: str,
        call_count: int,
        previous_status: str,
        now: datetime,
        tz: ZoneInfo,
        queue_capacity: int | None = None,
    ) -> bool:
        task_id = int(task_snap["id"])
        tenant_id = int(task_snap["tenant_id"])
        max_concurrency = int(task_snap["max_concurrency"])
        daily_limit = int(task_snap["daily_per_number_limit"])
        windows = task_snap["daily_time_windows"]
        queue_id = (
            int(task_snap["queue_id"])
            if task_snap.get("execution_mode") == "agent"
            and task_snap.get("queue_id")
            and queue_capacity is not None
            else None
        )
        trunk_key = str(task_snap["caller_number_id"]) if task_snap.get("caller_number_id") else None
        tenant_cap = int(getattr(settings, "AUTO_OUTBOUND_TENANT_MAX_CONCURRENCY", 0) or 0)
        tenant_limit = tenant_cap if tenant_cap > 0 else None
        trunk_limit = task_snap.get("caller_number_concurrency")
        if trunk_limit is not None:
            try:
                trunk_limit = int(trunk_limit)
            except (TypeError, ValueError):
                trunk_limit = None
            if trunk_limit is not None and trunk_limit <= 0:
                trunk_limit = None

        # Concurrency BEFORE frequency so a full slot does not burn a daily count.
        if queue_id is not None:
            acquired = await freq.acquire_pacing_slot(
                task_id,
                max_concurrency,
                tenant_id=tenant_id,
                queue_id=queue_id,
                queue_capacity=int(queue_capacity or 0),
                target_id=target_id,
                redis=self._r(),
            )
        else:
            acquired = await freq.acquire_concurrency(
                task_id, max_concurrency, redis=self._r()
            )
        if not acquired:
            await self._restore_target_status(target_id, previous_status)
            return False
        if not await freq.acquire_tenant_trunk(
            tenant_id=tenant_id,
            tenant_limit=tenant_limit,
            trunk_key=trunk_key,
            trunk_limit=trunk_limit,
            redis=self._r(),
        ):
            await self._release_dial_slot(
                task_id=task_id,
                tenant_id=tenant_id,
                queue_id=queue_id,
                target_id=target_id,
            )
            await self._restore_target_status(target_id, previous_status)
            return False

        allowed = await freq.check_and_incr(
            task_id, phone_number, daily_limit, redis=self._r(), now=now, tz=tz
        )
        if not allowed:
            await self._release_dial_slot(
                task_id=task_id,
                tenant_id=tenant_id,
                queue_id=queue_id,
                target_id=target_id,
            )
            await freq.release_tenant_trunk(
                tenant_id=tenant_id, trunk_key=trunk_key, redis=self._r()
            )
            # Keep status pending and push next_call_at past today's windows.
            # Frequency counter is intentionally not rolled back.
            defer_at = next_daily_window_start(windows, now=now, tz=tz)
            async with self._session_factory() as db:
                target = await AutoOutboundRepository.get_target(db, target_id)
                if target is not None:
                    await AutoOutboundRepository.update_target(
                        db,
                        target,
                        {"status": "pending", "next_call_at": defer_at},
                    )
            return False

        attempt_no = call_count + 1
        attempt_id = uuid.uuid4().hex
        record_id: int | None = None
        try:
            async with self._session_factory() as db:
                record = await AutoOutboundRepository.create_record(
                    db,
                    {
                        "tenant_id": tenant_id,
                        "task_id": task_id,
                        "target_id": target_id,
                        "phone_number": phone_number,
                        "attempt_id": attempt_id,
                        "attempt_no": attempt_no,
                        "started_at": _utc_now(),
                        "reception_type": None,
                    },
                    commit=False,
                )
                record_id = record.id
                target = await AutoOutboundRepository.get_target(db, target_id)
                if target is not None:
                    await AutoOutboundRepository.update_target(
                        db,
                        target,
                        {
                            "call_count": attempt_no,
                            "last_called_at": _utc_now(),
                        },
                        commit=False,
                    )
                    task = await AutoOutboundRepository.get_task(db, task_id)
                    if task is not None:
                        await AutoOutboundEventService.emit_call_event(
                            db,
                            task=task,
                            target=target,
                            record=record,
                            event_type="auto_outbound.call.started",
                            occurred_at=record.started_at,
                        )
                await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "auto_outbound create_record failed task=%s target=%s", task_id, target_id
            )
            await self._release_dial_slot(
                task_id=task_id,
                tenant_id=tenant_id,
                queue_id=queue_id,
                target_id=target_id,
            )
            await freq.release_tenant_trunk(
                tenant_id=tenant_id, trunk_key=trunk_key, redis=self._r()
            )
            await self._restore_target_status(target_id, previous_status)
            return False

        assert record_id is not None
        ctx = DialSessionContext(
            tenant_id=tenant_id,
            task_id=task_id,
            target_id=target_id,
            record_id=record_id,
            phone_number=phone_number,
            queue_id=queue_id,
            attempt_id=attempt_id,
            trunk_key=trunk_key,
        )
        # Persist the attempt mapping before RPC so early FlowKit events can bind.
        await self._store_session("", ctx)

        try:
            call_id, originate_meta = await asyncio.wait_for(
                self._originate(task_snap, phone_number=phone_number, ctx=ctx),
                timeout=ORIGINATE_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "auto_outbound originate failed task=%s target=%s: %s",
                task_id,
                target_id,
                exc,
            )
            if _is_uncertain_originate_error(exc):
                reconciled = await self._reconcile_attempt(attempt_id)
                if reconciled:
                    await self._store_session(reconciled, ctx)
                    await self._ensure_call_record_linked(ctx, reconciled)
                    await freq.clear_consecutive_failures(task_id, redis=self._r())
                    return True
                logger.warning(
                    "auto_outbound originate uncertain task=%s target=%s attempt=%s — holding calling",
                    task_id,
                    target_id,
                    attempt_id,
                )
                return True
            await self._on_originate_failure(
                ctx, fail_reason=str(exc) or "originate_failed", now=now, tz=tz
            )
            return False

        await self._store_session(call_id, ctx)
        await self._ensure_call_record_linked(ctx, call_id, **originate_meta)
        await freq.clear_consecutive_failures(task_id, redis=self._r())

        if _is_simulation_enabled():
            await self._start_simulation(call_id)
        return True

    async def _originate(
        self,
        task_snap: dict,
        *,
        phone_number: str,
        ctx: DialSessionContext,
    ) -> tuple[str, dict[str, Any]]:
        if _is_simulation_enabled():
            from app.services.auto_outbound.simulator import new_simulated_call_id

            return new_simulated_call_id(), {}

        caller_number_id = task_snap.get("caller_number_id")
        if not caller_number_id:
            raise RuntimeError("caller_number_id missing")

        # Short session: resolve DID / trunk / prefix, then close before RPC.
        async with self._session_factory() as db:
            number = await db.get(PhoneNumber, caller_number_id)
            if number is None:
                raise RuntimeError("caller phone number not found")
            caller_id = number.phone_number
            trunk_id = number.trunk_id
            prefix = (number.called_number_prefix or "").strip()
            dialed = prefix + phone_number if prefix and not phone_number.startswith(prefix) else phone_number

        if self._telephony_factory is not None:
            telephony = self._telephony_factory()
        else:
            from app.libs.telephony.factory import get_telephony_client

            telephony = get_telephony_client()

        # System / agentless originate: no employee, no SIP extension —
        # only destination URI + outbound DID + trunk (FlowKit defaults apply
        # when trunk_id is None).
        result = await telephony.call_originate(
            uri=dialed,
            caller_id=caller_id,
            trunk_id=trunk_id,
            request_id=ctx.attempt_id,
        )
        call_id = result.get("call_id")
        if not call_id:
            raise RuntimeError("telephony returned no call_id")

        return str(call_id), {
            "conversation_id": result.get("conversation_id"),
            "root_call_id": result.get("root_call_id") or str(call_id),
            "from_number": caller_id,
        }

    async def _ensure_call_record_linked(
        self,
        ctx: DialSessionContext,
        call_id: str,
        *,
        conversation_id: str | None = None,
        root_call_id: str | None = None,
        from_number: str | None = None,
    ) -> None:
        """Create the CDR if needed and persist auto_outbound_call_records.call_record_id.

        Kept outside the originate RPC timeout so a slow CDR write cannot cancel a
        live SIP session, and reused on reconcile / answer / hangup so a missed
        link can still be backfilled.
        """
        if not call_id or _is_simulation_enabled():
            return
        try:
            async with self._session_factory() as db:
                from app.services.call_record_service import CallRecordService

                record = await AutoOutboundRepository.get_record(db, ctx.record_id)
                if record is not None and record.call_record_id is not None:
                    return

                detail = await CallRecordService.create_for_outbound(
                    db,
                    ctx.tenant_id,
                    call_id=str(call_id),
                    conversation_id=conversation_id,
                    root_call_id=root_call_id or str(call_id),
                    from_number=from_number,
                    to_number=ctx.phone_number,
                    agent_id=None,
                    call_source="auto_outbound",
                    identify_user=False,
                )
                cdr_id = detail.get("id") if isinstance(detail, dict) else None
                if not isinstance(cdr_id, int):
                    return
                await AutoOutboundRepository.set_call_record_id_if_empty(
                    db, ctx.record_id, cdr_id
                )
                try:
                    from app.services.call_center.orchestrator import get_orchestrator

                    orch = get_orchestrator()
                except Exception:  # noqa: BLE001
                    orch = None
                if orch is not None:
                    await orch.finalize_outbound_cdr_if_already_ended(
                        db,
                        tenant_id=ctx.tenant_id,
                        call_id=str(call_id),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "auto_outbound CallRecord create skipped "
                "tenant_id=%s record_id=%s call_id=%s error=%s",
                ctx.tenant_id,
                ctx.record_id,
                call_id,
                exc,
            )
            return
        self._spawn_user_identify(ctx.tenant_id, str(call_id))

    def _spawn_user_identify(self, tenant_id: int, call_id: str) -> None:
        """Match callee→user off the answer / reception path."""
        from app.services.call_record_service import CallRecordService

        async def _identify() -> None:
            try:
                await CallRecordService.identify_user_for_call_managed(tenant_id, call_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "auto_outbound background user identify failed call_id=%s", call_id
                )

        asyncio.create_task(_identify(), name=f"identify-auto-outbound-{call_id}")

    async def _start_simulation(self, call_id: str) -> None:
        from app.services.auto_outbound.simulator import CallSimulator

        sim = self._simulator
        if sim is None:
            sim = CallSimulator()
            self._simulator = sim
        sim.spawn(
            call_id,
            on_answered=self.handle_call_answered,
            on_ended=self.handle_call_ended,
        )

    async def _on_originate_failure(
        self,
        ctx: DialSessionContext,
        *,
        fail_reason: str,
        now: datetime | None = None,
        tz: ZoneInfo | None = None,
    ) -> None:
        await self._release_inflight(ctx)
        await freq.rollback_daily_count(
            ctx.task_id, ctx.phone_number, redis=self._r(), now=now, tz=tz
        )
        utc_now = _utc_now()
        retry_at = utc_now + ORIGINATE_FAILURE_RETRY_DELAY
        async with self._session_factory() as db:
            record = await AutoOutboundRepository.get_record(db, ctx.record_id)
            target = await AutoOutboundRepository.get_target(db, ctx.target_id)
            task = await AutoOutboundRepository.get_task(db, ctx.task_id)
            persisted_terminal = None
            if record is not None:
                persisted_terminal = await AutoOutboundRepository.finalize_record_once(
                    db,
                    record_id=record.id,
                    ended_at=utc_now,
                    terminal_state=AutoOutboundTerminalState.FAILED.value,
                    fail_reason=fail_reason[:500],
                    duration_ms=0,
                    commit=False,
                )
            if target is not None:
                # Do not burn the number — park for a short retry instead of completing.
                await AutoOutboundRepository.update_target(
                    db,
                    target,
                    {
                        "status": "pending",
                        "last_call_result": AutoOutboundTerminalState.FAILED.value,
                        "next_call_at": retry_at,
                    },
                    commit=False,
                )
            if persisted_terminal is not None and record is not None:
                await db.refresh(record)
                if task is not None and target is not None:
                    await AutoOutboundEventService.emit_call_event(
                        db,
                        task=task,
                        target=target,
                        record=record,
                        event_type="auto_outbound.call.ended",
                        occurred_at=utc_now,
                    )
            await db.commit()

        failures = await freq.incr_consecutive_failures(ctx.task_id, redis=self._r())
        threshold = max(1, int(settings.AUTO_OUTBOUND_AUTO_PAUSE_CONSECUTIVE_FAILURES))
        if failures >= threshold:
            await self._auto_pause_task(ctx.task_id, ctx.tenant_id)

    async def _auto_pause_task(self, task_id: int, tenant_id: int) -> None:
        async with self._session_factory() as db:
            task = await AutoOutboundRepository.get_task(db, task_id)
            if task is None or task.status != "active":
                return
            previous_status = task.status
            now = _utc_now()
            updated = await AutoOutboundRepository.update_task(
                db,
                task,
                {
                    "status": "paused",
                    "auto_pause_reason": AUTO_PAUSE_REASON_DIAL_UNAVAILABLE,
                },
                commit=False,
            )
            await AutoOutboundEventService.emit_task_event(
                db,
                task=updated,
                event_type="auto_outbound.task.paused",
                occurred_at=now,
                actor={"type": "system"},
                previous_status=previous_status,
                reason="dial_unavailable",
            )
            await db.commit()
        await freq.reset_concurrency(task_id, redis=self._r())
        await freq.clear_consecutive_failures(task_id, redis=self._r())
        logger.warning(
            "auto_outbound task %s auto-paused (tenant=%s): %s",
            task_id,
            tenant_id,
            AUTO_PAUSE_REASON_DIAL_UNAVAILABLE,
        )

    async def _release_dial_slot(
        self,
        *,
        task_id: int,
        tenant_id: int,
        queue_id: int | None,
        target_id: int,
    ) -> None:
        if queue_id is None:
            await freq.release_concurrency(task_id, redis=self._r())
            return
        await freq.release_pacing_slot(
            task_id,
            tenant_id=tenant_id,
            queue_id=queue_id,
            target_id=target_id,
            redis=self._r(),
        )

    async def _restore_target_status(self, target_id: int, status: str) -> None:
        async with self._session_factory() as db:
            target = await AutoOutboundRepository.get_target(db, target_id)
            if target is not None and target.status == "calling":
                await AutoOutboundRepository.update_target(db, target, {"status": status})

    async def _is_task_active(self, task_id: int) -> bool:
        """Re-check task state immediately before starting the next call."""
        async with self._session_factory() as db:
            return await AutoOutboundRepository.is_task_active(db, task_id)

    # ── event handlers ─────────────────────────────────────────────────────

    async def handle_call_answered(self, call_id: str) -> None:
        ctx = await self._load_session(call_id)
        if ctx is None:
            return

        await self._ensure_call_record_linked(ctx, call_id)

        # Duplicate answered events: skip reception; count only on first mark.
        if ctx.answered:
            return

        now = _utc_now()
        async with self._session_factory() as db:
            is_first_answer = await AutoOutboundRepository.mark_answered_once(
                db,
                record_id=ctx.record_id,
                target_id=ctx.target_id,
                answered_at=now,
                commit=False,
            )
            if is_first_answer:
                task = await AutoOutboundRepository.get_task(db, ctx.task_id)
                target = await AutoOutboundRepository.get_target(db, ctx.target_id)
                record = await AutoOutboundRepository.get_record(db, ctx.record_id)
                if task is not None and target is not None and record is not None:
                    await AutoOutboundEventService.emit_call_event(
                        db,
                        task=task,
                        target=target,
                        record=record,
                        event_type="auto_outbound.call.answered",
                        occurred_at=now,
                    )
                await db.commit()

        if not is_first_answer:
            return

        answered_ctx = DialSessionContext(
            tenant_id=ctx.tenant_id,
            task_id=ctx.task_id,
            target_id=ctx.target_id,
            record_id=ctx.record_id,
            phone_number=ctx.phone_number,
            queue_id=ctx.queue_id,
            answered=True,
            call_id=call_id,
            attempt_id=ctx.attempt_id,
            trunk_key=ctx.trunk_key,
        )
        await self._store_session(call_id, answered_ctx)

        # Wave B2 mount: reception dispatcher takes over the live call.
        # Default (None): keep the call alive until hangup arrives. In
        # simulation mode the simulator already schedules talk + hangup;
        # for real telephony without a dispatcher we hang up after a short
        # hold so agentless tasks do not linger forever.
        if self._reception is not None:
            try:
                await self._reception.on_answered(answered_ctx)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "auto_outbound reception dispatcher failed call_id=%s", call_id
                )
        elif not _is_simulation_enabled():
            asyncio.create_task(
                self._default_post_answer_hangup(call_id),
                name=f"auto-outbound-hangup-{call_id}",
            )

    async def _default_post_answer_hangup(self, call_id: str) -> None:
        """Placeholder until Wave B2 wires real reception — brief hold then hangup."""
        try:
            await asyncio.sleep(DEFAULT_POST_ANSWER_HANGUP_SECONDS)
            if self._telephony_factory is not None:
                telephony = self._telephony_factory()
            else:
                from app.libs.telephony.factory import get_telephony_client

                telephony = get_telephony_client()
            await telephony.call_hangup(call_id, reason="auto_outbound_no_reception")
        except Exception:  # noqa: BLE001
            logger.exception("default post-answer hangup failed call_id=%s", call_id)

    async def handle_call_ended(
        self,
        call_id: str,
        reason: str | None = None,
        sip_status: int | None = None,
    ) -> None:
        ctx = await self._load_session(call_id)
        if ctx is None:
            return

        await self._ensure_call_record_linked(ctx, call_id)

        # Only treat as answered when we previously saw call.answered (Redis
        # flag / answered_at). Do not infer from hangup reason alone — carriers
        # often send reason=normal for unanswered clearings too.
        terminal = map_outcome(reason, sip_status, answered=ctx.answered)

        now = _utc_now()
        owns_finalization = False
        try:
            async with self._session_factory() as db:
                record = await AutoOutboundRepository.get_record(db, ctx.record_id)
                if record is None:
                    return

                start = record.answered_at or record.started_at
                duration_ms = 0
                if start is not None:
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=timezone.utc)
                    duration_ms = max(0, int((now - start).total_seconds() * 1000))

                fail_reason = (
                    reason or "failed"
                    if terminal == AutoOutboundTerminalState.FAILED
                    else None
                )
                persisted_terminal = await AutoOutboundRepository.finalize_record_once(
                    db,
                    record_id=ctx.record_id,
                    ended_at=now,
                    duration_ms=duration_ms,
                    terminal_state=terminal.value,
                    fail_reason=fail_reason,
                    commit=False,
                )
                if persisted_terminal is None:
                    return
                terminal = AutoOutboundTerminalState(persisted_terminal)
                await db.refresh(record)

                task = await AutoOutboundRepository.get_task(db, ctx.task_id)
                target = await AutoOutboundRepository.get_target(db, ctx.target_id)

                if target is not None:
                    await self._apply_target_terminal(
                        db,
                        target,
                        task=task,
                        terminal=terminal,
                        now=now,
                    )

                if task is not None and target is not None:
                    await AutoOutboundEventService.emit_call_event(
                        db,
                        task=task,
                        target=target,
                        record=record,
                        event_type="auto_outbound.call.ended",
                        occurred_at=now,
                    )

                await self._maybe_pause_task_when_queue_finished_locked(db, ctx.task_id)
                await db.commit()
                owns_finalization = True
        finally:
            # Only the process that atomically finalized the record owns cleanup.
            if owns_finalization:
                await self._release_inflight(ctx)
                await freq.delete_session_mapping(call_id, redis=self._r())

    async def _apply_target_terminal(
        self,
        db,
        target: AutoOutboundTarget,
        *,
        task: AutoOutboundTask | None,
        terminal: AutoOutboundTerminalState,
        now: datetime,
    ) -> None:
        updates: dict[str, Any] = {
            "last_call_result": terminal.value,
        }
        if terminal == AutoOutboundTerminalState.ANSWERED:
            updates["status"] = "completed"
            updates["next_call_at"] = None
        elif terminal == AutoOutboundTerminalState.INVALID_NUMBER:
            updates["status"] = "invalid"
            updates["next_call_at"] = None
        elif terminal == AutoOutboundTerminalState.FAILED:
            updates["status"] = "completed"
            updates["next_call_at"] = None
        elif terminal.value in _RETRIABLE:
            policy = (task.retry_policy if task is not None else None) or {}
            item = policy.get(terminal.value) or {}
            max_retries = int(item.get("max_retries", 0) or 0)
            interval_minutes = int(item.get("interval_minutes", 120) or 120)
            counts = dict(target.retry_counts or {})
            used = int(counts.get(terminal.value, 0) or 0)
            if used < max_retries:
                counts[terminal.value] = used + 1
                updates["retry_counts"] = counts
                updates["status"] = "redial_pending"
                updates["next_call_at"] = now + timedelta(minutes=interval_minutes)
            else:
                updates["status"] = "completed"
                updates["next_call_at"] = None
                updates["retry_counts"] = counts
        else:
            updates["status"] = "completed"
            updates["next_call_at"] = None

        await AutoOutboundRepository.update_target(db, target, updates, commit=False)

    async def _maybe_pause_task_when_queue_finished(self, task_id: int, *, tenant_id: int) -> None:
        async with self._session_factory() as db:
            changed = await self._maybe_pause_task_when_queue_finished_locked(db, task_id)
            if changed:
                await db.commit()

    async def _maybe_complete_expired_task(self, task_id: int, *, tenant_id: int) -> None:
        async with self._session_factory() as db:
            calling = await AutoOutboundRepository.count_targets_by_status(
                db, task_id, statuses=["calling"]
            )
            if calling > 0:
                return
            task = await AutoOutboundRepository.get_task(db, task_id)
            # Past end_date, both active and paused tasks (manual, dial-failure,
            # or queue-finished auto-pause) complete once nothing is in-flight.
            if task is not None and task.status in {"active", "paused"}:
                previous_status = task.status
                now = _utc_now()
                updated = await AutoOutboundRepository.update_task(
                    db,
                    task,
                    {
                        "status": "completed",
                        "completed_at": now,
                    },
                    commit=False,
                )
                await AutoOutboundEventService.emit_task_event(
                    db,
                    task=updated,
                    event_type="auto_outbound.task.completed",
                    occurred_at=now,
                    actor={"type": "system"},
                    previous_status=previous_status,
                    reason="schedule_ended",
                )
                await db.commit()

    async def _maybe_pause_task_when_queue_finished_locked(self, db, task_id: int) -> bool:
        # Queue finished (no pending/calling/redial_pending targets) auto-pauses
        # the task instead of completing it, so operators can append numbers and
        # resume. Only passing end_date completes the task.
        open_count = await AutoOutboundRepository.count_targets_by_status(
            db,
            task_id,
            statuses=["pending", "calling", "redial_pending"],
        )
        if open_count > 0:
            return False
        task = await AutoOutboundRepository.get_task(db, task_id)
        if task is not None and task.status == "active":
            previous_status = task.status
            now = _utc_now()
            updated = await AutoOutboundRepository.update_task(
                db,
                task,
                {
                    "status": "paused",
                    "auto_pause_reason": AUTO_PAUSE_REASON_QUEUE_FINISHED,
                },
                commit=False,
            )
            await AutoOutboundEventService.emit_task_event(
                db,
                task=updated,
                event_type="auto_outbound.task.paused",
                occurred_at=now,
                actor={"type": "system"},
                previous_status=previous_status,
                reason="queue_finished",
            )
            return True
        return False


# Process-wide singleton used by lifespan + orchestrator hooks.
_engine: AutoOutboundDialEngine | None = None


def get_dial_engine() -> AutoOutboundDialEngine | None:
    return _engine


def set_dial_engine(engine: AutoOutboundDialEngine | None) -> None:
    global _engine
    _engine = engine


async def try_handle_auto_outbound_answered(
    call_id: str,
    request_id: str | None = None,
) -> bool:
    """Orchestrator hook: return True when the call belongs to auto-outbound."""
    engine = get_dial_engine()
    if engine is None or not call_id:
        return False
    if await engine.bind_session_from_attempt(call_id, request_id):
        await engine.handle_call_answered(call_id)
        return True
    if not await engine.has_session(call_id):
        return False
    await engine.handle_call_answered(call_id)
    return True


async def try_handle_auto_outbound_ended(
    call_id: str,
    reason: str | None,
    sip_status: int | None,
    request_id: str | None = None,
) -> bool:
    """Orchestrator hook: return True when the call belongs to auto-outbound."""
    engine = get_dial_engine()
    if engine is None or not call_id:
        return False
    if await engine.bind_session_from_attempt(call_id, request_id):
        status_int: int | None
        try:
            status_int = int(sip_status) if sip_status is not None else None
        except (TypeError, ValueError):
            status_int = None
        await engine.handle_call_ended(call_id, reason, status_int)
        return True
    if not await engine.has_session(call_id):
        return False
    # Coerce sip_status when FlowKit sends it as a string.
    status_int: int | None
    try:
        status_int = int(sip_status) if sip_status is not None else None
    except (TypeError, ValueError):
        status_int = None
    await engine.handle_call_ended(call_id, reason, status_int)
    return True
