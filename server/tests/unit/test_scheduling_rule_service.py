"""
Unit tests for scheduling rule set service: CRUD validation, copy naming,
and tenant-default management.
"""
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import NotFoundError, ValidationError
from app.models.scheduling import ScheduleShift
from app.models.scheduling_rule import ScheduleRuleSet
from app.schemas.scheduling_rule import (
    RuleSetCreate,
    RuleSetResponse,
    RuleSetUpdate,
    normalize_targets,
)
from app.services.scheduling_rule_service import SchedulingRuleService


def week_band(days: list[int]) -> dict[str, list[int]]:
    return {"min": list(days), "target": list(days), "max": list(days)}


def make_shift(
    shift_id: int = 1, shift_type: str = "work", enabled: bool = True
) -> ScheduleShift:
    return ScheduleShift(
        id=shift_id,
        tenant_id=1,
        name="早班",
        shift_type=shift_type,
        start_time="09:00",
        end_time="13:00",
        color="#4B9CF5",
        sort_order=1,
        is_enabled=enabled,
    )


def make_rule_set(rule_set_id: int = 1, name: str = "标准周", is_default: bool = False) -> ScheduleRuleSet:
    return ScheduleRuleSet(
        id=rule_set_id,
        tenant_id=1,
        name=name,
        description=None,
        is_default=is_default,
        default_group_ids=[1],
        targets_enabled=True,
        targets={"1": week_band([4, 4, 4, 4, 4, 2, 2])},
        constraints={"max_consecutive_days": {"enabled": True, "level": "hard", "value": 6}},
        rotation_templates=[],
    )


def create_payload(**overrides) -> RuleSetCreate:
    data = {
        "name": "在线客服标准周",
        "default_group_ids": [1, 2],
        "targets_enabled": True,
        "targets": {"1": week_band([4, 4, 4, 4, 4, 2, 2])},
        "constraints": {
            "max_consecutive_days": {"enabled": True, "level": "hard", "value": 6},
            "coverage_gap": {"enabled": True, "level": "soft"},
        },
        "rotation_templates": [
            {
                "id": "t1",
                "name": "上三休二",
                "is_default": True,
                "days": [
                    {"kind": "shift", "shift_id": 1},
                    {"kind": "shift", "shift_id": 1},
                    {"kind": "off"},
                ],
            }
        ],
    }
    data.update(overrides)
    return RuleSetCreate(**data)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _patch_repos():
    rule_repo = patch("app.services.scheduling_rule_service.ScheduleRuleSetRepository").start()
    shift_repo = patch("app.services.scheduling_rule_service.ScheduleShiftRepository").start()
    for name in (
        "list_by_tenant", "get_by_id", "get_by_name", "get_default",
        "count_by_tenant", "create", "update", "delete", "clear_default",
    ):
        setattr(rule_repo, name, AsyncMock())
    shift_repo.list_by_tenant = AsyncMock(return_value=[make_shift(1)])
    return SimpleNamespace(rule=rule_repo, shift=shift_repo)


class TestSchemaValidation:
    def test_constraint_value_out_of_range_rejected(self):
        with pytest.raises(PydanticValidationError):
            create_payload(
                constraints={"max_consecutive_days": {"enabled": True, "level": "hard", "value": 40}}
            )

    def test_coverage_gap_with_level_hard_rejected(self):
        with pytest.raises(PydanticValidationError):
            create_payload(
                constraints={"coverage_gap": {"enabled": True, "level": "hard"}}
            )

    def test_unknown_constraint_key_rejected(self):
        with pytest.raises(PydanticValidationError):
            create_payload(constraints={"unknown_key": {"enabled": True, "level": "soft"}})

    def test_targets_requires_seven_days(self):
        with pytest.raises(PydanticValidationError):
            create_payload(targets={"1": week_band([4, 4, 4])})

    def test_targets_reject_legacy_array_on_write(self):
        with pytest.raises(PydanticValidationError):
            create_payload(targets={"1": [4, 4, 4, 4, 4, 2, 2]})

    def test_targets_reject_min_above_target(self):
        with pytest.raises(PydanticValidationError):
            create_payload(
                targets={
                    "1": {
                        "min": [3] * 7,
                        "target": [2] * 7,
                        "max": [4] * 7,
                    }
                }
            )

    def test_normalize_legacy_targets_on_read(self):
        assert normalize_targets({"1": [1, 2, 3, 4, 5, 6, 7]}) == {
            "1": week_band([1, 2, 3, 4, 5, 6, 7])
        }
        resp = RuleSetResponse(
            id=1,
            name="x",
            is_default=False,
            default_group_ids=[],
            targets_enabled=True,
            targets={"1": [1] * 7},
            constraints={},
            rotation_templates=[],
        )
        assert resp.targets["1"]["max"] == [1] * 7

    def test_rotation_template_requires_two_days(self):
        with pytest.raises(PydanticValidationError):
            create_payload(
                rotation_templates=[{"id": "t1", "name": "x", "days": [{"kind": "off"}]}]
            )

    def test_rotation_template_shift_day_requires_shift_id(self):
        with pytest.raises(PydanticValidationError):
            create_payload(
                rotation_templates=[
                    {"id": "t1", "name": "x", "days": [{"kind": "shift"}, {"kind": "off"}]}
                ]
            )

    def test_rotation_template_single_default(self):
        with pytest.raises(PydanticValidationError):
            create_payload(
                rotation_templates=[
                    {"id": "t1", "name": "a", "is_default": True, "days": [{"kind": "off"}, {"kind": "off"}]},
                    {"id": "t2", "name": "b", "is_default": True, "days": [{"kind": "off"}, {"kind": "off"}]},
                ]
            )


class TestCreateRuleSet:
    @pytest.mark.asyncio
    async def test_create_first_rule_set_becomes_default(self):
        repos = _patch_repos()
        repos.rule.get_by_name = AsyncMock(return_value=None)
        repos.rule.count_by_tenant = AsyncMock(return_value=0)
        repos.rule.create = AsyncMock(side_effect=lambda db, data: ScheduleRuleSet(id=1, **data))

        result = await SchedulingRuleService.create_rule_set(AsyncMock(), tenant_id=1, data=create_payload())

        payload = repos.rule.create.call_args.args[1]
        assert payload["is_default"] is True
        assert payload["tenant_id"] == 1
        assert result.id == 1

    @pytest.mark.asyncio
    async def test_create_non_first_keeps_requested_default_flag(self):
        repos = _patch_repos()
        repos.rule.get_by_name = AsyncMock(return_value=None)
        repos.rule.count_by_tenant = AsyncMock(return_value=2)
        repos.rule.create = AsyncMock(side_effect=lambda db, data: ScheduleRuleSet(id=2, **data))

        await SchedulingRuleService.create_rule_set(AsyncMock(), tenant_id=1, data=create_payload())

        payload = repos.rule.create.call_args.args[1]
        assert payload["is_default"] is False
        repos.rule.clear_default.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_with_duplicate_name_raises_validation(self):
        repos = _patch_repos()
        repos.rule.get_by_name = AsyncMock(return_value=make_rule_set())

        with pytest.raises(ValidationError):
            await SchedulingRuleService.create_rule_set(AsyncMock(), tenant_id=1, data=create_payload())
        repos.rule.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_filters_unknown_shift_refs(self):
        repos = _patch_repos()
        repos.rule.get_by_name = AsyncMock(return_value=None)
        repos.rule.count_by_tenant = AsyncMock(return_value=0)
        repos.rule.create = AsyncMock(side_effect=lambda db, data: ScheduleRuleSet(id=1, **data))

        await SchedulingRuleService.create_rule_set(
            AsyncMock(),
            tenant_id=1,
            data=create_payload(
                targets={"1": week_band([1] * 7), "99": week_band([2] * 7)}
            ),
        )

        payload = repos.rule.create.call_args.args[1]
        assert set(payload["targets"].keys()) == {"1"}

    @pytest.mark.asyncio
    async def test_create_filters_leave_and_disabled_shift_refs(self):
        repos = _patch_repos()
        repos.shift.list_by_tenant = AsyncMock(
            return_value=[
                make_shift(1),
                make_shift(2, shift_type="leave"),
                make_shift(3, enabled=False),
            ]
        )
        repos.rule.get_by_name = AsyncMock(return_value=None)
        repos.rule.count_by_tenant = AsyncMock(return_value=0)
        repos.rule.create = AsyncMock(
            side_effect=lambda db, data: ScheduleRuleSet(id=1, **data)
        )

        await SchedulingRuleService.create_rule_set(
            AsyncMock(),
            tenant_id=1,
            data=create_payload(
                targets={
                    "1": week_band([1] * 7),
                    "2": week_band([1] * 7),
                    "3": week_band([1] * 7),
                },
                rotation_templates=[
                    {
                        "id": "t1",
                        "name": "过滤假期",
                        "days": [
                            {"kind": "shift", "shift_id": 1},
                            {"kind": "shift", "shift_id": 2},
                            {"kind": "off"},
                        ],
                    }
                ],
            ),
        )

        payload = repos.rule.create.call_args.args[1]
        assert set(payload["targets"]) == {"1"}
        assert payload["rotation_templates"][0]["days"] == [
            {"kind": "shift", "shift_id": 1},
            {"kind": "off", "shift_id": None},
        ]


class TestUpdateRuleSet:
    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        repos = _patch_repos()
        repos.rule.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await SchedulingRuleService.update_rule_set(
                AsyncMock(), tenant_id=1, rule_set_id=99, data=RuleSetUpdate(name="x")
            )

    @pytest.mark.asyncio
    async def test_update_with_duplicate_name_excludes_self(self):
        repos = _patch_repos()
        repos.rule.get_by_id = AsyncMock(return_value=make_rule_set(1))
        repos.rule.get_by_name = AsyncMock(return_value=make_rule_set(2, name="其他"))

        with pytest.raises(ValidationError):
            await SchedulingRuleService.update_rule_set(
                AsyncMock(), tenant_id=1, rule_set_id=1, data=RuleSetUpdate(name="其他")
            )
        # name uniqueness check must exclude the rule set being updated
        assert repos.rule.get_by_name.call_args.kwargs["exclude_id"] == 1


class TestDeleteRuleSet:
    @pytest.mark.asyncio
    async def test_delete_default_with_others_raises_validation(self):
        repos = _patch_repos()
        repos.rule.get_by_id = AsyncMock(return_value=make_rule_set(1, is_default=True))
        repos.rule.count_by_tenant = AsyncMock(return_value=2)

        with pytest.raises(ValidationError):
            await SchedulingRuleService.delete_rule_set(AsyncMock(), tenant_id=1, rule_set_id=1)
        repos.rule.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_only_default_rule_set_allowed(self):
        repos = _patch_repos()
        rule_set = make_rule_set(1, is_default=True)
        repos.rule.get_by_id = AsyncMock(return_value=rule_set)
        repos.rule.count_by_tenant = AsyncMock(return_value=1)

        await SchedulingRuleService.delete_rule_set(AsyncMock(), tenant_id=1, rule_set_id=1)

        repos.rule.delete.assert_called_once_with(ANY, rule_set)


class TestCopyRuleSet:
    @pytest.mark.asyncio
    async def test_copy_names_duplicate_with_suffix(self):
        repos = _patch_repos()
        source = make_rule_set(1, name="标准周")
        repos.rule.get_by_id = AsyncMock(return_value=source)
        repos.rule.get_by_name = AsyncMock(side_effect=[make_rule_set(2, "标准周 副本"), None])
        repos.rule.create = AsyncMock(side_effect=lambda db, data: ScheduleRuleSet(id=3, **data))

        result = await SchedulingRuleService.copy_rule_set(AsyncMock(), tenant_id=1, rule_set_id=1)

        payload = repos.rule.create.call_args.args[1]
        assert payload["name"] == "标准周 副本2"
        assert payload["is_default"] is False
        assert result.id == 3


class TestSetDefault:
    @pytest.mark.asyncio
    async def test_set_default_clears_others(self):
        repos = _patch_repos()
        rule_set = make_rule_set(1, is_default=False)
        repos.rule.get_by_id = AsyncMock(return_value=rule_set)
        repos.rule.update = AsyncMock(side_effect=lambda db, rs, data: ScheduleRuleSet(
            id=rs.id, tenant_id=1, name=rs.name, description=None,
            is_default=data.get("is_default", rs.is_default),
            default_group_ids=[], targets_enabled=True, targets={},
            constraints={}, rotation_templates=[],
        ))

        result = await SchedulingRuleService.set_default(AsyncMock(), tenant_id=1, rule_set_id=1)

        repos.rule.clear_default.assert_called_once()
        assert repos.rule.clear_default.call_args.kwargs["exclude_id"] == 1
        assert result.is_default is True
