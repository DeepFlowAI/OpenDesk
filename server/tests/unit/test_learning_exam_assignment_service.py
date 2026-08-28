"""
Unit tests for the learning exam assignment service: visibility, target CRUD
and the admin learner results table.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessError, NotFoundError
from app.schemas.learning import AssignmentTarget
from app.services.learning_exam_assignment_service import LearningExamAssignmentService

TENANT = 1
MOD = "app.services.learning_exam_assignment_service"


def _exam(**overrides):
    data = {
        "id": 10,
        "tenant_id": TENANT,
        "name": "客服上岗认证",
        "status": "published",
        "visibility": "assigned",
        "pass_percent": 60,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _employee(employee_id, name):
    return SimpleNamespace(id=employee_id, name=name)


@pytest.fixture
def mock_db():
    return AsyncMock()


class TestAssignments:
    @pytest.mark.asyncio
    async def test_update_visibility(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.get_by_id", AsyncMock(return_value=_exam())
        )
        update = AsyncMock(side_effect=lambda db, exam, data: _exam(visibility=data["visibility"]))
        monkeypatch.setattr(f"{MOD}.LearningExamRepository.update", update)

        exam = await LearningExamAssignmentService.update_visibility(
            mock_db, tenant_id=TENANT, exam_id=10, visibility="all"
        )
        assert exam.visibility == "all"

    @pytest.mark.asyncio
    async def test_add_assignments_skips_existing_pairs(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.get_by_id", AsyncMock(return_value=_exam())
        )
        monkeypatch.setattr(
            f"{MOD}.LearningAssignmentRepository.get_groups_by_ids",
            AsyncMock(return_value={5: SimpleNamespace(id=5, name="客服一组")}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningAssignmentRepository.get_employees_by_ids",
            AsyncMock(return_value={7: _employee(7, "小王"), 8: _employee(8, "小李")}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAssignmentRepository.list_existing_pairs",
            AsyncMock(return_value={("employee", 7)}),
        )
        captured = {}

        async def fake_add_many(db, rows):
            captured["rows"] = rows

        monkeypatch.setattr(f"{MOD}.LearningExamAssignmentRepository.add_many", fake_add_many)

        added = await LearningExamAssignmentService.add_assignments(
            mock_db,
            tenant_id=TENANT,
            exam_id=10,
            targets=[
                AssignmentTarget(target_type="employee", target_id=7),
                AssignmentTarget(target_type="employee", target_id=8),
                AssignmentTarget(target_type="group", target_id=5),
            ],
        )
        assert added == 2
        assert {row["target_id"] for row in captured["rows"]} == {8, 5}

    @pytest.mark.asyncio
    async def test_add_assignments_rejects_unknown_target(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.get_by_id", AsyncMock(return_value=_exam())
        )
        monkeypatch.setattr(
            f"{MOD}.LearningAssignmentRepository.get_groups_by_ids", AsyncMock(return_value={})
        )
        monkeypatch.setattr(
            f"{MOD}.LearningAssignmentRepository.get_employees_by_ids", AsyncMock(return_value={})
        )

        with pytest.raises(BusinessError) as exc_info:
            await LearningExamAssignmentService.add_assignments(
                mock_db,
                tenant_id=TENANT,
                exam_id=10,
                targets=[AssignmentTarget(target_type="employee", target_id=999)],
            )
        assert exc_info.value.code == "INVALID_ASSIGNMENT_TARGET"

    @pytest.mark.asyncio
    async def test_remove_assignment_from_other_exam_404(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.get_by_id", AsyncMock(return_value=_exam())
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAssignmentRepository.get_by_id",
            AsyncMock(return_value=SimpleNamespace(id=1, exam_id=99)),
        )

        with pytest.raises(NotFoundError):
            await LearningExamAssignmentService.remove_assignment(
                mock_db, tenant_id=TENANT, exam_id=10, assignment_id=1
            )


class TestResultsTable:
    @pytest.mark.asyncio
    async def test_all_visibility_uses_active_employees_with_status(self, mock_db, monkeypatch):
        exam = _exam(visibility="all", pass_percent=60)
        monkeypatch.setattr(f"{MOD}.LearningExamRepository.get_by_id", AsyncMock(return_value=exam))
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 2, "total_score": 100}}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningAssignmentRepository.list_active_employees",
            AsyncMock(return_value=[_employee(1, "通过者"), _employee(2, "落榜者"), _employee(3, "新人")]),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.aggregate_by_exam",
            AsyncMock(
                return_value={
                    1: {"submitted_count": 2, "best_score": 80, "last_submitted_at": "t"},
                    2: {"submitted_count": 1, "best_score": 59, "last_submitted_at": "t"},
                }
            ),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningAssignmentRepository.list_group_names_by_employees",
            AsyncMock(return_value={}),
        )

        result = await LearningExamAssignmentService.list_results(
            mock_db, tenant_id=TENANT, exam_id=10, q=None, page=1, per_page=20
        )
        statuses = {item["name"]: item["status"] for item in result["items"]}
        assert statuses == {"通过者": "passed", "落榜者": "failed", "新人": "not_started"}
        assert result["total"] == 3
        by_name = {item["name"]: item for item in result["items"]}
        assert by_name["通过者"]["best_score"] == 80
        assert by_name["新人"]["best_score"] is None
        assert by_name["落榜者"]["submitted_count"] == 1

    @pytest.mark.asyncio
    async def test_assigned_visibility_filters_by_visible_set(self, mock_db, monkeypatch):
        exam = _exam(visibility="assigned")
        monkeypatch.setattr(f"{MOD}.LearningExamRepository.get_by_id", AsyncMock(return_value=exam))
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 1, "total_score": 10}}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAssignmentRepository.list_visible_employee_ids",
            AsyncMock(return_value={1}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningAssignmentRepository.get_employees_by_ids",
            AsyncMock(return_value={1: _employee(1, "可见员工")}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAssignmentRepository.list_existing_pairs",
            AsyncMock(return_value={("employee", 1)}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAssignmentRepository.list_by_exam", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.aggregate_by_exam", AsyncMock(return_value={})
        )
        monkeypatch.setattr(
            f"{MOD}.LearningAssignmentRepository.list_group_names_by_employees",
            AsyncMock(return_value={}),
        )

        result = await LearningExamAssignmentService.list_results(
            mock_db, tenant_id=TENANT, exam_id=10, q=None, page=1, per_page=20
        )
        assert [item["name"] for item in result["items"]] == ["可见员工"]
        assert result["items"][0]["direct_assigned"] is True
