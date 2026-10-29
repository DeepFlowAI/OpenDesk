"""Queue traffic metrics."""
from .base import QueueMetricDescriptor, QueueMetricGroupProvider


class QueueFlowGroup(QueueMetricGroupProvider):
    key = "queue_flow"
    descriptors = [
        QueueMetricDescriptor("queue_call_count"),
        QueueMetricDescriptor("queue_entry_count"),
        QueueMetricDescriptor("first_queue_entry_count"),
        QueueMetricDescriptor("transfer_in_entry_count"),
    ]

    def values(
        self, raw: dict[str, float | int | None]
    ) -> dict[str, float | None]:
        return {
            descriptor.key: int(raw.get(descriptor.key) or 0)
            for descriptor in self.descriptors
        }
