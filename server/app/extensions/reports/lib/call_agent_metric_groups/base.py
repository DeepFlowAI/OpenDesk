"""Contracts and helpers for employee call-report metric groups."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...schemas import MetricFormat, MetricLevel


class AgentMetricDescriptor:
    def __init__(
        self,
        key: str,
        metric_format: MetricFormat = MetricFormat.INTEGER,
        level: MetricLevel = MetricLevel.PRIMARY,
    ) -> None:
        self.key = key
        self.format = metric_format
        self.level = level


class AgentMetricGroupProvider(ABC):
    key: str = ""
    descriptors: list[AgentMetricDescriptor] = []

    @abstractmethod
    def values(self, raw: dict[str, float | int | None]) -> dict[str, float | None]:
        """Convert raw fact counters into public values."""


def ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if not denominator:
        return None
    return float(numerator or 0) / float(denominator)


def average_ms(total: float | int | None, count: float | int | None) -> float | None:
    if not count:
        return None
    return float(total or 0) / float(count) / 1000.0


def seconds(total_ms: float | int | None, count: float | int | None) -> float | None:
    if not count:
        return None
    return float(total_ms or 0) / 1000.0
