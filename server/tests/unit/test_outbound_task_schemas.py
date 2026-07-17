"""Unit tests for manual outbound task response schemas."""

from typing import Any

from app.models.outbound_task import OutboundTask, OutboundTaskTarget
from app.schemas.outbound_task import OutboundTargetResponse, OutboundTargetWithTaskResponse


class TargetWithUnloadedTask:
    def __init__(self, target: OutboundTaskTarget) -> None:
        self._target = target

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)

    @property
    def task(self) -> None:
        raise AssertionError("The task relationship must not be accessed")


def test_outbound_target_response_does_not_access_task_relationship():
    target = TargetWithUnloadedTask(
        OutboundTaskTarget(
            id=3,
            tenant_id=1,
            task_id=1,
            phone_number="13800000000",
            status="pending",
            field_values={},
            call_count=0,
            answered_count=0,
            total_talk_duration_ms=0,
        )
    )

    response = OutboundTargetResponse.model_validate(target)

    assert response.id == 3
    assert response.phone_number == "13800000000"
    assert "task" not in response.model_dump()


def test_outbound_target_with_task_response_keeps_task_details():
    target = OutboundTaskTarget(
        id=3,
        tenant_id=1,
        task_id=1,
        phone_number="13800000000",
        status="pending",
        field_values={},
        call_count=0,
        answered_count=0,
        total_talk_duration_ms=0,
    )
    target.task = OutboundTask(
        id=1,
        tenant_id=1,
        template_name="回访模板",
        name="回访任务",
        status="active",
        fields=[],
        assignee_scope_ids=[],
        allow_self_claim=False,
        assignment_mode="manual",
    )

    response = OutboundTargetWithTaskResponse.model_validate(target)

    assert response.task.id == 1
    assert response.task.name == "回访任务"
