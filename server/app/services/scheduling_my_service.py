"""Read-only personal schedule service backed by published snapshots."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ScheduleShiftType
from app.repositories.scheduling_repository import (
    SchedulePublishedSnapshotRepository,
    ScheduleShiftRepository,
)
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.schemas.scheduling import (
    MyScheduleDayResponse,
    MyScheduleResponse,
    MyScheduleShiftResponse,
)
from app.services.scheduling_publish_service import week_start_of

DEFAULT_TENANT_TIMEZONE = "Asia/Shanghai"
DELETED_SHIFT_COLOR = "#737373"


def _timezone_or_default(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((name or DEFAULT_TENANT_TIMEZONE).strip())
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return ZoneInfo(DEFAULT_TENANT_TIMEZONE)


def _snapshot_details(entry: dict) -> dict | None:
    details = entry.get("shift")
    if not isinstance(details, dict) or not str(details.get("name") or "").strip():
        return None
    return details


class SchedulingMyService:
    """Build one employee's week from the tenant's published snapshot."""

    @staticmethod
    async def get_week(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int,
        requested_week: date | None = None,
        now: datetime | None = None,
    ) -> MyScheduleResponse:
        settings = await SystemSettingsRepository.get_by_tenant_id(db, tenant_id)
        tenant_tz = _timezone_or_default(settings.default_timezone if settings else None)
        current_instant = now or datetime.now(timezone.utc)
        if current_instant.tzinfo is None:
            current_instant = current_instant.replace(tzinfo=timezone.utc)
        today = current_instant.astimezone(tenant_tz).date()
        week_start = week_start_of(requested_week or today)
        week_end = week_start + timedelta(days=6)

        days = {
            week_start + timedelta(days=offset): []
            for offset in range(7)
        }
        snapshot = await SchedulePublishedSnapshotRepository.get_by_week(
            db, tenant_id, week_start
        )
        if snapshot is None:
            return MyScheduleResponse(
                week_start=week_start,
                week_end=week_end,
                today=today,
                is_published=False,
                days=[
                    MyScheduleDayResponse(date=day, shifts=[])
                    for day in days
                ],
            )

        payload = snapshot.payload if isinstance(snapshot.payload, list) else []
        own_entries = [
            entry
            for entry in payload
            if isinstance(entry, dict)
            and str(entry.get("employee_id")) == str(employee_id)
        ]
        shifts = await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        live_shifts = {shift.id: shift for shift in shifts}

        for entry in own_entries:
            try:
                shift_id = int(entry["shift_id"])
                shift_date = date.fromisoformat(str(entry["date"]))
            except (KeyError, TypeError, ValueError):
                continue
            if shift_date not in days:
                continue

            details = _snapshot_details(entry)
            live_shift = live_shifts.get(shift_id)
            if details is not None:
                shift_type = (
                    ScheduleShiftType.LEAVE.value
                    if details.get("shift_type") == ScheduleShiftType.LEAVE.value
                    else ScheduleShiftType.WORK.value
                )
                shift = MyScheduleShiftResponse(
                    id=shift_id,
                    name=str(details["name"]),
                    shift_type=shift_type,
                    start_time=(
                        None
                        if shift_type == ScheduleShiftType.LEAVE.value
                        else str(details.get("start_time") or "") or None
                    ),
                    end_time=(
                        None
                        if shift_type == ScheduleShiftType.LEAVE.value
                        else str(details.get("end_time") or "") or None
                    ),
                    color=str(details.get("color") or DELETED_SHIFT_COLOR),
                )
            elif live_shift is not None:
                shift_type = live_shift.shift_type or ScheduleShiftType.WORK.value
                shift = MyScheduleShiftResponse(
                    id=shift_id,
                    name=live_shift.name,
                    shift_type=shift_type,
                    start_time=(
                        None
                        if shift_type == ScheduleShiftType.LEAVE.value
                        else live_shift.start_time.strftime("%H:%M")
                    ),
                    end_time=(
                        None
                        if shift_type == ScheduleShiftType.LEAVE.value
                        else live_shift.end_time.strftime("%H:%M")
                    ),
                    color=live_shift.color,
                )
            else:
                shift = MyScheduleShiftResponse(
                    id=shift_id,
                    name=f"#{shift_id}",
                    color=DELETED_SHIFT_COLOR,
                    is_deleted=True,
                )
            days[shift_date].append(shift)

        for shifts_for_day in days.values():
            shifts_for_day.sort(
                key=lambda shift: (
                    shift.shift_type == ScheduleShiftType.LEAVE.value,
                    shift.start_time or "99:99",
                    shift.name,
                    shift.id,
                )
            )

        return MyScheduleResponse(
            week_start=week_start,
            week_end=week_end,
            today=today,
            is_published=True,
            published_at=snapshot.published_at,
            days=[
                MyScheduleDayResponse(date=day, shifts=shifts_for_day)
                for day, shifts_for_day in days.items()
            ],
        )
