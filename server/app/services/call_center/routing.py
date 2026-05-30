"""
Routing rule matcher — given an inbound call's number/time, finds the first
enabled rule whose conditions all match and returns its target voice flow.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_routing_rule import InboundRoutingRule
from app.models.service_hours import ServiceHours
from app.models.voice_flow import VoiceFlow
from app.services.call_center.variables import now_in_schedule


async def match_routing_rule(
    db: AsyncSession,
    tenant_id: int,
    *,
    from_number: str | None,
    to_number: str | None,
    now: datetime | None = None,
) -> tuple[InboundRoutingRule, VoiceFlow] | None:
    now = now or datetime.now()

    q = (
        select(InboundRoutingRule)
        .where(
            InboundRoutingRule.tenant_id == tenant_id,
            InboundRoutingRule.enabled.is_(True),
        )
        .order_by(asc(InboundRoutingRule.priority))
    )
    rules: list[InboundRoutingRule] = list((await db.execute(q)).scalars().all())

    # Precompute schedule membership for time-based conditions
    sched_cache: dict[int, bool] = {}
    sids_to_load: set[int] = set()
    for r in rules:
        for c in r.conditions or []:
            if c.get("condition_type") == "call_time":
                try:
                    sids_to_load.add(int(c.get("value")))
                except (TypeError, ValueError):
                    pass

    if sids_to_load:
        sched_rows = list(
            (
                await db.execute(
                    select(ServiceHours).where(
                        ServiceHours.id.in_(sids_to_load),
                        ServiceHours.tenant_id == tenant_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for sh in sched_rows:
            schedule_payload = {
                "weekly_schedules": getattr(sh, "weekly_schedules", []) or [],
                "holidays": getattr(sh, "holidays", []) or [],
                "makeup_days": getattr(sh, "makeup_days", []) or [],
            }
            sched_cache[sh.id] = now_in_schedule(now, schedule_payload)

    # Try each rule in priority order
    for rule in rules:
        if _rule_matches(rule, from_number, to_number, sched_cache):
            flow = (
                await db.execute(
                    select(VoiceFlow).where(
                        VoiceFlow.id == rule.target_voice_flow_id,
                        VoiceFlow.tenant_id == tenant_id,
                        VoiceFlow.deleted_at.is_(None),
                        VoiceFlow.enabled.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if flow:
                return (rule, flow)
    return None


def _rule_matches(
    rule: InboundRoutingRule,
    from_number: str | None,
    to_number: str | None,
    sched_cache: dict[int, bool],
) -> bool:
    """All AND'd conditions must be satisfied."""

    for c in rule.conditions or []:
        ct = c.get("condition_type")
        op = c.get("operator")
        val = c.get("value")
        if ct == "caller_number":
            if op == "eq" and (from_number or "") != (val or ""):
                return False
            if op == "ne" and (from_number or "") == (val or ""):
                return False
        elif ct == "callee_number":
            if op == "eq" and (to_number or "") != (val or ""):
                return False
            if op == "ne" and (to_number or "") == (val or ""):
                return False
        elif ct == "call_time":
            try:
                sid = int(val)
            except (TypeError, ValueError):
                return False
            in_sched = sched_cache.get(sid, False)
            if op == "in_schedule" and not in_sched:
                return False
            if op == "not_in_schedule" and in_sched:
                return False
        else:
            return False
    return True
