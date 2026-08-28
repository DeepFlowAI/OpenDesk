"""
Unit tests for learning center exam admin services: exam lifecycle, question
validation/reorder rules and list aggregation (score/learner counts).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.schemas.learning_exam import (
    ExamQuestionOption,
    LearningExamCreate,
    LearningExamQuestionCreate,
    LearningExamQuestionUpdate,
    LearningExamUpdate,
)
from app.services.learning_exam_admin_service import (
    LearningExamAdminService,
    LearningExamQuestionAdminService,
    pass_score_of,
)

TENANT = 1


def _exam(**overrides):
    data = {
        "id": 10,
        "tenant_id": TENANT,
        "name": "客服上岗认证",
        "intro": None,
        "status": "draft",
        "visibility": "assigned",
        "time_limit_minutes": None,
        "pass_percent": 60,
        "max_attempts": 0,
        "shuffle_questions": False,
        "created_by": 7,
        "created_at": None,
        "updated_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _question(**overrides):
    data = {
        "id": 20,
        "tenant_id": TENANT,
        "exam_id": 10,
        "type": "single",
        "stem": "服务敬语包括？",
        "score": 10,
        "options": [
            {"key": "a", "text": "您好", "is_correct": True},
            {"key": "b", "text": "喂", "is_correct": False},
        ],
        "sort_order": 0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _options(*specs):
    return [ExamQuestionOption(key=key, text=text, is_correct=ok) for key, text, ok in specs]


@pytest.fixture
def mock_db():
    return AsyncMock()


class TestExamLifecycle:
    @pytest.mark.asyncio
    async def test_create_exam_defaults_to_untitled(self, mock_db, monkeypatch):
        captured = {}

        async def fake_create(db, data):
            captured.update(data)
            return _exam(name=data["name"])

        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.create", fake_create
        )

        exam = await LearningExamAdminService.create_exam(
            mock_db, tenant_id=TENANT, employee_id=7, data=LearningExamCreate()
        )
        assert captured["tenant_id"] == TENANT
        assert captured["created_by"] == 7
        assert exam.name == "未命名考试"

    @pytest.mark.asyncio
    async def test_publish_without_questions_raises_not_ready(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 0, "total_score": 0}}),
        )

        with pytest.raises(BusinessError) as exc_info:
            await LearningExamAdminService.publish_exam(mock_db, tenant_id=TENANT, exam_id=10)
        assert exc_info.value.code == "EXAM_NOT_READY"

    @pytest.mark.asyncio
    async def test_publish_with_questions_marks_published(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 2, "total_score": 20}}),
        )
        update = AsyncMock(side_effect=lambda db, exam, data: _exam(status=data["status"]))
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.update", update
        )

        exam = await LearningExamAdminService.publish_exam(mock_db, tenant_id=TENANT, exam_id=10)
        assert exam.status == "published"

    @pytest.mark.asyncio
    async def test_delete_published_exam_rejected(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam(status="published")),
        )

        with pytest.raises(BusinessError) as exc_info:
            await LearningExamAdminService.delete_exam(mock_db, tenant_id=TENANT, exam_id=10)
        assert exc_info.value.code == "EXAM_NOT_DELETABLE"

    @pytest.mark.asyncio
    async def test_delete_draft_exam_calls_repository(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )
        delete = AsyncMock()
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.delete", delete
        )

        await LearningExamAdminService.delete_exam(mock_db, tenant_id=TENANT, exam_id=10)
        delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_exam_not_found_raises(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=None),
        )

        with pytest.raises(NotFoundError):
            await LearningExamAdminService.update_exam(
                mock_db, tenant_id=TENANT, exam_id=999, data=LearningExamUpdate(name="x")
            )

    @pytest.mark.asyncio
    async def test_update_exam_clears_time_limit_and_ignores_null_name(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam(time_limit_minutes=30)),
        )
        captured = {}

        async def fake_update(db, exam, data):
            captured.update(data)
            return exam

        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.update", fake_update
        )

        # model_construct marks passed keys as "set" so exclude_unset keeps
        # the explicit nulls (name=None must be ignored, time_limit=None clears).
        payload = LearningExamUpdate.model_construct(name=None, time_limit_minutes=None)
        await LearningExamAdminService.update_exam(
            mock_db, tenant_id=TENANT, exam_id=10, data=payload
        )
        assert "name" not in captured
        assert captured["time_limit_minutes"] is None


class TestListAggregation:
    @pytest.mark.asyncio
    async def test_all_visibility_renders_null_learner_count(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.list_paginated",
            AsyncMock(return_value=([_exam(visibility="all")], 1)),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 3, "total_score": 95}}),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamAttemptRepository.count_passed_employees_by_exam",
            AsyncMock(return_value={10: 4}),
        )

        result = await LearningExamAdminService.list_exams(
            mock_db, tenant_id=TENANT, page=1, per_page=20, q=None, status=None
        )
        item = result["items"][0]
        assert item["learner_count"] is None
        assert item["question_count"] == 3
        assert item["total_score"] == 95
        # floor(95 * 60 / 100) = 57
        assert item["pass_score"] == 57
        assert item["passed_count"] == 4

    @pytest.mark.asyncio
    async def test_assigned_visibility_counts_visible_employees(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.list_paginated",
            AsyncMock(return_value=([_exam(visibility="assigned")], 1)),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 1, "total_score": 10}}),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamAssignmentRepository.list_visible_employee_ids",
            AsyncMock(return_value={1, 2, 3}),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamAttemptRepository.count_passed_employees_by_exam",
            AsyncMock(return_value={}),
        )

        result = await LearningExamAdminService.list_exams(
            mock_db, tenant_id=TENANT, page=1, per_page=20, q=None, status=None
        )
        assert result["items"][0]["learner_count"] == 3

    def test_pass_score_uses_floor(self):
        assert pass_score_of(100, 60) == 60
        assert pass_score_of(95, 60) == 57
        assert pass_score_of(33, 60) == 19
        assert pass_score_of(0, 80) == 0


class TestQuestionManagement:
    @pytest.mark.asyncio
    async def test_create_single_requires_exactly_one_correct(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )

        with pytest.raises(ValidationError):
            await LearningExamQuestionAdminService.create_question(
                mock_db,
                tenant_id=TENANT,
                exam_id=10,
                data=LearningExamQuestionCreate(
                    type="single",
                    stem="题干",
                    score=10,
                    options=_options(("a", "甲", False), ("b", "乙", False)),
                ),
            )

    @pytest.mark.asyncio
    async def test_create_multiple_requires_at_least_two_correct(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )

        with pytest.raises(ValidationError):
            await LearningExamQuestionAdminService.create_question(
                mock_db,
                tenant_id=TENANT,
                exam_id=10,
                data=LearningExamQuestionCreate(
                    type="multiple",
                    stem="题干",
                    score=10,
                    options=_options(("a", "甲", True), ("b", "乙", False)),
                ),
            )

    @pytest.mark.asyncio
    async def test_create_judge_normalizes_options(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamQuestionRepository.next_sort_order",
            AsyncMock(return_value=1),
        )
        captured = {}

        async def fake_create(db, data):
            captured.update(data)
            return _question(**{k: v for k, v in data.items() if k in _question().__dict__})

        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamQuestionRepository.create", fake_create
        )

        await LearningExamQuestionAdminService.create_question(
            mock_db,
            tenant_id=TENANT,
            exam_id=10,
            data=LearningExamQuestionCreate(
                type="judge",
                stem="判断题",
                score=5,
                options=_options(("true", "对", True), ("false", "错", False)),
            ),
        )
        assert captured["options"] == [
            {"key": "true", "text": None, "is_correct": True},
            {"key": "false", "text": None, "is_correct": False},
        ]
        assert captured["sort_order"] == 1

    @pytest.mark.asyncio
    async def test_create_judge_rejects_arbitrary_keys(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )

        with pytest.raises(ValidationError):
            await LearningExamQuestionAdminService.create_question(
                mock_db,
                tenant_id=TENANT,
                exam_id=10,
                data=LearningExamQuestionCreate(
                    type="judge",
                    stem="判断题",
                    score=5,
                    options=_options(("a", "对", True), ("b", "错", False)),
                ),
            )

    @pytest.mark.asyncio
    async def test_create_rejects_blank_option_text(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )

        with pytest.raises(ValidationError):
            await LearningExamQuestionAdminService.create_question(
                mock_db,
                tenant_id=TENANT,
                exam_id=10,
                data=LearningExamQuestionCreate(
                    type="single",
                    stem="题干",
                    score=10,
                    options=_options(("a", "   ", True), ("b", "乙", False)),
                ),
            )

    @pytest.mark.asyncio
    async def test_update_question_revalidates_merged_options(self, mock_db, monkeypatch):
        existing = _question(
            options=[
                {"key": "a", "text": "甲", "is_correct": True},
                {"key": "b", "text": "乙", "is_correct": False},
            ]
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamQuestionRepository.get_by_id",
            AsyncMock(return_value=existing),
        )

        # Switching the stored single-choice question to multiple without
        # adding a second correct option must fail validation.
        with pytest.raises(ValidationError):
            await LearningExamQuestionAdminService.update_question(
                mock_db,
                tenant_id=TENANT,
                question_id=20,
                data=LearningExamQuestionUpdate(type="multiple"),
            )

    @pytest.mark.asyncio
    async def test_reorder_rejects_mismatched_ids(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam()),
        )
        monkeypatch.setattr(
            "app.services.learning_exam_admin_service.LearningExamQuestionRepository.list_by_exam",
            AsyncMock(return_value=[_question(id=1), _question(id=2)]),
        )

        with pytest.raises(ValidationError):
            await LearningExamQuestionAdminService.reorder_questions(
                mock_db, tenant_id=TENANT, exam_id=10, ordered_ids=[2, 3]
            )
