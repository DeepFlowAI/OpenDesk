"""Unit tests for final satisfaction summaries on call records."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.call_satisfaction_projection_service import (
    CallSatisfactionProjectionService,
)


@pytest.mark.asyncio
async def test_projects_completed_execution_from_first_mapped_answer() -> None:
    ended_at = datetime.now(timezone.utc)
    record = SimpleNamespace(
        id=7,
        lifecycle_status="ended",
        ended_at=ended_at,
        satisfaction_projected_at=None,
    )
    execution = SimpleNamespace(
        id=11,
        status="completed",
        trigger_source="agent_invite",
        started_at=ended_at - timedelta(seconds=9),
        ended_at=ended_at,
    )
    answers = [
        SimpleNamespace(option_id="satisfied", option_label_snapshot="满意")
    ]
    db = SimpleNamespace(commit=AsyncMock())
    update = AsyncMock()
    with (
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallRecordRepository.lock_by_id",
            new=AsyncMock(return_value=record),
        ),
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallSatisfactionExecutionRepository.get_by_call_record_id",
            new=AsyncMock(return_value=execution),
        ),
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallSatisfactionAnswerRepository.list_for_execution",
            new=AsyncMock(return_value=answers),
        ),
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallRecordRepository.update",
            new=update,
        ),
    ):
        projected = await CallSatisfactionProjectionService.project(
            db, call_record_id=7
        )

    assert projected is True
    patch_data = update.await_args.args[2]
    assert patch_data["satisfaction_result"] == "completed"
    assert patch_data["satisfaction_primary_option_id"] == "satisfied"
    assert patch_data["satisfaction_primary_option_label"] == "满意"
    assert patch_data["satisfaction_answer_count"] == 1
    assert patch_data["satisfaction_duration_ms"] == 9000
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_projects_untriggered_call_as_not_surveyed() -> None:
    ended_at = datetime.now(timezone.utc)
    record = SimpleNamespace(
        id=7,
        lifecycle_status="ended",
        ended_at=ended_at,
        satisfaction_projected_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock())
    update = AsyncMock()
    with (
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallRecordRepository.lock_by_id",
            new=AsyncMock(return_value=record),
        ),
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallSatisfactionExecutionRepository.get_by_call_record_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallRecordRepository.update",
            new=update,
        ),
    ):
        projected = await CallSatisfactionProjectionService.project(
            db, call_record_id=7
        )

    assert projected is True
    patch_data = update.await_args.args[2]
    assert patch_data["satisfaction_result"] == "not_surveyed"
    assert patch_data["satisfaction_answer_count"] == 0
    assert patch_data["satisfaction_projected_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_projection_is_idempotent_after_projected_at_is_set() -> None:
    projected_at = datetime.now(timezone.utc)
    record = SimpleNamespace(
        id=7,
        lifecycle_status="ended",
        ended_at=projected_at,
        satisfaction_projected_at=projected_at,
    )
    db = SimpleNamespace(commit=AsyncMock())
    execution_lookup = AsyncMock()
    with (
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallRecordRepository.lock_by_id",
            new=AsyncMock(return_value=record),
        ),
        patch(
            "app.services.call_satisfaction_projection_service."
            "CallSatisfactionExecutionRepository.get_by_call_record_id",
            new=execution_lookup,
        ),
    ):
        projected = await CallSatisfactionProjectionService.project(
            db, call_record_id=7
        )

    assert projected is True
    execution_lookup.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalizing_an_execution_projects_onto_a_closed_record() -> None:
    """A survey can outlive its call: the customer hangs up, the record closes
    while the survey is still running, and it settles a beat later. The record
    projects only on close, so without this the survey would leave no trace."""

    from app.services.call_satisfaction_execution_service import (
        CallSatisfactionExecutionService,
    )

    execution = SimpleNamespace(
        id=11,
        tenant_id=7,
        call_record_id=22,
        status="in_progress",
        termination_reason=None,
        ended_at=None,
        answer_count=0,
        flow_name_snapshot="服务评价",
    )
    db = SimpleNamespace(commit=AsyncMock())

    class _FakeSession:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return False

    project = AsyncMock(return_value=True)
    with (
        patch(
            "app.services.call_satisfaction_execution_service.AsyncSessionLocal",
            lambda: _FakeSession(),
        ),
        patch(
            "app.services.call_satisfaction_execution_service."
            "CallSatisfactionExecutionRepository.lock_by_id",
            new=AsyncMock(return_value=execution),
        ),
        patch(
            "app.services.call_satisfaction_execution_service."
            "CallRecordRepository.get_by_id_unscoped",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.call_satisfaction_execution_service."
            "CallSatisfactionProjectionService.project",
            new=project,
        ),
    ):
        status = await CallSatisfactionExecutionService.finalize_managed(
            execution_id=11, status="unanswered", reason="customer_hangup"
        )

    assert status == "unanswered"
    project.assert_awaited_once_with(db, call_record_id=22)
