"""Unit tests for the read-only personal schedule service."""

from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.scheduling import SchedulePublishedSnapshot, ScheduleShift
from app.services.scheduling_my_service import SchedulingMyService

MON = date(2026, 8, 3)
WED = date(2026, 8, 5)
NOW = datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc)
SERVICE = "app.services.scheduling_my_service"


def make_snapshot(payload: list) -> SchedulePublishedSnapshot:
    return SchedulePublishedSnapshot(
        id=1,
        tenant_id=1,
        week_start=MON,
        payload=payload,
        published_by=7,
        published_at=NOW,
    )


def make_shift(
    shift_id: int,
    name: str,
    start: time,
    end: time,
    color: str,
    shift_type: str = "work",
) -> ScheduleShift:
    return ScheduleShift(
        id=shift_id,
        tenant_id=1,
        name=name,
        shift_type=shift_type,
        start_time=start,
        end_time=end,
        color=color,
        sort_order=shift_id,
        is_enabled=True,
    )


def patch_repositories(snapshot=None, shifts=None, timezone_name="Asia/Shanghai"):
    settings_repo = patch(f"{SERVICE}.SystemSettingsRepository").start()
    snapshot_repo = patch(f"{SERVICE}.SchedulePublishedSnapshotRepository").start()
    shift_repo = patch(f"{SERVICE}.ScheduleShiftRepository").start()
    settings_repo.get_by_tenant_id = AsyncMock(
        return_value=SimpleNamespace(default_timezone=timezone_name)
    )
    snapshot_repo.get_by_week = AsyncMock(return_value=snapshot)
    shift_repo.list_by_tenant = AsyncMock(return_value=shifts or [])
    return snapshot_repo, shift_repo


@pytest.fixture(autouse=True)
def stop_patches():
    yield
    patch.stopall()


@pytest.mark.asyncio
async def test_unpublished_week_returns_seven_empty_days_in_tenant_timezone():
    snapshot_repo, shift_repo = patch_repositories(snapshot=None)
    just_after_midnight_shanghai = datetime(2026, 8, 2, 16, 30, tzinfo=timezone.utc)

    result = await SchedulingMyService.get_week(
        AsyncMock(),
        tenant_id=1,
        employee_id=7,
        now=just_after_midnight_shanghai,
    )

    assert result.today == MON
    assert result.week_start == MON
    assert result.week_end == date(2026, 8, 9)
    assert result.is_published is False
    assert len(result.days) == 7
    assert all(not day.shifts for day in result.days)
    assert snapshot_repo.get_by_week.await_count == 1
    assert snapshot_repo.get_by_week.call_args.args[1:] == (1, MON)
    shift_repo.list_by_tenant.assert_not_awaited()


@pytest.mark.asyncio
async def test_published_week_filters_current_employee_and_uses_snapshot_details():
    payload = [
        {
            "shift_id": 1,
            "employee_id": 7,
            "date": WED.isoformat(),
            "shift": {
                "name": "发布时早班",
                "start_time": "09:00",
                "end_time": "13:00",
                "color": "#111111",
            },
        },
        {
            "shift_id": 2,
            "employee_id": 8,
            "date": WED.isoformat(),
            "shift": {
                "name": "同事班次",
                "start_time": "10:00",
                "end_time": "14:00",
                "color": "#222222",
            },
        },
    ]
    patch_repositories(snapshot=make_snapshot(payload))

    result = await SchedulingMyService.get_week(
        AsyncMock(), 1, 7, requested_week=WED, now=NOW
    )

    assert result.is_published is True
    assert result.published_at == NOW
    wednesday = result.days[2]
    assert [shift.name for shift in wednesday.shifts] == ["发布时早班"]
    assert wednesday.shifts[0].start_time == "09:00"


@pytest.mark.asyncio
async def test_published_leave_uses_snapshot_name_and_all_day_type():
    payload = [
        {
            "shift_id": 3,
            "employee_id": 7,
            "date": WED.isoformat(),
            "shift": {
                "name": "发布时请假",
                "shift_type": "leave",
                "start_time": None,
                "end_time": None,
                "color": "#8B5CF6",
            },
        }
    ]
    patch_repositories(snapshot=make_snapshot(payload))

    result = await SchedulingMyService.get_week(
        AsyncMock(), 1, 7, requested_week=WED, now=NOW
    )

    leave = result.days[2].shifts[0]
    assert leave.name == "发布时请假"
    assert leave.shift_type == "leave"
    assert leave.start_time is None and leave.end_time is None


@pytest.mark.asyncio
async def test_legacy_snapshot_uses_live_shift_and_deleted_placeholder_and_sorts():
    payload = [
        {"shift_id": 99, "employee_id": 7, "date": MON.isoformat()},
        {"shift_id": 2, "employee_id": 7, "date": MON.isoformat()},
        {"shift_id": 1, "employee_id": 7, "date": MON.isoformat()},
    ]
    shifts = [
        make_shift(1, "早班", time(9), time(13), "#111111"),
        make_shift(2, "晚班", time(18), time(22), "#222222"),
    ]
    patch_repositories(snapshot=make_snapshot(payload), shifts=shifts)

    result = await SchedulingMyService.get_week(
        AsyncMock(), 1, 7, requested_week=MON, now=NOW
    )

    monday_shifts = result.days[0].shifts
    assert [shift.id for shift in monday_shifts] == [1, 2, 99]
    assert monday_shifts[0].name == "早班"
    assert monday_shifts[-1].name == "#99"
    assert monday_shifts[-1].is_deleted is True
    assert monday_shifts[-1].start_time is None


@pytest.mark.asyncio
async def test_requested_day_is_normalized_to_monday():
    snapshot_repo, _ = patch_repositories(snapshot=None)

    result = await SchedulingMyService.get_week(
        AsyncMock(), 1, 7, requested_week=WED, now=NOW
    )

    assert result.week_start == MON
    assert snapshot_repo.get_by_week.call_args.args[2] == MON


@pytest.mark.asyncio
async def test_invalid_timezone_falls_back_to_default():
    patch_repositories(snapshot=None, timezone_name="Not/A-Timezone")

    result = await SchedulingMyService.get_week(
        AsyncMock(), 1, 7, requested_week=MON, now=NOW
    )

    assert result.today == WED
