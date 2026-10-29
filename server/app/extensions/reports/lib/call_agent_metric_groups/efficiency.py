"""Employee handling-efficiency metrics."""
from ...schemas import MetricFormat, MetricLevel
from .base import AgentMetricDescriptor, AgentMetricGroupProvider, average_ms, seconds


class AgentEfficiencyGroup(AgentMetricGroupProvider):
    key = "efficiency"
    descriptors = [
        AgentMetricDescriptor("total_talk_seconds", MetricFormat.DURATION_SECONDS),
        AgentMetricDescriptor("avg_talk_seconds", MetricFormat.DURATION_SECONDS),
        AgentMetricDescriptor("held_segment_count", level=MetricLevel.AUXILIARY),
        AgentMetricDescriptor("total_hold_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY),
        AgentMetricDescriptor("avg_hold_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY),
        AgentMetricDescriptor(
            "total_after_call_work_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY
        ),
        AgentMetricDescriptor(
            "avg_after_call_work_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY
        ),
        AgentMetricDescriptor("avg_handle_seconds", MetricFormat.DURATION_SECONDS),
    ]

    def values(self, raw: dict[str, float | int | None]) -> dict[str, float | None]:
        return {
            "total_talk_seconds": seconds(raw.get("talk_total_ms"), raw.get("talk_count")),
            "avg_talk_seconds": average_ms(raw.get("talk_total_ms"), raw.get("talk_count")),
            "held_segment_count": int(raw.get("held_segment_count") or 0),
            "total_hold_seconds": seconds(raw.get("hold_total_ms"), raw.get("hold_count")),
            "avg_hold_seconds": average_ms(raw.get("hold_total_ms"), raw.get("hold_count")),
            "total_after_call_work_seconds": seconds(
                raw.get("acw_total_ms"), raw.get("acw_count")
            ),
            "avg_after_call_work_seconds": average_ms(
                raw.get("acw_total_ms"), raw.get("acw_count")
            ),
            "avg_handle_seconds": average_ms(
                raw.get("handle_total_ms"), raw.get("handle_count")
            ),
        }
