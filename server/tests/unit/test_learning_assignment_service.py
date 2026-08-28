"""Unit tests for the learning assignment service (visibility, assignment CRUD,
assignable pickers and the learner progress table)."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import BusinessError, NotFoundError
from app.services.learning_assignment_service import (
    LearningAssignmentService,
    _progress_and_status,
)

TENANT_ID = 1
COURSE_ID = 10


def _course(visibility: str = "assigned", status: str = "draft"):
    return SimpleNamespace(id=COURSE_ID, tenant_id=TENANT_ID, visibility=visibility, status=status, name="课程")


def _employee(employee_id: int, name: str = "员工"):
    return SimpleNamespace(id=employee_id, tenant_id=TENANT_ID, name=name, is_active=True)


def _group(group_id: int, name: str = "客服组"):
    return SimpleNamespace(id=group_id, tenant_id=TENANT_ID, name=name)


class TestUpdateVisibility:
    async def test_switches_visibility(self):
        course = _course(visibility="assigned")
        with (
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
                new=AsyncMock(return_value=course),
            ),
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.update",
                new=AsyncMock(side_effect=lambda db, c, data: SimpleNamespace(**{**vars(c), **data})),
            ) as update_mock,
        ):
            result = await LearningAssignmentService.update_visibility(
                AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, visibility="all"
            )
        update_mock.assert_awaited_once()
        assert result.visibility == "all"

    async def test_missing_course_raises_404(self):
        with patch(
            "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await LearningAssignmentService.update_visibility(
                    AsyncMock(), tenant_id=TENANT_ID, course_id=999, visibility="all"
                )


class TestAddAssignments:
    async def test_invalid_target_raises(self):
        target = SimpleNamespace(target_type="employee", target_id=42)
        with (
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
                new=AsyncMock(return_value=_course()),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.get_groups_by_ids",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.get_employees_by_ids",
                new=AsyncMock(return_value={}),
            ),
        ):
            with pytest.raises(BusinessError) as exc:
                await LearningAssignmentService.add_assignments(
                    AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, targets=[target]
                )
        assert exc.value.code == "INVALID_ASSIGNMENT_TARGET"

    async def test_duplicates_are_skipped(self):
        targets = [
            SimpleNamespace(target_type="employee", target_id=1),
            SimpleNamespace(target_type="employee", target_id=2),
            SimpleNamespace(target_type="group", target_id=7),
        ]
        with (
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
                new=AsyncMock(return_value=_course()),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.get_groups_by_ids",
                new=AsyncMock(return_value={7: _group(7)}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.get_employees_by_ids",
                new=AsyncMock(return_value={1: _employee(1), 2: _employee(2)}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_existing_pairs",
                new=AsyncMock(return_value={("employee", 1)}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.add_many",
                new=AsyncMock(),
            ) as add_mock,
        ):
            added = await LearningAssignmentService.add_assignments(
                AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, targets=targets
            )
        assert added == 2
        rows = add_mock.await_args.args[1]
        assert {(row["target_type"], row["target_id"]) for row in rows} == {
            ("employee", 2),
            ("group", 7),
        }


class TestRemoveAssignment:
    async def test_assignment_of_other_course_rejected(self):
        assignment = SimpleNamespace(id=5, tenant_id=TENANT_ID, course_id=999)
        with (
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
                new=AsyncMock(return_value=_course()),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.get_by_id",
                new=AsyncMock(return_value=assignment),
            ),
        ):
            with pytest.raises(NotFoundError):
                await LearningAssignmentService.remove_assignment(
                    AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, assignment_id=5
                )


class TestAssignableEmployees:
    async def test_assigned_and_covered_flags(self):
        employees = [_employee(1, "直属"), _employee(2, "组覆盖"), _employee(3, "可选")]
        with (
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
                new=AsyncMock(return_value=_course()),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_active_employees",
                new=AsyncMock(return_value=employees),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_existing_pairs",
                new=AsyncMock(return_value={("employee", 1)}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_visible_employee_ids",
                new=AsyncMock(return_value={1, 2}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_group_names_by_employees",
                new=AsyncMock(return_value={1: ["A组"], 2: ["A组"]}),
            ),
        ):
            result = await LearningAssignmentService.list_assignable_employees(
                AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, q=None, page=1, per_page=20
            )
        items = {item["id"]: item for item in result["items"]}
        assert items[1]["assigned"] is True and items[1]["covered"] is False
        assert items[2]["assigned"] is False and items[2]["covered"] is True
        assert items[3]["assigned"] is False and items[3]["covered"] is False
        assert items[1]["group_names"] == ["A组"]


class TestListLearners:
    async def test_assigned_course_merges_direct_and_group_members(self):
        employees = {1: _employee(1, "直属"), 2: _employee(2, "组内"), 3: _employee(3, "双来源")}
        with (
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
                new=AsyncMock(return_value=_course(visibility="assigned")),
            ),
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.count_materials_by_course",
                new=AsyncMock(return_value={COURSE_ID: 2}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_visible_employee_ids",
                new=AsyncMock(return_value={1, 2, 3}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.get_employees_by_ids",
                new=AsyncMock(return_value=employees),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_existing_pairs",
                new=AsyncMock(return_value={("employee", 1), ("employee", 3), ("group", 7)}),
            ),
            patch(
                "app.services.learning_assignment_service._assigned_group_names_by_employee",
                new=AsyncMock(return_value={2: ["客服组"], 3: ["客服组"]}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningRecordRepository.aggregate_by_course",
                new=AsyncMock(
                    return_value={
                        1: {"total_records": 1, "completed": 1, "last_learn_at": datetime(2026, 8, 1, tzinfo=timezone.utc)},
                        3: {"total_records": 2, "completed": 2, "last_learn_at": None},
                    }
                ),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_group_names_by_employees",
                new=AsyncMock(return_value={2: ["客服组"], 3: ["客服组"]}),
            ),
        ):
            result = await LearningAssignmentService.list_learners(
                AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, q=None, page=1, per_page=20
            )
        items = {item["employee_id"]: item for item in result["items"]}
        assert result["total"] == 3
        assert items[1]["direct_assigned"] is True and items[1]["assigned_group_names"] == []
        assert items[2]["direct_assigned"] is False and items[2]["assigned_group_names"] == ["客服组"]
        assert items[3]["direct_assigned"] is True and items[3]["assigned_group_names"] == ["客服组"]
        # 1/2 materials completed -> 50% in progress; 2/2 -> completed.
        assert items[1]["progress"] == 50 and items[1]["status"] == "in_progress"
        assert items[3]["progress"] == 100 and items[3]["status"] == "completed"

    async def test_all_visibility_lists_every_active_employee(self):
        employees = [_employee(1, "甲"), _employee(2, "乙")]
        with (
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
                new=AsyncMock(return_value=_course(visibility="all")),
            ),
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.count_materials_by_course",
                new=AsyncMock(return_value={COURSE_ID: 4}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_active_employees",
                new=AsyncMock(return_value=employees),
            ),
            patch(
                "app.services.learning_assignment_service.LearningRecordRepository.aggregate_by_course",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_group_names_by_employees",
                new=AsyncMock(return_value={}),
            ),
        ):
            result = await LearningAssignmentService.list_learners(
                AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, q=None, page=1, per_page=20
            )
        assert result["total"] == 2
        assert all(item["status"] == "not_started" and item["progress"] == 0 for item in result["items"])
        assert all(item["direct_assigned"] is False for item in result["items"])

    async def test_search_filters_by_name(self):
        employees = {1: _employee(1, "张三"), 2: _employee(2, "李四")}
        with (
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.get_by_id",
                new=AsyncMock(return_value=_course()),
            ),
            patch(
                "app.services.learning_assignment_service.LearningCourseRepository.count_materials_by_course",
                new=AsyncMock(return_value={COURSE_ID: 1}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_visible_employee_ids",
                new=AsyncMock(return_value={1, 2}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.get_employees_by_ids",
                new=AsyncMock(return_value=employees),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_existing_pairs",
                new=AsyncMock(return_value=set()),
            ),
            patch(
                "app.services.learning_assignment_service._assigned_group_names_by_employee",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningRecordRepository.aggregate_by_course",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.learning_assignment_service.LearningAssignmentRepository.list_group_names_by_employees",
                new=AsyncMock(return_value={}),
            ),
        ):
            result = await LearningAssignmentService.list_learners(
                AsyncMock(), tenant_id=TENANT_ID, course_id=COURSE_ID, q="张", page=1, per_page=20
            )
        assert result["total"] == 1
        assert result["items"][0]["name"] == "张三"


class TestProgressRule:
    def test_zero_materials_is_not_started(self):
        assert _progress_and_status(0, 0, 0) == (0, "not_started")

    def test_no_records_is_not_started(self):
        assert _progress_and_status(0, 0, 3) == (0, "not_started")

    def test_partial_is_in_progress(self):
        assert _progress_and_status(1, 1, 2) == (50, "in_progress")

    def test_full_completion(self):
        assert _progress_and_status(2, 2, 2) == (100, "completed")
