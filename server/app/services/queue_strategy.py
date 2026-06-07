"""
Candidate ordering for the unified queue engine.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.enums import QueueAssignmentStrategy


@dataclass(slots=True)
class QueueCandidate:
    employee_id: int
    name: str | None = None
    available: bool = True
    current_load: int = 0
    max_capacity: int = 1
    today_assignments: int = 0
    today_call_duration_seconds: int = 0
    idle_since: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def load_ratio(self) -> float:
        if self.max_capacity <= 0:
            return 1.0
        return self.current_load / self.max_capacity

    def load_payload(self) -> dict[str, Any]:
        return {
            "current_load": self.current_load,
            "max_capacity": self.max_capacity,
            "load_ratio": self.load_ratio,
            **self.metrics,
        }


class QueueStrategyService:
    @staticmethod
    def choose_candidate(
        candidates: list[QueueCandidate],
        strategy: str | None,
        *,
        last_agent_id: int | None = None,
        config: dict[str, Any] | None = None,
    ) -> QueueCandidate | None:
        available = [candidate for candidate in candidates if candidate.available]
        if not available:
            return None
        if len(available) == 1:
            return available[0]

        strategy = strategy or QueueAssignmentStrategy.ROUND_ROBIN.value
        config = config or {}

        if strategy == QueueAssignmentStrategy.RANDOM.value:
            return random.choice(available)
        if strategy == QueueAssignmentStrategy.FIXED_ORDER.value:
            return QueueStrategyService._fixed_order(available, config)
        if strategy == QueueAssignmentStrategy.CURRENT_LOAD_LOW.value:
            return min(available, key=lambda item: (item.load_ratio, item.current_load, item.employee_id))
        if strategy == QueueAssignmentStrategy.TODAY_ASSIGNMENTS_LOW.value:
            return min(available, key=lambda item: (item.today_assignments, item.load_ratio, item.employee_id))
        if strategy == QueueAssignmentStrategy.TODAY_CALL_DURATION_LOW.value:
            return min(available, key=lambda item: (item.today_call_duration_seconds, item.employee_id))
        if strategy == QueueAssignmentStrategy.IDLE_LONGEST.value:
            return min(
                available,
                key=lambda item: (
                    item.idle_since or datetime.max,
                    item.load_ratio,
                    item.employee_id,
                ),
            )
        return QueueStrategyService._round_robin(available, last_agent_id, config)

    @staticmethod
    def ordered_candidates(
        candidates: list[QueueCandidate],
        strategy: str | None,
        *,
        last_agent_id: int | None = None,
        config: dict[str, Any] | None = None,
    ) -> list[QueueCandidate]:
        available = [candidate for candidate in candidates if candidate.available]
        if not available:
            return []
        first = QueueStrategyService.choose_candidate(
            available,
            strategy,
            last_agent_id=last_agent_id,
            config=config,
        )
        if first is None:
            return []
        remaining = [candidate for candidate in available if candidate.employee_id != first.employee_id]
        remaining.sort(key=lambda item: (item.load_ratio, item.employee_id))
        return [first, *remaining]

    @staticmethod
    def _fixed_order(candidates: list[QueueCandidate], config: dict[str, Any]) -> QueueCandidate:
        order = config.get("employee_order") or []
        rank = {int(employee_id): index for index, employee_id in enumerate(order)}
        return min(candidates, key=lambda item: (rank.get(item.employee_id, len(rank)), item.employee_id))

    @staticmethod
    def _round_robin(
        candidates: list[QueueCandidate],
        last_agent_id: int | None,
        config: dict[str, Any],
    ) -> QueueCandidate:
        order = config.get("employee_order") or [candidate.employee_id for candidate in candidates]
        rank = {int(employee_id): index for index, employee_id in enumerate(order)}
        ordered = sorted(candidates, key=lambda item: (rank.get(item.employee_id, len(rank)), item.employee_id))
        if last_agent_id is None:
            return ordered[0]
        for index, candidate in enumerate(ordered):
            if candidate.employee_id == last_agent_id:
                return ordered[(index + 1) % len(ordered)]
        return ordered[0]
