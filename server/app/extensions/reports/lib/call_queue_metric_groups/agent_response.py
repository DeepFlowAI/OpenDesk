"""Agent offer-response metrics."""
from ...schemas import MetricFormat, MetricLevel
from .base import QueueMetricDescriptor, QueueMetricGroupProvider, ratio


class QueueAgentResponseGroup(QueueMetricGroupProvider):
    key = "agent_response"
    descriptors = [
        QueueMetricDescriptor("offered_call_count"),
        QueueMetricDescriptor("offer_attempt_count"),
        QueueMetricDescriptor("offer_accepted_count"),
        QueueMetricDescriptor("offer_rejected_count", level=MetricLevel.AUXILIARY),
        QueueMetricDescriptor("offer_timeout_count", level=MetricLevel.AUXILIARY),
        QueueMetricDescriptor("offer_accept_rate", MetricFormat.PERCENT, MetricLevel.AUXILIARY),
    ]

    def values(
        self, raw: dict[str, float | int | None]
    ) -> dict[str, float | None]:
        return {
            "offered_call_count": int(raw.get("offered_call_count") or 0),
            "offer_attempt_count": int(raw.get("offer_attempt_count") or 0),
            "offer_accepted_count": int(raw.get("offer_accepted_count") or 0),
            "offer_rejected_count": int(raw.get("offer_rejected_count") or 0),
            "offer_timeout_count": int(raw.get("offer_timeout_count") or 0),
            "offer_accept_rate": ratio(
                raw.get("offer_accepted_count"), raw.get("offer_rate_denominator")
            ),
        }
