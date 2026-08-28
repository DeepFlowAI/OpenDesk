"""
Unit tests for the rule-based scheduling orchestration: generation
preview/apply and write validation (hard block / soft warn).
"""
from datetime import date, time
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.models.scheduling import ScheduleShift
from app.models.scheduling_rule import ScheduleRuleSet
from app.schemas.scheduling_rule import GenerateRequest
from app.services.scheduling_plan_service import SchedulingPlanService

MON = date(2026, 8, 3)
SUN = date(2026, 8, 9)


def week_band(n: int = 1) -> dict[str, list[int]]:
    days = [n] * 7
    return {"min": list(days), "target": list(days), "max": list(days)}


def make_shift(
    shift_id: int = 1, name: str = "早班", shift_type: str = "work"
) -> ScheduleShift:
    return ScheduleShift(
        id=shift_id,
        tenant_id=1,
        name=name,
        shift_type=shift_type,
        start_time=time(9, 0),
        end_time=time(13, 0),
        color="#4B9CF5",
        sort_order=shift_id,
        is_enabled=True,
    )


def make_rule_set(**overrides) -> ScheduleRuleSet:
    data = {
        "id": 1,
        "tenant_id": 1,
        "name": "标准周",
        "description": None,
        "is_default": True,
        "default_group_ids": [1],
        "targets_enabled": True,
        "targets": {"1": week_band(1)},
        "constraints": {},
        "rotation_templates": [],
    }
    data.update(overrides)
    return ScheduleRuleSet(**data)


def make_request(**overrides) -> GenerateRequest:
    data = {
        "rule_set_id": 1,
        "start_date": MON,
        "end_date": SUN,
        "mode": "fill",
        "use_template": False,
        "on_hard_conflict": "skip",
        "group_ids": [1],
    }
    data.update(overrides)
    return GenerateRequest(**data)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _patch_repos(pool=None, shifts=None, records=None, rule_set=None):
    plan_module = "app.services.scheduling_plan_service"
    rule_repo = patch(f"{plan_module}.ScheduleRuleSetRepository").start()
    shift_repo = patch(f"{plan_module}.ScheduleShiftRepository").start()
    assignment_repo = patch(f"{plan_module}.ScheduleAssignmentRepository").start()
    pool_fn = patch(f"{plan_module}.list_pool_members").start()

    rule_repo.get_by_id = AsyncMock(return_value=rule_set)
    rule_repo.get_default = AsyncMock(return_value=rule_set)
    shift_repo.list_by_tenant = AsyncMock(
        return_value=shifts if shifts is not None else [make_shift()]
    )
    assignment_repo.list_by_date_range = AsyncMock(
        return_value=records if records is not None else []
    )
    assignment_repo.bulk_create = AsyncMock(side_effect=lambda db, rows: len(rows))
    assignment_repo.delete_work_by_employee_dates = AsyncMock(return_value=0)
    pool_fn.side_effect = lambda db, tenant_id, group_ids: (
        pool if pool is not None else [(1, "甲", None), (2, "乙", None)]
    )
    return rule_repo, shift_repo, assignment_repo, pool_fn


class TestPreview:
    @pytest.mark.asyncio
    async def test_preview_returns_counts_without_writing(self):
        _, _, assignment_repo, _ = _patch_repos(rule_set=make_rule_set())
        result = await SchedulingPlanService.preview(AsyncMock(), 1, make_request())
        assert result.to_create == 7
        assert result.to_delete == 0
        assert result.target_met == 7 and result.target_total == 7
        assert result.sample
        assignment_repo.bulk_create.assert_not_called()
        assignment_repo.delete_work_by_employee_dates.assert_not_called()

    @pytest.mark.asyncio
    async def test_preview_rule_set_not_found(self):
        _patch_repos(rule_set=None)
        with pytest.raises(NotFoundError):
            await SchedulingPlanService.preview(AsyncMock(), 1, make_request())


class TestApply:
    @pytest.mark.asyncio
    async def test_apply_fill_writes_rows(self):
        _, _, assignment_repo, _ = _patch_repos(rule_set=make_rule_set())
        result = await SchedulingPlanService.apply(AsyncMock(), 1, make_request())
        assert result.created == 7
        assert result.deleted == 0
        assignment_repo.bulk_create.assert_called_once()
        assignment_repo.delete_work_by_employee_dates.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_clear_deletes_pool_rows_first(self):
        existing = type(
            "Row", (), {"employee_id": 1, "shift_id": 1, "date": MON}
        )()
        _, _, assignment_repo, _ = _patch_repos(
            records=[existing], rule_set=make_rule_set()
        )
        assignment_repo.delete_work_by_employee_dates = AsyncMock(return_value=1)
        result = await SchedulingPlanService.apply(
            AsyncMock(), 1, make_request(mode="clear")
        )
        assert result.deleted == 1
        assignment_repo.delete_work_by_employee_dates.assert_called_once()
        assignment_repo.bulk_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_preserves_leave_and_reports_unavailable_day(self):
        work = make_shift(1)
        leave = make_shift(2, "请假", "leave")
        records = [
            type("Row", (), {"employee_id": 1, "shift_id": 1, "date": MON})(),
            type("Row", (), {"employee_id": 2, "shift_id": 2, "date": MON})(),
        ]
        _, _, assignment_repo, _ = _patch_repos(
            shifts=[work, leave], records=records, rule_set=make_rule_set()
        )
        assignment_repo.delete_work_by_employee_dates = AsyncMock(return_value=1)
        preview = await SchedulingPlanService.preview(
            AsyncMock(), 1, make_request(mode="clear", end_date=MON)
        )
        assert preview.leave_skipped == 1
        result = await SchedulingPlanService.apply(
            AsyncMock(), 1, make_request(mode="clear", end_date=MON)
        )
        assert result.deleted == 1
        args = assignment_repo.delete_work_by_employee_dates.await_args.args
        assert args[3] == [1]


class TestValidateWrite:
    @pytest.mark.asyncio
    async def test_no_default_rule_set_skips_validation(self):
        _patch_repos(rule_set=None)
        # Should simply return without raising.
        await SchedulingPlanService.validate_write(
            AsyncMock(), 1, [1], {(1, 1, MON)}
        )

    @pytest.mark.asyncio
    async def test_hard_violation_raises_409(self):
        rule_set = make_rule_set(
            constraints={
                "max_consecutive_days": {"enabled": True, "level": "hard", "value": 2}
            }
        )
        _patch_repos(rule_set=rule_set)
        candidate = {(1, 1, MON + __import__("datetime").timedelta(days=i)) for i in range(3)}
        with pytest.raises(BusinessError) as exc_info:
            await SchedulingPlanService.validate_write(AsyncMock(), 1, [1], candidate)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "RULE_HARD_VIOLATION"
        assert exc_info.value.details["violations"]

    @pytest.mark.asyncio
    async def test_soft_violation_requires_allow_soft(self):
        rule_set = make_rule_set(
            targets={"1": week_band(1)},
            constraints={"coverage_overflow": {"enabled": True, "level": "soft"}},
        )
        _patch_repos(rule_set=rule_set)
        # Two pool members into a cell with target 1 -> overflow (soft).
        candidate = {(1, 1, MON), (2, 1, MON)}
        with pytest.raises(BusinessError) as exc_info:
            await SchedulingPlanService.validate_write(AsyncMock(), 1, [1], candidate)
        assert exc_info.value.code == "RULE_SOFT_VIOLATION"
        # allow_soft lets the write through.
        await SchedulingPlanService.validate_write(
            AsyncMock(), 1, [1], candidate, allow_soft=True
        )

    @pytest.mark.asyncio
    async def test_unrelated_history_does_not_block(self):
        # A pre-existing hard violation on other dates must not block a
        # candidate that doesn't touch it.
        rule_set = make_rule_set(
            constraints={
                "max_consecutive_days": {"enabled": True, "level": "hard", "value": 2}
            }
        )
        from datetime import timedelta

        records = [
            type("Row", (), {"employee_id": 1, "shift_id": 1, "date": MON - timedelta(days=10 + i)})()
            for i in range(3)
        ]
        _patch_repos(records=records, rule_set=rule_set)
        await SchedulingPlanService.validate_write(
            AsyncMock(), 1, [1], {(1, 1, MON)}
        )


class TestPreviewTargetsDisabled:
    @pytest.mark.asyncio
    async def test_targets_disabled_without_template_raises(self):
        _patch_repos(
            rule_set=make_rule_set(targets_enabled=False, rotation_templates=[])
        )
        with pytest.raises(ValidationError, match="Coverage targets are disabled"):
            await SchedulingPlanService.preview(
                AsyncMock(), 1, make_request(use_template=True)
            )

    @pytest.mark.asyncio
    async def test_targets_disabled_with_template_generates(self):
        rule_set = make_rule_set(
            targets_enabled=False,
            targets={"1": week_band(9)},
            rotation_templates=[
                {
                    "id": "t1",
                    "name": "做一休一",
                    "is_default": True,
                    "days": [
                        {"kind": "shift", "shift_id": 1},
                        {"kind": "off"},
                    ],
                }
            ],
        )
        _patch_repos(rule_set=rule_set)
        result = await SchedulingPlanService.preview(
            AsyncMock(), 1, make_request(use_template=True, mode="clear", end_date=MON)
        )
        assert result.to_create >= 1
        assert result.target_total == 0


class TestListViolations:
    @pytest.mark.asyncio
    async def test_returns_counts_and_items(self):
        rule_set = make_rule_set(
            targets={"1": week_band(2)},
            constraints={"coverage_gap": {"enabled": True, "level": "soft"}},
        )
        _patch_repos(rule_set=rule_set)
        result = await SchedulingPlanService.list_violations(
            AsyncMock(), 1, [1], MON, SUN
        )
        assert result.soft_count == 7
        assert result.hard_count == 0
        assert all(item.constraint == "coverage_gap" for item in result.items)

    @pytest.mark.asyncio
    async def test_no_rule_set_returns_empty(self):
        _patch_repos(rule_set=None)
        result = await SchedulingPlanService.list_violations(
            AsyncMock(), 1, [1], MON, SUN
        )
        assert result.items == [] and result.hard_count == 0


class TestListViolationsRouterContract:
    """Router must pass start=/end= (service param names), not start_date=/end_date=."""

    @pytest.mark.asyncio
    async def test_router_passes_start_and_end_kwargs(self, monkeypatch):
        from types import SimpleNamespace

        from app.routers.v1 import scheduling as scheduling_router
        from app.schemas.scheduling_rule import ViolationListResponse

        seen: dict = {}

        async def fake_list_violations(db, *, tenant_id, group_ids, start, end):
            seen.update(
                tenant_id=tenant_id, group_ids=group_ids, start=start, end=end
            )
            return ViolationListResponse(items=[], hard_count=0, soft_count=0)

        monkeypatch.setattr(
            scheduling_router.SchedulingPlanService,
            "list_violations",
            staticmethod(fake_list_violations),
        )
        result = await scheduling_router.list_violations(
            start_date=MON,
            end_date=SUN,
            group_ids=[1],
            principal=SimpleNamespace(tenant_id=7),
            db=AsyncMock(),
        )
        assert result.hard_count == 0
        assert seen == {
            "tenant_id": 7,
            "group_ids": [1],
            "start": MON,
            "end": SUN,
        }
