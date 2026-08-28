"""
Unit tests for the scheduling publish/reset orchestration: snapshot status,
publish (create/overwrite), and reset (restore from snapshot).
"""
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import BusinessError
from app.models.scheduling import ScheduleAssignment, SchedulePublishedSnapshot, ScheduleShift
from app.services.scheduling_publish_service import SchedulingPublishService, week_start_of

MON = date(2026, 8, 3)
WED = date(2026, 8, 5)
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)

SERVICE = "app.services.scheduling_publish_service"


def make_assignment(
    assignment_id: int, employee_id: int = 1, shift_id: int = 1, day: date = MON
) -> ScheduleAssignment:
    return ScheduleAssignment(
        id=assignment_id,
        tenant_id=1,
        shift_id=shift_id,
        employee_id=employee_id,
        date=day,
    )


def make_snapshot(payload: list | None = None) -> SchedulePublishedSnapshot:
    return SchedulePublishedSnapshot(
        id=1,
        tenant_id=1,
        week_start=MON,
        payload=payload if payload is not None else [],
        published_by=7,
        published_at=NOW,
    )


def make_shift(shift_id: int = 1, shift_type: str = "work") -> ScheduleShift:
    return ScheduleShift(
        id=shift_id,
        tenant_id=1,
        name="早班",
        shift_type=shift_type,
        start_time=time(9, 0),
        end_time=time(13, 0),
        color="#4B9CF5",
        sort_order=shift_id,
        is_enabled=True,
    )


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _patch_repos(snapshot=None, records=None, shifts=None, employees=None, publisher_name="张三"):
    snapshot_repo = patch(f"{SERVICE}.SchedulePublishedSnapshotRepository").start()
    assignment_repo = patch(f"{SERVICE}.ScheduleAssignmentRepository").start()
    shift_repo = patch(f"{SERVICE}.ScheduleShiftRepository").start()
    employees_fn = patch(f"{SERVICE}.list_employees_by_ids").start()
    employee_repo = patch(f"{SERVICE}.EmployeeRepository").start()

    snapshot_repo.get_by_week = AsyncMock(return_value=snapshot)

    async def _upsert(db, tenant_id, week_start, payload, published_by, published_at):
        # After upsert, subsequent status reads see the new snapshot.
        snapshot_repo.get_by_week = AsyncMock(return_value=make_snapshot(payload))

    snapshot_repo.upsert = AsyncMock(side_effect=_upsert)
    assignment_repo.list_by_date_range = AsyncMock(return_value=records or [])
    assignment_repo.delete_by_date_range = AsyncMock(return_value=len(records or []))
    assignment_repo.bulk_create = AsyncMock(side_effect=lambda db, rows: len(rows))
    shift_repo.list_by_tenant = AsyncMock(
        return_value=shifts if shifts is not None else [make_shift()]
    )
    employees_fn.return_value = employees if employees is not None else {1: (1, "甲", None)}
    publisher = type("Employee", (), {"name": publisher_name})() if publisher_name else None
    employee_repo.get_by_id = AsyncMock(return_value=publisher)
    return snapshot_repo, assignment_repo


# ----------------------------------------------------------------------
# week_start_of
# ----------------------------------------------------------------------


def test_week_start_normalizes_to_monday():
    assert week_start_of(WED) == MON
    assert week_start_of(MON) == MON
    assert week_start_of(date(2026, 8, 9)) == MON  # Sunday belongs to same week


# ----------------------------------------------------------------------
# get_status
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_unpublished_without_snapshot():
    _patch_repos(snapshot=None)
    result = await SchedulingPublishService.get_status(AsyncMock(), 1, WED)
    assert result.week_start == MON
    assert result.state == "unpublished"
    assert result.published_at is None


@pytest.mark.asyncio
async def test_status_published_when_current_matches_snapshot():
    payload = [{"shift_id": 1, "employee_id": 1, "date": MON.isoformat()}]
    records = [make_assignment(1)]
    _patch_repos(snapshot=make_snapshot(payload), records=records)
    result = await SchedulingPublishService.get_status(AsyncMock(), 1, MON)
    assert result.state == "published"
    assert result.published_at == NOW
    assert result.published_by_name == "张三"


@pytest.mark.asyncio
async def test_status_dirty_when_current_differs_from_snapshot():
    payload = [{"shift_id": 1, "employee_id": 1, "date": MON.isoformat()}]
    records = [make_assignment(1), make_assignment(2, employee_id=2)]
    _patch_repos(snapshot=make_snapshot(payload), records=records)
    result = await SchedulingPublishService.get_status(AsyncMock(), 1, MON)
    assert result.state == "dirty"


@pytest.mark.asyncio
async def test_status_dirty_ignores_assignment_ids():
    # Same keys but different assignment ids (e.g. after a reset) → published.
    payload = [{"shift_id": 1, "employee_id": 1, "date": MON.isoformat()}]
    records = [make_assignment(99)]
    _patch_repos(snapshot=make_snapshot(payload), records=records)
    result = await SchedulingPublishService.get_status(AsyncMock(), 1, MON)
    assert result.state == "published"


# ----------------------------------------------------------------------
# publish
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_writes_sorted_payload_and_returns_published():
    records = [
        make_assignment(1, employee_id=2, day=WED),
        make_assignment(2, employee_id=1, day=MON),
    ]
    snapshot_repo, _ = _patch_repos(snapshot=None, records=records)
    db = AsyncMock()
    result = await SchedulingPublishService.publish(db, 1, WED, published_by=7)

    payload = snapshot_repo.upsert.call_args[0][3]
    assert payload == [
        {
            "shift_id": 1,
            "employee_id": 1,
            "date": MON.isoformat(),
            "shift": {
                "name": "早班",
                "shift_type": "work",
                "start_time": "09:00",
                "end_time": "13:00",
                "color": "#4B9CF5",
            },
        },
        {
            "shift_id": 1,
            "employee_id": 2,
            "date": WED.isoformat(),
            "shift": {
                "name": "早班",
                "shift_type": "work",
                "start_time": "09:00",
                "end_time": "13:00",
                "color": "#4B9CF5",
            },
        },
    ]
    db.commit.assert_awaited_once()
    assert result.state == "published"


@pytest.mark.asyncio
async def test_publish_leave_snapshot_preserves_all_day_semantics():
    records = [make_assignment(1, shift_id=2)]
    leave = make_shift(2, shift_type="leave")
    leave.name = "请假"
    snapshot_repo, _ = _patch_repos(snapshot=None, records=records, shifts=[leave])

    await SchedulingPublishService.publish(AsyncMock(), 1, MON, published_by=7)

    details = snapshot_repo.upsert.call_args.args[3][0]["shift"]
    assert details == {
        "name": "请假",
        "shift_type": "leave",
        "start_time": None,
        "end_time": None,
        "color": "#4B9CF5",
    }


@pytest.mark.asyncio
async def test_publish_empty_week_allowed():
    snapshot_repo, _ = _patch_repos(snapshot=None, records=[])
    result = await SchedulingPublishService.publish(AsyncMock(), 1, MON, published_by=7)
    payload = snapshot_repo.upsert.call_args[0][3]
    assert payload == []
    assert result.state == "published"


# ----------------------------------------------------------------------
# reset
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_without_snapshot_raises():
    _patch_repos(snapshot=None)
    with pytest.raises(BusinessError) as exc_info:
        await SchedulingPublishService.reset(AsyncMock(), 1, MON)
    assert exc_info.value.code == "NO_PUBLISHED_SNAPSHOT"


@pytest.mark.asyncio
async def test_reset_restores_snapshot_entries():
    payload = [
        {"shift_id": 1, "employee_id": 1, "date": MON.isoformat()},
        {"shift_id": 1, "employee_id": 1, "date": WED.isoformat()},
    ]
    records = [make_assignment(1, employee_id=2)]
    _, assignment_repo = _patch_repos(snapshot=make_snapshot(payload), records=records)

    result = await SchedulingPublishService.reset(AsyncMock(), 1, WED)

    assert result.week_start == MON
    assert result.deleted == 1
    assert result.restored == 2
    rows = assignment_repo.bulk_create.call_args[0][1]
    assert {(r["employee_id"], r["shift_id"], r["date"]) for r in rows} == {
        (1, 1, MON),
        (1, 1, WED),
    }


@pytest.mark.asyncio
async def test_reset_skips_entries_with_deleted_shift_or_employee():
    payload = [
        {"shift_id": 1, "employee_id": 1, "date": MON.isoformat()},
        {"shift_id": 99, "employee_id": 1, "date": MON.isoformat()},  # shift gone
        {"shift_id": 1, "employee_id": 88, "date": MON.isoformat()},  # employee gone
    ]
    _, assignment_repo = _patch_repos(
        snapshot=make_snapshot(payload), records=[], employees={1: (1, "甲", None)}
    )
    result = await SchedulingPublishService.reset(AsyncMock(), 1, MON)
    assert result.restored == 1
    rows = assignment_repo.bulk_create.call_args[0][1]
    assert len(rows) == 1
    assert rows[0]["shift_id"] == 1 and rows[0]["employee_id"] == 1
