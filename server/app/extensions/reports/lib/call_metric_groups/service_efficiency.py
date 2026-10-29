"""Service-efficiency metric group."""
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


def _finalized():
    cr = CallRecord
    return and_(cr.lifecycle_status == "ended", cr.finalization_status == "completed")


class ServiceEfficiencyGroup(CallMetricGroupProvider):
    key = "service_efficiency"
    descriptors = [
        CallMetricDescriptor("human_served_call_count"),
        CallMetricDescriptor("total_human_talk_seconds", MetricFormat.DURATION_SECONDS),
        CallMetricDescriptor("avg_human_talk_seconds", MetricFormat.DURATION_SECONDS),
        CallMetricDescriptor("avg_total_duration_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY),
        CallMetricDescriptor("customer_hangup_rate", MetricFormat.PERCENT, MetricLevel.AUXILIARY),
    ]

    def metric_columns(self) -> tuple:
        cr = CallRecord
        finalized = _finalized()
        human_sample = and_(
            finalized,
            cr.first_agent_connected_at.is_not(None),
            cr.customer_agent_talk_duration_ms.is_not(None),
        )
        total_sample = and_(finalized, cr.total_duration_ms.is_not(None))
        hangup_sample = and_(finalized, cr.hangup_party.is_not(None))
        return (
            count_when(
                and_(finalized, cr.first_agent_connected_at.is_not(None)),
                "human_served_count",
            ),
            func.sum(cr.customer_agent_talk_duration_ms).filter(finalized).label("human_talk_ms_sum"),
            count_when(human_sample, "human_talk_sample_count"),
            func.sum(cr.total_duration_ms).filter(total_sample).label("total_duration_ms_sum"),
            count_when(total_sample, "total_duration_sample_count"),
            count_when(and_(finalized, cr.hangup_party == "customer"), "customer_hangup_count"),
            count_when(hangup_sample, "hangup_sample_count"),
        )

    def values_from_row(self, row) -> dict[str, float | None]:
        total_human_seconds = float(row.human_talk_ms_sum or 0) / 1000.0
        return {
            "human_served_call_count": int(row.human_served_count or 0),
            "total_human_talk_seconds": total_human_seconds,
            "avg_human_talk_seconds": average_milliseconds(
                row.human_talk_ms_sum,
                row.human_talk_sample_count,
            ),
            "avg_total_duration_seconds": average_milliseconds(
                row.total_duration_ms_sum,
                row.total_duration_sample_count,
            ),
            "customer_hangup_rate": ratio(
                row.customer_hangup_count,
                row.hangup_sample_count,
            ),
        }

    async def summary_distributions(
        self,
        db: AsyncSession,
        ctx: CallOverallContext,
    ) -> list:
        finalized = _finalized()
        return [
            await enum_distribution(
                db,
                ctx,
                distribution_key="call_result",
                group=self.key,
                value_column=CallRecord.call_result,
                extra_filters=(finalized,),
            ),
            await enum_distribution(
                db,
                ctx,
                distribution_key="hangup_party",
                group=self.key,
                value_column=CallRecord.hangup_party,
                extra_filters=(finalized,),
            ),
            await enum_distribution(
                db,
                ctx,
                distribution_key="hangup_stage",
                group=self.key,
                value_column=CallRecord.hangup_stage,
                extra_filters=(finalized,),
            ),
        ]
