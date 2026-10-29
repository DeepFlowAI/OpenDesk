from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.quality_review import QualityLLMResult
from app.services.platform_llm_queue_service import PlatformLLMQueueService
from app.services.quality_review_execution_service import QualityReviewExecutionService


@pytest.mark.asyncio
async def test_run_tick_closes_db_session_before_llm_wait(monkeypatch):
    state = {"session_active": False, "completed": None}

    class SessionContext:
        async def __aenter__(self):
            state["session_active"] = True
            return object()

        async def __aexit__(self, *_args):
            state["session_active"] = False

    async def claim_next(_db, _worker_id):
        return SimpleNamespace(
            id=17,
            request_payload={"messages": [{"role": "user", "content": "review"}]},
        )

    class Client:
        async def complete(self, *_args, **_kwargs):
            assert state["session_active"] is False
            return '{"result_type":"not_applicable","option_id":null,"reason":"N/A","evidence_message_ids":[]}'

    async def complete_managed(call_id, payload):
        state["completed"] = (call_id, payload)

    monkeypatch.setattr(
        "app.services.platform_llm_queue_service.AsyncSessionLocal",
        SessionContext,
    )
    monkeypatch.setattr(
        "app.services.platform_llm_queue_service.PlatformLLMCallRepository.claim_next",
        claim_next,
    )
    monkeypatch.setattr(
        "app.services.platform_llm_queue_service.create_llm_client",
        lambda: Client(),
    )
    monkeypatch.setattr(
        QualityReviewExecutionService,
        "complete_call_managed",
        complete_managed,
    )

    assert await PlatformLLMQueueService.run_tick() is True
    assert state["completed"][0] == 17
    assert state["session_active"] is False


def test_llm_result_rejects_extra_fields():
    with pytest.raises(PydanticValidationError):
        QualityLLMResult.model_validate(
            {
                "result_type": "option",
                "option_id": 1,
                "reason": "matched",
                "evidence_message_ids": [],
                "score": 100,
            }
        )


def test_evidence_policy_requires_issue_evidence():
    criterion = {
        "evidence_policy": "issue_only",
        "options": [
            {"id": 1, "severity": "normal"},
            {"id": 2, "severity": "issue"},
        ],
    }
    assert QualityReviewExecutionService._evidence_required(criterion, 1) is False
    assert QualityReviewExecutionService._evidence_required(criterion, 2) is True


def test_retry_exhaustion_marks_call_failed():
    call = SimpleNamespace(
        attempt_count=3,
        max_attempts=3,
        status="running",
        completed_at=None,
    )
    now = datetime.now(timezone.utc)
    assert PlatformLLMQueueService.schedule_retry(call, now) is False
    assert call.status == "failed"
    assert call.completed_at == now
