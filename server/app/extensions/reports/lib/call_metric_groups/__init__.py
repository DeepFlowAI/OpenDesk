"""Ordered registry for grouped call-report providers."""
from __future__ import annotations

from .base import CallMetricDescriptor, CallMetricGroupProvider, CallOverallContext
from .call_overview import CallOverviewGroup
from .inbound_service import InboundServiceGroup
from .outbound_service import OutboundServiceGroup
from .satisfaction import SatisfactionGroup
from .service_efficiency import ServiceEfficiencyGroup

REGISTRY: list[CallMetricGroupProvider] = [
    CallOverviewGroup(),
    InboundServiceGroup(),
    OutboundServiceGroup(),
    ServiceEfficiencyGroup(),
    SatisfactionGroup(),
]

_BY_KEY = {group.key: group for group in REGISTRY}


def all_groups() -> list[CallMetricGroupProvider]:
    return list(REGISTRY)


def get_group(key: str | None) -> CallMetricGroupProvider:
    if key and key in _BY_KEY:
        return _BY_KEY[key]
    return REGISTRY[0]


__all__ = [
    "CallMetricDescriptor",
    "CallMetricGroupProvider",
    "CallOverallContext",
    "REGISTRY",
    "all_groups",
    "get_group",
]
