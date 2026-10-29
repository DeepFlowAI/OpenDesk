"""Queue answer and loss metrics."""
from ...schemas import MetricFormat, MetricLevel
from .base import QueueMetricDescriptor, QueueMetricGroupProvider, ratio


class QueueOutcomesGroup(QueueMetricGroupProvider):
    key = "queue_outcomes"
    descriptors = [
        QueueMetricDescriptor("queue_answered_count"),
        QueueMetricDescriptor("queue_answer_rate", MetricFormat.PERCENT),
        QueueMetricDescriptor("queue_abandoned_count"),
        QueueMetricDescriptor("queue_abandon_rate", MetricFormat.PERCENT),
        QueueMetricDescriptor("queue_short_abandon_count", level=MetricLevel.AUXILIARY),
        QueueMetricDescriptor(
            "queue_short_abandon_rate", MetricFormat.PERCENT, MetricLevel.AUXILIARY
        ),
        QueueMetricDescriptor("queue_timeout_count", level=MetricLevel.AUXILIARY),
        QueueMetricDescriptor("queue_transfer_out_count", level=MetricLevel.AUXILIARY),
    ]

    def values(
        self, raw: dict[str, float | int | None]
    ) -> dict[str, float | None]:
        denominator = raw.get("valid_result_count")
        return {
            "queue_answered_count": int(raw.get("queue_answered_count") or 0),
            "queue_answer_rate": ratio(raw.get("queue_answered_count"), denominator),
            "queue_abandoned_count": int(raw.get("queue_abandoned_count") or 0),
            "queue_abandon_rate": ratio(raw.get("queue_abandoned_count"), denominator),
            "queue_short_abandon_count": int(raw.get("queue_short_abandon_count") or 0),
            "queue_short_abandon_rate": ratio(
                raw.get("queue_short_abandon_count"), denominator
            ),
            "queue_timeout_count": int(raw.get("queue_timeout_count") or 0),
            "queue_transfer_out_count": int(raw.get("queue_transfer_out_count") or 0),
        }
