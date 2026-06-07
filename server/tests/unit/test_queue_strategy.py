from datetime import datetime, timedelta, timezone

from app.services.queue_strategy import QueueCandidate, QueueStrategyService


def test_round_robin_picks_after_last_agent():
    candidates = [
        QueueCandidate(employee_id=1),
        QueueCandidate(employee_id=2),
        QueueCandidate(employee_id=3),
    ]

    picked = QueueStrategyService.choose_candidate(
        candidates,
        "round_robin",
        last_agent_id=2,
    )

    assert picked is not None
    assert picked.employee_id == 3


def test_current_load_low_uses_load_ratio_then_employee_id():
    candidates = [
        QueueCandidate(employee_id=1, current_load=5, max_capacity=10),
        QueueCandidate(employee_id=2, current_load=1, max_capacity=2),
        QueueCandidate(employee_id=3, current_load=1, max_capacity=10),
    ]

    picked = QueueStrategyService.choose_candidate(candidates, "current_load_low")

    assert picked is not None
    assert picked.employee_id == 3


def test_idle_longest_picks_oldest_idle_since():
    now = datetime.now(timezone.utc)
    candidates = [
        QueueCandidate(employee_id=1, idle_since=now - timedelta(minutes=1)),
        QueueCandidate(employee_id=2, idle_since=now - timedelta(minutes=5)),
    ]

    picked = QueueStrategyService.choose_candidate(candidates, "idle_longest")

    assert picked is not None
    assert picked.employee_id == 2
