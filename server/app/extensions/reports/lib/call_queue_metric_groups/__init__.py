"""Ordered call queue metric group registry."""
from .agent_response import QueueAgentResponseGroup
from .base import QueueMetricGroupProvider
from .outcomes import QueueOutcomesGroup
from .queue_flow import QueueFlowGroup
from .waiting import QueueWaitingGroup


_GROUPS: tuple[QueueMetricGroupProvider, ...] = (
    QueueFlowGroup(),
    QueueOutcomesGroup(),
    QueueWaitingGroup(),
    QueueAgentResponseGroup(),
)


def all_groups() -> tuple[QueueMetricGroupProvider, ...]:
    return _GROUPS


def get_group(key: str | None) -> QueueMetricGroupProvider:
    selected = key or _GROUPS[0].key
    for provider in _GROUPS:
        if provider.key == selected:
            return provider
    raise ValueError(f"Unsupported call queue metric group: {selected}")
