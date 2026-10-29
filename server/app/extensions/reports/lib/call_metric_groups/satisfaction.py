"""Call satisfaction metric group."""
from __future__ import annotations

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord

from ...schemas import MetricFormat, MetricLevel
from .base import (
    CallMetricDescriptor,
    CallMetricGroupProvider,
    CallOverallContext,
    count_when,
    enum_distribution,
    ratio,
)


def _satisfaction_sample():
    cr = CallRecord
    return and_(cr.lifecycle_status == "ended", cr.satisfaction_result.is_not(None))


class SatisfactionGroup(CallMetricGroupProvider):
    key = "satisfaction"
    descriptors = [
        CallMetricDescriptor("survey_triggered_count"),
        CallMetricDescriptor("survey_answered_count"),
        CallMetricDescriptor("survey_participation_rate", MetricFormat.PERCENT),
        CallMetricDescriptor("survey_completed_count", level=MetricLevel.AUXILIARY),
        CallMetricDescriptor("survey_completion_rate", MetricFormat.PERCENT, MetricLevel.AUXILIARY),
    ]

    def metric_columns(self) -> tuple:
        cr = CallRecord
        sample = _satisfaction_sample()
        triggered = and_(
            sample,
            cr.satisfaction_trigger_source.is_not(None),
            cr.satisfaction_trigger_source != "not_surveyed",
        )
        answered = and_(triggered, cr.satisfaction_answer_count > 0)
        completed = and_(triggered, cr.satisfaction_result == "completed")
        return (
            count_when(triggered, "triggered_count"),
            count_when(answered, "answered_count"),
            count_when(completed, "completed_count"),
        )

    def values_from_row(self, row) -> dict[str, float | None]:
        triggered = int(row.triggered_count or 0)
        answered = int(row.answered_count or 0)
        completed = int(row.completed_count or 0)
        return {
            "survey_triggered_count": triggered,
            "survey_answered_count": answered,
            "survey_participation_rate": ratio(answered, triggered),
            "survey_completed_count": completed,
            "survey_completion_rate": ratio(completed, triggered),
        }

    async def summary_distributions(
        self,
        db: AsyncSession,
        ctx: CallOverallContext,
    ) -> list:
        sample = _satisfaction_sample()
        return [
            await enum_distribution(
                db,
                ctx,
                distribution_key="satisfaction_result",
                group=self.key,
                value_column=CallRecord.satisfaction_result,
                extra_filters=(sample,),
            ),
            await enum_distribution(
                db,
                ctx,
                distribution_key="satisfaction_trigger_source",
                group=self.key,
                value_column=CallRecord.satisfaction_trigger_source,
                extra_filters=(sample,),
            ),
            await enum_distribution(
                db,
                ctx,
                distribution_key="satisfaction_primary_option",
                group=self.key,
                value_column=CallRecord.satisfaction_primary_option_id,
                label_column=CallRecord.satisfaction_primary_option_label,
                extra_filters=(sample,),
            ),
        ]
