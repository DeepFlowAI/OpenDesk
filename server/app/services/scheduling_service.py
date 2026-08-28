"""
Scheduling Center service: shift templates, scheduling pool, and assignments.
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.enums import ScheduleShiftType
from app.models.scheduling import ScheduleAssignment, ScheduleShift
from app.libs.excel import build_xlsx
from app.models.employee_group import EmployeeGroup
from app.repositories.scheduling_repository import (
    PoolMemberRow,
    ScheduleAssignmentRepository,
    ScheduleShiftRepository,
    list_employees_by_ids,
    list_pool_members,
)
from sqlalchemy import select
from app.schemas.scheduling import (
    AssignmentBulkCreateRequest,
    AssignmentResponse,
    AssignmentEmployeeInfo,
    AssignmentShiftInfo,
    CopyWeekRequest,
    PoolMemberItem,
    ShiftCreate,
    ShiftUpdate,
    hhmm_to_time,
)
from app.services.scheduling_plan_service import SchedulingPlanService

# Max range for the assignment range query (week view = 7d, month view <= 42d).
MAX_QUERY_RANGE_DAYS = 62

# Keep time columns non-null for blue/green compatibility. Product surfaces
# render leave types as all-day and never expose these internal values.
LEAVE_PLACEHOLDER_START = time(0, 0)
LEAVE_PLACEHOLDER_END = time(0, 1)

# Preset shifts for new tenants / first-time module init. Colors are hex so
# they can be reused directly by Excel exports; they match the design tokens.
PRESET_SHIFTS: dict[str, list[tuple[str, str, str, int, str]]] = {
    "zh": [
        ("早班", "09:00", "13:00", 1, "#4B9CF5"),
        ("中班", "13:00", "18:00", 2, "#2DB8A8"),
        ("晚班", "18:00", "22:00", 3, "#7B82E8"),
    ],
    "en": [
        ("Morning", "09:00", "13:00", 1, "#4B9CF5"),
        ("Midday", "13:00", "18:00", 2, "#2DB8A8"),
        ("Evening", "18:00", "22:00", 3, "#7B82E8"),
    ],
}


async def seed_preset_shifts(db: AsyncSession, tenant_id: int, lang: str = "zh") -> None:
    """Insert the preset morning/midday/evening shifts for a tenant.

    Idempotent: shifts that already exist (by tenant + name) are skipped.
    """
    presets = PRESET_SHIFTS.get("en" if lang.lower().startswith("en") else "zh", PRESET_SHIFTS["zh"])
    existing = await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
    existing_names = {shift.name for shift in existing}
    for name, start, end, sort_order, color in presets:
        if name in existing_names:
            continue
        db.add(
            ScheduleShift(
                tenant_id=tenant_id,
                name=name,
                shift_type=ScheduleShiftType.WORK.value,
                start_time=hhmm_to_time(start),
                end_time=hhmm_to_time(end),
                color=color,
                sort_order=sort_order,
                is_enabled=True,
            )
        )
    await db.flush()


class SchedulingService:

    @staticmethod
    async def list_shifts(db: AsyncSession, tenant_id: int) -> list[ScheduleShift]:
        shifts = await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        counts = await ScheduleShiftRepository.count_assignments_by_shift(db, tenant_id)
        referenced_ids = await ScheduleShiftRepository.list_referenced_shift_ids(
            db, tenant_id
        )
        for shift in shifts:
            shift.has_assignments = counts.get(shift.id, 0) > 0
            shift.has_references = shift.id in referenced_ids
        return shifts

    @staticmethod
    async def create_shift(db: AsyncSession, tenant_id: int, data: ShiftCreate) -> ScheduleShift:
        existing = await ScheduleShiftRepository.get_by_name(db, tenant_id, data.name)
        if existing:
            raise ValidationError("Shift name already exists")
        if data.shift_type == ScheduleShiftType.LEAVE.value:
            start_time = LEAVE_PLACEHOLDER_START
            end_time = LEAVE_PLACEHOLDER_END
        else:
            SchedulingService._validate_time_range(data.start_time, data.end_time)
            start_time = hhmm_to_time(data.start_time)
            end_time = hhmm_to_time(data.end_time)
        return await ScheduleShiftRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": data.name,
                "shift_type": data.shift_type,
                "start_time": start_time,
                "end_time": end_time,
                "color": data.color,
                "sort_order": data.sort_order,
                "is_enabled": data.is_enabled,
            },
        )

    @staticmethod
    async def update_shift(
        db: AsyncSession, tenant_id: int, shift_id: int, data: ShiftUpdate
    ) -> ScheduleShift:
        shift = await ScheduleShiftRepository.get_by_id(db, tenant_id, shift_id)
        if not shift:
            raise NotFoundError("Shift not found")

        update_data = data.model_dump(exclude_unset=True)
        current_type = shift.shift_type or ScheduleShiftType.WORK.value
        target_type = update_data.get("shift_type", current_type)
        if target_type != current_type:
            referenced_ids = await ScheduleShiftRepository.list_referenced_shift_ids(
                db, tenant_id
            )
            if shift.id in referenced_ids:
                raise ValidationError(
                    "This shift is referenced by schedules or rules and its type cannot be changed"
                )

        if target_type == ScheduleShiftType.LEAVE.value:
            update_data["start_time"] = LEAVE_PLACEHOLDER_START
            update_data["end_time"] = LEAVE_PLACEHOLDER_END
        else:
            if target_type != current_type and (
                update_data.get("start_time") is None
                or update_data.get("end_time") is None
            ):
                raise ValidationError(
                    "Start time and end time are required for work shifts"
                )
            new_start = update_data.get(
                "start_time", shift.start_time.strftime("%H:%M")
            )
            new_end = update_data.get(
                "end_time", shift.end_time.strftime("%H:%M")
            )
            SchedulingService._validate_time_range(new_start, new_end)
            if "start_time" in update_data:
                update_data["start_time"] = hhmm_to_time(new_start)
            if "end_time" in update_data:
                update_data["end_time"] = hhmm_to_time(new_end)

        new_name = update_data.get("name")
        if new_name and new_name != shift.name:
            existing = await ScheduleShiftRepository.get_by_name(db, tenant_id, new_name)
            if existing:
                raise ValidationError("Shift name already exists")

        return await ScheduleShiftRepository.update(db, shift, update_data)

    @staticmethod
    async def delete_shift(db: AsyncSession, tenant_id: int, shift_id: int) -> None:
        shift = await ScheduleShiftRepository.get_by_id(db, tenant_id, shift_id)
        if not shift:
            raise NotFoundError("Shift not found")
        referenced_ids = await ScheduleShiftRepository.list_referenced_shift_ids(
            db, tenant_id
        )
        if shift_id in referenced_ids:
            raise ValidationError(
                "This shift is referenced by schedules or rules. Disable it instead."
            )
        await ScheduleShiftRepository.delete(db, shift)

    @staticmethod
    def _validate_time_range(start_time: str | None, end_time: str | None) -> None:
        if start_time is None or end_time is None:
            raise ValidationError(
                "Start time and end time are required for work shifts"
            )
        if start_time == end_time:
            raise ValidationError("End time must differ from start time")

    # ------------------------------------------------------------------
    # Scheduling pool
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_pool(
        db: AsyncSession, tenant_id: int, group_ids: list[int]
    ) -> dict[int, PoolMemberRow]:
        rows = await list_pool_members(db, tenant_id, sorted(set(group_ids)))
        return {row[0]: row for row in rows}

    @staticmethod
    async def list_pool(
        db: AsyncSession, tenant_id: int, group_ids: list[int]
    ) -> list[PoolMemberItem]:
        pool = await SchedulingService._resolve_pool(db, tenant_id, group_ids)
        return [
            PoolMemberItem(id=row[0], name=row[1], job_number=row[2])
            for row in pool.values()
        ]

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------

    @staticmethod
    async def list_assignments(
        db: AsyncSession, tenant_id: int, start_date: date, end_date: date
    ) -> list[AssignmentResponse]:
        if end_date < start_date:
            raise ValidationError("end_date must not be earlier than start_date")
        if (end_date - start_date).days + 1 > MAX_QUERY_RANGE_DAYS:
            raise ValidationError(
                f"Date range must not exceed {MAX_QUERY_RANGE_DAYS} days"
            )
        records = await ScheduleAssignmentRepository.list_by_date_range(
            db, tenant_id, start_date, end_date
        )
        if not records:
            return []
        shifts = {
            shift.id: shift
            for shift in await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        }
        employees = await list_employees_by_ids(
            db, tenant_id, sorted({r.employee_id for r in records})
        )
        items: list[AssignmentResponse] = []
        for record in records:
            shift = shifts.get(record.shift_id)
            employee = employees.get(record.employee_id)
            if not shift or not employee:
                # Referenced shift/employee was hard-deleted; skip the orphan row.
                continue
            items.append(
                AssignmentResponse(
                    id=record.id,
                    date=record.date,
                    shift=AssignmentShiftInfo(
                        id=shift.id,
                        name=shift.name,
                        shift_type=shift.shift_type or ScheduleShiftType.WORK.value,
                        color=shift.color,
                        start_time=shift.start_time,
                        end_time=shift.end_time,
                        is_enabled=shift.is_enabled,
                    ),
                    employee=AssignmentEmployeeInfo(
                        id=employee[0], name=employee[1], job_number=employee[2]
                    ),
                    created_at=record.created_at,
                )
            )
        return items

    @staticmethod
    async def create_assignments(
        db: AsyncSession, tenant_id: int, data: AssignmentBulkCreateRequest
    ) -> tuple[int, int, int]:
        pool = await SchedulingService._resolve_pool(db, tenant_id, data.group_ids)
        shift_ids = {item.shift_id for item in data.items}
        shifts = {
            shift.id: shift
            for shift in await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        }
        for shift_id in shift_ids:
            if shift_id not in shifts:
                raise NotFoundError(f"Shift {shift_id} not found")
        for item in data.items:
            if not shifts[item.shift_id].is_enabled:
                raise ValidationError(
                    f"Shift '{shifts[item.shift_id].name}' is disabled"
                )
            member = pool.get(item.employee_id)
            if not member:
                raise ValidationError(
                    f"Employee {item.employee_id} is not in the scheduling pool"
                )

        requested_by_employee_date: dict[tuple[int, date], set[int]] = {}
        for item in data.items:
            requested_by_employee_date.setdefault(
                (item.employee_id, item.date), set()
            ).add(item.shift_id)
        for requested_shift_ids in requested_by_employee_date.values():
            requested_types = {
                shifts[shift_id].shift_type or ScheduleShiftType.WORK.value
                for shift_id in requested_shift_ids
            }
            leave_ids = {
                shift_id
                for shift_id in requested_shift_ids
                if (shifts[shift_id].shift_type or ScheduleShiftType.WORK.value)
                == ScheduleShiftType.LEAVE.value
            }
            if len(requested_types) > 1 or len(leave_ids) > 1:
                raise ValidationError(
                    "An employee cannot have work shifts and leave, or multiple leave types, on the same day"
                )

        min_date = min(item.date for item in data.items)
        max_date = max(item.date for item in data.items)
        existing_records = await ScheduleAssignmentRepository.list_by_employee_date_range(
            db,
            tenant_id,
            sorted({item.employee_id for item in data.items}),
            min_date,
            max_date,
        )
        existing_by_employee_date: dict[
            tuple[int, date], list[ScheduleAssignment]
        ] = {}
        for record in existing_records:
            existing_by_employee_date.setdefault(
                (record.employee_id, record.date), []
            ).append(record)

        conflict_ids: set[int] = set()
        for employee_date, requested_shift_ids in requested_by_employee_date.items():
            requested_leave = any(
                (shifts[shift_id].shift_type or ScheduleShiftType.WORK.value)
                == ScheduleShiftType.LEAVE.value
                for shift_id in requested_shift_ids
            )
            for record in existing_by_employee_date.get(employee_date, []):
                existing_shift = shifts.get(record.shift_id)
                existing_leave = bool(
                    existing_shift
                    and (
                        existing_shift.shift_type or ScheduleShiftType.WORK.value
                    )
                    == ScheduleShiftType.LEAVE.value
                )
                conflicts = (
                    requested_leave and record.shift_id not in requested_shift_ids
                ) or (not requested_leave and existing_leave)
                if conflicts:
                    conflict_ids.add(record.id)

        if conflict_ids and not data.replace_conflicts:
            conflict_employee_dates = {
                (record.employee_id, record.date)
                for record in existing_records
                if record.id in conflict_ids
            }
            raise BusinessError(
                "The change conflicts with existing work or leave assignments",
                status_code=409,
                code="LEAVE_WORK_CONFLICT",
                details={
                    "affected_employee_dates": len(conflict_employee_dates),
                    "conflict_assignment_ids": sorted(conflict_ids),
                },
            )

        existing = {
            (record.employee_id, record.shift_id, record.date)
            for record in existing_records
            if record.id not in conflict_ids
        }
        seen: set[tuple[int, int, date]] = set()
        rows: list[dict] = []
        skipped = 0
        for item in data.items:
            key = (item.employee_id, item.shift_id, item.date)
            if key in existing or key in seen:
                skipped += 1
                continue
            seen.add(key)
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "employee_id": item.employee_id,
                    "shift_id": item.shift_id,
                    "date": item.date,
                }
            )
        work_rows = [
            row
            for row in rows
            if (
                shifts[row["shift_id"]].shift_type or ScheduleShiftType.WORK.value
            )
            == ScheduleShiftType.WORK.value
        ]
        deleted_work_keys = {
            (record.employee_id, record.shift_id, record.date)
            for record in existing_records
            if record.id in conflict_ids
            and (
                shifts.get(record.shift_id)
                and (
                    shifts[record.shift_id].shift_type
                    or ScheduleShiftType.WORK.value
                )
                == ScheduleShiftType.WORK.value
            )
        }
        await SchedulingPlanService.validate_write(
            db,
            tenant_id,
            data.group_ids,
            {
                (row["employee_id"], row["shift_id"], row["date"])
                for row in work_rows
            },
            deleted_keys=deleted_work_keys,
            allow_soft=data.allow_soft,
        )
        created, replaced = (
            await ScheduleAssignmentRepository.replace_conflicts_and_create(
                db, tenant_id, sorted(conflict_ids), rows
            )
        )
        return created, skipped, replaced

    @staticmethod
    async def delete_assignments(
        db: AsyncSession, tenant_id: int, ids: list[int]
    ) -> int:
        return await ScheduleAssignmentRepository.delete_by_ids(db, tenant_id, ids)

    @staticmethod
    async def copy_week(
        db: AsyncSession, tenant_id: int, data: CopyWeekRequest
    ) -> tuple[int, int, int]:
        target_start = data.week_start
        source_start = target_start - timedelta(days=7)
        source_end = target_start - timedelta(days=1)
        target_end = target_start + timedelta(days=6)

        pool = await SchedulingService._resolve_pool(db, tenant_id, data.group_ids)
        shifts = {
            shift.id: shift
            for shift in await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        }
        work_shift_ids = {
            shift.id
            for shift in shifts.values()
            if (shift.shift_type or ScheduleShiftType.WORK.value)
            == ScheduleShiftType.WORK.value
        }
        leave_shift_ids = set(shifts) - work_shift_ids
        source_records = [
            r
            for r in await ScheduleAssignmentRepository.list_by_date_range(
                db, tenant_id, source_start, source_end
            )
            if r.employee_id in pool and r.shift_id in work_shift_ids
        ]
        if not source_records:
            return 0, 0, 0
        target_records = await ScheduleAssignmentRepository.list_by_date_range(
            db, tenant_id, target_start, target_end
        )

        # Cell = (target date, shift id). Group source rows by target cell.
        source_by_cell: dict[tuple[date, int], list[int]] = {}
        for record in source_records:
            cell = (record.date + timedelta(days=7), record.shift_id)
            source_by_cell.setdefault(cell, []).append(record.employee_id)
        occupied_cells = {(r.date, r.shift_id) for r in target_records}
        protected_leave_dates = {
            (record.employee_id, record.date)
            for record in target_records
            if record.shift_id in leave_shift_ids
        }

        to_delete: list[tuple[int, date]] = []
        rows: list[dict] = []
        skipped_cells = 0
        skipped_leave_conflicts = 0
        for (day, shift_id), employee_ids in source_by_cell.items():
            if data.mode == "skip" and (day, shift_id) in occupied_cells:
                skipped_cells += 1
                continue
            if data.mode == "overwrite" and (day, shift_id) in occupied_cells:
                to_delete.append((shift_id, day))
            for employee_id in dict.fromkeys(employee_ids):
                if (employee_id, day) in protected_leave_dates:
                    skipped_leave_conflicts += 1
                    continue
                rows.append(
                    {
                        "tenant_id": tenant_id,
                        "employee_id": employee_id,
                        "shift_id": shift_id,
                        "date": day,
                    }
                )

        if rows:
            deleted_keys: set[tuple[int, int, date]] = set()
            if to_delete:
                cells = {(day, shift_id) for shift_id, day in to_delete}
                deleted_keys = {
                    (r.employee_id, r.shift_id, r.date)
                    for r in target_records
                    if (r.date, r.shift_id) in cells
                }
            await SchedulingPlanService.validate_write(
                db,
                tenant_id,
                data.group_ids,
                {(row["employee_id"], row["shift_id"], row["date"]) for row in rows},
                deleted_keys=deleted_keys,
                allow_soft=data.allow_soft,
            )
        if to_delete:
            await ScheduleAssignmentRepository.delete_by_cells(db, tenant_id, to_delete)
        for row in rows:
            db.add(ScheduleAssignment(**row))
        await db.commit()
        return len(rows), skipped_cells, skipped_leave_conflicts

    # ------------------------------------------------------------------
    # Excel export
    # ------------------------------------------------------------------

    @staticmethod
    async def export_assignments_xlsx(
        db: AsyncSession,
        tenant_id: int,
        start_date: date,
        end_date: date,
        group_ids: list[int],
        lang: str = "zh",
    ) -> tuple[bytes, str]:
        """Build the export workbook; returns (xlsx bytes, download filename).

        Sheets: shift×day matrix, employee×day matrix, and a flat detail list.
        """
        SchedulingService._validate_export_range(start_date, end_date)
        is_zh = not lang.lower().startswith("en")

        records = await ScheduleAssignmentRepository.list_by_date_range(
            db, tenant_id, start_date, end_date
        )
        shifts = await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        shift_map = {s.id: s for s in shifts}
        pool_rows = await list_pool_members(db, tenant_id, sorted(set(group_ids)))
        employees = await list_employees_by_ids(
            db, tenant_id, sorted({r.employee_id for r in records})
        )

        days = [
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]
        weekday_zh = ["一", "二", "三", "四", "五", "六", "日"]
        weekday_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        def weekday_label(d: date) -> str:
            idx = d.weekday()
            return f"周{weekday_zh[idx]}" if is_zh else weekday_en[idx]

        # Rows: enabled shifts first (by sort order), then disabled shifts that
        # still have records in range.
        enabled_shifts = [s for s in shifts if s.is_enabled]
        recorded_shift_ids = {r.shift_id for r in records}
        extra_shifts = [
            s for s in shifts if not s.is_enabled and s.id in recorded_shift_ids
        ]
        row_shifts = sorted(
            enabled_shifts + extra_shifts,
            key=lambda shift: (
                (shift.shift_type or ScheduleShiftType.WORK.value)
                == ScheduleShiftType.LEAVE.value,
                not shift.is_enabled,
                shift.sort_order,
                shift.id,
            ),
        )

        # Employee rows: pool members (name order) first, then off-pool employees
        # that still have records in range.
        pool_ids = {row[0] for row in pool_rows}
        extra_employees = sorted(
            (emp for emp in employees.values() if emp[0] not in pool_ids),
            key=lambda row: (row[1], row[0]),
        )
        row_employees: list[PoolMemberRow] = list(pool_rows) + extra_employees

        def shift_label(s: ScheduleShift) -> str:
            if (s.shift_type or ScheduleShiftType.WORK.value) == ScheduleShiftType.LEAVE.value:
                prefix = "[假期]" if is_zh else "[Leave]"
                all_day = "全天" if is_zh else "All day"
                return f"{prefix} {s.name} {all_day}"
            return f"{s.name} {s.start_time.strftime('%H:%M')}-{s.end_time.strftime('%H:%M')}"

        day_headers = [
            f"{d.strftime('%Y-%m-%d')} {weekday_label(d)}" for d in days
        ]

        # Sheet 1: shift × day matrix.
        sheet1_headers = ["班次 \\ 日期" if is_zh else "Shift \\ Day"] + day_headers
        sheet1_rows: list[list[object]] = []
        for s in row_shifts:
            row: list[object] = [shift_label(s)]
            for d in days:
                names = [
                    employees[r.employee_id][1]
                    for r in records
                    if r.shift_id == s.id and r.date == d and r.employee_id in employees
                ]
                row.append("\n".join(names))
            sheet1_rows.append(row)

        # Sheet 2: employee × day matrix.
        sheet2_headers = ["员工 \\ 日期" if is_zh else "Employee \\ Day"] + day_headers
        sheet2_rows: list[list[object]] = []
        for emp in row_employees:
            row = [emp[1]]
            for d in days:
                names = [
                    (
                        ("[假期] " if is_zh else "[Leave] ")
                        + shift_map[r.shift_id].name
                        if (
                            shift_map[r.shift_id].shift_type
                            or ScheduleShiftType.WORK.value
                        )
                        == ScheduleShiftType.LEAVE.value
                        else shift_map[r.shift_id].name
                    )
                    for r in records
                    if r.employee_id == emp[0] and r.date == d and r.shift_id in shift_map
                ]
                row.append("、".join(names))
            sheet2_rows.append(row)

        # Sheet 3: flat detail list.
        sheet3_headers = (
            ["日期", "星期", "类型", "名称", "时段", "员工姓名", "工号"]
            if is_zh
            else ["Date", "Weekday", "Type", "Name", "Time", "Employee", "Job Number"]
        )
        sheet3_rows: list[list[object]] = []
        for r in records:
            s = shift_map.get(r.shift_id)
            emp = employees.get(r.employee_id)
            if not s or not emp:
                continue
            is_leave = (
                s.shift_type or ScheduleShiftType.WORK.value
            ) == ScheduleShiftType.LEAVE.value
            sheet3_rows.append(
                [
                    r.date.strftime("%Y-%m-%d"),
                    weekday_label(r.date),
                    ("假期类型" if is_zh else "Leave type")
                    if is_leave
                    else ("工作班次" if is_zh else "Work shift"),
                    s.name,
                    (
                        "全天" if is_zh else "All day"
                    )
                    if is_leave
                    else f"{s.start_time.strftime('%H:%M')}-{s.end_time.strftime('%H:%M')}",
                    emp[1],
                    emp[2] or "",
                ]
            )

        content = build_xlsx(
            sheet1_headers,
            sheet1_rows,
            sheet_name="班次日期表" if is_zh else "Shift × Day",
            extra_sheets=[
                ("员工日期表" if is_zh else "Employee × Day", sheet2_headers, sheet2_rows),
                ("明细" if is_zh else "Detail", sheet3_headers, sheet3_rows),
            ],
        )

        # Pool label: group names joined, truncated.
        group_names: list[str] = []
        if group_ids:
            result = await db.execute(
                select(EmployeeGroup.name).where(
                    EmployeeGroup.tenant_id == tenant_id,
                    EmployeeGroup.id.in_(sorted(set(group_ids))),
                )
            )
            group_names = list(result.scalars().all())
        pool_label = "、".join(group_names)[:30] if group_names else ("全部" if is_zh else "all")

        exported_at = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        if start_date.day == 1 and (end_date - start_date).days >= 27:
            period = start_date.strftime("%Y-%m")
        else:
            period = f"{start_date.strftime('%Y-%m-%d')}_{end_date.strftime('%Y-%m-%d')}"
        filename = (
            f"排班_{pool_label}_{period}_{exported_at}.xlsx"
            if is_zh
            else f"schedule_{pool_label}_{period}_{exported_at}.xlsx"
        )
        return content, filename

    @staticmethod
    def _validate_export_range(start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise ValidationError("end_date must not be earlier than start_date")
        if (end_date - start_date).days + 1 > MAX_QUERY_RANGE_DAYS:
            raise ValidationError(
                f"Date range must not exceed {MAX_QUERY_RANGE_DAYS} days"
            )
