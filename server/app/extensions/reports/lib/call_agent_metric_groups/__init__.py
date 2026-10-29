"""Ordered employee call-report metric group registry."""
from .base import AgentMetricGroupProvider
from .collaboration import AgentCollaborationGroup
from .efficiency import AgentEfficiencyGroup
from .offer_response import AgentOfferResponseGroup
from .workload import AgentWorkloadGroup


_GROUPS: tuple[AgentMetricGroupProvider, ...] = (
    AgentWorkloadGroup(),
    AgentOfferResponseGroup(),
    AgentEfficiencyGroup(),
    AgentCollaborationGroup(),
)


def all_groups() -> tuple[AgentMetricGroupProvider, ...]:
    return _GROUPS


def get_group(key: str | None) -> AgentMetricGroupProvider:
    selected = key or _GROUPS[0].key
    for provider in _GROUPS:
        if provider.key == selected:
            return provider
    raise ValueError(f"Unsupported call employee metric group: {selected}")
