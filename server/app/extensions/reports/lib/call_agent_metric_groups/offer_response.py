"""Employee Offer response metrics."""
from ...schemas import MetricFormat, MetricLevel
from .base import AgentMetricDescriptor, AgentMetricGroupProvider, average_ms, ratio


class AgentOfferResponseGroup(AgentMetricGroupProvider):
    key = "offer_response"
    descriptors = [
        AgentMetricDescriptor("offered_call_count"),
        AgentMetricDescriptor("offer_attempt_count"),
        AgentMetricDescriptor("offer_accepted_count"),
        AgentMetricDescriptor("offer_accept_rate", MetricFormat.PERCENT),
        AgentMetricDescriptor("offer_rejected_count", level=MetricLevel.AUXILIARY),
        AgentMetricDescriptor("offer_timeout_count"),
        AgentMetricDescriptor("offer_timeout_rate", MetricFormat.PERCENT, MetricLevel.AUXILIARY),
        AgentMetricDescriptor(
            "avg_offer_response_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY
        ),
    ]

    def values(self, raw: dict[str, float | int | None]) -> dict[str, float | None]:
        denominator = raw.get("offer_rate_denominator")
        return {
            "offered_call_count": int(raw.get("offered_call_count") or 0),
            "offer_attempt_count": int(raw.get("offer_attempt_count") or 0),
            "offer_accepted_count": int(raw.get("offer_accepted_count") or 0),
            "offer_accept_rate": ratio(raw.get("offer_accepted_count"), denominator),
            "offer_rejected_count": int(raw.get("offer_rejected_count") or 0),
            "offer_timeout_count": int(raw.get("offer_timeout_count") or 0),
            "offer_timeout_rate": ratio(raw.get("offer_timeout_count"), denominator),
            "avg_offer_response_seconds": average_ms(
                raw.get("offer_response_total_ms"), raw.get("offer_response_count")
            ),
        }
