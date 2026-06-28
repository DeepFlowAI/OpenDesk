"""
Queue policy schema validation tests.
"""
import pytest
from pydantic import ValidationError

from app.schemas.queue import QueueEnqueueRequest, QueuePolicyUpsert


@pytest.mark.parametrize("strategy", ["idle_longest", "today_assignments_low", "today_call_duration_low"])
def test_online_chat_policy_rejects_metric_strategy_without_source(strategy: str):
    with pytest.raises(ValidationError):
        QueuePolicyUpsert(
            channel="online_chat",
            scope_type="employee_group",
            scope_id=1,
            assignment_strategy=strategy,
        )


@pytest.mark.parametrize(
    "strategy",
    ["current_load_low", "idle_longest", "today_assignments_low", "today_call_duration_low"],
)
def test_call_center_policy_rejects_metric_strategy_without_source(strategy: str):
    with pytest.raises(ValidationError):
        QueuePolicyUpsert(
            channel="call_center",
            scope_type="employee_group",
            scope_id=1,
            assignment_strategy=strategy,
        )


def test_global_policy_defaults_strategy_to_round_robin():
    policy = QueuePolicyUpsert(
        channel="online_chat",
        scope_type="global",
        max_waiting_count=1,
        max_wait_seconds=86400,
    )

    assert policy.scope_id is None
    assert policy.assignment_strategy == "round_robin"


def test_employee_policy_clears_assignment_strategy():
    policy = QueuePolicyUpsert(
        channel="call_center",
        scope_type="employee",
        scope_id=10,
        assignment_strategy="round_robin",
        max_waiting_count=99999,
        max_wait_seconds=1,
    )

    assert policy.assignment_strategy is None


def test_enqueue_rejects_unsupported_explicit_strategy():
    with pytest.raises(ValidationError):
        QueueEnqueueRequest(
            channel="call_center",
            task_type="call",
            task_ref_id="call-1",
            queue_type="employee_group",
            queue_id=1,
            assignment_strategy="idle_longest",
        )


def test_employee_enqueue_clears_explicit_strategy():
    request = QueueEnqueueRequest(
        channel="online_chat",
        task_type="manual",
        task_ref_id="manual-1",
        queue_type="employee",
        queue_id=1,
        assignment_strategy="current_load_low",
    )

    assert request.assignment_strategy is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_waiting_count", 0),
        ("max_waiting_count", 100000),
        ("max_wait_seconds", 0),
        ("max_wait_seconds", 86401),
    ],
)
def test_policy_limit_ranges(field: str, value: int):
    payload = {
        "channel": "online_chat",
        "scope_type": "global",
        "assignment_strategy": "round_robin",
        field: value,
    }

    with pytest.raises(ValidationError):
        QueuePolicyUpsert(**payload)


def test_policy_defaults_returning_agent_window_when_enabled():
    policy = QueuePolicyUpsert(
        channel="online_chat",
        scope_type="employee_group",
        scope_id=1,
        assignment_strategy="round_robin",
        config={"returning_agent_priority_enabled": True},
    )

    assert policy.config["returning_agent_priority_enabled"] is True
    assert policy.config["returning_agent_window_hours"] == 24


@pytest.mark.parametrize(
    "config",
    [
        {"returning_agent_priority_enabled": "yes", "returning_agent_window_hours": 24},
        {"returning_agent_priority_enabled": True, "returning_agent_window_hours": None},
        {"returning_agent_priority_enabled": True, "returning_agent_window_hours": 0},
        {"returning_agent_priority_enabled": True, "returning_agent_window_hours": 721},
        {"returning_agent_priority_enabled": True, "returning_agent_window_hours": 24.0},
    ],
)
def test_policy_rejects_invalid_returning_agent_config(config: dict):
    with pytest.raises(ValidationError):
        QueuePolicyUpsert(
            channel="online_chat",
            scope_type="employee_group",
            scope_id=1,
            assignment_strategy="round_robin",
            config=config,
        )
