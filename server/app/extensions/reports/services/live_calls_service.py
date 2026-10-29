"""Supervisor live-call list — data-scope-filtered in-progress calls."""
from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import (
    SCOPE_SELF,
    DataScopeService,
    RESOURCE_CALL_RECORD,
)

from ..lib.active_calls import (
    fetch_active_calls,
    mask_number,
    talk_duration_seconds,
)
from ..lib import intervention_state
from ..schemas import EmployeeBrief, LiveCallRow, SupervisorBrief


async def get_live_calls(
    db: AsyncSession,
    redis: aioredis.Redis | None,
    principal: EffectivePrincipal,
) -> dict:
    """Return the in-progress calls this supervisor may see and monitor.

    Applies the same ``call_record`` data scope used across reports. Under the
    ``self`` scope a user can only see their own call, which they are not
    allowed to monitor (文档 1: ``self`` 不允许对自己发起监控干预), so those
    rows are excluded from the monitoring list entirely.
    """

    scope = DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD)
    if scope == SCOPE_SELF:
        # Nothing monitorable: the only visible calls are the supervisor's own.
        return {"items": [], "as_of": datetime.now(timezone.utc).isoformat()}

    peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
    predicate = DataScopeService.build_call_record_predicate(principal, peer_ids)

    calls, agents, group_names = await fetch_active_calls(
        db, principal.tenant_id, scope_predicate=predicate
    )

    now = datetime.now(timezone.utc)
    holders = await intervention_state.get_holders_bulk(
        redis, principal.tenant_id, [c.call_id for c in calls]
    )

    items: list[LiveCallRow] = []
    for call in calls:
        # A supervisor never monitors their own call, even under group/all scope.
        if call.agent_id == principal.user_id:
            continue
        agent = agents.get(call.agent_id) if call.agent_id is not None else None
        holder = holders.get(call.call_id)
        raw_number = call.customer_number
        # Imported lazily: the intervention service pulls in the call-control
        # module, which imports reporting in turn. Derives consulting /
        # three_way from the agent's Redis legs; degrades to ``single`` on
        # failure, so the list never breaks on a phase read.
        from .call_intervention_service import CallInterventionService

        phase = await CallInterventionService._derive_phase(
            principal.tenant_id, call.agent_id or 0
        )
        items.append(
            LiveCallRow(
                call_id=call.call_id,
                conversation_id=call.conversation_id,
                agent=EmployeeBrief(
                    id=agent.id if agent else (call.agent_id or 0),
                    name=(agent.name if agent else "") or "",
                    username=agent.username if agent else None,
                    display_name=agent.display_name if agent else None,
                    email=agent.email if agent else None,
                    avatar=agent.avatar if agent else None,
                    is_active=agent.is_active if agent else True,
                ),
                masked_customer_number=mask_number(raw_number),
                direction="inbound" if call.direction == "inbound" else "outbound",
                queue_name=(
                    group_names.get(call.employee_group_id)
                    if call.employee_group_id is not None
                    else None
                ),
                # consulting / three_way come from the agent's Redis legs
                # (same derivation the intervention capability matrix uses);
                # customer_hold / transferring have no durable marker.
                phase=phase,  # type: ignore[arg-type]
                answered_at=call.answered_at.isoformat() if call.answered_at else None,
                talk_duration_seconds=talk_duration_seconds(call.answered_at, now=now),
                current_supervisor=(
                    SupervisorBrief(
                        employee_id=holder.supervisor_id,
                        name=holder.name,
                        mode=holder.mode,  # type: ignore[arg-type]
                    )
                    if holder is not None
                    else None
                ),
            )
        )

    # Default sort: longest talk time first (文档 2.1 默认按时长倒序).
    items.sort(key=lambda row: row.talk_duration_seconds, reverse=True)
    return {"items": [row.model_dump() for row in items], "as_of": now.isoformat()}
