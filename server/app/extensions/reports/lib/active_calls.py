"""Active-call data source for supervisor live monitoring.

An "active call" is an in-progress customer call an agent is currently handling.
The only server-authoritative source for this today is the ``call_records`` CDR
table: the orchestrator upserts a row per call and keeps ``lifecycle_status`` as
``active`` until finalize. A call is "live" (and monitorable) when
``lifecycle_status == 'active'``, it has not ended yet, and a serving agent is
already bridged (``first_agent_connected_at`` / ``last_serving_agent_id``).

PHASE GAP (FLOWKIT / ORCHESTRATOR): the finer call phases the UI wants —
客户保持 (hold), 咨询中 (consult), 三方通话 (three-way), 转接提交中 (transfer in
flight) — are live media-kernel states. The kernel exposes hold/consult/
conference/transfer only as low-level primitives and does not push a durable
"current phase" we persist, and the orchestrator keeps only transient in-memory
routing maps (no per-call phase). So this module can reliably report only the
``single`` phase from persisted state. The richer phases are surfaced as the
``phase`` field's other literals for when a live phase feed becomes available;
until then every in-progress call is reported as ``single``. Callers must not
fabricate a phase from incomplete signals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.constants.call_center import CallLifecycleStatus
from app.models.call_record import CallRecord
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup

# Call is being actively handled by an agent and can be monitored.
LIVE_LIFECYCLE = CallLifecycleStatus.ACTIVE.value
# Backward-compatible alias for callers that still import LIVE_STATE.
LIVE_STATE = LIVE_LIFECYCLE


@dataclass(frozen=True)
class ActiveCall:
    """A single in-progress call resolved from the CDR table."""

    call_id: str
    root_call_id: str | None
    conversation_id: str | None
    agent_id: int | None
    employee_group_id: int | None
    direction: str
    customer_number: str | None
    answered_at: datetime | None


def customer_number(direction: str, from_number: str | None, to_number: str | None) -> str | None:
    """Legacy helper: inbound customer is ``from``, outbound customer is ``to``.

    New CDR rows expose ``customer_number`` directly; prefer that field when
    available. This helper remains for older call sites / unit tests.
    """

    return from_number if direction == "inbound" else to_number


def mask_number(number: str | None) -> str:
    """Mask a phone number for display, keeping only head and tail digits.

    Short numbers (internal extensions) are masked more aggressively so no more
    than the first digit survives. ``None`` renders as an em dash.
    """

    if not number:
        return "—"
    digits = number.strip()
    if len(digits) <= 4:
        return digits[0] + "*" * (len(digits) - 1) if len(digits) > 1 else "*"
    return f"{digits[:3]}****{digits[-4:]}"


def talk_duration_seconds(answered_at: datetime | None, *, now: datetime | None = None) -> int:
    """Answered talk time in whole seconds; 0 until the call is answered."""

    if answered_at is None:
        return 0
    reference = now or datetime.now(timezone.utc)
    if answered_at.tzinfo is None:
        answered_at = answered_at.replace(tzinfo=timezone.utc)
    delta = (reference - answered_at).total_seconds()
    return max(0, int(delta))


async def fetch_active_calls(
    db: AsyncSession,
    tenant_id: int,
    *,
    scope_predicate: ColumnElement | None = None,
) -> tuple[list[ActiveCall], dict[int, Employee], dict[int, str]]:
    """Load in-progress calls for a tenant, restricted by an optional data-scope
    predicate.

    Returns the active calls plus lookup maps for their agents and employee
    group names, so the service can build display rows without extra round
    trips. The predicate is the same ``call_record`` scope clause used across
    reports, so ``self`` supervisors see only their own calls (which they are
    not allowed to monitor — the service filters those out).
    """

    stmt = select(CallRecord).where(
        CallRecord.tenant_id == tenant_id,
        CallRecord.lifecycle_status == LIVE_LIFECYCLE,
        CallRecord.ended_at.is_(None),
        CallRecord.last_serving_agent_id.is_not(None),
        CallRecord.first_agent_connected_at.is_not(None),
    )
    if scope_predicate is not None:
        stmt = stmt.where(scope_predicate)
    stmt = stmt.order_by(CallRecord.first_agent_connected_at.asc())

    rows = list((await db.execute(stmt)).scalars().all())
    calls = [
        ActiveCall(
            call_id=row.call_id,
            root_call_id=row.root_call_id,
            conversation_id=row.conversation_id,
            agent_id=row.last_serving_agent_id,
            employee_group_id=(
                row.last_queue_id if row.last_queue_type == "employee_group" else None
            ),
            direction=row.direction,
            customer_number=row.customer_number,
            answered_at=row.first_agent_connected_at,
        )
        for row in rows
    ]

    agent_ids = sorted({c.agent_id for c in calls if c.agent_id is not None})
    group_ids = sorted({c.employee_group_id for c in calls if c.employee_group_id is not None})

    agents: dict[int, Employee] = {}
    if agent_ids:
        result = await db.execute(select(Employee).where(Employee.id.in_(agent_ids)))
        agents = {e.id: e for e in result.scalars().all()}

    group_names: dict[int, str] = {}
    if group_ids:
        result = await db.execute(
            select(EmployeeGroup.id, EmployeeGroup.name).where(EmployeeGroup.id.in_(group_ids))
        )
        group_names = {gid: name for gid, name in result.all()}

    return calls, agents, group_names
