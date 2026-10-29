"""Contracts and helpers for call queue metric groups."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...schemas import MetricFormat, MetricLevel


class QueueMetricDescriptor:
    """Stable metadata for a queue report metric."""

    def __init__(
        self,
        key: str,
        metric_format: MetricFormat = MetricFormat.INTEGER,
        level: MetricLevel = MetricLevel.PRIMARY,
    ) -> None:
        self.key = key
        self.format = metric_format
        self.level = level


class QueueMetricGroupProvider(ABC):
    """Convert raw fact counters into one public metric group."""

    key: str = ""
    descriptors: list[QueueMetricDescriptor] = []

    @abstractmethod
    def values(self, raw: dict[str, float | int | None]) -> dict[str, float | None]:
        """Return public values derived from raw numerators and denominators."""


def ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if not denominator:
        return None
    return float(numerator or 0) / float(denominator)


def average_ms(total: float | int | None, count: float | int | None) -> float | None:
    if not count:
        return None
    return float(total or 0) / float(count) / 1000.0
