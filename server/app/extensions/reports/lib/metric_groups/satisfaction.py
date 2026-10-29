"""``satisfaction`` metric group — "were surveys invited and how did visitors rate".

Source: ``satisfaction_survey_records`` joined to ``conversations``. Only the
current satisfaction config version is aggregated; historical versions stay in
session-record detail views. Pure-bot sessions are excluded from the base.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.conversation import Conversation
from app.models.satisfaction_survey_config import SatisfactionSurveyConfig, SatisfactionSurveyConfigVersion
from app.models.satisfaction_survey_record import SatisfactionSurveyRecord

from ...schemas import MetricDistribution, MetricDistributionSlice, MetricFormat, MetricLevel
from ..buckets import TimeBucket, TrendType
from ..queries import _absolute_bucket_key_sql, _distribution_bucket_key_sql
from .base import MetricDescriptor, MetricGroupProvider, OverallContext

_INVITATION = "satisfaction_invitation_count"
_SUBMISSION = "satisfaction_submission_count"
_PARTICIPATION_RATE = "satisfaction_participation_rate"
_SUBMISSION_RATE = "satisfaction_submission_rate"
_PRODUCT = "product_satisfaction_count"

_RESOLUTION_DISTRIBUTION = "satisfaction_resolution"
_SERVICE_DISTRIBUTION = "service_satisfaction_rating"
_PRODUCT_DISTRIBUTION = "product_satisfaction_rating"
_DISTRIBUTION_METRIC_SEPARATOR = ":"


@dataclass(frozen=True)
class _Option:
    key: str
    label: str


@dataclass(frozen=True)
class _Settings:
    enabled: bool
    current_version: int | None = None
    service_enabled: bool = False
    product_enabled: bool = False
    show_resolution: bool = False
    service_options: tuple[_Option, ...] = ()
    product_options: tuple[_Option, ...] = ()

    @property
    def has_any_type(self) -> bool:
        return self.service_enabled or self.product_enabled


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _submitted(record: type[SatisfactionSurveyRecord]) -> ColumnElement:
    return or_(record.status == "submitted", record.submitted_at.is_not(None))


def _enabled_options(settings: dict) -> tuple[_Option, ...]:
    return tuple(
        _Option(
            key=str(option.get("key")),
            label=str(option.get("name") or option.get("key")),
        )
        for option in settings.get("rating_options") or []
        if option.get("enabled", True) and option.get("key")
    )


def _distribution(
    key: str,
    slices: list[MetricDistributionSlice],
) -> MetricDistribution:
    return MetricDistribution(
        key=key,
        group=SatisfactionGroup.key,
        total=sum(item.value for item in slices),
        slices=slices,
    )


def _distribution_metric_key(distribution_key: str, slice_key: str) -> str:
    return f"{distribution_key}{_DISTRIBUTION_METRIC_SEPARATOR}{slice_key}"


def _distribution_trend_descriptors(settings: _Settings) -> list[MetricDescriptor]:
    descriptors: list[MetricDescriptor] = []
    if settings.show_resolution:
        descriptors.extend([
            MetricDescriptor(_distribution_metric_key(_RESOLUTION_DISTRIBUTION, "resolved")),
            MetricDescriptor(_distribution_metric_key(_RESOLUTION_DISTRIBUTION, "unresolved")),
        ])
    if settings.service_enabled:
        descriptors.extend(
            MetricDescriptor(_distribution_metric_key(_SERVICE_DISTRIBUTION, option.key))
            for option in settings.service_options
        )
    if settings.product_enabled:
        descriptors.extend(
            MetricDescriptor(_distribution_metric_key(_PRODUCT_DISTRIBUTION, option.key))
            for option in settings.product_options
        )
    return descriptors


def _bucket_sql(trend_type: TrendType, ctx: OverallContext, column: ColumnElement) -> ColumnElement:
    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        return _distribution_bucket_key_sql(trend_type, ctx.tz, column)
    return _absolute_bucket_key_sql(trend_type, ctx.tz, column)


class SatisfactionGroup(MetricGroupProvider):
    key = "satisfaction"
    descriptors = [
        MetricDescriptor(_INVITATION, level=MetricLevel.PRIMARY),
        MetricDescriptor(_SUBMISSION, level=MetricLevel.PRIMARY),
        MetricDescriptor(
            _PARTICIPATION_RATE,
            format=MetricFormat.PERCENT,
            level=MetricLevel.PRIMARY,
            trendable=False,
        ),
        MetricDescriptor(
            _SUBMISSION_RATE,
            format=MetricFormat.PERCENT,
            level=MetricLevel.AUXILIARY,
            trendable=False,
        ),
        MetricDescriptor(_PRODUCT, level=MetricLevel.AUXILIARY),
    ]

    async def _settings(self, db: AsyncSession, tenant_id: int) -> _Settings:
        cfg = (
            await db.execute(
                select(SatisfactionSurveyConfig).where(SatisfactionSurveyConfig.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not cfg or not cfg.enabled or cfg.current_version is None:
            return _Settings(enabled=False)

        version = (
            await db.execute(
                select(SatisfactionSurveyConfigVersion).where(
                    SatisfactionSurveyConfigVersion.tenant_id == tenant_id,
                    SatisfactionSurveyConfigVersion.version == cfg.current_version,
                )
            )
        ).scalar_one_or_none()
        snapshot = (version.snapshot if version else None) or {
            "enabled": cfg.enabled,
            "service": cfg.service_settings or {},
            "product": cfg.product_settings or {},
        }
        if not snapshot.get("enabled", True):
            return _Settings(enabled=False, current_version=cfg.current_version)

        service = snapshot.get("service") or {}
        product = snapshot.get("product") or {}
        return _Settings(
            enabled=True,
            current_version=cfg.current_version,
            service_enabled=bool(service.get("enabled")),
            product_enabled=bool(product.get("enabled")),
            show_resolution=bool(service.get("enabled") and service.get("show_resolution")),
            service_options=_enabled_options(service),
            product_options=_enabled_options(product),
        )

    def _conversation_filter(self, ctx: OverallContext) -> list[ColumnElement]:
        conv = Conversation
        filters: list[ColumnElement] = [
            conv.tenant_id == ctx.tenant_id,
            or_(conv.had_bot_session.is_(False), conv.bot_handoff_succeeded.is_(True)),
        ]
        if ctx.agent_ids is not None:
            filters.append(conv.agent_id.in_(ctx.agent_ids))
        return filters

    def _record_filter(self, ctx: OverallContext, settings: _Settings) -> list[ColumnElement]:
        rec = SatisfactionSurveyRecord
        filters: list[ColumnElement] = [
            rec.tenant_id == ctx.tenant_id,
            rec.config_version == settings.current_version,
            *self._conversation_filter(ctx),
        ]
        return filters

    def _empty_values(self, settings: _Settings) -> dict[str, float | None]:
        values: dict[str, float | None] = {
            _INVITATION: 0,
            _SUBMISSION: 0,
            _PARTICIPATION_RATE: None,
            _SUBMISSION_RATE: None,
        }
        if settings.product_enabled:
            values[_PRODUCT] = 0
        return values

    async def visible_trend_descriptors(
        self,
        db: AsyncSession,
        ctx: OverallContext,
    ) -> list[MetricDescriptor]:
        settings = await self._settings(db, ctx.tenant_id)
        if not settings.enabled or not settings.has_any_type:
            return []
        keys = {_INVITATION, _SUBMISSION}
        if settings.product_enabled:
            keys.add(_PRODUCT)
        return [
            *[d for d in self.trendable_descriptors() if d.key in keys],
            *_distribution_trend_descriptors(settings),
        ]

    async def summary(self, db: AsyncSession, ctx: OverallContext) -> dict[str, float | None]:
        settings = await self._settings(db, ctx.tenant_id)
        if not settings.enabled or not settings.has_any_type:
            return {}
        if ctx.agent_ids is not None and not ctx.agent_ids:
            return self._empty_values(settings)

        conv = Conversation
        rec = SatisfactionSurveyRecord

        human_sessions = (
            await db.execute(
                select(func.count(conv.id)).where(
                    *self._conversation_filter(ctx),
                    conv.started_at >= ctx.range_start,
                    conv.started_at < ctx.range_end,
                )
            )
        ).scalar_one()

        row = (
            await db.execute(
                select(
                    func.sum(case((rec.invited_at.is_not(None), 1), else_=0)).label(_INVITATION),
                    func.sum(case((_submitted(rec), 1), else_=0)).label(_SUBMISSION),
                    func.sum(case((rec.product_result.is_not(None), 1), else_=0)).label(_PRODUCT),
                )
                .select_from(rec)
                .join(conv, conv.id == rec.conversation_id)
                .where(
                    *self._record_filter(ctx, settings),
                    rec.submitted_at >= ctx.range_start,
                    rec.submitted_at < ctx.range_end,
                )
            )
        ).one()

        invitation_count = (
            await db.execute(
                select(func.count(rec.id))
                .select_from(rec)
                .join(conv, conv.id == rec.conversation_id)
                .where(
                    *self._record_filter(ctx, settings),
                    rec.invited_at >= ctx.range_start,
                    rec.invited_at < ctx.range_end,
                )
            )
        ).scalar_one()

        submission_count = int(row.satisfaction_submission_count or 0)
        invitation_count = int(invitation_count or 0)
        values: dict[str, float | None] = {
            _INVITATION: invitation_count,
            _SUBMISSION: submission_count,
            _PARTICIPATION_RATE: _rate(submission_count, int(human_sessions or 0)),
            _SUBMISSION_RATE: _rate(submission_count, invitation_count),
        }
        if settings.product_enabled:
            values[_PRODUCT] = int(row.product_satisfaction_count or 0)
        return values

    def _empty_distributions(self, settings: _Settings) -> list[MetricDistribution]:
        distributions: list[MetricDistribution] = []
        if settings.show_resolution:
            distributions.append(
                _distribution(
                    _RESOLUTION_DISTRIBUTION,
                    [
                        MetricDistributionSlice(key="resolved", label="resolved", value=0),
                        MetricDistributionSlice(key="unresolved", label="unresolved", value=0),
                    ],
                )
            )
        if settings.service_enabled:
            distributions.append(
                _distribution(
                    _SERVICE_DISTRIBUTION,
                    [
                        MetricDistributionSlice(key=option.key, label=option.label, value=0)
                        for option in settings.service_options
                    ],
                )
            )
        if settings.product_enabled:
            distributions.append(
                _distribution(
                    _PRODUCT_DISTRIBUTION,
                    [
                        MetricDistributionSlice(key=option.key, label=option.label, value=0)
                        for option in settings.product_options
                    ],
                )
            )
        return distributions

    async def _resolution_distribution(
        self,
        db: AsyncSession,
        ctx: OverallContext,
        settings: _Settings,
    ) -> MetricDistribution:
        rec = SatisfactionSurveyRecord
        conv = Conversation
        resolved = rec.service_result["resolved"].astext
        rows = (
            await db.execute(
                select(
                    resolved.label("resolved_key"),
                    func.count(rec.id).label("count_value"),
                )
                .select_from(rec)
                .join(conv, conv.id == rec.conversation_id)
                .where(
                    *self._record_filter(ctx, settings),
                    _submitted(rec),
                    rec.submitted_at >= ctx.range_start,
                    rec.submitted_at < ctx.range_end,
                    resolved.in_(["true", "false"]),
                )
                .group_by(resolved)
            )
        ).all()
        counts = {str(row.resolved_key): int(row.count_value or 0) for row in rows}
        return _distribution(
            _RESOLUTION_DISTRIBUTION,
            [
                MetricDistributionSlice(key="resolved", label="resolved", value=counts.get("true", 0)),
                MetricDistributionSlice(key="unresolved", label="unresolved", value=counts.get("false", 0)),
            ],
        )

    async def _rating_distribution(
        self,
        db: AsyncSession,
        ctx: OverallContext,
        settings: _Settings,
        *,
        key: str,
        result_field: str,
        options: tuple[_Option, ...],
    ) -> MetricDistribution:
        rec = SatisfactionSurveyRecord
        conv = Conversation
        result_column = rec.service_result if result_field == "service" else rec.product_result
        option_key = result_column["option_key"].astext
        rows = (
            await db.execute(
                select(
                    option_key.label("option_key"),
                    func.count(rec.id).label("count_value"),
                )
                .select_from(rec)
                .join(conv, conv.id == rec.conversation_id)
                .where(
                    *self._record_filter(ctx, settings),
                    _submitted(rec),
                    rec.submitted_at >= ctx.range_start,
                    rec.submitted_at < ctx.range_end,
                    result_column.is_not(None),
                )
                .group_by(option_key)
            )
        ).all()
        counts = {str(row.option_key): int(row.count_value or 0) for row in rows if row.option_key is not None}
        return _distribution(
            key,
            [
                MetricDistributionSlice(key=option.key, label=option.label, value=counts.get(option.key, 0))
                for option in options
            ],
        )

    async def summary_distributions(
        self,
        db: AsyncSession,
        ctx: OverallContext,
    ) -> list[MetricDistribution]:
        settings = await self._settings(db, ctx.tenant_id)
        if not settings.enabled or not settings.has_any_type:
            return []
        if ctx.agent_ids is not None and not ctx.agent_ids:
            return self._empty_distributions(settings)

        distributions: list[MetricDistribution] = []
        if settings.show_resolution:
            distributions.append(await self._resolution_distribution(db, ctx, settings))
        if settings.service_enabled:
            distributions.append(
                await self._rating_distribution(
                    db,
                    ctx,
                    settings,
                    key=_SERVICE_DISTRIBUTION,
                    result_field="service",
                    options=settings.service_options,
                )
            )
        if settings.product_enabled:
            distributions.append(
                await self._rating_distribution(
                    db,
                    ctx,
                    settings,
                    key=_PRODUCT_DISTRIBUTION,
                    result_field="product",
                    options=settings.product_options,
                )
            )
        return distributions

    async def _add_resolution_trend_counts(
        self,
        db: AsyncSession,
        ctx: OverallContext,
        settings: _Settings,
        trend_type: TrendType,
        out: dict[object, dict[str, float | None]],
    ) -> None:
        rec = SatisfactionSurveyRecord
        conv = Conversation
        resolved = rec.service_result["resolved"].astext
        submitted_bucket = _bucket_sql(trend_type, ctx, rec.submitted_at)
        rows = (
            await db.execute(
                select(
                    submitted_bucket.label("bkey"),
                    resolved.label("resolved_key"),
                    func.count(rec.id).label("count_value"),
                )
                .select_from(rec)
                .join(conv, conv.id == rec.conversation_id)
                .where(
                    *self._record_filter(ctx, settings),
                    _submitted(rec),
                    rec.submitted_at >= ctx.range_start,
                    rec.submitted_at < ctx.range_end,
                    resolved.in_(["true", "false"]),
                )
                .group_by(literal_column("bkey"), resolved)
            )
        ).all()
        for row in rows:
            slice_key = "resolved" if str(row.resolved_key) == "true" else "unresolved"
            out.setdefault(row.bkey, {})[
                _distribution_metric_key(_RESOLUTION_DISTRIBUTION, slice_key)
            ] = int(row.count_value or 0)

    async def _add_rating_trend_counts(
        self,
        db: AsyncSession,
        ctx: OverallContext,
        settings: _Settings,
        trend_type: TrendType,
        out: dict[object, dict[str, float | None]],
        *,
        distribution_key: str,
        result_field: str,
        options: tuple[_Option, ...],
    ) -> None:
        if not options:
            return

        rec = SatisfactionSurveyRecord
        conv = Conversation
        result_column = rec.service_result if result_field == "service" else rec.product_result
        option_key = result_column["option_key"].astext
        submitted_bucket = _bucket_sql(trend_type, ctx, rec.submitted_at)
        rows = (
            await db.execute(
                select(
                    submitted_bucket.label("bkey"),
                    option_key.label("option_key"),
                    func.count(rec.id).label("count_value"),
                )
                .select_from(rec)
                .join(conv, conv.id == rec.conversation_id)
                .where(
                    *self._record_filter(ctx, settings),
                    _submitted(rec),
                    rec.submitted_at >= ctx.range_start,
                    rec.submitted_at < ctx.range_end,
                    result_column.is_not(None),
                    option_key.in_([option.key for option in options]),
                )
                .group_by(literal_column("bkey"), option_key)
            )
        ).all()
        for row in rows:
            if row.option_key is None:
                continue
            out.setdefault(row.bkey, {})[
                _distribution_metric_key(distribution_key, str(row.option_key))
            ] = int(row.count_value or 0)

    async def trend(
        self,
        db: AsyncSession,
        ctx: OverallContext,
        trend_type: TrendType,
        buckets: list[TimeBucket],
    ) -> dict[object, dict[str, float | None]]:
        settings = await self._settings(db, ctx.tenant_id)
        if not settings.enabled or not settings.has_any_type:
            return {}
        if ctx.agent_ids is not None and not ctx.agent_ids:
            return {}

        rec = SatisfactionSurveyRecord
        conv = Conversation
        out: dict[object, dict[str, float | None]] = {}

        invitation_bucket = _bucket_sql(trend_type, ctx, rec.invited_at)
        invitation_rows = (
            await db.execute(
                select(
                    invitation_bucket.label("bkey"),
                    func.count(rec.id).label(_INVITATION),
                )
                .select_from(rec)
                .join(conv, conv.id == rec.conversation_id)
                .where(
                    *self._record_filter(ctx, settings),
                    rec.invited_at >= ctx.range_start,
                    rec.invited_at < ctx.range_end,
                )
                .group_by(literal_column("bkey"))
            )
        ).all()
        for row in invitation_rows:
            out.setdefault(row.bkey, {})[_INVITATION] = int(row.satisfaction_invitation_count or 0)

        submitted_bucket = _bucket_sql(trend_type, ctx, rec.submitted_at)
        submitted_rows = (
            await db.execute(
                select(
                    submitted_bucket.label("bkey"),
                    func.count(rec.id).label(_SUBMISSION),
                    func.sum(case((rec.product_result.is_not(None), 1), else_=0)).label(_PRODUCT),
                )
                .select_from(rec)
                .join(conv, conv.id == rec.conversation_id)
                .where(
                    *self._record_filter(ctx, settings),
                    _submitted(rec),
                    rec.submitted_at >= ctx.range_start,
                    rec.submitted_at < ctx.range_end,
                )
                .group_by(literal_column("bkey"))
            )
        ).all()
        for row in submitted_rows:
            values = out.setdefault(row.bkey, {})
            values[_SUBMISSION] = int(row.satisfaction_submission_count or 0)
            if settings.product_enabled:
                values[_PRODUCT] = int(row.product_satisfaction_count or 0)

        if settings.show_resolution:
            await self._add_resolution_trend_counts(db, ctx, settings, trend_type, out)
        if settings.service_enabled:
            await self._add_rating_trend_counts(
                db,
                ctx,
                settings,
                trend_type,
                out,
                distribution_key=_SERVICE_DISTRIBUTION,
                result_field="service",
                options=settings.service_options,
            )
        if settings.product_enabled:
            await self._add_rating_trend_counts(
                db,
                ctx,
                settings,
                trend_type,
                out,
                distribution_key=_PRODUCT_DISTRIBUTION,
                result_field="product",
                options=settings.product_options,
            )

        return out
