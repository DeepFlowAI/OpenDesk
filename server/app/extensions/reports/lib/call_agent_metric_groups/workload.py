"""Employee reception workload metrics."""
from ...schemas import MetricLevel
from .base import AgentMetricDescriptor, AgentMetricGroupProvider


class AgentWorkloadGroup(AgentMetricGroupProvider):
    key = "workload"
    descriptors = [
        AgentMetricDescriptor("participated_call_count"),
        AgentMetricDescriptor("handled_call_count"),
        AgentMetricDescriptor("reception_segment_count"),
        AgentMetricDescriptor("inbound_handled_call_count"),
        AgentMetricDescriptor("outbound_attempt_count"),
        AgentMetricDescriptor("outbound_customer_answered_count"),
        AgentMetricDescriptor("outbound_handled_call_count", level=MetricLevel.AUXILIARY),
        AgentMetricDescriptor("transfer_in_segment_count", level=MetricLevel.AUXILIARY),
    ]

    def values(self, raw: dict[str, float | int | None]) -> dict[str, float | None]:
        return {item.key: int(raw.get(item.key) or 0) for item in self.descriptors}
