"""Queue waiting-time and service-level metrics."""
from ...schemas import MetricFormat, MetricLevel
from .base import QueueMetricDescriptor, QueueMetricGroupProvider, average_ms, ratio


class QueueWaitingGroup(QueueMetricGroupProvider):
    key = "queue_waiting"
    descriptors = [
        QueueMetricDescriptor("avg_answer_wait_seconds", MetricFormat.DURATION_SECONDS),
        QueueMetricDescriptor(
            "avg_abandon_wait_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY
        ),
        QueueMetricDescriptor(
            "avg_queue_wait_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY
        ),
        QueueMetricDescriptor(
            "max_queue_wait_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY
        ),
        QueueMetricDescriptor("queue_service_level_20s", MetricFormat.PERCENT),
    ]

    def values(
        self, raw: dict[str, float | int | None]
    ) -> dict[str, float | None]:
        maximum = raw.get("max_queue_wait_ms")
        return {
            "avg_answer_wait_seconds": average_ms(
                raw.get("answer_wait_total_ms"), raw.get("answer_wait_count")
            ),
            "avg_abandon_wait_seconds": average_ms(
                raw.get("abandon_wait_total_ms"), raw.get("abandon_wait_count")
            ),
            "avg_queue_wait_seconds": average_ms(
                raw.get("queue_wait_total_ms"), raw.get("queue_wait_count")
            ),
            "max_queue_wait_seconds": (
                float(maximum) / 1000.0 if maximum is not None else None
            ),
            "queue_service_level_20s": ratio(
                raw.get("service_level_answered_count"), raw.get("service_level_count")
            ),
        }
