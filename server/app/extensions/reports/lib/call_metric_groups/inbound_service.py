"""Inbound human-service metric group."""
from __future__ import annotations

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord

from ...schemas import MetricDistribution, MetricDistributionSlice, MetricFormat, MetricLevel
from .base import (
    CallMetricDescriptor,
    CallMetricGroupProvider,
    CallOverallContext,
    average_milliseconds,
    count_when,
    enum_distribution,
    ratio,
)


def _finalized_inbound():
    cr = CallRecord
    return and_(
        cr.direction == "inbound",
        cr.lifecycle_status == "ended",
        cr.finalization_status == "completed",
    )


class InboundServiceGroup(CallMetricGroupProvider):
    key = "inbound_service"
    descriptors = [
        CallMetricDescriptor("inbound_human_request_count", projection_required=True),
        CallMetricDescriptor("inbound_human_wait_count", projection_required=True),
        CallMetricDescriptor("inbound_agent_ringing_count", projection_required=True),
        CallMetricDescriptor("inbound_agent_answered_count"),
        CallMetricDescriptor(
            "inbound_human_answer_rate",
            MetricFormat.PERCENT,
            MetricLevel.AUXILIARY,
            projection_required=True,
        ),
        CallMetricDescriptor(
            "inbound_queue_answer_rate",
            MetricFormat.PERCENT,
            MetricLevel.AUXILIARY,
            projection_required=True,
        ),
        CallMetricDescriptor("inbound_short_abandon_count", level=MetricLevel.AUXILIARY),
        CallMetricDescriptor(
            "inbound_short_abandon_rate",
            MetricFormat.PERCENT,
            MetricLevel.AUXILIARY,
            projection_required=True,
        ),
        CallMetricDescriptor(
            "inbound_avg_wait_seconds",
            MetricFormat.DURATION_SECONDS,
            MetricLevel.AUXILIARY,
            projection_required=True,
        ),
        CallMetricDescriptor(
            "inbound_service_level_20s",
            MetricFormat.PERCENT,
            MetricLevel.AUXILIARY,
            projection_required=True,
        ),
    ]

    def metric_columns(self) -> tuple:
        cr = CallRecord
        fi = _finalized_inbound()
        human_request = and_(fi, cr.human_service_requested_at.is_not(None))
        human_wait = and_(fi, cr.first_agent_wait_started_at.is_not(None))
        non_short_wait = and_(
            human_wait,
            or_(cr.call_result.is_(None), cr.call_result != "customer_short_abandon"),
        )
        return (
            count_when(human_request, "human_request_count"),
            count_when(human_wait, "human_wait_count"),
            count_when(and_(fi, cr.first_agent_offer_started_at.is_not(None)), "ringing_count"),
            count_when(and_(fi, cr.first_agent_connected_at.is_not(None)), "answered_count"),
            count_when(and_(human_request, cr.first_agent_connected_at.is_not(None)), "human_answered_count"),
            count_when(and_(human_wait, cr.first_agent_connected_at.is_not(None)), "queue_answered_count"),
            count_when(and_(fi, cr.call_result == "customer_short_abandon"), "short_abandon_count"),
            func.sum(cr.agent_wait_duration_ms).filter(
                and_(human_wait, cr.agent_wait_duration_ms.is_not(None))
            ).label("wait_ms_sum"),
            count_when(
                and_(human_wait, cr.agent_wait_duration_ms.is_not(None)),
                "wait_sample_count",
            ),
            count_when(non_short_wait, "service_level_denominator"),
            count_when(
                and_(
                    non_short_wait,
                    cr.first_agent_connected_at.is_not(None),
                    cr.agent_wait_duration_ms <= 20_000,
                ),
                "service_level_numerator",
            ),
        )

    def values_from_row(self, row) -> dict[str, float | None]:
        requests = int(row.human_request_count or 0)
        waits = int(row.human_wait_count or 0)
        short = int(row.short_abandon_count or 0)
        return {
            "inbound_human_request_count": requests,
            "inbound_human_wait_count": waits,
            "inbound_agent_ringing_count": int(row.ringing_count or 0),
            "inbound_agent_answered_count": int(row.answered_count or 0),
            "inbound_human_answer_rate": ratio(row.human_answered_count, requests),
            "inbound_queue_answer_rate": ratio(row.queue_answered_count, waits),
            "inbound_short_abandon_count": short,
            "inbound_short_abandon_rate": ratio(short, waits),
            "inbound_avg_wait_seconds": average_milliseconds(row.wait_ms_sum, row.wait_sample_count),
            "inbound_service_level_20s": ratio(
                row.service_level_numerator,
                row.service_level_denominator,
            ),
        }

    async def summary_distributions(
        self,
        db: AsyncSession,
        ctx: CallOverallContext,
    ) -> list[MetricDistribution]:
        fi = _finalized_inbound()
        values = await self.summary(db, ctx)
        funnel_keys = (
            "inbound_human_request_count",
            "inbound_human_wait_count",
            "inbound_agent_ringing_count",
            "inbound_agent_answered_count",
        )
        funnel = MetricDistribution(
            key="inbound_human_funnel",
            group=self.key,
            total=int(values["inbound_human_request_count"] or 0),
            slices=[
                MetricDistributionSlice(key=key, label=key, value=int(values[key] or 0))
                for key in funnel_keys
            ],
        )
        return [
            await enum_distribution(
                db,
                ctx,
                distribution_key="inbound_call_result",
                group=self.key,
                value_column=CallRecord.call_result,
                extra_filters=(fi,),
            ),
            funnel,
        ]
