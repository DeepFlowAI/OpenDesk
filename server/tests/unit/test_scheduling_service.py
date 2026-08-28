"""
Unit tests for Scheduling Center shift service: CRUD validation, delete
constraint, and preset seeding idempotency.
"""
from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.scheduling import ScheduleShift
from app.repositories.scheduling_repository import ScheduleShiftRepository
from app.schemas.scheduling import ShiftCreate, ShiftUpdate
from app.services.scheduling_service import (
    LEAVE_PLACEHOLDER_END,
    LEAVE_PLACEHOLDER_START,
    SchedulingService,
    seed_preset_shifts,
)


def shift(
    shift_id: int = 1,
    name: str = "早班",
    start: time = time(9, 0),
    end: time = time(13, 0),
) -> ScheduleShift:
    return ScheduleShift(
        id=shift_id,
        tenant_id=1,
        name=name,
        shift_type="work",
        start_time=start,
        end_time=end,
        color="#4B9CF5",
        sort_order=1,
        is_enabled=True,
    )


def create_payload(**overrides) -> ShiftCreate:
    data = {
        "name": "夜班",
        "start_time": "22:00",
        "end_time": "06:00",
        "color": "#7B82E8",
        "sort_order": 4,
    }
    data.update(overrides)
    return ShiftCreate(**data)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _patch_repos():
    shift_repo = patch("app.services.scheduling_service.ScheduleShiftRepository").start()
    assignment_repo = patch("app.services.scheduling_service.ScheduleAssignmentRepository").start()
    for name in (
        "list_by_tenant",
        "get_by_id",
        "get_by_name",
        "create",
        "update",
        "delete",
        "count_assignments_by_shift",
        "list_referenced_shift_ids",
    ):
        setattr(shift_repo, name, AsyncMock())
    shift_repo.list_referenced_shift_ids.return_value = set()
    for name in ("count_by_shift", "list_by_date_range"):
        setattr(assignment_repo, name, AsyncMock())
    return SimpleNamespace(shift=shift_repo, assignment=assignment_repo)


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class _RowResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class TestShiftReferences:
    @pytest.mark.asyncio
    async def test_collects_assignment_snapshot_and_rule_references(self):
        db = AsyncMock()
        db.execute.side_effect = [
            _ScalarResult([1]),
            _ScalarResult([[{"shift_id": 2}, {"shift_id": "invalid"}]]),
            _RowResult([
                (
                    {"3": {"min": [], "target": [], "max": []}},
                    [{"days": [{"kind": "shift", "shift_id": 4}, {"kind": "off"}]}],
                )
            ]),
        ]

        result = await ScheduleShiftRepository.list_referenced_shift_ids(db, tenant_id=1)

        assert result == {1, 2, 3, 4}


class TestListShifts:
    @pytest.mark.asyncio
    async def test_list_marks_has_assignments(self):
        repos = _patch_repos()
        shifts = [shift(1), shift(2, "中班", time(13, 0), time(18, 0))]
        repos.shift.list_by_tenant = AsyncMock(return_value=shifts)
        repos.shift.count_assignments_by_shift = AsyncMock(return_value={2: 5})
        repos.shift.list_referenced_shift_ids = AsyncMock(return_value={1, 2})

        result = await SchedulingService.list_shifts(AsyncMock(), tenant_id=1)

        assert result[0].has_assignments is False
        assert result[1].has_assignments is True
        assert result[0].has_references is True
        assert result[1].has_references is True


class TestCreateShift:
    @pytest.mark.asyncio
    async def test_create_with_valid_data_returns_shift(self):
        repos = _patch_repos()
        repos.shift.get_by_name = AsyncMock(return_value=None)
        repos.shift.create = AsyncMock(side_effect=lambda db, data: ScheduleShift(id=9, **data))

        result = await SchedulingService.create_shift(AsyncMock(), tenant_id=1, data=create_payload())

        repos.shift.create.assert_called_once()
        payload = repos.shift.create.call_args.args[1]
        assert payload["start_time"] == time(22, 0)
        assert payload["end_time"] == time(6, 0)  # overnight is allowed
        assert result.id == 9

    @pytest.mark.asyncio
    async def test_create_with_duplicate_name_raises_validation(self):
        repos = _patch_repos()
        repos.shift.get_by_name = AsyncMock(return_value=shift())

        with pytest.raises(ValidationError):
            await SchedulingService.create_shift(AsyncMock(), tenant_id=1, data=create_payload())
        repos.shift.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_leave_uses_all_day_placeholder(self):
        repos = _patch_repos()
        repos.shift.get_by_name = AsyncMock(return_value=None)
        repos.shift.create = AsyncMock(side_effect=lambda db, data: ScheduleShift(id=9, **data))

        result = await SchedulingService.create_shift(
            AsyncMock(),
            tenant_id=1,
            data=create_payload(shift_type="leave", start_time=None, end_time=None),
        )

        payload = repos.shift.create.call_args.args[1]
        assert payload["shift_type"] == "leave"
        assert payload["start_time"] == LEAVE_PLACEHOLDER_START
        assert payload["end_time"] == LEAVE_PLACEHOLDER_END
        assert result.shift_type == "leave"

    @pytest.mark.asyncio
    async def test_create_work_without_times_raises_validation(self):
        repos = _patch_repos()
        repos.shift.get_by_name = AsyncMock(return_value=None)
        with pytest.raises(ValidationError, match="required for work shifts"):
            await SchedulingService.create_shift(
                AsyncMock(),
                tenant_id=1,
                data=create_payload(start_time=None, end_time=None),
            )

    @pytest.mark.asyncio
    async def test_create_with_zero_length_raises_validation(self):
        _patch_repos()
        with pytest.raises(ValidationError):
            await SchedulingService.create_shift(
                AsyncMock(), tenant_id=1, data=create_payload(start_time="09:00", end_time="09:00")
            )


class TestUpdateShift:
    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        repos = _patch_repos()
        repos.shift.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await SchedulingService.update_shift(AsyncMock(), tenant_id=1, shift_id=99, data=ShiftUpdate(name="x"))

    @pytest.mark.asyncio
    async def test_update_to_duplicate_name_raises_validation(self):
        repos = _patch_repos()
        repos.shift.get_by_id = AsyncMock(return_value=shift(1, "早班"))
        repos.shift.get_by_name = AsyncMock(return_value=shift(2, "中班"))

        with pytest.raises(ValidationError):
            await SchedulingService.update_shift(
                AsyncMock(), tenant_id=1, shift_id=1, data=ShiftUpdate(name="中班")
            )

    @pytest.mark.asyncio
    async def test_update_resulting_zero_length_raises_validation(self):
        repos = _patch_repos()
        repos.shift.get_by_id = AsyncMock(return_value=shift(1))  # 09:00-13:00

        with pytest.raises(ValidationError):
            await SchedulingService.update_shift(
                AsyncMock(), tenant_id=1, shift_id=1, data=ShiftUpdate(end_time="09:00")
            )

    @pytest.mark.asyncio
    async def test_disable_shift_keeps_times_valid(self):
        repos = _patch_repos()
        repos.shift.get_by_id = AsyncMock(return_value=shift(1))
        repos.shift.update = AsyncMock(side_effect=lambda db, item, data: item)

        result = await SchedulingService.update_shift(
            AsyncMock(), tenant_id=1, shift_id=1, data=ShiftUpdate(is_enabled=False)
        )

        repos.shift.update.assert_called_once()
        assert repos.shift.update.call_args.args[2] == {"is_enabled": False}
        assert result.is_enabled is True  # in-memory object unchanged by mocked repo

    @pytest.mark.asyncio
    async def test_update_referenced_shift_type_raises_validation(self):
        repos = _patch_repos()
        repos.shift.get_by_id = AsyncMock(return_value=shift(1))
        repos.shift.list_referenced_shift_ids = AsyncMock(return_value={1})

        with pytest.raises(ValidationError, match="type cannot be changed"):
            await SchedulingService.update_shift(
                AsyncMock(), tenant_id=1, shift_id=1, data=ShiftUpdate(shift_type="leave")
            )

    @pytest.mark.asyncio
    async def test_update_unreferenced_work_to_leave_sets_placeholder(self):
        repos = _patch_repos()
        repos.shift.get_by_id = AsyncMock(return_value=shift(1))
        repos.shift.update = AsyncMock(side_effect=lambda db, item, data: item)

        await SchedulingService.update_shift(
            AsyncMock(), tenant_id=1, shift_id=1, data=ShiftUpdate(shift_type="leave")
        )

        payload = repos.shift.update.await_args.args[2]
        assert payload["shift_type"] == "leave"
        assert payload["start_time"] == LEAVE_PLACEHOLDER_START
        assert payload["end_time"] == LEAVE_PLACEHOLDER_END

    @pytest.mark.asyncio
    async def test_update_leave_to_work_requires_times(self):
        repos = _patch_repos()
        leave = shift(1)
        leave.shift_type = "leave"
        leave.start_time = LEAVE_PLACEHOLDER_START
        leave.end_time = LEAVE_PLACEHOLDER_END
        repos.shift.get_by_id = AsyncMock(return_value=leave)

        with pytest.raises(ValidationError, match="required for work shifts"):
            await SchedulingService.update_shift(
                AsyncMock(), tenant_id=1, shift_id=1, data=ShiftUpdate(shift_type="work")
            )


class TestDeleteShift:
    @pytest.mark.asyncio
    async def test_delete_with_assignments_raises_validation(self):
        repos = _patch_repos()
        repos.shift.get_by_id = AsyncMock(return_value=shift(1))
        repos.shift.list_referenced_shift_ids = AsyncMock(return_value={1})

        with pytest.raises(ValidationError):
            await SchedulingService.delete_shift(AsyncMock(), tenant_id=1, shift_id=1)
        repos.shift.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_without_assignments_succeeds(self):
        repos = _patch_repos()
        repos.shift.get_by_id = AsyncMock(return_value=shift(1))
        repos.shift.list_referenced_shift_ids = AsyncMock(return_value=set())

        await SchedulingService.delete_shift(AsyncMock(), tenant_id=1, shift_id=1)
        repos.shift.delete.assert_called_once()


class TestSeedPresetShifts:
    @pytest.mark.asyncio
    async def test_seed_inserts_all_three_for_empty_tenant(self):
        repos = _patch_repos()
        repos.shift.list_by_tenant = AsyncMock(return_value=[])
        db = AsyncMock()
        db.add = MagicMock()

        await seed_preset_shifts(db, tenant_id=1, lang="zh")

        assert db.add.call_count == 3
        names = [call.args[0].name for call in db.add.call_args_list]
        assert names == ["早班", "中班", "晚班"]
        assert all(call.args[0].shift_type == "work" for call in db.add.call_args_list)
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_seed_is_idempotent_for_existing_names(self):
        repos = _patch_repos()
        repos.shift.list_by_tenant = AsyncMock(return_value=[shift(1, "早班")])
        db = AsyncMock()
        db.add = MagicMock()

        await seed_preset_shifts(db, tenant_id=1, lang="zh")

        assert db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_seed_english_names_for_en_language(self):
        repos = _patch_repos()
        repos.shift.list_by_tenant = AsyncMock(return_value=[])
        db = AsyncMock()
        db.add = MagicMock()

        await seed_preset_shifts(db, tenant_id=1, lang="en-US")

        names = [call.args[0].name for call in db.add.call_args_list]
        assert names == ["Morning", "Midday", "Evening"]
