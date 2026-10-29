"""Metric-group registry for the overall session report.

The registry is the single ordered source of truth for which groups the overall
report exposes and in what order. Adding a new group = implement a provider and
append it here; nothing else in the report pipeline changes.
"""
from __future__ import annotations

from .base import MetricDescriptor, MetricGroupProvider, OverallContext
from .human_messages import HumanMessagesGroup
from .queue_access import QueueAccessGroup
from .service_efficiency import ServiceEfficiencyGroup
from .session_overall import SessionOverallGroup
from .satisfaction import SatisfactionGroup

# Ordered list of metric groups shown by the overall report. Frontend renders
# groups in this order. More groups (服务效率 / 满意度 / 业务补充) are appended
# here as they land.
REGISTRY: list[MetricGroupProvider] = [
    SessionOverallGroup(),
    HumanMessagesGroup(),
    QueueAccessGroup(),
    ServiceEfficiencyGroup(),
    SatisfactionGroup(),
]

_BY_KEY = {group.key: group for group in REGISTRY}


def all_groups() -> list[MetricGroupProvider]:
    return list(REGISTRY)


def get_group(key: str | None) -> MetricGroupProvider:
    """Return the requested group, or the first registered group when key is
    missing/unknown (the default selection for the trend view)."""
    if key and key in _BY_KEY:
        return _BY_KEY[key]
    return REGISTRY[0]


__all__ = [
    "MetricDescriptor",
    "MetricGroupProvider",
    "OverallContext",
    "REGISTRY",
    "all_groups",
    "get_group",
]
