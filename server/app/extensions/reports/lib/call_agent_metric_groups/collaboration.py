"""Employee transfer and consultation metrics."""
from ...schemas import MetricFormat, MetricLevel
from .base import AgentMetricDescriptor, AgentMetricGroupProvider, ratio


class AgentCollaborationGroup(AgentMetricGroupProvider):
    key = "collaboration"
    descriptors = [
        AgentMetricDescriptor("transfer_attempt_count"),
        AgentMetricDescriptor("transfer_completed_count"),
        AgentMetricDescriptor("transfer_success_rate", MetricFormat.PERCENT),
        AgentMetricDescriptor("transfer_failed_count", level=MetricLevel.AUXILIARY),
        AgentMetricDescriptor("consult_attempt_count"),
        AgentMetricDescriptor("consult_connected_count", level=MetricLevel.AUXILIARY),
        AgentMetricDescriptor("consult_success_rate", MetricFormat.PERCENT, MetricLevel.AUXILIARY),
        AgentMetricDescriptor("conference_join_count", level=MetricLevel.AUXILIARY),
    ]

    def values(self, raw: dict[str, float | int | None]) -> dict[str, float | None]:
        return {
            "transfer_attempt_count": int(raw.get("transfer_attempt_count") or 0),
            "transfer_completed_count": int(raw.get("transfer_completed_count") or 0),
            "transfer_success_rate": ratio(
                raw.get("transfer_completed_count"), raw.get("transfer_terminal_count")
            ),
            "transfer_failed_count": int(raw.get("transfer_failed_count") or 0),
            "consult_attempt_count": int(raw.get("consult_attempt_count") or 0),
            "consult_connected_count": int(raw.get("consult_connected_count") or 0),
            "consult_success_rate": ratio(
                raw.get("consult_connected_count"), raw.get("consult_terminal_count")
            ),
            "conference_join_count": int(raw.get("conference_join_count") or 0),
        }
