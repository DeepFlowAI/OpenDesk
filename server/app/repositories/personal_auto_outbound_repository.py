"""Persistence for personal auto-outbound configuration and sessions."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbound_task import OutboundTask, OutboundTaskTarget
from app.models.user import User
from app.models.personal_auto_outbound import (
    PersonalAutoOutboundCall,
    PersonalAutoOutboundSession,
    PersonalOutboundRecording,
)

ACTIVE_SESSION_STATUSES = ("running", "paused", "auto_paused", "stopping")


class PersonalAutoOutboundRepository:
    @staticmethod
    async def list_task_options(db: AsyncSession, tenant_id: int, employee_id: int) -> list[dict]:
        rows = (
            await db.execute(
                select(OutboundTask.id, OutboundTask.name, func.count(OutboundTaskTarget.id))
                .join(OutboundTaskTarget, OutboundTaskTarget.task_id == OutboundTask.id)
                .where(
                    OutboundTask.tenant_id == tenant_id,
                    OutboundTask.status == "active",
                    OutboundTaskTarget.assignee_id == employee_id,
                    OutboundTaskTarget.status.in_(("pending", "redial")),
                )
                .group_by(OutboundTask.id, OutboundTask.name)
                .order_by(OutboundTask.updated_at.desc())
            )
        ).all()
        return [{"id": row[0], "name": row[1], "callable_count": row[2]} for row in rows]

    @staticmethod
    async def get_task_option(db: AsyncSession, tenant_id: int, employee_id: int, task_id: int) -> dict | None:
        options = await PersonalAutoOutboundRepository.list_task_options(db, tenant_id, employee_id)
        return next((item for item in options if item["id"] == task_id), None)

    @staticmethod
    async def list_recordings(db: AsyncSession, tenant_id: int, employee_id: int) -> list[PersonalOutboundRecording]:
        result = await db.execute(
            select(PersonalOutboundRecording).where(
                PersonalOutboundRecording.tenant_id == tenant_id,
                PersonalOutboundRecording.employee_id == employee_id,
                PersonalOutboundRecording.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_recording(db: AsyncSession, tenant_id: int, employee_id: int, recording_type: str, *, include_inactive: bool = False) -> PersonalOutboundRecording | None:
        conditions = [
            PersonalOutboundRecording.tenant_id == tenant_id,
            PersonalOutboundRecording.employee_id == employee_id,
            PersonalOutboundRecording.recording_type == recording_type,
        ]
        if not include_inactive:
            conditions.append(PersonalOutboundRecording.is_active.is_(True))
        result = await db.execute(select(PersonalOutboundRecording).where(*conditions))
        return result.scalar_one_or_none()

    @staticmethod
    async def replace_recording(db: AsyncSession, tenant_id: int, employee_id: int, recording_type: str, audio_asset_id: int) -> PersonalOutboundRecording:
        # Include inactive rows: the unique constraint on
        # (tenant_id, employee_id, recording_type) covers them, so a
        # previously-removed recording must be reactivated, not re-inserted.
        row = await PersonalAutoOutboundRepository.get_recording(db, tenant_id, employee_id, recording_type, include_inactive=True)
        if row is None:
            row = PersonalOutboundRecording(
                tenant_id=tenant_id,
                employee_id=employee_id,
                recording_type=recording_type,
                audio_asset_id=audio_asset_id,
            )
            db.add(row)
        else:
            row.audio_asset_id = audio_asset_id
            row.is_active = True
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def remove_recording(db: AsyncSession, row: PersonalOutboundRecording) -> None:
        row.is_active = False
        await db.commit()

    @staticmethod
    async def update_recording_script(
        db: AsyncSession, row: PersonalOutboundRecording, script_text: str | None
    ) -> PersonalOutboundRecording:
        row.script_text = script_text
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def get_current_session(db: AsyncSession, tenant_id: int, employee_id: int) -> PersonalAutoOutboundSession | None:
        result = await db.execute(
            select(PersonalAutoOutboundSession)
            .where(
                PersonalAutoOutboundSession.tenant_id == tenant_id,
                PersonalAutoOutboundSession.primary_agent_id == employee_id,
                PersonalAutoOutboundSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
            .order_by(PersonalAutoOutboundSession.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_by_outbound_phone_number_id(
        db: AsyncSession,
        phone_number_id: str,
        *,
        statuses: tuple[str, ...] | None = None,
    ) -> int:
        query = (
            select(func.count())
            .select_from(PersonalAutoOutboundSession)
            .where(PersonalAutoOutboundSession.outbound_phone_number_id == phone_number_id)
        )
        if statuses is not None:
            query = query.where(PersonalAutoOutboundSession.status.in_(statuses))
        result = await db.execute(query)
        return int(result.scalar_one())

    @staticmethod
    async def create_session(db: AsyncSession, data: dict) -> PersonalAutoOutboundSession:
        row = PersonalAutoOutboundSession(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def get_session(db: AsyncSession, session_id: int) -> PersonalAutoOutboundSession | None:
        return await db.get(PersonalAutoOutboundSession, session_id)

    @staticmethod
    async def get_session_for_update(
        db: AsyncSession, session_id: int
    ) -> PersonalAutoOutboundSession | None:
        result = await db.execute(
            select(PersonalAutoOutboundSession)
            .where(PersonalAutoOutboundSession.id == session_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_running_session_ids(db: AsyncSession) -> list[int]:
        result = await db.execute(
            select(PersonalAutoOutboundSession.id).where(
                PersonalAutoOutboundSession.status == "running"
            )
        )
        return [int(item) for item in result.scalars().all()]

    @staticmethod
    async def list_active_calls(
        db: AsyncSession, session_ids: list[int] | None = None
    ) -> list[PersonalAutoOutboundCall]:
        query = (
            select(PersonalAutoOutboundCall)
            .join(
                PersonalAutoOutboundSession,
                PersonalAutoOutboundSession.id == PersonalAutoOutboundCall.session_id,
            )
            .where(
                PersonalAutoOutboundSession.status.in_(ACTIVE_SESSION_STATUSES),
                PersonalAutoOutboundCall.ended_at.is_(None),
                PersonalAutoOutboundCall.stage.in_(
                    ("dialing", "ringing", "screening", "assigning", "human", "filtered")
                ),
            )
            .order_by(PersonalAutoOutboundCall.id)
        )
        if session_ids is not None:
            if not session_ids:
                return []
            query = query.where(PersonalAutoOutboundCall.session_id.in_(session_ids))
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_owned_session(
        db: AsyncSession, tenant_id: int, employee_id: int, session_id: int
    ) -> PersonalAutoOutboundSession | None:
        result = await db.execute(
            select(PersonalAutoOutboundSession).where(
                PersonalAutoOutboundSession.id == session_id,
                PersonalAutoOutboundSession.tenant_id == tenant_id,
                PersonalAutoOutboundSession.primary_agent_id == employee_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_session(
        db: AsyncSession, row: PersonalAutoOutboundSession, data: dict
    ) -> PersonalAutoOutboundSession:
        for key, value in data.items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def claim_calls(
        db: AsyncSession, session: PersonalAutoOutboundSession, limit: int
    ) -> list[PersonalAutoOutboundCall]:
        if limit <= 0:
            return []
        claimed_target_ids = select(PersonalAutoOutboundCall.target_id).where(
            PersonalAutoOutboundCall.session_id == session.id
        )
        targets = list(
            (
                await db.execute(
                    select(OutboundTaskTarget)
                    .join(OutboundTask, OutboundTask.id == OutboundTaskTarget.task_id)
                    .where(
                        OutboundTask.tenant_id == session.tenant_id,
                        OutboundTask.status == "active",
                        OutboundTaskTarget.tenant_id == session.tenant_id,
                        OutboundTaskTarget.task_id == session.task_id,
                        OutboundTaskTarget.assignee_id == session.primary_agent_id,
                        OutboundTaskTarget.status.in_(("pending", "redial")),
                        OutboundTaskTarget.id.not_in(claimed_target_ids),
                    )
                    .order_by(OutboundTaskTarget.id)
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
            ).scalars().all()
        )
        now = datetime.now(timezone.utc)
        calls: list[PersonalAutoOutboundCall] = []
        for target in targets:
            previous_status = target.status
            target.status = "calling"
            call = PersonalAutoOutboundCall(
                tenant_id=session.tenant_id,
                session_id=session.id,
                task_id=session.task_id,
                target_id=target.id,
                phone_number=target.phone_number,
                stage="dialing",
                started_at=now,
                metadata_json={"previous_target_status": previous_status},
            )
            db.add(call)
            calls.append(call)
        await db.commit()
        for call in calls:
            await db.refresh(call)
        return calls

    @staticmethod
    async def get_call(db: AsyncSession, call_row_id: int) -> PersonalAutoOutboundCall | None:
        return await db.get(PersonalAutoOutboundCall, call_row_id)

    @staticmethod
    async def get_call_for_update(
        db: AsyncSession, call_row_id: int
    ) -> PersonalAutoOutboundCall | None:
        result = await db.execute(
            select(PersonalAutoOutboundCall)
            .where(PersonalAutoOutboundCall.id == call_row_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_call_by_telephony_id(
        db: AsyncSession, telephony_call_id: str
    ) -> PersonalAutoOutboundCall | None:
        result = await db.execute(
            select(PersonalAutoOutboundCall).where(
                PersonalAutoOutboundCall.telephony_call_id == telephony_call_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_call(
        db: AsyncSession, row: PersonalAutoOutboundCall, data: dict
    ) -> PersonalAutoOutboundCall:
        for key, value in data.items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update_call_and_settle_target(
        db: AsyncSession,
        row: PersonalAutoOutboundCall,
        data: dict,
        *,
        target_status: str | None,
        result: str,
        answered: bool,
    ) -> PersonalAutoOutboundCall:
        for key, value in data.items():
            setattr(row, key, value)
        if target_status is not None:
            target_result = await db.execute(
                select(OutboundTaskTarget)
                .where(OutboundTaskTarget.id == row.target_id)
                .with_for_update()
            )
            target = target_result.scalar_one_or_none()
            if target is not None:
                target.status = target_status
                target.call_count = int(target.call_count or 0) + 1
                target.answered_count = int(target.answered_count or 0) + (1 if answered else 0)
                target.last_called_at = row.started_at
                target.last_call_result = result
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def list_calls(
        db: AsyncSession, session_id: int, limit: int = 200
    ) -> list[PersonalAutoOutboundCall]:
        result = await db.execute(
            select(PersonalAutoOutboundCall, User.name)
            .outerjoin(OutboundTaskTarget, OutboundTaskTarget.id == PersonalAutoOutboundCall.target_id)
            .outerjoin(User, User.id == OutboundTaskTarget.user_id)
            .where(PersonalAutoOutboundCall.session_id == session_id)
            .order_by(PersonalAutoOutboundCall.started_at.desc())
            .limit(limit)
        )
        calls: list[PersonalAutoOutboundCall] = []
        for call, user_name in result.all():
            call.target_name = user_name  # type: ignore[attr-defined]
            calls.append(call)
        return calls

    @staticmethod
    async def counts(db: AsyncSession, session_id: int) -> dict[str, int]:
        ringing = ("dialing", "ringing")
        screening = ("screening", "assigning")
        row = (
            await db.execute(
                select(
                    func.count().filter(PersonalAutoOutboundCall.stage.in_(ringing)).label("ringing_current"),
                    func.count().filter(PersonalAutoOutboundCall.stage.in_(screening)).label("screening_current"),
                    func.count().filter(PersonalAutoOutboundCall.stage == "human").label("human_current"),
                    func.count().filter(PersonalAutoOutboundCall.stage == "filtered").label("filtered_current"),
                    func.count().filter(PersonalAutoOutboundCall.telephony_call_id.is_not(None)).label("ringing_total"),
                    func.count().filter(PersonalAutoOutboundCall.answered_at.is_not(None)).label("screening_total"),
                    func.count().filter(PersonalAutoOutboundCall.assigned_agent_id.is_not(None)).label("human_total"),
                    func.count().filter(
                        PersonalAutoOutboundCall.prescreen_result.is_not(None)
                        & PersonalAutoOutboundCall.prescreen_result.not_in(
                            ("uncertain", "non_rejection", "human_completed")
                        )
                    ).label("filtered_total"),
                    func.count().filter(
                        (PersonalAutoOutboundCall.stage == "human")
                        & (PersonalAutoOutboundCall.assignment_type == "primary")
                    ).label("primary_human_current"),
                ).where(PersonalAutoOutboundCall.session_id == session_id)
            )
        ).one()
        return {key: int(getattr(row, key) or 0) for key in row._fields}

    @staticmethod
    async def active_call_ids(db: AsyncSession, session_id: int, stages: tuple[str, ...]) -> list[str]:
        result = await db.execute(
            select(PersonalAutoOutboundCall.telephony_call_id).where(
                PersonalAutoOutboundCall.session_id == session_id,
                PersonalAutoOutboundCall.stage.in_(stages),
                PersonalAutoOutboundCall.telephony_call_id.is_not(None),
            )
        )
        return [str(item) for item in result.scalars().all()]
