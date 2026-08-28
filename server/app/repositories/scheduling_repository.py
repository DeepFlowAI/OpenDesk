"""
Scheduling Center repository: shift templates and assignment records.
"""
from datetime import date, datetime
from typing import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.models.scheduling import ScheduleAssignment, SchedulePublishedSnapshot, ScheduleShift
from app.models.scheduling_rule import ScheduleRuleSet

# A pool row: employee id, display name, job number.
PoolMemberRow = tuple[int, str, str | None]


async def list_pool_members(
    db: AsyncSession, tenant_id: int, group_ids: Sequence[int]
) -> list[PoolMemberRow]:
    """Resolve the scheduling pool: distinct active members of the given groups."""
    result = await db.execute(
        select(Employee.id, Employee.name, Employee.job_number)
        .select_from(EmployeeGroupMember)
        .join(Employee, Employee.id == EmployeeGroupMember.employee_id)
        .join(EmployeeGroup, EmployeeGroup.id == EmployeeGroupMember.group_id)
        .where(
            EmployeeGroupMember.group_id.in_(group_ids),
            EmployeeGroup.tenant_id == tenant_id,
            Employee.tenant_id == tenant_id,
            Employee.is_active.is_(True),
        )
        .distinct()
        .order_by(Employee.name.asc(), Employee.id.asc())
    )
    return [(row.id, row.name, row.job_number) for row in result.all()]


async def list_employees_by_ids(
    db: AsyncSession, tenant_id: int, employee_ids: Sequence[int]
) -> dict[int, PoolMemberRow]:
    if not employee_ids:
        return {}
    result = await db.execute(
        select(Employee.id, Employee.name, Employee.job_number).where(
            Employee.tenant_id == tenant_id,
            Employee.id.in_(employee_ids),
        )
    )
    return {row.id: (row.id, row.name, row.job_number) for row in result.all()}


class ScheduleShiftRepository:

    @staticmethod
    async def list_by_tenant(db: AsyncSession, tenant_id: int) -> list[ScheduleShift]:
        result = await db.execute(
            select(ScheduleShift)
            .where(ScheduleShift.tenant_id == tenant_id)
            .order_by(ScheduleShift.sort_order.asc(), ScheduleShift.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int, shift_id: int) -> ScheduleShift | None:
        result = await db.execute(
            select(ScheduleShift).where(
                ScheduleShift.id == shift_id,
                ScheduleShift.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(db: AsyncSession, tenant_id: int, name: str) -> ScheduleShift | None:
        result = await db.execute(
            select(ScheduleShift).where(
                ScheduleShift.tenant_id == tenant_id,
                ScheduleShift.name == name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ScheduleShift:
        shift = ScheduleShift(**data)
        db.add(shift)
        await db.commit()
        await db.refresh(shift)
        return shift

    @staticmethod
    async def update(db: AsyncSession, shift: ScheduleShift, data: dict) -> ScheduleShift:
        for key, value in data.items():
            setattr(shift, key, value)
        await db.commit()
        await db.refresh(shift)
        return shift

    @staticmethod
    async def delete(db: AsyncSession, shift: ScheduleShift) -> None:
        await db.delete(shift)
        await db.commit()

    @staticmethod
    async def count_assignments_by_shift(db: AsyncSession, tenant_id: int) -> dict[int, int]:
        result = await db.execute(
            select(ScheduleAssignment.shift_id, func.count())
            .where(ScheduleAssignment.tenant_id == tenant_id)
            .group_by(ScheduleAssignment.shift_id)
        )
        return {shift_id: count for shift_id, count in result.all()}

    @staticmethod
    async def list_referenced_shift_ids(db: AsyncSession, tenant_id: int) -> set[int]:
        """Return shift ids referenced by assignments, snapshots, or rule sets."""
        assignment_result = await db.execute(
            select(ScheduleAssignment.shift_id)
            .where(ScheduleAssignment.tenant_id == tenant_id)
            .distinct()
        )
        referenced = {shift_id for shift_id in assignment_result.scalars().all()}

        snapshot_result = await db.execute(
            select(SchedulePublishedSnapshot.payload).where(
                SchedulePublishedSnapshot.tenant_id == tenant_id
            )
        )
        for payload in snapshot_result.scalars().all():
            for item in payload or []:
                if isinstance(item, dict) and isinstance(item.get("shift_id"), int):
                    referenced.add(item["shift_id"])

        rule_result = await db.execute(
            select(ScheduleRuleSet.targets, ScheduleRuleSet.rotation_templates).where(
                ScheduleRuleSet.tenant_id == tenant_id
            )
        )
        for targets, templates in rule_result.all():
            for raw_shift_id in (targets or {}).keys():
                try:
                    referenced.add(int(raw_shift_id))
                except (TypeError, ValueError):
                    continue
            for template in templates or []:
                if not isinstance(template, dict):
                    continue
                for day in template.get("days") or []:
                    if not isinstance(day, dict):
                        continue
                    shift_id = day.get("shift_id")
                    if isinstance(shift_id, int):
                        referenced.add(shift_id)
        return referenced


class ScheduleAssignmentRepository:

    @staticmethod
    async def count_by_shift(db: AsyncSession, tenant_id: int, shift_id: int) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(ScheduleAssignment)
            .where(
                ScheduleAssignment.tenant_id == tenant_id,
                ScheduleAssignment.shift_id == shift_id,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def list_by_date_range(
        db: AsyncSession, tenant_id: int, start_date: date, end_date: date
    ) -> list[ScheduleAssignment]:
        result = await db.execute(
            select(ScheduleAssignment)
            .where(
                ScheduleAssignment.tenant_id == tenant_id,
                ScheduleAssignment.date >= start_date,
                ScheduleAssignment.date <= end_date,
            )
            .order_by(ScheduleAssignment.date.asc(), ScheduleAssignment.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_existing_keys(
        db: AsyncSession,
        tenant_id: int,
        employee_ids: Sequence[int],
        shift_ids: Sequence[int],
        start_date: date,
        end_date: date,
    ) -> set[tuple[int, int, date]]:
        """Existing (employee_id, shift_id, date) keys, used to skip duplicates."""
        if not employee_ids or not shift_ids:
            return set()
        result = await db.execute(
            select(
                ScheduleAssignment.employee_id,
                ScheduleAssignment.shift_id,
                ScheduleAssignment.date,
            ).where(
                ScheduleAssignment.tenant_id == tenant_id,
                ScheduleAssignment.employee_id.in_(employee_ids),
                ScheduleAssignment.shift_id.in_(shift_ids),
                ScheduleAssignment.date >= start_date,
                ScheduleAssignment.date <= end_date,
            )
        )
        return {(row.employee_id, row.shift_id, row.date) for row in result.all()}

    @staticmethod
    async def list_by_employee_date_range(
        db: AsyncSession,
        tenant_id: int,
        employee_ids: Sequence[int],
        start_date: date,
        end_date: date,
    ) -> list[ScheduleAssignment]:
        """Load and lock assignments that may conflict with a bulk write."""
        if not employee_ids:
            return []
        result = await db.execute(
            select(ScheduleAssignment)
            .where(
                ScheduleAssignment.tenant_id == tenant_id,
                ScheduleAssignment.employee_id.in_(employee_ids),
                ScheduleAssignment.date >= start_date,
                ScheduleAssignment.date <= end_date,
            )
            .with_for_update()
            .order_by(ScheduleAssignment.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def bulk_create(
        db: AsyncSession, rows: list[dict]
    ) -> int:
        for row in rows:
            db.add(ScheduleAssignment(**row))
        await db.commit()
        return len(rows)

    @staticmethod
    async def replace_conflicts_and_create(
        db: AsyncSession,
        tenant_id: int,
        conflict_ids: Sequence[int],
        rows: list[dict],
    ) -> tuple[int, int]:
        """Delete conflicting rows and create replacements in one transaction."""
        replaced = 0
        if conflict_ids:
            result = await db.execute(
                delete(ScheduleAssignment).where(
                    ScheduleAssignment.tenant_id == tenant_id,
                    ScheduleAssignment.id.in_(conflict_ids),
                )
            )
            replaced = result.rowcount or 0
        for row in rows:
            db.add(ScheduleAssignment(**row))
        await db.commit()
        return len(rows), replaced

    @staticmethod
    async def delete_by_ids(db: AsyncSession, tenant_id: int, ids: Sequence[int]) -> int:
        result = await db.execute(
            delete(ScheduleAssignment).where(
                ScheduleAssignment.tenant_id == tenant_id,
                ScheduleAssignment.id.in_(ids),
            )
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def delete_by_cells(
        db: AsyncSession, tenant_id: int, cells: Sequence[tuple[int, date]]
    ) -> int:
        """Delete all assignments in the given (shift_id, date) cells.

        Does not commit: callers combine this with subsequent inserts in one
        transaction (copy-week overwrite) and commit themselves.
        """
        total = 0
        for shift_id, day in cells:
            result = await db.execute(
                delete(ScheduleAssignment).where(
                    ScheduleAssignment.tenant_id == tenant_id,
                    ScheduleAssignment.shift_id == shift_id,
                    ScheduleAssignment.date == day,
                )
            )
            total += result.rowcount or 0
        await db.flush()
        return total

    @staticmethod
    async def delete_by_employee_dates(
        db: AsyncSession,
        tenant_id: int,
        employee_ids: Sequence[int],
        start_date: date,
        end_date: date,
    ) -> int:
        """Delete pool members' assignments in a range (rule-generation clear mode).

        Does not commit: callers combine this with subsequent inserts in one
        transaction and commit themselves.
        """
        if not employee_ids:
            return 0
        result = await db.execute(
            delete(ScheduleAssignment).where(
                ScheduleAssignment.tenant_id == tenant_id,
                ScheduleAssignment.employee_id.in_(employee_ids),
                ScheduleAssignment.date >= start_date,
                ScheduleAssignment.date <= end_date,
            )
        )
        await db.flush()
        return result.rowcount or 0

    @staticmethod
    async def delete_work_by_employee_dates(
        db: AsyncSession,
        tenant_id: int,
        employee_ids: Sequence[int],
        shift_ids: Sequence[int],
        start_date: date,
        end_date: date,
    ) -> int:
        """Delete only work assignments during clear-and-regenerate."""
        if not employee_ids or not shift_ids:
            return 0
        result = await db.execute(
            delete(ScheduleAssignment).where(
                ScheduleAssignment.tenant_id == tenant_id,
                ScheduleAssignment.employee_id.in_(employee_ids),
                ScheduleAssignment.shift_id.in_(shift_ids),
                ScheduleAssignment.date >= start_date,
                ScheduleAssignment.date <= end_date,
            )
        )
        await db.flush()
        return result.rowcount or 0

    @staticmethod
    async def delete_by_date_range(
        db: AsyncSession, tenant_id: int, start_date: date, end_date: date
    ) -> int:
        """Delete all assignments in a range (publish reset). No commit."""
        result = await db.execute(
            delete(ScheduleAssignment).where(
                ScheduleAssignment.tenant_id == tenant_id,
                ScheduleAssignment.date >= start_date,
                ScheduleAssignment.date <= end_date,
            )
        )
        await db.flush()
        return result.rowcount or 0


class SchedulePublishedSnapshotRepository:
    """One published snapshot row per tenant + calendar week."""

    @staticmethod
    async def get_by_week(
        db: AsyncSession, tenant_id: int, week_start: date
    ) -> SchedulePublishedSnapshot | None:
        result = await db.execute(
            select(SchedulePublishedSnapshot).where(
                SchedulePublishedSnapshot.tenant_id == tenant_id,
                SchedulePublishedSnapshot.week_start == week_start,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(
        db: AsyncSession,
        tenant_id: int,
        week_start: date,
        payload: list,
        published_by: int | None,
        published_at: datetime,
    ) -> SchedulePublishedSnapshot:
        snapshot = await SchedulePublishedSnapshotRepository.get_by_week(
            db, tenant_id, week_start
        )
        if snapshot is None:
            snapshot = SchedulePublishedSnapshot(
                tenant_id=tenant_id,
                week_start=week_start,
                payload=payload,
                published_by=published_by,
                published_at=published_at,
            )
            db.add(snapshot)
        else:
            snapshot.payload = payload
            snapshot.published_by = published_by
            snapshot.published_at = published_at
        await db.flush()
        return snapshot
