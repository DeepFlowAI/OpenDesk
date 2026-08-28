"""Unit tests for the DTMF-only satisfaction runtime."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.libs.telephony.base import TelephonyRPCError
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.models.call_satisfaction import CallSatisfactionAnswer
from app.schemas.satisfaction_flow_graph import default_satisfaction_graph
from app.services.call_center.satisfaction_workflow import SatisfactionWorkflow
from app.services.call_satisfaction_execution_service import (
    PreparedSatisfactionExecution,
)


def _prepared(graph: dict | None = None) -> PreparedSatisfactionExecution:
    return PreparedSatisfactionExecution(
        execution_id=81,
        tenant_id=7,
        call_record_id=22,
        call_id="customer-call",
        flow_id=4,
        flow_version_id=9,
        flow_name="服务评价",
        flow_version_no=3,
        graph=graph or default_satisfaction_graph(),
        settings={
            "auto_transfer": True,
            "agent_invite": True,
            "inbound": True,
            "outbound": True,
        },
        status="preparing",
        created=True,
    )


@pytest.mark.asyncio
async def test_valid_dtmf_persists_option_then_completes() -> None:
    telephony = MockTelephonyClient()
    record_answer = AsyncMock(
        return_value={
            "question_node_id": "question-1",
            "question_name": "服务满意度",
            "option_id": "satisfied",
            "option_label": "满意",
            "created": True,
        }
    )
    finalize = AsyncMock(return_value="completed")
    with (
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.mark_started_managed",
            new=AsyncMock(),
        ),
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.record_answer_managed",
            new=record_answer,
        ),
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.finalize_managed",
            new=finalize,
        ),
    ):
        workflow = SatisfactionWorkflow(prepared=_prepared(), telephony=telephony)
        await workflow.start()
        await workflow.handle_event(
            "call.dtmf", {"call_id": "customer-call", "digit": "3"}
        )
        end_play = next(
            payload["play_id"]
            for method, payload in reversed(telephony.recorded)
            if method == "call.say"
        )
        await workflow.handle_event(
            "call.play_end",
            {"call_id": "customer-call", "play_id": end_play},
        )

    record_answer.assert_awaited_once_with(
        execution_id=81,
        question_node_id="question-1",
        digit="3",
    )
    finalize.assert_awaited_once_with(
        execution_id=81,
        status="completed",
        reason="completed",
    )
    assert workflow.done.is_set()
    assert telephony.recorded[-1] == (
        "call.hangup",
        {"call_id": "customer-call", "reason": "satisfaction_completed"},
    )


@pytest.mark.asyncio
async def test_invalid_dtmf_retries_without_persisting() -> None:
    telephony = MockTelephonyClient()
    record_answer = AsyncMock()
    with (
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.mark_started_managed",
            new=AsyncMock(),
        ),
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.record_answer_managed",
            new=record_answer,
        ),
    ):
        workflow = SatisfactionWorkflow(prepared=_prepared(), telephony=telephony)
        await workflow.start()
        await workflow.handle_event(
            "call.dtmf", {"call_id": "customer-call", "digit": "9"}
        )

    record_answer.assert_not_awaited()
    assert any(
        method == "call.say" and payload["text"] == "输入无效，请按提示重新选择。"
        for method, payload in telephony.recorded
    )
    assert not workflow.done.is_set()
    workflow._cancel_timeout()


@pytest.mark.asyncio
async def test_customer_hangup_keeps_partial_answer_and_cancels_timeout() -> None:
    graph = default_satisfaction_graph()
    question = next(node for node in graph["nodes"] if node["type"] == "question")
    question["data"]["timeout_seconds"] = 30
    telephony = MockTelephonyClient()
    finalize = AsyncMock(return_value="unanswered")
    with (
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.mark_started_managed",
            new=AsyncMock(),
        ),
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.finalize_managed",
            new=finalize,
        ),
    ):
        workflow = SatisfactionWorkflow(
            prepared=_prepared(graph), telephony=telephony
        )
        await workflow.start()
        assert workflow._timeout_task is not None
        await workflow.on_call_hangup({"reason": "remote_bye"})

    finalize.assert_awaited_once_with(
        execution_id=81,
        status="unanswered",
        reason="customer_hangup",
    )
    assert workflow.done.is_set()
    assert workflow._timeout_task is None
    assert not any(method == "call.hangup" for method, _ in telephony.recorded)


@pytest.mark.asyncio
async def test_customer_hangup_media_timeout_maps_like_remote_bye() -> None:
    telephony = MockTelephonyClient()
    finalize = AsyncMock(return_value="unanswered")
    with (
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.finalize_managed",
            new=finalize,
        ),
    ):
        workflow = SatisfactionWorkflow(
            prepared=_prepared(), telephony=telephony
        )
        await workflow.on_call_hangup({"reason": "media_timeout"})

    finalize.assert_awaited_once_with(
        execution_id=81,
        status="unanswered",
        reason="customer_hangup",
    )


def test_answer_model_has_no_raw_dtmf_column() -> None:
    assert "dtmf" not in CallSatisfactionAnswer.__table__.columns
    assert "digits" not in CallSatisfactionAnswer.__table__.columns


@pytest.mark.asyncio
async def test_call_gone_mid_survey_ends_as_customer_hangup() -> None:
    """A customer who hangs up during the survey is the most common outcome, and
    the kernel reports it as an unknown call on the next prompt. Recording that
    as a workflow error would mark ordinary surveys as broken."""

    graph = default_satisfaction_graph()
    question = next(node for node in graph["nodes"] if node["type"] == "question")
    question["data"]["timeout_seconds"] = 0.05
    telephony = MockTelephonyClient()
    finalize = AsyncMock(return_value="unanswered")
    with (
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.mark_started_managed",
            new=AsyncMock(),
        ),
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.finalize_managed",
            new=finalize,
        ),
    ):
        workflow = SatisfactionWorkflow(prepared=_prepared(graph), telephony=telephony)
        await workflow.start()
        # The leg dies only after the survey is under way, so this is not the
        # startup-failure path.
        telephony.call_say = AsyncMock(
            side_effect=TelephonyRPCError(-32002, "call not found: customer-call")
        )
        await asyncio.sleep(0.2)

    finalize.assert_awaited_once_with(
        execution_id=81,
        status="unanswered",
        reason="customer_hangup",
    )
    assert workflow.done.is_set()
    # Nothing left to hang up: the kernel already dropped the leg.
    assert not any(method == "call.hangup" for method, _ in telephony.recorded)


@pytest.mark.asyncio
async def test_unexpected_error_mid_survey_still_reports_workflow_error() -> None:
    graph = default_satisfaction_graph()
    question = next(node for node in graph["nodes"] if node["type"] == "question")
    question["data"]["timeout_seconds"] = 0.05
    telephony = MockTelephonyClient()
    finalize = AsyncMock(return_value="unanswered")
    with (
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.mark_started_managed",
            new=AsyncMock(),
        ),
        patch(
            "app.services.call_center.satisfaction_workflow."
            "CallSatisfactionExecutionService.finalize_managed",
            new=finalize,
        ),
    ):
        workflow = SatisfactionWorkflow(prepared=_prepared(graph), telephony=telephony)
        await workflow.start()
        telephony.call_say = AsyncMock(side_effect=RuntimeError("boom"))
        await asyncio.sleep(0.2)

    assert finalize.await_args.kwargs["reason"] == "workflow_error"
