"""Call overview metric group."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord

from ...schemas import MetricLevel
from .base import (
    CallMetricDescriptor,
    CallMetricGroupProvider,
    CallOverallContext,
    count_when,
    enum_distribution,
)


class CallOverviewGroup(CallMetricGroupProvider):
    key = "call_overview"
    descriptors = [
        CallMetricDescriptor("call_count"),
        CallMetricDescriptor("inbound_call_count"),
        CallMetricDescriptor("outbound_call_count"),
        CallMetricDescriptor("active_call_count", level=MetricLevel.AUXILIARY),
        CallMetricDescriptor("ended_call_count", level=MetricLevel.AUXILIARY),
    ]

    def metric_columns(self) -> tuple:
        cr = CallRecord
        return (
            count_when(cr.id.is_not(None), "call_count"),
            count_when(cr.direction == "inbound", "inbound_call_count"),
            count_when(cr.direction == "outbound", "outbound_call_count"),
            count_when(cr.lifecycle_status == "active", "active_call_count"),
            count_when(cr.lifecycle_status == "ended", "ended_call_count"),
        )

    def values_from_row(self, row) -> dict[str, float | None]:
        return {
            "call_count": int(row.call_count or 0),
            "inbound_call_count": int(row.inbound_call_count or 0),
            "outbound_call_count": int(row.outbound_call_count or 0),
            "active_call_count": int(row.active_call_count or 0),
            "ended_call_count": int(row.ended_call_count or 0),
        }

    async def summary_distributions(
        self,
        db: AsyncSession,
        ctx: CallOverallContext,
    ) -> list:
        finalized = (
            CallRecord.lifecycle_status == "ended",
            CallRecord.finalization_status == "completed",
        )
        return [
            await enum_distribution(
                db,
                ctx,
                distribution_key="direction",
                group=self.key,
                value_column=CallRecord.direction,
            ),
            await enum_distribution(
                db,
                ctx,
                distribution_key="call_source",
                group=self.key,
                value_column=CallRecord.call_source,
            ),
            await enum_distribution(
                db,
                ctx,
                distribution_key="actual_reception_type",
                group=self.key,
                value_column=CallRecord.actual_reception_type,
                extra_filters=finalized,
                null_key="not_formed",
            ),
        ]
