"""
Unit tests for Scheduling Center assignment service: pool resolution, bulk
write validation/idempotency, bulk delete, and copy-week semantics.
"""
from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.models.scheduling import ScheduleAssignment, ScheduleShift
from app.schemas.scheduling import (
    AssignmentBulkCreateRequest,
    AssignmentWriteItem,
    CopyWeekRequest,
)
from app.services.scheduling_service import SchedulingService

TENANT = 1
WEEK_START = date(2026, 8, 10)  # Monday


def shift(
    shift_id: int = 1, enabled: bool = True, shift_type: str = "work"
) -> ScheduleShift:
    return ScheduleShift(
        id=shift_id,
        tenant_id=TENANT,
        name=f"班次{shift_id}",
        shift_type=shift_type,
        start_time=time(9, 0),
        end_time=time(13, 0),
        color="#4B9CF5",
        sort_order=shift_id,
        is_enabled=enabled,
    )


def assignment(
    record_id: int, employee_id: int, shift_id: int, day: date
) -> ScheduleAssignment:
    return ScheduleAssignment(
        id=record_id,
        tenant_id=TENANT,
        employee_id=employee_id,
        shift_id=shift_id,
        date=day,
    )


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _patch_all(
    pool: list[tuple[int, str, str | None]] | None = None,
    shifts: dict[int, ScheduleShift] | None = None,
):
    """Patch repositories and module-level pool helpers used by the service."""
    ns = SimpleNamespace()
    ns.shift_repo = patch(
        "app.services.scheduling_service.ScheduleShiftRepository"
    ).start()
    ns.assignment_repo = patch(
        "app.services.scheduling_service.ScheduleAssignmentRepository"
    ).start()
    ns.list_pool_members = patch(
        "app.services.scheduling_service.list_pool_members", new_callable=AsyncMock
    ).start()
    ns.list_employees_by_ids = patch(
        "app.services.scheduling_service.list_employees_by_ids", new_callable=AsyncMock
    ).start()
    ns.plan_service = patch(
        "app.services.scheduling_service.SchedulingPlanService"
    ).start()
    ns.plan_service.validate_write = AsyncMock()

    ns.list_pool_members.return_value = pool or []
    ns.shift_repo.list_by_tenant = AsyncMock(return_value=list((shifts or {}).values()))
    ns.shift_repo.get_by_id = AsyncMock(
        side_effect=lambda db, tenant_id, shift_id: (shifts or {}).get(shift_id)
    )
    for name in (
        "list_by_date_range",
        "list_existing_keys",
        "list_by_employee_date_range",
        "bulk_create",
        "replace_conflicts_and_create",
        "delete_by_ids",
        "delete_by_cells",
    ):
        setattr(ns.assignment_repo, name, AsyncMock())
    ns.assignment_repo.list_existing_keys.return_value = set()
    ns.assignment_repo.list_by_employee_date_range.return_value = []
    ns.assignment_repo.bulk_create.side_effect = lambda db, rows: len(rows)
    ns.assignment_repo.replace_conflicts_and_create.side_effect = (
        lambda db, tenant_id, conflict_ids, rows: (len(rows), len(conflict_ids))
    )
    ns.assignment_repo.delete_by_ids.side_effect = lambda db, tenant_id, ids: len(ids)
    return ns


def _db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


class TestListPool:
    @pytest.mark.asyncio
    async def test_pool_returns_members(self):
        ns = _patch_all(pool=[(1, "Alice", "A001"), (2, "Bob", None)])
        result = await SchedulingService.list_pool(_db(), TENANT, [1, 2])
        assert [m.id for m in result] == [1, 2]
        assert result[0].name == "Alice"
        assert result[1].job_number is None
        ns.list_pool_members.assert_awaited_once()


class TestListAssignments:
    @pytest.mark.asyncio
    async def test_invalid_range_rejected(self):
        _patch_all()
        with pytest.raises(ValidationError):
            await SchedulingService.list_assignments(
                _db(), TENANT, date(2026, 8, 10), date(2026, 8, 1)
            )

    @pytest.mark.asyncio
    async def test_range_too_long_rejected(self):
        _patch_all()
        with pytest.raises(ValidationError):
            await SchedulingService.list_assignments(
                _db(), TENANT, date(2026, 8, 1), date(2026, 11, 1)
            )

    @pytest.mark.asyncio
    async def test_list_assembles_shift_and_employee(self):
        ns = _patch_all(shifts={1: shift(1)})
        record = assignment(10, employee_id=5, shift_id=1, day=WEEK_START)
        ns.assignment_repo.list_by_date_range.return_value = [record]
        ns.list_employees_by_ids.return_value = {5: (5, "Alice", "A001")}

        result = await SchedulingService.list_assignments(
            _db(), TENANT, WEEK_START, WEEK_START
        )

        assert len(result) == 1
        item = result[0]
        assert item.id == 10
        assert item.shift.name == "班次1"
        assert item.employee.name == "Alice"

    @pytest.mark.asyncio
    async def test_list_skips_orphan_rows(self):
        ns = _patch_all(shifts={1: shift(1)})
        orphan = assignment(11, employee_id=99, shift_id=2, day=WEEK_START)
        ns.assignment_repo.list_by_date_range.return_value = [orphan]
        ns.list_employees_by_ids.return_value = {99: (99, "Gone", None)}

        result = await SchedulingService.list_assignments(
            _db(), TENANT, WEEK_START, WEEK_START
        )
        assert result == []


def _bulk_request(**overrides) -> AssignmentBulkCreateRequest:
    data = {
        "group_ids": [1],
        "items": [
            {"employee_id": 1, "shift_id": 1, "date": "2026-08-10"},
        ],
    }
    data.update(overrides)
    return AssignmentBulkCreateRequest(**data)


class TestCreateAssignments:
    @pytest.mark.asyncio
    async def test_create_happy_path(self):
        ns = _patch_all(pool=[(1, "Alice", None)], shifts={1: shift(1)})
        created, skipped, replaced = await SchedulingService.create_assignments(
            _db(), TENANT, _bulk_request()
        )
        assert (created, skipped, replaced) == (1, 0, 0)
        rows = ns.assignment_repo.replace_conflicts_and_create.await_args.args[3]
        assert rows[0]["employee_id"] == 1

    @pytest.mark.asyncio
    async def test_out_of_pool_employee_rejected(self):
        _patch_all(pool=[(2, "Bob", None)], shifts={1: shift(1)})
        with pytest.raises(ValidationError, match="not in the scheduling pool"):
            await SchedulingService.create_assignments(_db(), TENANT, _bulk_request())

    @pytest.mark.asyncio
    async def test_disabled_shift_rejected(self):
        _patch_all(pool=[(1, "Alice", None)], shifts={1: shift(1, enabled=False)})
        with pytest.raises(ValidationError, match="disabled"):
            await SchedulingService.create_assignments(_db(), TENANT, _bulk_request())

    @pytest.mark.asyncio
    async def test_unknown_shift_rejected(self):
        _patch_all(pool=[(1, "Alice", None)], shifts={})
        with pytest.raises(NotFoundError):
            await SchedulingService.create_assignments(_db(), TENANT, _bulk_request())

    @pytest.mark.asyncio
    async def test_existing_and_duplicate_items_skipped(self):
        ns = _patch_all(pool=[(1, "Alice", None)], shifts={1: shift(1)})
        ns.assignment_repo.list_by_employee_date_range.return_value = [
            assignment(10, 1, 1, date(2026, 8, 10))
        ]
        request = _bulk_request(
            items=[
                {"employee_id": 1, "shift_id": 1, "date": "2026-08-10"},  # existing
                {"employee_id": 1, "shift_id": 1, "date": "2026-08-11"},  # new
                {"employee_id": 1, "shift_id": 1, "date": "2026-08-11"},  # in-payload dup
            ]
        )
        created, skipped, replaced = await SchedulingService.create_assignments(
            _db(), TENANT, request
        )
        assert (created, skipped, replaced) == (1, 2, 0)

    @pytest.mark.asyncio
    async def test_work_and_leave_in_same_request_rejected(self):
        _patch_all(
            pool=[(1, "Alice", None)],
            shifts={1: shift(1), 2: shift(2, shift_type="leave")},
        )
        request = _bulk_request(
            items=[
                {"employee_id": 1, "shift_id": 1, "date": "2026-08-10"},
                {"employee_id": 1, "shift_id": 2, "date": "2026-08-10"},
            ]
        )
        with pytest.raises(ValidationError, match="cannot have work shifts and leave"):
            await SchedulingService.create_assignments(_db(), TENANT, request)

    @pytest.mark.asyncio
    async def test_leave_replacing_work_requires_confirmation(self):
        ns = _patch_all(
            pool=[(1, "Alice", None)],
            shifts={1: shift(1), 2: shift(2, shift_type="leave")},
        )
        ns.assignment_repo.list_by_employee_date_range.return_value = [
            assignment(10, 1, 1, WEEK_START)
        ]
        request = _bulk_request(
            items=[{"employee_id": 1, "shift_id": 2, "date": "2026-08-10"}]
        )
        with pytest.raises(BusinessError) as exc_info:
            await SchedulingService.create_assignments(_db(), TENANT, request)
        assert exc_info.value.code == "LEAVE_WORK_CONFLICT"
        ns.assignment_repo.replace_conflicts_and_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirmed_leave_replaces_work_atomically(self):
        ns = _patch_all(
            pool=[(1, "Alice", None)],
            shifts={1: shift(1), 2: shift(2, shift_type="leave")},
        )
        ns.assignment_repo.list_by_employee_date_range.return_value = [
            assignment(10, 1, 1, WEEK_START)
        ]
        request = _bulk_request(
            replace_conflicts=True,
            items=[{"employee_id": 1, "shift_id": 2, "date": "2026-08-10"}],
        )
        result = await SchedulingService.create_assignments(_db(), TENANT, request)
        assert result == (1, 0, 1)
        args = ns.assignment_repo.replace_conflicts_and_create.await_args.args
        assert args[2] == [10]
        assert args[3][0]["shift_id"] == 2
        ns.plan_service.validate_write.assert_awaited_once()
        assert ns.plan_service.validate_write.await_args.args[3] == set()

    @pytest.mark.asyncio
    async def test_confirmed_work_replaces_leave(self):
        ns = _patch_all(
            pool=[(1, "Alice", None)],
            shifts={1: shift(1), 2: shift(2, shift_type="leave")},
        )
        ns.assignment_repo.list_by_employee_date_range.return_value = [
            assignment(10, 1, 2, WEEK_START)
        ]
        result = await SchedulingService.create_assignments(
            _db(), TENANT, _bulk_request(replace_conflicts=True)
        )
        assert result == (1, 0, 1)
        assert ns.plan_service.validate_write.await_args.args[3] == {
            (1, 1, WEEK_START)
        }


class TestDeleteAssignments:
    @pytest.mark.asyncio
    async def test_delete_by_ids(self):
        _patch_all()
        deleted = await SchedulingService.delete_assignments(_db(), TENANT, [1, 2, 3])
        assert deleted == 3


def _copy_request(mode: str = "skip") -> CopyWeekRequest:
    return CopyWeekRequest(week_start=WEEK_START, mode=mode, group_ids=[1])


class TestCopyWeek:
    @pytest.mark.asyncio
    async def test_copy_skip_writes_empty_cells_only(self):
        ns = _patch_all(
            pool=[(1, "Alice", None), (2, "Bob", None)], shifts={1: shift(1)}
        )
        source_day = WEEK_START - timedelta(days=7)
        ns.assignment_repo.list_by_date_range.side_effect = [
            # Source week: Alice on shift 1.
            [assignment(1, employee_id=1, shift_id=1, day=source_day)],
            # Target week: cell (Mon, shift 1) already occupied by Bob.
            [assignment(2, employee_id=2, shift_id=1, day=WEEK_START)],
        ]
        copied, skipped_cells, skipped_leave = await SchedulingService.copy_week(
            _db(), TENANT, _copy_request("skip")
        )
        assert (copied, skipped_cells, skipped_leave) == (0, 1, 0)

    @pytest.mark.asyncio
    async def test_copy_overwrite_clears_cell_then_writes(self):
        ns = _patch_all(
            pool=[(1, "Alice", None), (2, "Bob", None)], shifts={1: shift(1)}
        )
        source_day = WEEK_START - timedelta(days=7)
        ns.assignment_repo.list_by_date_range.side_effect = [
            [assignment(1, employee_id=1, shift_id=1, day=source_day)],
            [assignment(2, employee_id=2, shift_id=1, day=WEEK_START)],
        ]
        db = _db()
        copied, skipped_cells, skipped_leave = await SchedulingService.copy_week(
            db, TENANT, _copy_request("overwrite")
        )
        assert (copied, skipped_cells, skipped_leave) == (1, 0, 0)
        ns.assignment_repo.delete_by_cells.assert_awaited_once()
        cells = ns.assignment_repo.delete_by_cells.await_args.args[2]
        assert cells == [(1, WEEK_START)]
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_copy_skips_out_of_pool_source_members(self):
        ns = _patch_all(pool=[(1, "Alice", None)], shifts={1: shift(1)})
        source_day = WEEK_START - timedelta(days=7)
        ns.assignment_repo.list_by_date_range.side_effect = [
            # Carol (id 3) left the pool; her source rows must not be copied.
            [assignment(1, employee_id=3, shift_id=1, day=source_day)],
            [],
        ]
        copied, skipped_cells, skipped_leave = await SchedulingService.copy_week(
            _db(), TENANT, _copy_request("skip")
        )
        assert (copied, skipped_cells, skipped_leave) == (0, 0, 0)

    @pytest.mark.asyncio
    async def test_copy_empty_source_is_noop(self):
        ns = _patch_all(pool=[(1, "Alice", None)], shifts={1: shift(1)})
        ns.assignment_repo.list_by_date_range.side_effect = [[], []]
        copied, skipped_cells, skipped_leave = await SchedulingService.copy_week(
            _db(), TENANT, _copy_request()
        )
        assert (copied, skipped_cells, skipped_leave) == (0, 0, 0)
        ns.assignment_repo.bulk_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_copy_ignores_source_leave_and_protects_target_leave(self):
        ns = _patch_all(
            pool=[(1, "Alice", None), (2, "Bob", None)],
            shifts={1: shift(1), 2: shift(2, shift_type="leave")},
        )
        source_day = WEEK_START - timedelta(days=7)
        ns.assignment_repo.list_by_date_range.side_effect = [
            [
                assignment(1, 1, 1, source_day),
                assignment(2, 2, 2, source_day),
            ],
            [assignment(3, 1, 2, WEEK_START)],
        ]
        result = await SchedulingService.copy_week(
            _db(), TENANT, _copy_request("overwrite")
        )
        assert result == (0, 0, 1)
