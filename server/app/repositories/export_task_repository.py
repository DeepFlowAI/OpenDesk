"""SQL and atomic state transitions for export jobs."""
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.employee import Employee
from app.models.export_task import ExportTask


class ExportTaskRepository:
    @staticmethod
    def owned(tenant_id: int, employee_id: int, now: datetime) -> tuple:
        return (ExportTask.tenant_id == tenant_id, ExportTask.employee_id == employee_id,
                ExportTask.created_at > now - timedelta(days=90))

    @staticmethod
    async def lock_owner(db: AsyncSession, tenant_id: int, employee_id: int) -> bool:
        return (await db.execute(select(Employee.id).where(
            Employee.id == employee_id, Employee.tenant_id == tenant_id, Employee.is_active.is_(True)
        ).with_for_update())).scalar_one_or_none() is not None

    @staticmethod
    async def by_key(db: AsyncSession, tenant_id: int, employee_id: int, key: UUID) -> ExportTask | None:
        return (await db.execute(select(ExportTask).where(
            ExportTask.tenant_id == tenant_id, ExportTask.employee_id == employee_id,
            ExportTask.idempotency_key == key,
        ))).scalar_one_or_none()

    @staticmethod
    async def get_owned(db: AsyncSession, tenant_id: int, employee_id: int, task_id: UUID,
                        now: datetime) -> ExportTask | None:
        return (await db.execute(select(ExportTask).where(
            *ExportTaskRepository.owned(tenant_id, employee_id, now), ExportTask.id == task_id,
        ))).scalar_one_or_none()

    @staticmethod
    async def get(db: AsyncSession, task_id: UUID) -> ExportTask | None:
        return await db.get(ExportTask, task_id)

    @staticmethod
    async def add(db: AsyncSession, values: dict) -> ExportTask:
        task = ExportTask(**values)
        db.add(task)
        await db.flush()
        return task

    @staticmethod
    async def pending_count(db: AsyncSession, tenant_id: int, employee_id: int) -> int:
        return (await db.execute(select(func.count()).select_from(ExportTask).where(
            ExportTask.tenant_id == tenant_id, ExportTask.employee_id == employee_id,
            ExportTask.status.in_(("pending", "running")),
        ))).scalar_one()

    @staticmethod
    async def page(db: AsyncSession, tenant_id: int, employee_id: int, now: datetime,
                   page: int, per_page: int) -> tuple[list[ExportTask], int, int]:
        filters = ExportTaskRepository.owned(tenant_id, employee_id, now)
        total = (await db.execute(select(func.count()).select_from(ExportTask).where(*filters))).scalar_one()
        page = min(page, max(1, (total + per_page - 1) // per_page))
        items = (await db.execute(select(ExportTask).where(*filters).order_by(
            ExportTask.created_at.desc(), ExportTask.id.desc()
        ).offset((page - 1) * per_page).limit(per_page))).scalars().all()
        return list(items), total, page

    @staticmethod
    async def counts(db: AsyncSession, tenant_id: int, employee_id: int, now: datetime) -> tuple[int, int]:
        result = (await db.execute(select(func.count(), func.count().filter(
            ExportTask.viewed_at.is_(None), ExportTask.status.in_(("completed", "failed", "expired")),
        )).select_from(ExportTask).where(*ExportTaskRepository.owned(tenant_id, employee_id, now)))).one()
        return result[0], result[1]

    @staticmethod
    async def transition(db: AsyncSession, task_id: UUID, states: tuple[str, ...], values: dict) -> bool:
        result = await db.execute(update(ExportTask).where(
            ExportTask.id == task_id, ExportTask.status.in_(states),
        ).values(**values).execution_options(synchronize_session=False))
        return result.rowcount == 1

    @staticmethod
    async def mark_viewed(db: AsyncSession, tenant_id: int, employee_id: int,
                          ids: list[UUID], now: datetime) -> None:
        await db.execute(update(ExportTask).where(
            *ExportTaskRepository.owned(tenant_id, employee_id, now), ExportTask.id.in_(ids),
            ExportTask.status.in_(("completed", "failed", "expired")), ExportTask.viewed_at.is_(None),
        ).values(viewed_at=now))

    @staticmethod
    async def claim_notifications(db: AsyncSession, tenant_id: int, employee_id: int,
                                  since: datetime, now: datetime) -> list[ExportTask]:
        result = await db.execute(update(ExportTask).where(
            *ExportTaskRepository.owned(tenant_id, employee_id, now),
            ExportTask.status.in_(("completed", "failed")), ExportTask.notified_at.is_(None),
            ExportTask.completed_at > since, ExportTask.completed_at <= now,
        ).values(notified_at=now).returning(ExportTask))
        return list(result.scalars().all())

    @staticmethod
    async def claim_next(db: AsyncSession, now: datetime) -> ExportTask | None:
        # Serialize only the short scheduling transaction across API processes.
        if not (await db.execute(text("SELECT pg_try_advisory_xact_lock(58408101)"))).scalar_one():
            return None
        running = aliased(ExportTask)
        earlier = aliased(ExportTask)
        last_run = select(ExportTask.tenant_id, func.max(ExportTask.started_at).label("last_started")).group_by(
            ExportTask.tenant_id).subquery()
        task = (await db.execute(select(ExportTask).outerjoin(last_run, last_run.c.tenant_id == ExportTask.tenant_id).where(
            ExportTask.status == "pending", ExportTask.created_at > now - timedelta(hours=24),
            ~exists(select(running.id).where(running.tenant_id == ExportTask.tenant_id,
                running.employee_id == ExportTask.employee_id, running.status == "running")),
            ~exists(select(earlier.id).where(earlier.tenant_id == ExportTask.tenant_id,
                earlier.employee_id == ExportTask.employee_id, earlier.status == "pending",
                (earlier.created_at < ExportTask.created_at) | and_(
                    earlier.created_at == ExportTask.created_at, earlier.id < ExportTask.id))),
        ).order_by(last_run.c.last_started.asc().nullsfirst(), ExportTask.created_at, ExportTask.id)
            .limit(1).with_for_update(of=ExportTask, skip_locked=True))).scalar_one_or_none()
        if task:
            task.status = "running"
            task.started_at = now
            await db.flush()
        return task

    @staticmethod
    async def expire_timeouts(db: AsyncSession, now: datetime) -> None:
        for state, column, cutoff, code in (
            ("pending", ExportTask.created_at, now - timedelta(hours=24), "queue_timeout"),
            ("running", ExportTask.started_at, now - timedelta(minutes=30), "execution_timeout"),
        ):
            await db.execute(update(ExportTask).where(ExportTask.status == state, column <= cutoff)
                             .values(status="failed", error_code=code, completed_at=now))
        await db.execute(update(ExportTask).where(ExportTask.status == "completed", ExportTask.expires_at <= now)
                         .values(status="expired"))

    @staticmethod
    async def cleanup_candidates(db: AsyncSession, now: datetime) -> list[ExportTask]:
        return list((await db.execute(select(ExportTask).where(
            ExportTask.storage_key.is_not(None),
            (ExportTask.status.in_(("failed", "cancelled", "expired"))) |
            (ExportTask.expires_at <= now) | (ExportTask.created_at <= now - timedelta(days=90)),
        ).order_by(ExportTask.updated_at, ExportTask.id).limit(100))).scalars().all())

    @staticmethod
    async def cleaned(db: AsyncSession, task_id: UUID, now: datetime) -> None:
        # Keep the key until execution cannot still upload after cancellation.
        await db.execute(update(ExportTask).where(ExportTask.id == task_id,
            (ExportTask.started_at.is_(None)) | (ExportTask.started_at <= now - timedelta(minutes=31))
        ).values(storage_key=None))
        await db.execute(delete(ExportTask).where(ExportTask.id == task_id,
            ExportTask.created_at <= now - timedelta(days=90), ExportTask.storage_key.is_(None)))

    @staticmethod
    async def prune(db: AsyncSession, now: datetime) -> None:
        await db.execute(delete(ExportTask).where(
            ExportTask.created_at <= now - timedelta(days=90), ExportTask.storage_key.is_(None)))
