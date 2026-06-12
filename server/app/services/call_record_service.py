"""
Call record service — write CDR lifecycle (orchestrator) + read for history.
"""
from datetime import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.enums import QueueChannel, QueueTaskType, QueueType
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup
from app.models.user import User
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService, RESOURCE_CALL_RECORD
from app.services.queue_history_service import QueueHistoryService
from app.services.call_user_association_service import CallUserAssociationService


logger = logging.getLogger(__name__)
CALL_QUEUE_SUMMARY_METADATA_KEY = "queue_summary"


class CallRecordService:

    # ─────────── Write (called from orchestrator) ───────────

    @staticmethod
    async def create_for_incoming(
        db: AsyncSession,
        tenant_id: int,
        *,
        call_id: str,
        conversation_id: str | None,
        root_call_id: str | None,
        from_number: str | None,
        to_number: str | None,
        voice_flow_id: int | None = None,
        voice_flow_version_id: int | None = None,
    ) -> dict:
        existing = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if existing:
            await _best_effort_identify_user(db, tenant_id, existing)
            return _to_detail(existing, None)
        row = await CallRecordRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "call_id": call_id,
                "conversation_id": conversation_id,
                "root_call_id": root_call_id,
                "direction": "inbound",
                "state": "ringing",
                "from_number": from_number,
                "to_number": to_number,
                "voice_flow_id": voice_flow_id,
                "voice_flow_version_id": voice_flow_version_id,
                "started_at": datetime.now(),
                "extra_metadata": {},
            },
        )
        await _best_effort_identify_user(db, tenant_id, row)
        return _to_detail(row, None)

    @staticmethod
    async def create_for_outbound(
        db: AsyncSession,
        tenant_id: int,
        *,
        call_id: str,
        conversation_id: str | None,
        root_call_id: str | None,
        from_number: str | None,
        to_number: str | None,
        agent_id: int | None = None,
    ) -> dict:
        """Same shape as create_for_incoming but direction=outbound and the
        agent who dialed is known immediately (no queue routing). Called
        from OutboundDialService after FlowKit accepts the originate."""

        existing = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if existing:
            await _best_effort_identify_user(db, tenant_id, existing, actor_id=agent_id)
            return _to_detail(existing, None)
        row = await CallRecordRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "call_id": call_id,
                "conversation_id": conversation_id,
                "root_call_id": root_call_id,
                "direction": "outbound",
                "state": "ringing",
                "from_number": from_number,  # outbound DID (caller_id)
                "to_number": to_number,      # dialed number
                "agent_id": agent_id,
                "started_at": datetime.now(),
                "extra_metadata": {},
            },
        )
        await _best_effort_identify_user(db, tenant_id, row, actor_id=agent_id)
        return _to_detail(row, None)

    @staticmethod
    async def mark_answered(
        db: AsyncSession, tenant_id: int, call_id: str, agent_id: int | None = None
    ) -> None:
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not row:
            return
        ts = datetime.now()
        patch: dict = {"state": "in_progress", "answered_at": ts}
        if agent_id is not None:
            patch["agent_id"] = agent_id
        if row.started_at:
            patch["ring_duration_ms"] = int((ts - row.started_at).total_seconds() * 1000)
        await CallRecordRepository.update(db, row, patch)

    @staticmethod
    async def mark_completed(
        db: AsyncSession,
        tenant_id: int,
        call_id: str,
        *,
        hangup_reason: str | None = None,
        end_state: str = "completed",
    ) -> None:
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not row:
            return
        ts = datetime.now()
        patch: dict = {"state": end_state, "ended_at": ts, "hangup_reason": hangup_reason}
        if row.answered_at:
            patch["talk_duration_ms"] = int((ts - row.answered_at).total_seconds() * 1000)
        elif row.started_at and "ring_duration_ms" not in patch:
            patch["ring_duration_ms"] = int((ts - row.started_at).total_seconds() * 1000)
        await CallRecordRepository.update(db, row, patch)

    @staticmethod
    async def bind_queue(
        db: AsyncSession,
        tenant_id: int,
        call_id: str,
        queue_type: str | int,
        queue_id: int | None = None,
    ) -> None:
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not row:
            return
        if queue_id is None:
            queue_id = int(queue_type)
            queue_type = QueueType.EMPLOYEE_GROUP.value
        else:
            queue_type = str(queue_type)

        queue_brief = await _queue_record_brief(db, tenant_id, queue_type, queue_id)
        metadata = dict(row.extra_metadata or {})
        metadata[CALL_QUEUE_SUMMARY_METADATA_KEY] = {
            "last_assigned_queue": queue_brief,
        }
        patch: dict = {"state": "queued", "extra_metadata": metadata}
        if queue_type == QueueType.EMPLOYEE_GROUP.value:
            patch["employee_group_id"] = queue_id
        await CallRecordRepository.update(
            db,
            row,
            patch,
        )

    @staticmethod
    async def save_recording(
        db: AsyncSession,
        *,
        call_id: str,
        url: str,
        partial: bool = False,
        phase: str | None = None,
        header_patched: bool | None = None,
    ) -> bool:
        """Persist telephony kernel recording URL onto the CDR.

        Returns True when a row was updated. Bridge recordings (phase=bridged)
        replace earlier single-leg (phase=ai) URLs; the reverse is ignored.
        """

        row = await CallRecordRepository.find_by_media_call_id(db, call_id)
        if row is None:
            return False

        existing = (row.extra_metadata or {}).get("recording") or {}
        if row.recording_url and existing.get("phase") == "bridged" and phase != "bridged":
            return False

        metadata = dict(row.extra_metadata or {})
        metadata["recording"] = {
            "partial": partial,
            "phase": phase,
            "header_patched": header_patched,
        }
        patch: dict = {"recording_url": url, "extra_metadata": metadata}
        if row.talk_duration_ms is not None:
            patch["recording_duration_ms"] = row.talk_duration_ms
        await CallRecordRepository.update(db, row, patch)
        return True

    # ─────────── Read ───────────

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        direction: str | None = None,
        agent_id: int | None = None,
        user_id: int | None = None,
        keyword: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        peer_ids: list[int] = []
        scope_predicate = None
        effective_agent_id = agent_id
        if principal is not None:
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            scope_predicate = DataScopeService.build_call_record_predicate(principal, peer_ids)
            effective_agent_id = DataScopeService.resolve_agent_filter(
                principal,
                RESOURCE_CALL_RECORD,
                agent_id,
                peer_ids,
            )
        rows, total = await CallRecordRepository.get_paginated(
            db,
            tenant_id,
            page,
            per_page,
            direction,
            effective_agent_id,
            user_id,
            keyword,
            start_time,
            end_time,
            scope_predicate=scope_predicate,
        )
        # Resolve agent names
        agent_ids = sorted({r.agent_id for r in rows if r.agent_id})
        agents = {}
        if agent_ids:
            emps = list(
                (await db.execute(select(Employee).where(Employee.id.in_(agent_ids))))
                .scalars()
                .all()
            )
            agents = {
                e.id: (e.display_name or e.nickname or e.name or e.username) for e in emps
            }
        users = await _load_user_map(db, tenant_id, [r.user_id for r in rows if r.user_id])
        queue_summaries = await QueueHistoryService.summaries_for_refs(
            db,
            tenant_id,
            channel=QueueChannel.CALL_CENTER.value,
            task_types=[QueueTaskType.CALL.value],
            ref_ids=[r.call_id for r in rows],
        )
        items = [
            _to_list_item(
                r,
                agents.get(r.agent_id) if r.agent_id else None,
                users.get(r.user_id) if r.user_id else None,
                queue_summaries.get(r.call_id),
            )
            for r in rows
        ]
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": items, "total": total, "page": page, "per_page": per_page, "pages": pages,
        }

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        record_id: int,
        tenant_id: int,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        row = await CallRecordRepository.get_by_id(db, record_id, tenant_id)
        if not row:
            raise NotFoundError("Call record not found")
        if principal is not None:
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            DataScopeService.assert_call_record_in_scope(principal, row, peer_ids)
        agent_name = None
        if row.agent_id:
            emp = (
                await db.execute(select(Employee).where(Employee.id == row.agent_id))
            ).scalar_one_or_none()
            if emp:
                agent_name = emp.display_name or emp.nickname or emp.name or emp.username
        user_map = await _load_user_map(db, tenant_id, [row.user_id] if row.user_id else [])
        candidates = await CallUserAssociationService.candidate_users(db, tenant_id, row)
        related_tickets = await TicketRepository.list_by_call_record_id(db, tenant_id, record_id)
        queue_summaries = await QueueHistoryService.summaries_for_refs(
            db,
            tenant_id,
            channel=QueueChannel.CALL_CENTER.value,
            task_types=[QueueTaskType.CALL.value],
            ref_ids=[row.call_id],
        )
        return _to_detail(
            row,
            agent_name,
            user_map.get(row.user_id) if row.user_id else None,
            candidates,
            related_tickets,
            queue_summaries.get(row.call_id),
        )


async def _best_effort_identify_user(
    db: AsyncSession,
    tenant_id: int,
    row,
    *,
    actor_id: int | None = None,
) -> None:
    try:
        await CallUserAssociationService.identify_for_record(
            db, tenant_id, row, actor_id=actor_id
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to identify user for call_record_id=%s", row.id)


async def _load_user_map(db: AsyncSession, tenant_id: int, user_ids: list[int]) -> dict[int, User]:
    users = await UserRepository.list_by_ids(db, tenant_id, user_ids)
    return {user.id: user for user in users}


async def _queue_record_brief(
    db: AsyncSession,
    tenant_id: int,
    queue_type: str,
    queue_id: int,
) -> dict | None:
    if queue_type == QueueType.EMPLOYEE.value:
        result = await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.id == queue_id,
            )
        )
        employee = result.scalar_one_or_none()
        if employee is None:
            return None
        name = employee.display_name or employee.nickname or employee.name or employee.username
    elif queue_type == QueueType.EMPLOYEE_GROUP.value:
        result = await db.execute(
            select(EmployeeGroup).where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroup.id == queue_id,
            )
        )
        group = result.scalar_one_or_none()
        name = group.name if group else None
    else:
        return None

    if not name:
        return None
    return {"queue_type": queue_type, "queue_id": queue_id, "name": name}


def _effective_queue_summary(row, queue_summary: dict | None) -> dict:
    metadata_summary = _queue_summary_from_metadata(row)
    queue_summary = queue_summary or {}
    return {
        "last_assigned_queue": (
            queue_summary.get("last_assigned_queue")
            or metadata_summary.get("last_assigned_queue")
        ),
        "queue_duration_seconds": (
            queue_summary.get("queue_duration_seconds")
            if queue_summary.get("queue_duration_seconds") is not None
            else metadata_summary.get("queue_duration_seconds")
        ),
    }


def _queue_summary_from_metadata(row) -> dict:
    metadata = row.extra_metadata or {}
    summary = metadata.get(CALL_QUEUE_SUMMARY_METADATA_KEY)
    if not isinstance(summary, dict):
        return {}

    queue = summary.get("last_assigned_queue")
    if not isinstance(queue, dict):
        queue = None
    elif not queue.get("queue_type") or not queue.get("queue_id") or not queue.get("name"):
        queue = None

    return {
        "last_assigned_queue": queue,
        "queue_duration_seconds": None,
    }


def _to_list_item(
    row,
    agent_name: str | None,
    user: User | None = None,
    queue_summary: dict | None = None,
) -> dict:
    user_brief = CallUserAssociationService.brief_user(user)
    queue_summary = _effective_queue_summary(row, queue_summary)
    return {
        "id": row.id,
        "call_id": row.call_id,
        "direction": row.direction,
        "state": row.state,
        "from_number": row.from_number,
        "to_number": row.to_number,
        "employee_group_id": row.employee_group_id,
        "agent_id": row.agent_id,
        "agent_name": agent_name,
        "user_id": row.user_id,
        "user_public_id": user_brief["public_id"] if user_brief else None,
        "user_name": user_brief["name"] if user_brief else None,
        "user_phone": user_brief["phone"] if user_brief else None,
        "user_association_status": CallUserAssociationService.status_for_record(row),
        "started_at": row.started_at,
        "answered_at": row.answered_at,
        "ended_at": row.ended_at,
        "ring_duration_ms": row.ring_duration_ms,
        "talk_duration_ms": row.talk_duration_ms,
        "last_assigned_queue": queue_summary.get("last_assigned_queue"),
        "queue_duration_seconds": queue_summary.get("queue_duration_seconds"),
    }


def _to_detail(
    row,
    agent_name: str | None,
    user: User | None = None,
    candidates: list[User] | None = None,
    related_tickets: list | None = None,
    queue_summary: dict | None = None,
) -> dict:
    user_brief = CallUserAssociationService.brief_user(user)
    queue_summary = _effective_queue_summary(row, queue_summary)
    return {
        "id": row.id,
        "call_id": row.call_id,
        "conversation_id": row.conversation_id,
        "root_call_id": row.root_call_id,
        "direction": row.direction,
        "state": row.state,
        "from_number": row.from_number,
        "to_number": row.to_number,
        "voice_flow_id": row.voice_flow_id,
        "voice_flow_version_id": row.voice_flow_version_id,
        "employee_group_id": row.employee_group_id,
        "agent_id": row.agent_id,
        "agent_name": agent_name,
        "user_id": row.user_id,
        "user_public_id": user_brief["public_id"] if user_brief else None,
        "user_name": user_brief["name"] if user_brief else None,
        "user_phone": user_brief["phone"] if user_brief else None,
        "user_association_status": CallUserAssociationService.status_for_record(row),
        "associated_user_candidates": [
            brief
            for candidate in (candidates or [])
            if (brief := CallUserAssociationService.brief_user(candidate)) is not None
        ],
        "started_at": row.started_at,
        "answered_at": row.answered_at,
        "ended_at": row.ended_at,
        "ring_duration_ms": row.ring_duration_ms,
        "talk_duration_ms": row.talk_duration_ms,
        "hangup_reason": row.hangup_reason,
        "recording_url": row.recording_url,
        "recording_duration_ms": row.recording_duration_ms,
        "last_assigned_queue": queue_summary.get("last_assigned_queue"),
        "queue_duration_seconds": queue_summary.get("queue_duration_seconds"),
        "related_tickets": [
            {
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
            }
            for ticket in (related_tickets or [])
        ],
        "metadata": row.extra_metadata or {},
    }
