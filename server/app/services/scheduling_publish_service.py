"""
Scheduling publish/reset orchestration.

Publishing freezes the current calendar week's assignments (Monday-Sunday,
all employees of the tenant, not pool-filtered) into a per-week snapshot row.
Reset overwrites the editable assignments with the latest snapshot. Only the
latest snapshot per tenant+week is kept; re-publishing overwrites it.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.enums import ScheduleShiftType
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.scheduling_repository import (
    ScheduleAssignmentRepository,
    SchedulePublishedSnapshotRepository,
    ScheduleShiftRepository,
    list_employees_by_ids,
)
from app.schemas.scheduling import PublishResetResponse, PublishStatusResponse


def week_start_of(day: date) -> date:
    """Monday of the calendar week containing ``day``."""
    return day - timedelta(days=day.weekday())


def _current_keys(records: list) -> list[tuple[str, int, int]]:
    return sorted((r.date.isoformat(), r.shift_id, r.employee_id) for r in records)


def _payload_keys(payload: list) -> list[tuple[str, int, int]]:
    return sorted(
        (str(entry["date"]), int(entry["shift_id"]), int(entry["employee_id"]))
        for entry in payload
    )


class SchedulingPublishService:

    @staticmethod
    async def _week_records(db: AsyncSession, tenant_id: int, week_start: date) -> list:
        return await ScheduleAssignmentRepository.list_by_date_range(
            db, tenant_id, week_start, week_start + timedelta(days=6)
        )

    @staticmethod
    async def get_status(
        db: AsyncSession, tenant_id: int, day: date
    ) -> PublishStatusResponse:
        week_start = week_start_of(day)
        snapshot = await SchedulePublishedSnapshotRepository.get_by_week(
            db, tenant_id, week_start
        )
        if snapshot is None:
            return PublishStatusResponse(week_start=week_start, state="unpublished")

        records = await SchedulingPublishService._week_records(db, tenant_id, week_start)
        state = (
            "published"
            if _current_keys(records) == _payload_keys(snapshot.payload or [])
            else "dirty"
        )
        published_by_name = None
        if snapshot.published_by is not None:
            employee = await EmployeeRepository.get_by_id(db, snapshot.published_by)
            published_by_name = employee.name if employee else None
        return PublishStatusResponse(
            week_start=week_start,
            state=state,
            published_at=snapshot.published_at,
            published_by_name=published_by_name,
        )

    @staticmethod
    async def publish(
        db: AsyncSession, tenant_id: int, day: date, published_by: int | None
    ) -> PublishStatusResponse:
        week_start = week_start_of(day)
        records = await SchedulingPublishService._week_records(db, tenant_id, week_start)
        shifts = await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        shifts_by_id = {shift.id: shift for shift in shifts}
        payload = [
            {
                "shift_id": shift_id,
                "employee_id": employee_id,
                "date": day_iso,
                "shift": {
                    "name": shifts_by_id[shift_id].name,
                    "shift_type": (
                        shifts_by_id[shift_id].shift_type
                        or ScheduleShiftType.WORK.value
                    ),
                    "start_time": (
                        None
                        if shifts_by_id[shift_id].shift_type
                        == ScheduleShiftType.LEAVE.value
                        else shifts_by_id[shift_id].start_time.strftime("%H:%M")
                    ),
                    "end_time": (
                        None
                        if shifts_by_id[shift_id].shift_type
                        == ScheduleShiftType.LEAVE.value
                        else shifts_by_id[shift_id].end_time.strftime("%H:%M")
                    ),
                    "color": shifts_by_id[shift_id].color,
                },
            }
            for day_iso, shift_id, employee_id in _current_keys(records)
            if shift_id in shifts_by_id
        ]
        await SchedulePublishedSnapshotRepository.upsert(
            db,
            tenant_id,
            week_start,
            payload,
            published_by,
            datetime.now(timezone.utc),
        )
        await db.commit()
        return await SchedulingPublishService.get_status(db, tenant_id, week_start)

    @staticmethod
    async def reset(
        db: AsyncSession, tenant_id: int, day: date
    ) -> PublishResetResponse:
        week_start = week_start_of(day)
        snapshot = await SchedulePublishedSnapshotRepository.get_by_week(
            db, tenant_id, week_start
        )
        if snapshot is None:
            raise BusinessError(
                "This week has no published snapshot",
                status_code=409,
                code="NO_PUBLISHED_SNAPSHOT",
            )

        week_end = week_start + timedelta(days=6)
        deleted = await ScheduleAssignmentRepository.delete_by_date_range(
            db, tenant_id, week_start, week_end
        )

        payload = snapshot.payload or []
        shifts = await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        shift_ids = {s.id for s in shifts}
        employee_ids = {int(entry["employee_id"]) for entry in payload}
        employees = await list_employees_by_ids(db, tenant_id, sorted(employee_ids))
        live_employee_ids = set(employees.keys())

        rows = [
            {
                "tenant_id": tenant_id,
                "employee_id": int(entry["employee_id"]),
                "shift_id": int(entry["shift_id"]),
                "date": date.fromisoformat(str(entry["date"])),
            }
            for entry in payload
            if int(entry["shift_id"]) in shift_ids
            and int(entry["employee_id"]) in live_employee_ids
        ]
        restored = await ScheduleAssignmentRepository.bulk_create(db, rows)
        return PublishResetResponse(week_start=week_start, deleted=deleted, restored=restored)
