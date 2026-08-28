"""Effective after-call work (wrap-up) duration resolution and post-call
agent status transitions.

The wrap-up deadline is fixed at hangup time: auto-outbound agent-reception
calls use the task's own ``wrapup_seconds``; every other call uses the
tenant-level ``system_settings.call_wrapup_seconds``. A duration of 0 skips
after-call work entirely and returns the agent to ready immediately.

Entering after-call work pushes ``cc.wrap_up_started`` with the deadline so an
open workbench starts its countdown from the event itself instead of waiting
for the next agent-status poll.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.call_center import CcSocketEvent
from app.core.exceptions import ConflictError
from app.models.auto_outbound import AutoOutboundCallRecord, AutoOutboundTask
from app.models.call_record import CallRecord
from app.services.call_center.agent_notify import emit_to_agent
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services.system_settings_service import SystemSettingsService

logger = logging.getLogger(__name__)

# Last-resort duration when neither the task lookup nor the tenant settings
# can be read (e.g. a transient DB error mid-hangup). Matches the
# system_settings.call_wrapup_seconds column default so the sweep still frees
# the agent instead of stranding them in wrap-up forever.
FALLBACK_WRAPUP_SECONDS = 30


async def resolve_effective_wrapup_seconds(
    db: AsyncSession, tenant_id: int, call_id: str | None
) -> int:
    """Decide the wrap-up duration for a just-ended call.

    Auto-outbound calls received by an agent follow the task's configured
    post-call processing duration; all other calls follow the tenant-level
    wrap-up setting. This runs on the hangup path, which previously needed no
    extra DB read — resolution failures must not break the agent state
    transition, so each step degrades to the next.
    """
    if call_id:
        try:
            stmt = (
                select(AutoOutboundTask.wrapup_seconds)
                .select_from(AutoOutboundCallRecord)
                .join(
                    CallRecord,
                    CallRecord.id == AutoOutboundCallRecord.call_record_id,
                )
                .join(
                    AutoOutboundTask,
                    AutoOutboundTask.id == AutoOutboundCallRecord.task_id,
                )
                .where(
                    AutoOutboundCallRecord.tenant_id == tenant_id,
                    AutoOutboundCallRecord.reception_type == "agent",
                    CallRecord.call_id == call_id,
                )
                .order_by(AutoOutboundCallRecord.id.desc())
                .limit(1)
            )
            task_seconds = await db.scalar(stmt)
            if task_seconds is not None:
                return int(task_seconds)
        except Exception:  # noqa: BLE001
            logger.warning(
                "wrap-up duration: task lookup failed tenant=%s call=%s",
                tenant_id,
                call_id,
                exc_info=True,
            )
    try:
        settings = await SystemSettingsService.get_settings(db, tenant_id)
        return int(settings.call_wrapup_seconds)
    except Exception:  # noqa: BLE001
        logger.warning(
            "wrap-up duration: tenant settings unreadable tenant=%s, fallback=%s",
            tenant_id,
            FALLBACK_WRAPUP_SECONDS,
            exc_info=True,
        )
        return FALLBACK_WRAPUP_SECONDS


async def apply_post_call_agent_status(
    db: AsyncSession | None,
    redis: aioredis.Redis | None,
    tenant_id: int,
    employee_id: int,
    *,
    call_id: str | None,
    reason: str,
    wrapup_seconds: int,
) -> str:
    """Move the agent into after-call work, or straight back to ready when the
    effective duration is 0. Returns the resulting visible status."""
    if wrapup_seconds > 0:
        if redis is not None:
            snapshot = await CcAgentResourceService.mark_after_call_work(
                redis,
                tenant_id,
                employee_id,
                call_id=call_id,
                reason=reason,
                wrap_up_seconds=wrapup_seconds,
            )
            wrap_up_until = snapshot.get("wrap_up_until")
            if wrap_up_until is not None:
                await emit_to_agent(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    method=CcSocketEvent.WRAP_UP_STARTED.value,
                    payload={
                        "call_id": call_id,
                        "wrap_up_until": wrap_up_until.isoformat(),
                    },
                )
        if db is not None:
            await CcAgentStatusService.sync_pg_status(
                db, tenant_id, employee_id, "after_call_work", reason=reason
            )
        return "after_call_work"

    if redis is not None:
        try:
            await CcAgentResourceService.set_visible_status(
                redis, tenant_id, employee_id, "ready"
            )
        except ConflictError:
            # A new call was reserved between hangup and this write; the agent
            # is already occupied, so force-release would be wrong — leave the
            # active resource alone.
            logger.info(
                "post-call ready skipped, resource already occupied: "
                "tenant=%s employee=%s call=%s",
                tenant_id,
                employee_id,
                call_id,
            )
    if db is not None:
        await CcAgentStatusService.sync_pg_status(
            db, tenant_id, employee_id, "ready", reason=reason
        )
    return "ready"
