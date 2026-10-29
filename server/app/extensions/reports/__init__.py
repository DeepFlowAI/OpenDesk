"""Reports extension.

Session reports, call reports, the live online monitor, and the call-center
daily monitor:

- /api/v1/reports/sessions/*
- /api/v1/reports/calls/*
- /api/v1/reports/online-monitor
- /api/v1/reports/call-monitor

``reports_enabled`` in ``/api/v1/system/info`` reflects whether this extension
loaded (``app.state.loaded_extensions``).
"""
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def _optional_redis():
    """Redis if configured, else None (matches the router's fallback)."""

    try:
        from app.db.deps import get_redis

        return await get_redis()
    except Exception:  # noqa: BLE001 — Redis not configured in this deployment
        return None


async def _on_kernel_webrtc_ice(event) -> None:
    """Route a kernel ICE candidate for a supervisor leg to that supervisor.

    Runs alongside the orchestrator's own ``webrtc.ice`` handler (the telephony
    client supports multiple handlers per method). Agent legs are a no-op here;
    only supervisor media legs resolve via the leg → target index. Best-effort:
    a lookup miss or transport error must never raise into the event loop.
    """

    call_id = event.data.get("call_id")
    candidate = event.data.get("candidate")
    if not call_id or candidate is None:
        return
    from .services.call_intervention_service import CallInterventionService

    redis = await _optional_redis()
    await CallInterventionService.handle_kernel_ice(redis, call_id, candidate)


async def _on_call_hangup_release_monitor(event) -> None:
    """Release any supervisor monitor lock when a call ends.

    A customer SIP BYE reaches the orchestrator's ``call.hangup`` handler (which
    finalizes the CDR / agent), but that path never touches the monitor holder —
    without this hook a supervisor who was only *listening* stays pinned to the
    dead call until the Redis lock's TTL expires, and the next ``listen`` on a
    fresh call is rejected. Runs alongside the orchestrator's handler (multiple
    handlers per method are supported). Best-effort and idempotent.

    Two event shapes are handled:

    - The hangup names the customer call id (whole call ended): resolve the
      tenant from the CDR and release that call's holder.
    - The hangup names a *supervisor media leg* (e.g. the supervisor's browser
      died mid-whisper/barge): the leg → target index resolves the monitored
      call, and its holder is released so the same supervisor can re-enter
      through listen instead of being blocked by their own stale lock.
    """

    call_id = event.data.get("call_id")
    if not call_id:
        return
    try:
        from app.db.session import AsyncSessionLocal
        from .lib import intervention_state

        redis = await _optional_redis()

        # Supervisor media leg died first? The leg index maps it back to the
        # monitored call; release that holder (only when the holder's recorded
        # leg is exactly the dead one, so a stale index never frees a new
        # supervisor's lock).
        leg_target = await intervention_state.get_supervisor_leg_target(redis, call_id)
        if leg_target is not None:
            leg_tenant_id, leg_call_id = leg_target
            leg_holder = await intervention_state.get_call_holder(
                redis, leg_tenant_id, leg_call_id
            )
            if leg_holder is not None and leg_holder.supervisor_call_id == call_id:
                await intervention_state.clear_supervisor_leg_index(redis, call_id)
                await intervention_state.release(
                    redis, leg_tenant_id, leg_call_id, leg_holder.supervisor_id
                )
                entry = {
                    "supervisor_id": leg_holder.supervisor_id,
                    "mode": leg_holder.mode,
                    "event": "ended",
                    "detail": "supervisor_leg_hangup",
                }
                async with AsyncSessionLocal() as db:
                    await intervention_state.append_trail_event(
                        db, leg_tenant_id, leg_call_id, entry
                    )
                logger.info(
                    "supervisor intervention: supervisor=%s call=%s mode=%s event=ended detail=supervisor_leg_hangup",
                    leg_holder.supervisor_id, leg_call_id, leg_holder.mode,
                )
            return

        # The lock is keyed by (tenant, call_id) and the event does not carry
        # the tenant, so resolve it from this call's CDR. A hangup arriving for
        # a leg id (not the customer call_id) matches no holder and is a no-op.
        from sqlalchemy import select as _select
        from app.models.call_record import CallRecord as _CallRecord

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    _select(_CallRecord).where(_CallRecord.call_id == call_id)
                )
            ).scalar_one_or_none()
        if row is None:
            return
        tenant_id = row.tenant_id
        holder = await intervention_state.get_call_holder(redis, tenant_id, call_id)
        if holder is None:
            return
        if holder.supervisor_call_id:
            await intervention_state.clear_supervisor_leg_index(
                redis, holder.supervisor_call_id
            )
        await intervention_state.release(redis, tenant_id, call_id, holder.supervisor_id)
        entry = {"supervisor_id": holder.supervisor_id, "mode": holder.mode, "event": "ended"}
        async with AsyncSessionLocal() as db:
            await intervention_state.append_trail_event(db, tenant_id, call_id, entry)
        logger.info(
            "supervisor intervention: supervisor=%s call=%s mode=%s event=ended",
            holder.supervisor_id, call_id, holder.mode,
        )
    except Exception:  # noqa: BLE001 — event-loop handler must never raise
        logger.warning("reports: release monitor on call.hangup failed call=%s", call_id, exc_info=True)


def register(app: FastAPI) -> None:
    from .routers import call_intervention as call_intervention_router
    from .routers import call_monitor as call_monitor_router
    from .routers import calls as calls_router
    from .routers import online_monitor as online_monitor_router
    from .routers import sessions as sessions_router
    app.include_router(call_monitor_router.router, prefix="/api/v1")
    app.include_router(call_intervention_router.router, prefix="/api/v1")
    app.include_router(calls_router.router, prefix="/api/v1")
    app.include_router(sessions_router.router, prefix="/api/v1")
    app.include_router(online_monitor_router.router, prefix="/api/v1")

    # Route kernel ICE candidates for supervisor legs to the supervisor's
    # browser. Best-effort: telephony may be unconfigured in this deployment, in
    # which case the reports routers must still register.
    try:
        from app.libs.telephony import get_telephony_client

        get_telephony_client().on_event("webrtc.ice", _on_kernel_webrtc_ice)
        get_telephony_client().on_event("call.hangup", _on_call_hangup_release_monitor)
    except Exception:  # noqa: BLE001 — telephony not configured; routers still load
        logger.info("reports: telephony event handlers not registered (no telephony client)")
