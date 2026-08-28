"""
Bulk SMS task repositories: tasks, targets and per-task status statistics.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.sms_bulk_task import (
    SMS_BULK_TARGET_STATUS_DELIVERED,
    SMS_BULK_TARGET_STATUS_FAILED,
    SMS_BULK_TARGET_STATUS_PENDING,
    SMS_BULK_TARGET_STATUS_SENDING,
    SMS_BULK_TARGET_STATUS_SUBMITTED,
    SMS_BULK_TASK_STATUS_COMPLETED,
    SMS_BULK_TASK_STATUS_SCHEDULED,
    SMS_BULK_TASK_STATUS_SENDING,
    SmsBulkTask,
    SmsBulkTarget,
)


class SmsBulkTaskRepository:
    @staticmethod
    async def list_for_tenant(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        status: str | None = None,
        created_by_id: int | None = None,
    ) -> tuple[list[tuple[SmsBulkTask, str | None]], int]:
        stmt = select(SmsBulkTask, Employee.name).outerjoin(
            Employee, SmsBulkTask.created_by_id == Employee.id
        )
        count_stmt = select(func.count()).select_from(SmsBulkTask)
        conditions = [SmsBulkTask.tenant_id == tenant_id]
        if q:
            conditions.append(SmsBulkTask.name.ilike(f"%{q}%"))
        if status:
            conditions.append(SmsBulkTask.status == status)
        if created_by_id is not None:
            conditions.append(SmsBulkTask.created_by_id == created_by_id)
        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            stmt.order_by(SmsBulkTask.updated_at.desc()).offset((page - 1) * per_page).limit(per_page)
        )
        return [(task, employee_name) for task, employee_name in result.all()], total

    @staticmethod
    async def get_by_id(db: AsyncSession, task_id: int) -> SmsBulkTask | None:
        return await db.get(SmsBulkTask, task_id)

    @staticmethod
    async def get_status(db: AsyncSession, task_id: int) -> str | None:
        result = await db.execute(select(SmsBulkTask.status).where(SmsBulkTask.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_creator_name(db: AsyncSession, task: SmsBulkTask) -> str | None:
        if task.created_by_id is None:
            return None
        employee = await db.get(Employee, task.created_by_id)
        return employee.name if employee is not None else None

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SmsBulkTask:
        item = SmsBulkTask(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: SmsBulkTask, data: dict) -> SmsBulkTask:
        for key, value in data.items():
            setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: SmsBulkTask) -> None:
        await db.delete(item)
        await db.commit()

    @staticmethod
    async def stats_for_tasks(db: AsyncSession, task_ids: list[int]) -> dict[int, dict[str, int]]:
        """Group target counts by status for the given tasks."""
        if not task_ids:
            return {}
        result = await db.execute(
            select(SmsBulkTarget.task_id, SmsBulkTarget.status, func.count())
            .where(SmsBulkTarget.task_id.in_(task_ids))
            .group_by(SmsBulkTarget.task_id, SmsBulkTarget.status)
        )
        stats: dict[int, dict[str, int]] = {}
        for task_id, status, count in result.all():
            stats.setdefault(task_id, {})[status] = count
        return stats

    # ------------------------------------------------------------------
    # Send engine queries
    # ------------------------------------------------------------------

    @staticmethod
    async def list_due_scheduled(db: AsyncSession, now: datetime) -> list[int]:
        """Scheduled tasks whose send time has arrived."""
        result = await db.execute(
            select(SmsBulkTask.id).where(
                SmsBulkTask.status == SMS_BULK_TASK_STATUS_SCHEDULED,
                SmsBulkTask.scheduled_at.isnot(None),
                SmsBulkTask.scheduled_at <= now,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def start_scheduled_task(db: AsyncSession, task_id: int, now: datetime) -> bool:
        """Move a due scheduled task into sending; False if it changed meanwhile."""
        result = await db.execute(
            update(SmsBulkTask)
            .where(SmsBulkTask.id == task_id, SmsBulkTask.status == SMS_BULK_TASK_STATUS_SCHEDULED)
            .values(status=SMS_BULK_TASK_STATUS_SENDING, started_at=now, updated_at=now)
        )
        await db.commit()
        return (result.rowcount or 0) > 0

    @staticmethod
    async def list_sending_task_ids(db: AsyncSession) -> list[int]:
        result = await db.execute(
            select(SmsBulkTask.id).where(SmsBulkTask.status == SMS_BULK_TASK_STATUS_SENDING)
        )
        return list(result.scalars().all())

    @staticmethod
    async def complete_if_finished(db: AsyncSession, task_id: int, now: datetime) -> bool:
        """Mark a sending task completed when it has no open targets left."""
        open_statuses = (
            SMS_BULK_TARGET_STATUS_PENDING,
            SMS_BULK_TARGET_STATUS_SENDING,
            SMS_BULK_TARGET_STATUS_SUBMITTED,
        )
        open_exists = await db.execute(
            select(func.count())
            .select_from(SmsBulkTarget)
            .where(SmsBulkTarget.task_id == task_id, SmsBulkTarget.status.in_(open_statuses))
        )
        if open_exists.scalar_one() > 0:
            return False
        result = await db.execute(
            update(SmsBulkTask)
            .where(SmsBulkTask.id == task_id, SmsBulkTask.status == SMS_BULK_TASK_STATUS_SENDING)
            .values(status=SMS_BULK_TASK_STATUS_COMPLETED, completed_at=now, updated_at=now)
        )
        await db.commit()
        return (result.rowcount or 0) > 0


class SmsBulkTargetRepository:
    @staticmethod
    async def list_for_task(
        db: AsyncSession,
        *,
        tenant_id: int,
        task_id: int,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        status: str | None = None,
    ) -> tuple[list[SmsBulkTarget], int]:
        conditions = [SmsBulkTarget.tenant_id == tenant_id, SmsBulkTarget.task_id == task_id]
        if q:
            conditions.append(SmsBulkTarget.phone.ilike(f"%{q}%"))
        if status:
            conditions.append(SmsBulkTarget.status == status)
        stmt = select(SmsBulkTarget).where(*conditions)
        count_stmt = select(func.count()).select_from(SmsBulkTarget).where(*conditions)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            stmt.order_by(SmsBulkTarget.id.asc()).offset((page - 1) * per_page).limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_by_id(db: AsyncSession, target_id: int) -> SmsBulkTarget | None:
        return await db.get(SmsBulkTarget, target_id)

    @staticmethod
    async def get_by_phone(db: AsyncSession, *, task_id: int, phone: str) -> SmsBulkTarget | None:
        result = await db.execute(
            select(SmsBulkTarget).where(SmsBulkTarget.task_id == task_id, SmsBulkTarget.phone == phone)
        )
        return result.scalars().first()

    @staticmethod
    async def list_phones_for_task(db: AsyncSession, task_id: int) -> set[str]:
        result = await db.execute(select(SmsBulkTarget.phone).where(SmsBulkTarget.task_id == task_id))
        return set(result.scalars().all())

    @staticmethod
    async def create_many(db: AsyncSession, rows: list[dict]) -> int:
        """Bulk-insert rows in chunks without materializing ORM instances.

        A single add_all over up to 10k rows spikes both session memory and
        transaction length; executemany chunks keep the footprint flat while
        staying atomic (one commit).
        """
        inserted = 0
        for start in range(0, len(rows), 1000):
            chunk = rows[start : start + 1000]
            await db.execute(insert(SmsBulkTarget), chunk)
            inserted += len(chunk)
        await db.commit()
        return inserted

    @staticmethod
    async def count_for_task(db: AsyncSession, task_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(SmsBulkTarget).where(SmsBulkTarget.task_id == task_id)
        )
        return result.scalar_one()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SmsBulkTarget:
        item = SmsBulkTarget(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete_for_task(db: AsyncSession, task_id: int) -> None:
        await db.execute(delete(SmsBulkTarget).where(SmsBulkTarget.task_id == task_id))
        await db.commit()

    @staticmethod
    async def bulk_delete_pending(db: AsyncSession, *, task_id: int, target_ids: list[int]) -> int:
        """Delete only pending targets; returns the number of deleted rows."""
        result = await db.execute(
            delete(SmsBulkTarget).where(
                SmsBulkTarget.task_id == task_id,
                SmsBulkTarget.id.in_(target_ids),
                SmsBulkTarget.status == SMS_BULK_TARGET_STATUS_PENDING,
            )
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def reset_failed_for_task(db: AsyncSession, task_id: int) -> int:
        """Reset failed targets back to pending for a resend; returns reset count."""
        result = await db.execute(
            update(SmsBulkTarget)
            .where(SmsBulkTarget.task_id == task_id, SmsBulkTarget.status == SMS_BULK_TARGET_STATUS_FAILED)
            .values(
                status=SMS_BULK_TARGET_STATUS_PENDING,
                fail_reason=None,
                provider_biz_id=None,
                claimed_at=None,
                submitted_at=None,
                delivered_at=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        return result.rowcount or 0

    # ------------------------------------------------------------------
    # Send engine queries
    # ------------------------------------------------------------------

    @staticmethod
    async def claim_pending_targets(
        db: AsyncSession, *, task_id: int, limit: int, now: datetime
    ) -> list[SmsBulkTarget]:
        """Claim up to ``limit`` pending targets with FOR UPDATE SKIP LOCKED.

        Concurrent workers skip rows already locked by another claim, so the
        same target can never be handed to two senders at once.
        """
        result = await db.execute(
            select(SmsBulkTarget)
            .where(
                SmsBulkTarget.task_id == task_id,
                SmsBulkTarget.status == SMS_BULK_TARGET_STATUS_PENDING,
            )
            .order_by(SmsBulkTarget.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.status = SMS_BULK_TARGET_STATUS_SENDING
            row.claimed_at = now
            row.updated_at = now
        if rows:
            await db.commit()
        return rows

    @staticmethod
    async def sweep_stale_claimed(db: AsyncSession, *, stale_before: datetime, now: datetime) -> int:
        """Return targets stuck in sending (crashed worker) back to pending."""
        result = await db.execute(
            update(SmsBulkTarget)
            .where(
                SmsBulkTarget.status == SMS_BULK_TARGET_STATUS_SENDING,
                SmsBulkTarget.claimed_at.isnot(None),
                SmsBulkTarget.claimed_at < stale_before,
            )
            .values(status=SMS_BULK_TARGET_STATUS_PENDING, claimed_at=None, updated_at=now)
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def release_task_claimed(db: AsyncSession, *, task_id: int, now: datetime) -> int:
        """Return a task's claimed-but-unsubmitted targets to pending (auto-pause)."""
        result = await db.execute(
            update(SmsBulkTarget)
            .where(
                SmsBulkTarget.task_id == task_id,
                SmsBulkTarget.status == SMS_BULK_TARGET_STATUS_SENDING,
            )
            .values(status=SMS_BULK_TARGET_STATUS_PENDING, claimed_at=None, updated_at=now)
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def mark_submitted(
        db: AsyncSession, *, target_id: int, biz_id: str | None, now: datetime
    ) -> None:
        await db.execute(
            update(SmsBulkTarget)
            .where(SmsBulkTarget.id == target_id)
            .values(
                status=SMS_BULK_TARGET_STATUS_SUBMITTED,
                provider_biz_id=biz_id,
                submitted_at=now,
                updated_at=now,
            )
        )
        await db.commit()

    @staticmethod
    async def mark_failed(
        db: AsyncSession, *, target_id: int, fail_reason: str, now: datetime
    ) -> None:
        await db.execute(
            update(SmsBulkTarget)
            .where(SmsBulkTarget.id == target_id)
            .values(
                status=SMS_BULK_TARGET_STATUS_FAILED,
                fail_reason=fail_reason[:255],
                updated_at=now,
            )
        )
        await db.commit()

    @staticmethod
    async def bind_send_record(db: AsyncSession, *, target_id: int, record_id: int) -> None:
        await db.execute(
            update(SmsBulkTarget)
            .where(SmsBulkTarget.id == target_id)
            .values(send_record_id=record_id)
        )
        await db.commit()

    @staticmethod
    async def update_delivery_by_biz_id(
        db: AsyncSession, *, biz_id: str, delivered: bool, fail_reason: str | None, now: datetime
    ) -> list[int]:
        """Apply a delivery receipt to submitted targets; returns affected task ids."""
        rows = await db.execute(
            select(SmsBulkTarget.id, SmsBulkTarget.task_id).where(
                SmsBulkTarget.provider_biz_id == biz_id,
                SmsBulkTarget.status == SMS_BULK_TARGET_STATUS_SUBMITTED,
            )
        )
        targets = rows.all()
        if not targets:
            return []
        values: dict = {
            "status": SMS_BULK_TARGET_STATUS_DELIVERED if delivered else SMS_BULK_TARGET_STATUS_FAILED,
            "updated_at": now,
        }
        if delivered:
            values["delivered_at"] = now
        elif fail_reason:
            values["fail_reason"] = fail_reason[:255]
        await db.execute(
            update(SmsBulkTarget)
            .where(SmsBulkTarget.id.in_([target_id for target_id, _ in targets]))
            .values(**values)
        )
        await db.commit()
        return list({task_id for _, task_id in targets})
