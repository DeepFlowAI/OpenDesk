"""Outbound-service metric group."""
from __future__ import annotations

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord

from ...schemas import MetricFormat, MetricLevel
from .base import (
    CallMetricDescriptor,
    CallMetricGroupProvider,
    CallOverallContext,
    average_milliseconds,
    count_when,
    enum_distribution,
    ratio,
)


def _finalized_outbound():
    cr = CallRecord
    return and_(
        cr.direction == "outbound",
        cr.lifecycle_status == "ended",
        cr.finalization_status == "completed",
    )


class OutboundServiceGroup(CallMetricGroupProvider):
    key = "outbound_service"
    descriptors = [
        CallMetricDescriptor("outbound_attempt_count"),
        CallMetricDescriptor("outbound_customer_connected_count"),
        CallMetricDescriptor("outbound_agent_connected_count"),
        CallMetricDescriptor("outbound_customer_connect_rate", MetricFormat.PERCENT, MetricLevel.AUXILIARY),
        CallMetricDescriptor("outbound_avg_customer_ring_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY),
        CallMetricDescriptor("outbound_avg_talk_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY),
    ]

    def metric_columns(self) -> tuple:
        cr = CallRecord
        fo = _finalized_outbound()
        return (
            count_when(cr.direction == "outbound", "attempt_count"),
            count_when(fo, "finalized_outbound_count"),
            count_when(and_(fo, cr.customer_connected_at.is_not(None)), "customer_connected_count"),
            count_when(and_(fo, cr.first_agent_connected_at.is_not(None)), "agent_connected_count"),
            func.sum(cr.customer_ring_duration_ms).filter(
                and_(fo, cr.customer_ring_duration_ms.is_not(None))
            ).label("ring_ms_sum"),
            count_when(
                and_(fo, cr.customer_ring_duration_ms.is_not(None)),
                "ring_sample_count",
            ),
            func.sum(cr.customer_agent_talk_duration_ms).filter(
                and_(
                    fo,
                    cr.first_agent_connected_at.is_not(None),
                    cr.customer_agent_talk_duration_ms.is_not(None),
                )
            ).label("talk_ms_sum"),
            count_when(
                and_(
                    fo,
                    cr.first_agent_connected_at.is_not(None),
                    cr.customer_agent_talk_duration_ms.is_not(None),
                ),
                "talk_sample_count",
            ),
        )

    def values_from_row(self, row) -> dict[str, float | None]:
        finalized = int(row.finalized_outbound_count or 0)
        customer_connected = int(row.customer_connected_count or 0)
        return {
            "outbound_attempt_count": int(row.attempt_count or 0),
            "outbound_customer_connected_count": customer_connected,
            "outbound_customer_connect_rate": ratio(customer_connected, finalized),
            "outbound_agent_connected_count": int(row.agent_connected_count or 0),
            "outbound_avg_customer_ring_seconds": average_milliseconds(
                row.ring_ms_sum,
                row.ring_sample_count,
            ),
            "outbound_avg_talk_seconds": average_milliseconds(
                row.talk_ms_sum,
                row.talk_sample_count,
            ),
        }

    async def summary_distributions(
        self,
        db: AsyncSession,
        ctx: CallOverallContext,
    ) -> list:
        outbound = CallRecord.direction == "outbound"
        finalized = _finalized_outbound()
        return [
            await enum_distribution(
                db,
                ctx,
                distribution_key="outbound_call_source",
                group=self.key,
                value_column=CallRecord.call_source,
                extra_filters=(outbound,),
            ),
            await enum_distribution(
                db,
                ctx,
                distribution_key="outbound_call_result",
                group=self.key,
                value_column=CallRecord.call_result,
                extra_filters=(finalized,),
            ),
        ]
