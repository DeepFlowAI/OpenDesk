"""
Unit tests for the employee-side exam service: my exams, attempt lifecycle
(start/take/submit/abandon) and auto grading rules.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessError, NotFoundError
from app.services.learning_exam_my_service import LearningExamMyService

TENANT = 1
EMPLOYEE = 7
MOD = "app.services.learning_exam_my_service"

SNAPSHOT = [
    {
        "question_id": 101,
        "type": "single",
        "stem": "服务敬语包括？",
        "score": 10,
        "options": [
            {"key": "a", "text": "您好", "is_correct": True},
            {"key": "b", "text": "喂", "is_correct": False},
        ],
    },
    {
        "question_id": 102,
        "type": "multiple",
        "stem": "以下哪些属于禁忌？",
        "score": 20,
        "options": [
            {"key": "a", "text": "抢话", "is_correct": True},
            {"key": "b", "text": "辱骂", "is_correct": True},
            {"key": "c", "text": "复述需求", "is_correct": False},
        ],
    },
    {
        "question_id": 103,
        "type": "judge",
        "stem": "通话结束应先致谢。",
        "score": 5,
        "options": [
            {"key": "true", "text": None, "is_correct": True},
            {"key": "false", "text": None, "is_correct": False},
        ],
    },
]


def _exam(**overrides):
    data = {
        "id": 10,
        "tenant_id": TENANT,
        "name": "客服上岗认证",
        "intro": " intro ",
        "status": "published",
        "visibility": "all",
        "pass_percent": 60,
        "time_limit_minutes": 30,
        "max_attempts": 2,
        "shuffle_questions": False,
        "updated_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _question(question_id, score, options, qtype="single"):
    return SimpleNamespace(
        id=question_id, exam_id=10, type=qtype, stem=f"题干{question_id}", score=score, options=options
    )


def _attempt(**overrides):
    data = {
        "id": 50,
        "tenant_id": TENANT,
        "exam_id": 10,
        "employee_id": EMPLOYEE,
        "status": "in_progress",
        "attempt_index": None,
        "snapshot": [dict(entry, options=[dict(opt) for opt in entry["options"]]) for entry in SNAPSHOT],
        "answers": {},
        "score": None,
        "passed": None,
        "started_at": datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
        "submitted_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _submitted(index, score, passed=True):
    return _attempt(
        id=50 + index,
        status="submitted",
        attempt_index=index,
        score=score,
        passed=passed,
        submitted_at=datetime(2026, 8, 7, 11, index, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_db():
    return AsyncMock()


def _patch_visible_exam(monkeypatch, exam=None):
    monkeypatch.setattr(
        f"{MOD}.LearningExamRepository.get_by_id",
        AsyncMock(return_value=exam or _exam()),
    )


class TestListMyExams:
    @pytest.mark.asyncio
    async def test_only_published_visible_with_aggregates(self, mock_db, monkeypatch):
        exams = [_exam(id=10, visibility="all"), _exam(id=11, visibility="assigned", name="指定考试")]
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.list_paginated", AsyncMock(return_value=(exams, 2))
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAssignmentRepository.expand_assignments",
            AsyncMock(return_value={11: {EMPLOYEE}}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 3, "total_score": 95}, 11: {"question_count": 1, "total_score": 10}}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.aggregate_by_exams_for_employee",
            AsyncMock(return_value={10: {"submitted_count": 1, "best_score": 57}}),
        )

        result = await LearningExamMyService.list_my_exams(
            mock_db, tenant_id=TENANT, employee_id=EMPLOYEE, q=None, page=1, per_page=20
        )
        assert len(result["items"]) == 2
        by_id = {item["id"]: item for item in result["items"]}
        # floor(95 * 60 / 100) = 57 → best 57 is exactly the pass mark.
        assert by_id[10]["status"] == "passed"
        assert by_id[10]["remaining_attempts"] == 1
        assert by_id[11]["status"] == "not_started"
        assert by_id[11]["remaining_attempts"] == 2

    @pytest.mark.asyncio
    async def test_assigned_exam_hidden_when_not_visible(self, mock_db, monkeypatch):
        exams = [_exam(id=11, visibility="assigned")]
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.list_paginated", AsyncMock(return_value=(exams, 1))
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAssignmentRepository.expand_assignments",
            AsyncMock(return_value={11: {999}}),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.aggregate_questions_by_exam", AsyncMock(return_value={})
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.aggregate_by_exams_for_employee",
            AsyncMock(return_value={}),
        )

        result = await LearningExamMyService.list_my_exams(
            mock_db, tenant_id=TENANT, employee_id=EMPLOYEE, q=None, page=1, per_page=20
        )
        assert result["items"] == []


class TestStartAttempt:
    @pytest.mark.asyncio
    async def test_start_on_invisible_exam_404(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.get_by_id",
            AsyncMock(return_value=_exam(visibility="assigned")),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAssignmentRepository.list_visible_employee_ids",
            AsyncMock(return_value={999}),
        )

        with pytest.raises(NotFoundError):
            await LearningExamMyService.start_attempt(
                mock_db, tenant_id=TENANT, exam_id=10, employee_id=EMPLOYEE
            )

    @pytest.mark.asyncio
    async def test_start_rejected_when_attempts_exhausted(self, mock_db, monkeypatch):
        _patch_visible_exam(monkeypatch)
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.list_submitted_by_exam_employee",
            AsyncMock(return_value=[_submitted(1, 10), _submitted(2, 20)]),
        )

        with pytest.raises(BusinessError) as exc_info:
            await LearningExamMyService.start_attempt(
                mock_db, tenant_id=TENANT, exam_id=10, employee_id=EMPLOYEE
            )
        assert exc_info.value.code == "EXAM_NO_ATTEMPTS_LEFT"

    @pytest.mark.asyncio
    async def test_start_abandons_lingering_attempt_and_hides_answers(self, mock_db, monkeypatch):
        _patch_visible_exam(monkeypatch)
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.list_submitted_by_exam_employee",
            AsyncMock(return_value=[]),
        )
        abandon = AsyncMock()
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.abandon_in_progress", abandon
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamQuestionRepository.list_by_exam",
            AsyncMock(
                return_value=[
                    _question(101, 10, SNAPSHOT[0]["options"], "single"),
                    _question(103, 5, SNAPSHOT[2]["options"], "judge"),
                ]
            ),
        )
        captured = {}

        async def fake_create(db, data):
            captured.update(data)
            return _attempt(id=50, snapshot=data["snapshot"], started_at=data["started_at"])

        monkeypatch.setattr(f"{MOD}.LearningExamAttemptRepository.create", fake_create)

        result = await LearningExamMyService.start_attempt(
            mock_db, tenant_id=TENANT, exam_id=10, employee_id=EMPLOYEE
        )
        abandon.assert_awaited_once()
        assert captured["status"] == "in_progress"
        assert captured["employee_id"] == EMPLOYEE
        # Snapshot keeps the answers for grading...
        assert any(opt["is_correct"] for opt in captured["snapshot"][0]["options"])
        # ...but the taking payload strips them.
        assert all("is_correct" not in opt for q in result["questions"] for opt in q["options"])
        assert result["time_limit_minutes"] == 30

    @pytest.mark.asyncio
    async def test_start_shuffles_question_order_when_enabled(self, mock_db, monkeypatch):
        _patch_visible_exam(monkeypatch, _exam(shuffle_questions=True))
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.list_submitted_by_exam_employee",
            AsyncMock(return_value=[]),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.abandon_in_progress", AsyncMock()
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamQuestionRepository.list_by_exam",
            AsyncMock(
                return_value=[
                    _question(101, 10, SNAPSHOT[0]["options"]),
                    _question(102, 20, SNAPSHOT[1]["options"], "multiple"),
                    _question(103, 5, SNAPSHOT[2]["options"], "judge"),
                ]
            ),
        )
        monkeypatch.setattr(f"{MOD}.random.shuffle", lambda items: items.reverse())
        captured = {}

        async def fake_create(db, data):
            captured.update(data)
            return _attempt(snapshot=data["snapshot"])

        monkeypatch.setattr(f"{MOD}.LearningExamAttemptRepository.create", fake_create)

        await LearningExamMyService.start_attempt(
            mock_db, tenant_id=TENANT, exam_id=10, employee_id=EMPLOYEE
        )
        assert [entry["question_id"] for entry in captured["snapshot"]] == [103, 102, 101]


class TestAttemptDetail:
    @pytest.mark.asyncio
    async def test_in_progress_strips_answers(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id",
            AsyncMock(return_value=_attempt()),
        )
        _patch_visible_exam(monkeypatch)

        detail = await LearningExamMyService.get_attempt_detail(
            mock_db, tenant_id=TENANT, attempt_id=50, employee_id=EMPLOYEE
        )
        assert detail["status"] == "in_progress"
        assert all("is_correct" not in opt for q in detail["questions"] for opt in q["options"])
        # Review-only fields are absent while taking (serialized as null by the schema).
        assert all("selected_keys" not in q for q in detail["questions"])

    @pytest.mark.asyncio
    async def test_submitted_returns_review(self, mock_db, monkeypatch):
        attempt = _attempt(
            status="submitted",
            attempt_index=1,
            score=15,
            passed=True,
            answers={"101": ["a"], "103": ["true"]},
            submitted_at=datetime(2026, 8, 7, 11, 0, tzinfo=timezone.utc),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id", AsyncMock(return_value=attempt)
        )
        _patch_visible_exam(monkeypatch)

        detail = await LearningExamMyService.get_attempt_detail(
            mock_db, tenant_id=TENANT, attempt_id=50, employee_id=EMPLOYEE
        )
        by_id = {q["question_id"]: q for q in detail["questions"]}
        assert by_id[101]["gained_score"] == 10
        assert by_id[101]["is_correct"] is True
        # Unanswered multiple-choice question scores 0.
        assert by_id[102]["gained_score"] == 0
        assert by_id[102]["selected_keys"] == []
        assert by_id[103]["correct_keys"] == ["true"]
        assert by_id[101]["options"][0]["is_correct"] is True

    @pytest.mark.asyncio
    async def test_abandoned_attempt_not_found(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id",
            AsyncMock(return_value=_attempt(status="abandoned")),
        )

        with pytest.raises(NotFoundError):
            await LearningExamMyService.get_attempt_detail(
                mock_db, tenant_id=TENANT, attempt_id=50, employee_id=EMPLOYEE
            )

    @pytest.mark.asyncio
    async def test_other_employees_attempt_not_found(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id",
            AsyncMock(return_value=_attempt(employee_id=999)),
        )

        with pytest.raises(NotFoundError):
            await LearningExamMyService.get_attempt_detail(
                mock_db, tenant_id=TENANT, attempt_id=50, employee_id=EMPLOYEE
            )


class TestSubmitAttempt:
    def _patch_common(self, monkeypatch, attempt):
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id", AsyncMock(return_value=attempt)
        )
        _patch_visible_exam(monkeypatch)
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.list_submitted_by_exam_employee",
            AsyncMock(return_value=[]),
        )
        save = AsyncMock(side_effect=lambda db, row: row)
        monkeypatch.setattr(f"{MOD}.LearningExamAttemptRepository.save", save)
        return save

    @pytest.mark.asyncio
    async def test_full_score_when_all_correct(self, mock_db, monkeypatch):
        attempt = _attempt()
        self._patch_common(monkeypatch, attempt)

        result = await LearningExamMyService.submit_attempt(
            mock_db,
            tenant_id=TENANT,
            attempt_id=50,
            employee_id=EMPLOYEE,
            answers={"101": ["a"], "102": ["a", "b"], "103": ["true"]},
        )
        assert result["score"] == 35
        assert result["total_score"] == 35
        # floor(35 * 60 / 100) = 21
        assert result["pass_score"] == 21
        assert result["passed"] is True
        assert result["attempt_index"] == 1
        assert attempt.status == "submitted"

    @pytest.mark.asyncio
    async def test_multiple_choice_partial_answer_scores_zero(self, mock_db, monkeypatch):
        attempt = _attempt()
        self._patch_common(monkeypatch, attempt)

        result = await LearningExamMyService.submit_attempt(
            mock_db,
            tenant_id=TENANT,
            attempt_id=50,
            employee_id=EMPLOYEE,
            # 多选少选 b → 该题 0 分；其余两题正确。
            answers={"101": ["a"], "102": ["a"], "103": ["true"]},
        )
        assert result["score"] == 15
        assert result["passed"] is False  # 15 < 21

    @pytest.mark.asyncio
    async def test_empty_submit_scores_zero(self, mock_db, monkeypatch):
        attempt = _attempt()
        self._patch_common(monkeypatch, attempt)

        result = await LearningExamMyService.submit_attempt(
            mock_db, tenant_id=TENANT, attempt_id=50, employee_id=EMPLOYEE, answers={}
        )
        assert result["score"] == 0
        assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_attempt_index_increments_with_history(self, mock_db, monkeypatch):
        attempt = _attempt()
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id", AsyncMock(return_value=attempt)
        )
        _patch_visible_exam(monkeypatch)
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.list_submitted_by_exam_employee",
            AsyncMock(return_value=[_submitted(1, 10)]),
        )
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.save", AsyncMock(side_effect=lambda db, row: row)
        )

        result = await LearningExamMyService.submit_attempt(
            mock_db, tenant_id=TENANT, attempt_id=50, employee_id=EMPLOYEE, answers={}
        )
        assert result["attempt_index"] == 2

    @pytest.mark.asyncio
    async def test_resubmit_rejected(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id",
            AsyncMock(return_value=_submitted(1, 30)),
        )

        with pytest.raises(BusinessError) as exc_info:
            await LearningExamMyService.submit_attempt(
                mock_db, tenant_id=TENANT, attempt_id=51, employee_id=EMPLOYEE, answers={}
            )
        assert exc_info.value.code == "ATTEMPT_NOT_SUBMITTABLE"


class TestAbandonAttempt:
    @pytest.mark.asyncio
    async def test_abandon_in_progress(self, mock_db, monkeypatch):
        attempt = _attempt()
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id", AsyncMock(return_value=attempt)
        )
        save = AsyncMock(side_effect=lambda db, row: row)
        monkeypatch.setattr(f"{MOD}.LearningExamAttemptRepository.save", save)

        await LearningExamMyService.abandon_attempt(
            mock_db, tenant_id=TENANT, attempt_id=50, employee_id=EMPLOYEE
        )
        assert attempt.status == "abandoned"
        save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_abandon_submitted_is_noop(self, mock_db, monkeypatch):
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.get_by_id",
            AsyncMock(return_value=_submitted(1, 30)),
        )
        save = AsyncMock()
        monkeypatch.setattr(f"{MOD}.LearningExamAttemptRepository.save", save)

        await LearningExamMyService.abandon_attempt(
            mock_db, tenant_id=TENANT, attempt_id=51, employee_id=EMPLOYEE
        )
        save.assert_not_called()


class TestMyExamSummary:
    @pytest.mark.asyncio
    async def test_summary_best_attempt_and_history(self, mock_db, monkeypatch):
        _patch_visible_exam(monkeypatch)
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 3, "total_score": 35}}),
        )
        # Newest first from the repository; service re-sorts by attempt_index.
        submitted = [_submitted(2, 30), _submitted(1, 15, passed=False)]
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.list_submitted_by_exam_employee",
            AsyncMock(return_value=submitted),
        )

        summary = await LearningExamMyService.get_my_exam_summary(
            mock_db, tenant_id=TENANT, exam_id=10, employee_id=EMPLOYEE
        )
        assert summary["best_score"] == 30
        assert summary["best_attempt_id"] == submitted[0].id
        assert summary["status"] == "passed"
        assert summary["remaining_attempts"] == 0
        assert [item["attempt_index"] for item in summary["attempts"]] == [1, 2]

    @pytest.mark.asyncio
    async def test_summary_best_tie_prefers_latest(self, mock_db, monkeypatch):
        _patch_visible_exam(monkeypatch)
        monkeypatch.setattr(
            f"{MOD}.LearningExamRepository.aggregate_questions_by_exam",
            AsyncMock(return_value={10: {"question_count": 3, "total_score": 35}}),
        )
        first, second = _submitted(1, 30), _submitted(2, 30)
        monkeypatch.setattr(
            f"{MOD}.LearningExamAttemptRepository.list_submitted_by_exam_employee",
            AsyncMock(return_value=[second, first]),
        )

        summary = await LearningExamMyService.get_my_exam_summary(
            mock_db, tenant_id=TENANT, exam_id=10, employee_id=EMPLOYEE
        )
        assert summary["best_attempt_id"] == second.id
