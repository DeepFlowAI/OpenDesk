"""
Call record service — write CDR lifecycle (orchestrator) + read for history.
"""
from datetime import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.employee import Employee
from app.models.user import User
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.call_user_association_service import CallUserAssociationService


logger = logging.getLogger(__name__)


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
        db: AsyncSession, tenant_id: int, call_id: str, employee_group_id: int
    ) -> None:
        row = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not row:
            return
        await CallRecordRepository.update(
            db, row, {"employee_group_id": employee_group_id, "state": "queued"}
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
    ) -> dict:
        rows, total = await CallRecordRepository.get_paginated(
            db,
            tenant_id,
            page,
            per_page,
            direction,
            agent_id,
            user_id,
            keyword,
            start_time,
            end_time,
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
        items = [
            _to_list_item(
                r,
                agents.get(r.agent_id) if r.agent_id else None,
                users.get(r.user_id) if r.user_id else None,
            )
            for r in rows
        ]
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": items, "total": total, "page": page, "per_page": per_page, "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, record_id: int, tenant_id: int) -> dict:
        row = await CallRecordRepository.get_by_id(db, record_id, tenant_id)
        if not row:
            raise NotFoundError("Call record not found")
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
        return _to_detail(
            row,
            agent_name,
            user_map.get(row.user_id) if row.user_id else None,
            candidates,
            related_tickets,
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


def _to_list_item(row, agent_name: str | None, user: User | None = None) -> dict:
    user_brief = CallUserAssociationService.brief_user(user)
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
    }


def _to_detail(
    row,
    agent_name: str | None,
    user: User | None = None,
    candidates: list[User] | None = None,
    related_tickets: list | None = None,
) -> dict:
    user_brief = CallUserAssociationService.brief_user(user)
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
        "related_tickets": [
            {
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
            }
            for ticket in (related_tickets or [])
        ],
        "metadata": row.extra_metadata or {},
    }
