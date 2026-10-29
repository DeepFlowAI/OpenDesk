"""Queue-dimension session report service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, case, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import NotFoundError, ValidationError
from app.models.conversation import Conversation
from app.models.conversation_queue_summary import ConversationQueueSummary
from app.models.employee_group import EmployeeGroup
from app.models.satisfaction_survey_config import SatisfactionSurveyConfig, SatisfactionSurveyConfigVersion
from app.models.satisfaction_survey_record import SatisfactionSurveyRecord
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService, RESOURCE_SESSION_RECORD, SCOPE_ALL

from ..lib.buckets import TrendType, generate_buckets
from ..lib.queries import _absolute_bucket_key_sql, _bucket_python_key, _distribution_bucket_key_sql
from ..lib.scope import ReportScope
from ..lib.tz import get_tenant_timezone
from ..lib.validators import validate_date_range
from ..schemas import (
    MetricFormat,
    MetricDistribution,
    MetricDistributionSlice,
    MetricLevel,
    MetricResult,
    OverallTrendBucket,
    OverallTrendMetricValue,
    QueueBrief,
    QueueDetailResponse,
    QueueListResponse,
    QueueMetricGroupLiteral,
    QueueOverviewRow,
    QueueReportMetrics,
    QueueTrendResponse,
)

QUEUE_TYPE_GROUP = "employee_group"
QUEUE_TYPES = {QUEUE_TYPE_GROUP}

GROUP_QUEUE_ACCESS = "queue_access"
GROUP_HUMAN_MESSAGES = "human_messages"
GROUP_SERVICE_EFFICIENCY = "service_efficiency"
GROUP_SATISFACTION = "satisfaction"
QUEUE_GROUPS = {GROUP_QUEUE_ACCESS, GROUP_HUMAN_MESSAGES, GROUP_SERVICE_EFFICIENCY, GROUP_SATISFACTION}

_SATISFACTION_INVITATION = "satisfaction_invitation_count"
_SATISFACTION_SUBMISSION = "satisfaction_submission_count"
_SATISFACTION_PARTICIPATION_RATE = "satisfaction_participation_rate"
_SATISFACTION_SUBMISSION_RATE = "satisfaction_submission_rate"
_PRODUCT_SATISFACTION = "product_satisfaction_count"
_RESOLUTION_DISTRIBUTION = "satisfaction_resolution"
_SERVICE_DISTRIBUTION = "service_satisfaction_rating"
_PRODUCT_DISTRIBUTION = "product_satisfaction_rating"
_DISTRIBUTION_METRIC_SEPARATOR = ":"

_SORT_FIELDS = {
    "name",
    "queue_type",
    "status",
    "queued_session_count",
    "assigned_queue_session_count",
    "unassigned_queue_session_count",
    "queue_assign_rate",
    "avg_queue_duration_seconds",
    "max_queue_duration_seconds",
    "final_session_count",
    "effective_session_count",
    "user_message_count",
    "agent_message_count",
    "unreplied_session_count",
    "visitor_silent_session_count",
    "avg_first_human_response_seconds",
    "avg_agent_response_seconds",
    "avg_human_session_duration_seconds",
    "satisfaction_invitation_count",
    "satisfaction_submission_count",
    "satisfaction_participation_rate",
    "satisfaction_submission_rate",
    "product_satisfaction_count",
}

_GROUP_DESCRIPTORS: dict[str, list[tuple[str, MetricFormat, MetricLevel]]] = {
    GROUP_QUEUE_ACCESS: [
        ("queued_session_count", MetricFormat.INTEGER, MetricLevel.PRIMARY),
        ("assigned_queue_session_count", MetricFormat.INTEGER, MetricLevel.PRIMARY),
        ("unassigned_queue_session_count", MetricFormat.INTEGER, MetricLevel.PRIMARY),
        ("avg_queue_duration_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.PRIMARY),
        ("max_queue_duration_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY),
    ],
    GROUP_HUMAN_MESSAGES: [
        ("final_session_count", MetricFormat.INTEGER, MetricLevel.PRIMARY),
        ("effective_session_count", MetricFormat.INTEGER, MetricLevel.PRIMARY),
        ("user_message_count", MetricFormat.INTEGER, MetricLevel.AUXILIARY),
        ("agent_message_count", MetricFormat.INTEGER, MetricLevel.AUXILIARY),
        ("unreplied_session_count", MetricFormat.INTEGER, MetricLevel.AUXILIARY),
        ("visitor_silent_session_count", MetricFormat.INTEGER, MetricLevel.AUXILIARY),
    ],
    GROUP_SERVICE_EFFICIENCY: [
        ("avg_first_human_response_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.PRIMARY),
        ("avg_agent_response_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.PRIMARY),
        ("avg_human_session_duration_seconds", MetricFormat.DURATION_SECONDS, MetricLevel.AUXILIARY),
    ],
    GROUP_SATISFACTION: [
        (_SATISFACTION_INVITATION, MetricFormat.INTEGER, MetricLevel.PRIMARY),
        (_SATISFACTION_SUBMISSION, MetricFormat.INTEGER, MetricLevel.PRIMARY),
        (_PRODUCT_SATISFACTION, MetricFormat.INTEGER, MetricLevel.AUXILIARY),
    ],
}


@dataclass(frozen=True)
class _QueueInfo:
    brief: QueueBrief
    search_text: str


@dataclass(frozen=True)
class _Option:
    key: str
    label: str


@dataclass(frozen=True)
class _SatisfactionSettings:
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


async def list_queues_overview(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    q: str | None = None,
    queue_type: str | None = None,
    sort: str = "queued_session_count",
    order: str = "desc",
    page: int = 1,
    per_page: int = 20,
    paginate: bool = True,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> dict:
    """Return queue report rows for current queues plus visible historical queues."""
    queue_type = _normalize_queue_type(queue_type)
    if sort not in _SORT_FIELDS:
        sort = "queued_session_count"
    order = order.lower()
    if order not in ("asc", "desc"):
        order = "desc"
    page = max(1, page)
    if paginate:
        per_page = max(1, min(per_page, 100))

    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

    scope = report_scope or ReportScope(employee_id=None, agent_ids=None, visible_employee_ids=None)
    list_queue_type = queue_type or QUEUE_TYPE_GROUP
    current = await _current_queue_infos(db, tenant_id, list_queue_type, principal)
    access_map, snapshots_a = await _fetch_queue_access_metrics(
        db, tenant_id, range_start, range_end, queue_type=list_queue_type, report_scope=scope
    )
    final_map, snapshots_f = await _fetch_final_queue_metrics(
        db, tenant_id, range_start, range_end, queue_type=list_queue_type, report_scope=scope
    )
    satisfaction_map, snapshots_s = await _fetch_queue_satisfaction_metrics(
        db, tenant_id, range_start, range_end, queue_type=list_queue_type, report_scope=scope
    )
    snapshots = {**snapshots_a, **snapshots_f, **snapshots_s}

    keys = set(current) | set(access_map) | set(final_map) | set(satisfaction_map)
    rows = [
        QueueOverviewRow(
            queue=_brief_for_key(key, current, snapshots),
            metrics=_combine_metrics(access_map.get(key), final_map.get(key), satisfaction_map.get(key)),
        )
        for key in keys
    ]

    if q and q.strip():
        needle = q.strip().lower()
        rows = [
            row for row in rows
            if needle in current.get((row.queue.queue_type, row.queue.queue_id), _fallback_info(row.queue)).search_text
        ]

    _sort_rows(rows, sort, order)
    total = len(rows)
    if paginate:
        pages = max(1, (total + per_page - 1) // per_page)
        start_idx = (page - 1) * per_page
        items = rows[start_idx:start_idx + per_page]
    else:
        page = 1
        per_page = max(total, 1)
        pages = 1
        items = rows

    return QueueListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        sort=sort,
        order=order,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


async def get_queue_detail(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    queue_type: str,
    queue_id: int,
    *,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> dict:
    """Return one queue overview, including deleted queues with visible history."""
    queue_type = _normalize_queue_type(queue_type, required=True)
    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    scope = report_scope or ReportScope(employee_id=None, agent_ids=None, visible_employee_ids=None)

    key = (queue_type, queue_id)
    current = await _current_queue_infos(db, tenant_id, queue_type, principal, queue_id=queue_id)
    access_map, snapshots_a = await _fetch_queue_access_metrics(
        db, tenant_id, range_start, range_end, queue_type=queue_type, queue_id=queue_id, report_scope=scope
    )
    final_map, snapshots_f = await _fetch_final_queue_metrics(
        db, tenant_id, range_start, range_end, queue_type=queue_type, queue_id=queue_id, report_scope=scope
    )
    satisfaction_map, snapshots_s = await _fetch_queue_satisfaction_metrics(
        db, tenant_id, range_start, range_end, queue_type=queue_type, queue_id=queue_id, report_scope=scope
    )
    snapshots = {**snapshots_a, **snapshots_f, **snapshots_s}
    metrics = _combine_metrics(access_map.get(key), final_map.get(key), satisfaction_map.get(key))
    if key not in current and key not in access_map and key not in final_map and key not in satisfaction_map:
        raise NotFoundError("Queue not found or inaccessible")
    distributions = await _fetch_queue_satisfaction_distributions(
        db, tenant_id, range_start, range_end, queue_type=queue_type, queue_id=queue_id, report_scope=scope
    )

    return QueueDetailResponse(
        queue=_brief_for_key(key, current, snapshots),
        metrics=metrics,
        distributions=distributions,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


async def get_queue_trend(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    queue_type: str,
    queue_id: int,
    *,
    group: str | None = None,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> dict:
    """Return one metric-group trend for a queue."""
    group_key = _normalize_group(group)
    await get_queue_detail(
        db,
        tenant_id,
        start_date,
        end_date,
        queue_type,
        queue_id,
        report_scope=report_scope,
        principal=principal,
    )
    validate_date_range(start_date, end_date)
    tz = get_tenant_timezone(tenant_id)
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    buckets = generate_buckets(start_date, end_date, trend_type, tz)
    scope = report_scope or ReportScope(employee_id=None, agent_ids=None, visible_employee_ids=None)

    if group_key == GROUP_QUEUE_ACCESS:
        trend_map = await _fetch_queue_access_trend(
            db, tenant_id, range_start, range_end, trend_type, tz,
            queue_type=queue_type, queue_id=queue_id, report_scope=scope,
        )
    elif group_key == GROUP_SATISFACTION:
        trend_map = await _fetch_queue_satisfaction_trend(
            db, tenant_id, range_start, range_end, trend_type, tz,
            queue_type=queue_type, queue_id=queue_id, report_scope=scope,
        )
    else:
        trend_map = await _fetch_final_queue_trend(
            db, tenant_id, range_start, range_end, trend_type, tz,
            queue_type=queue_type, queue_id=queue_id, group=group_key, report_scope=scope,
        )

    descriptors = (
        await _satisfaction_trend_descriptors(db, tenant_id)
        if group_key == GROUP_SATISFACTION
        else _descriptors(group_key)
    )
    out_buckets = []
    for bucket in buckets:
        values = trend_map.get(_bucket_python_key(bucket, trend_type), {})
        out_buckets.append(
            OverallTrendBucket(
                label=bucket.label,
                bucket_start=bucket.start.isoformat(),
                bucket_end=bucket.end.isoformat(),
                metrics=[
                    OverallTrendMetricValue(
                        key=key,
                        value=values.get(key, 0 if fmt == MetricFormat.INTEGER else None),
                        format=fmt,
                    )
                    for key, fmt, _level in descriptors
                ],
            )
        )

    return QueueTrendResponse(
        trend=trend_type.value,
        group=group_key,
        metrics=[
            MetricResult(key=key, value=None, format=fmt, level=level, group=group_key)
            for key, fmt, level in descriptors
        ],
        buckets=out_buckets,
        as_of=datetime.now(tz).isoformat(),
    ).model_dump()


def _normalize_queue_type(queue_type: str | None, *, required: bool = False) -> str | None:
    if not queue_type:
        if required:
            raise ValidationError("queue_type is required")
        return None
    if queue_type not in QUEUE_TYPES:
        raise ValidationError("Unsupported queue type")
    return queue_type


def _normalize_group(group: str | None) -> QueueMetricGroupLiteral:
    if group in QUEUE_GROUPS:
        return group  # type: ignore[return-value]
    return GROUP_QUEUE_ACCESS  # type: ignore[return-value]


def _descriptors(group: str) -> list[tuple[str, MetricFormat, MetricLevel]]:
    return _GROUP_DESCRIPTORS.get(group, _GROUP_DESCRIPTORS[GROUP_QUEUE_ACCESS])


async def _satisfaction_trend_descriptors(
    db: AsyncSession,
    tenant_id: int,
) -> list[tuple[str, MetricFormat, MetricLevel]]:
    settings = await _satisfaction_settings(db, tenant_id)
    if not settings.enabled or not settings.has_any_type:
        return []
    descriptors = [
        (_SATISFACTION_INVITATION, MetricFormat.INTEGER, MetricLevel.PRIMARY),
        (_SATISFACTION_SUBMISSION, MetricFormat.INTEGER, MetricLevel.PRIMARY),
    ]
    if settings.product_enabled:
        descriptors.append((_PRODUCT_SATISFACTION, MetricFormat.INTEGER, MetricLevel.AUXILIARY))
    if settings.show_resolution:
        descriptors.extend([
            (_distribution_metric_key(_RESOLUTION_DISTRIBUTION, "resolved"), MetricFormat.INTEGER, MetricLevel.AUXILIARY),
            (_distribution_metric_key(_RESOLUTION_DISTRIBUTION, "unresolved"), MetricFormat.INTEGER, MetricLevel.AUXILIARY),
        ])
    if settings.service_enabled:
        descriptors.extend(
            (_distribution_metric_key(_SERVICE_DISTRIBUTION, option.key), MetricFormat.INTEGER, MetricLevel.AUXILIARY)
            for option in settings.service_options
        )
    if settings.product_enabled:
        descriptors.extend(
            (_distribution_metric_key(_PRODUCT_DISTRIBUTION, option.key), MetricFormat.INTEGER, MetricLevel.AUXILIARY)
            for option in settings.product_options
        )
    return descriptors


def _session_filters(
    conv: type[Conversation],
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    report_scope: ReportScope,
) -> list[ColumnElement] | None:
    filters: list[ColumnElement] = [
        conv.tenant_id == tenant_id,
        conv.started_at >= range_start,
        conv.started_at < range_end,
    ]
    if report_scope.agent_ids is not None:
        if not report_scope.agent_ids:
            return None
        filters.append(conv.agent_id.in_(report_scope.agent_ids))
    return filters


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
        group=GROUP_SATISFACTION,
        total=sum(item.value for item in slices),
        slices=slices,
    )


def _distribution_metric_key(distribution_key: str, slice_key: str) -> str:
    return f"{distribution_key}{_DISTRIBUTION_METRIC_SEPARATOR}{slice_key}"


async def _satisfaction_settings(db: AsyncSession, tenant_id: int) -> _SatisfactionSettings:
    cfg = (
        await db.execute(
            select(SatisfactionSurveyConfig).where(SatisfactionSurveyConfig.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if not cfg or not cfg.enabled or cfg.current_version is None:
        return _SatisfactionSettings(enabled=False)

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
        return _SatisfactionSettings(enabled=False, current_version=cfg.current_version)

    service = snapshot.get("service") or {}
    product = snapshot.get("product") or {}
    return _SatisfactionSettings(
        enabled=True,
        current_version=cfg.current_version,
        service_enabled=bool(service.get("enabled")),
        product_enabled=bool(product.get("enabled")),
        show_resolution=bool(service.get("enabled") and service.get("show_resolution")),
        service_options=_enabled_options(service),
        product_options=_enabled_options(product),
    )


def _satisfaction_queue_filters(
    conv: type[Conversation],
    tenant_id: int,
    *,
    queue_type: str | None,
    queue_id: int | None,
    report_scope: ReportScope,
) -> list[ColumnElement] | None:
    filters: list[ColumnElement] = [
        conv.tenant_id == tenant_id,
        or_(conv.had_bot_session.is_(False), conv.bot_handoff_succeeded.is_(True)),
        conv.last_assigned_queue_type.is_not(None),
        conv.last_assigned_queue_id.is_not(None),
    ]
    if queue_type:
        filters.append(conv.last_assigned_queue_type == queue_type)
    if queue_id is not None:
        filters.append(conv.last_assigned_queue_id == queue_id)
    if report_scope.agent_ids is not None:
        if not report_scope.agent_ids:
            return None
        filters.append(conv.agent_id.in_(report_scope.agent_ids))
    return filters


async def _fetch_queue_satisfaction_metrics(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    queue_type: str | None = None,
    queue_id: int | None = None,
    report_scope: ReportScope,
) -> tuple[dict[tuple[str, int], dict], dict[tuple[str, int], str]]:
    settings = await _satisfaction_settings(db, tenant_id)
    if not settings.enabled or not settings.has_any_type:
        return {}, {}

    conv = Conversation
    rec = SatisfactionSurveyRecord
    filters = _satisfaction_queue_filters(
        conv,
        tenant_id,
        queue_type=queue_type,
        queue_id=queue_id,
        report_scope=report_scope,
    )
    if filters is None:
        return {}, {}

    human_rows = (
        await db.execute(
            select(
                conv.last_assigned_queue_type.label("queue_type"),
                conv.last_assigned_queue_id.label("queue_id"),
                func.max(conv.last_assigned_queue_name).label("snapshot"),
                func.count(conv.id).label("human_session_count"),
            )
            .where(*filters, conv.started_at >= range_start, conv.started_at < range_end)
            .group_by(conv.last_assigned_queue_type, conv.last_assigned_queue_id)
        )
    ).all()
    invitation_rows = (
        await db.execute(
            select(
                conv.last_assigned_queue_type.label("queue_type"),
                conv.last_assigned_queue_id.label("queue_id"),
                func.max(conv.last_assigned_queue_name).label("snapshot"),
                func.count(rec.id).label(_SATISFACTION_INVITATION),
            )
            .select_from(rec)
            .join(conv, conv.id == rec.conversation_id)
            .where(
                rec.tenant_id == tenant_id,
                rec.config_version == settings.current_version,
                *filters,
                rec.invited_at >= range_start,
                rec.invited_at < range_end,
            )
            .group_by(conv.last_assigned_queue_type, conv.last_assigned_queue_id)
        )
    ).all()
    submission_rows = (
        await db.execute(
            select(
                conv.last_assigned_queue_type.label("queue_type"),
                conv.last_assigned_queue_id.label("queue_id"),
                func.max(conv.last_assigned_queue_name).label("snapshot"),
                func.count(rec.id).label(_SATISFACTION_SUBMISSION),
                func.sum(case((rec.product_result.is_not(None), 1), else_=0)).label(_PRODUCT_SATISFACTION),
            )
            .select_from(rec)
            .join(conv, conv.id == rec.conversation_id)
            .where(
                rec.tenant_id == tenant_id,
                rec.config_version == settings.current_version,
                *filters,
                _submitted(rec),
                rec.submitted_at >= range_start,
                rec.submitted_at < range_end,
            )
            .group_by(conv.last_assigned_queue_type, conv.last_assigned_queue_id)
        )
    ).all()

    human_by_key: dict[tuple[str, int], int] = {}
    invitations_by_key: dict[tuple[str, int], int] = {}
    submissions_by_key: dict[tuple[str, int], tuple[int, int]] = {}
    snapshots: dict[tuple[str, int], str] = {}
    for row in human_rows:
        key = (str(row.queue_type), int(row.queue_id))
        human_by_key[key] = int(row.human_session_count or 0)
        if row.snapshot:
            snapshots[key] = str(row.snapshot)
    for row in invitation_rows:
        key = (str(row.queue_type), int(row.queue_id))
        invitations_by_key[key] = int(row.satisfaction_invitation_count or 0)
        if row.snapshot:
            snapshots[key] = str(row.snapshot)
    for row in submission_rows:
        key = (str(row.queue_type), int(row.queue_id))
        submissions_by_key[key] = (
            int(row.satisfaction_submission_count or 0),
            int(row.product_satisfaction_count or 0) if settings.product_enabled else 0,
        )
        if row.snapshot:
            snapshots[key] = str(row.snapshot)

    metrics: dict[tuple[str, int], dict] = {}
    for key in set(human_by_key) | set(invitations_by_key) | set(submissions_by_key):
        human_sessions = human_by_key.get(key, 0)
        invitations = invitations_by_key.get(key, 0)
        submissions, product_count = submissions_by_key.get(key, (0, 0))
        metrics[key] = {
            _SATISFACTION_INVITATION: invitations,
            _SATISFACTION_SUBMISSION: submissions,
            _SATISFACTION_PARTICIPATION_RATE: _rate(submissions, human_sessions),
            _SATISFACTION_SUBMISSION_RATE: _rate(submissions, invitations),
            _PRODUCT_SATISFACTION: product_count,
        }
    return metrics, snapshots


def _empty_satisfaction_distributions(settings: _SatisfactionSettings) -> list[MetricDistribution]:
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


async def _fetch_queue_satisfaction_distributions(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    queue_type: str,
    queue_id: int,
    report_scope: ReportScope,
) -> list[MetricDistribution]:
    settings = await _satisfaction_settings(db, tenant_id)
    if not settings.enabled or not settings.has_any_type:
        return []

    conv = Conversation
    rec = SatisfactionSurveyRecord
    filters = _satisfaction_queue_filters(
        conv,
        tenant_id,
        queue_type=queue_type,
        queue_id=queue_id,
        report_scope=report_scope,
    )
    if filters is None:
        return _empty_satisfaction_distributions(settings)

    distributions: list[MetricDistribution] = []
    if settings.show_resolution:
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
                    rec.tenant_id == tenant_id,
                    rec.config_version == settings.current_version,
                    *filters,
                    _submitted(rec),
                    rec.submitted_at >= range_start,
                    rec.submitted_at < range_end,
                    resolved.in_(["true", "false"]),
                )
                .group_by(resolved)
            )
        ).all()
        counts = {str(row.resolved_key): int(row.count_value or 0) for row in rows}
        distributions.append(
            _distribution(
                _RESOLUTION_DISTRIBUTION,
                [
                    MetricDistributionSlice(key="resolved", label="resolved", value=counts.get("true", 0)),
                    MetricDistributionSlice(key="unresolved", label="unresolved", value=counts.get("false", 0)),
                ],
            )
        )
    if settings.service_enabled:
        distributions.append(
            await _fetch_queue_rating_distribution(
                db,
                tenant_id,
                range_start,
                range_end,
                queue_type=queue_type,
                queue_id=queue_id,
                report_scope=report_scope,
                settings=settings,
                key=_SERVICE_DISTRIBUTION,
                result_field="service",
                options=settings.service_options,
            )
        )
    if settings.product_enabled:
        distributions.append(
            await _fetch_queue_rating_distribution(
                db,
                tenant_id,
                range_start,
                range_end,
                queue_type=queue_type,
                queue_id=queue_id,
                report_scope=report_scope,
                settings=settings,
                key=_PRODUCT_DISTRIBUTION,
                result_field="product",
                options=settings.product_options,
            )
        )
    return distributions


async def _fetch_queue_rating_distribution(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    queue_type: str,
    queue_id: int,
    report_scope: ReportScope,
    settings: _SatisfactionSettings,
    key: str,
    result_field: str,
    options: tuple[_Option, ...],
) -> MetricDistribution:
    conv = Conversation
    rec = SatisfactionSurveyRecord
    filters = _satisfaction_queue_filters(
        conv,
        tenant_id,
        queue_type=queue_type,
        queue_id=queue_id,
        report_scope=report_scope,
    )
    if filters is None:
        return _distribution(
            key,
            [MetricDistributionSlice(key=option.key, label=option.label, value=0) for option in options],
        )

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
                rec.tenant_id == tenant_id,
                rec.config_version == settings.current_version,
                *filters,
                _submitted(rec),
                rec.submitted_at >= range_start,
                rec.submitted_at < range_end,
                result_column.is_not(None),
                option_key.in_([option.key for option in options]),
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


async def _current_queue_infos(
    db: AsyncSession,
    tenant_id: int,
    queue_type: str | None,
    principal: EffectivePrincipal | None,
    *,
    queue_id: int | None = None,
) -> dict[tuple[str, int], _QueueInfo]:
    out: dict[tuple[str, int], _QueueInfo] = {}
    scope_name = DataScopeService.get_scope(principal, RESOURCE_SESSION_RECORD) if principal else SCOPE_ALL

    if queue_type in (None, QUEUE_TYPE_GROUP):
        group_stmt = select(EmployeeGroup).where(EmployeeGroup.tenant_id == tenant_id)
        if queue_id is not None and queue_type == QUEUE_TYPE_GROUP:
            group_stmt = group_stmt.where(EmployeeGroup.id == queue_id)
        elif scope_name != SCOPE_ALL:
            if not principal or not principal.group_ids:
                group_stmt = None
            else:
                group_stmt = group_stmt.where(EmployeeGroup.id.in_(principal.group_ids))
        if group_stmt is not None:
            groups = (await db.execute(group_stmt)).scalars().all()
            for group in groups:
                brief = QueueBrief(
                    queue_type=QUEUE_TYPE_GROUP,
                    queue_id=group.id,
                    name=group.name or "Unknown queue",
                    status="active",
                )
                out[(brief.queue_type, brief.queue_id)] = _QueueInfo(
                    brief=brief,
                    search_text=(group.name or "").lower(),
                )

    return out


async def _fetch_queue_access_metrics(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    queue_type: str | None = None,
    queue_id: int | None = None,
    report_scope: ReportScope,
) -> tuple[dict[tuple[str, int], dict], dict[tuple[str, int], str]]:
    conv = Conversation
    qs = ConversationQueueSummary
    filters = _session_filters(conv, tenant_id, range_start, range_end, report_scope)
    if filters is None:
        return {}, {}
    filters.extend([qs.tenant_id == tenant_id, qs.wait_duration_seconds > 0])
    if queue_type:
        filters.append(qs.queue_type == queue_type)
    if queue_id is not None:
        filters.append(qs.queue_id == queue_id)

    stmt = (
        select(
            qs.queue_type.label("queue_type"),
            qs.queue_id.label("queue_id"),
            func.max(qs.queue_name_snapshot).label("snapshot"),
            func.count(qs.id).label("queued_session_count"),
            func.sum(case((qs.queue_result == "assigned", 1), else_=0)).label("assigned_queue_session_count"),
            func.sum(case((qs.queue_result.in_(["canceled", "timeout"]), 1), else_=0)).label("unassigned_queue_session_count"),
            func.avg(qs.wait_duration_seconds).label("avg_queue_duration_seconds"),
            func.max(qs.wait_duration_seconds).label("max_queue_duration_seconds"),
        )
        .join(conv, conv.id == qs.conversation_id)
        .where(*filters)
        .group_by(qs.queue_type, qs.queue_id)
    )
    rows = (await db.execute(stmt)).all()
    metrics: dict[tuple[str, int], dict] = {}
    snapshots: dict[tuple[str, int], str] = {}
    for row in rows:
        key = (str(row.queue_type), int(row.queue_id))
        metrics[key] = {
            "queued_session_count": int(row.queued_session_count or 0),
            "assigned_queue_session_count": int(row.assigned_queue_session_count or 0),
            "unassigned_queue_session_count": int(row.unassigned_queue_session_count or 0),
            "avg_queue_duration_seconds": (
                float(row.avg_queue_duration_seconds)
                if row.avg_queue_duration_seconds is not None
                else None
            ),
            "max_queue_duration_seconds": (
                float(row.max_queue_duration_seconds)
                if row.max_queue_duration_seconds is not None
                else None
            ),
        }
        if row.snapshot:
            snapshots[key] = str(row.snapshot)
    return metrics, snapshots


async def _fetch_final_queue_metrics(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    *,
    queue_type: str | None = None,
    queue_id: int | None = None,
    report_scope: ReportScope,
) -> tuple[dict[tuple[str, int], dict], dict[tuple[str, int], str]]:
    conv = Conversation
    filters = _session_filters(conv, tenant_id, range_start, range_end, report_scope)
    if filters is None:
        return {}, {}
    filters.extend([
        conv.last_assigned_queue_type.is_not(None),
        conv.last_assigned_queue_id.is_not(None),
    ])
    if queue_type:
        filters.append(conv.last_assigned_queue_type == queue_type)
    if queue_id is not None:
        filters.append(conv.last_assigned_queue_id == queue_id)

    stmt = (
        select(
            conv.last_assigned_queue_type.label("queue_type"),
            conv.last_assigned_queue_id.label("queue_id"),
            func.max(conv.last_assigned_queue_name).label("snapshot"),
            *_final_value_columns(),
        )
        .where(*filters)
        .group_by(conv.last_assigned_queue_type, conv.last_assigned_queue_id)
    )
    rows = (await db.execute(stmt)).all()
    metrics: dict[tuple[str, int], dict] = {}
    snapshots: dict[tuple[str, int], str] = {}
    for row in rows:
        key = (str(row.queue_type), int(row.queue_id))
        metrics[key] = _final_row_to_values(row)
        if row.snapshot:
            snapshots[key] = str(row.snapshot)
    return metrics, snapshots


def _final_value_columns() -> list:
    conv = Conversation
    return [
        func.count(conv.id).label("final_session_count"),
        func.sum(
            case((and_(conv.visitor_message_count > 0, conv.agent_message_count > 0), 1), else_=0)
        ).label("effective_session_count"),
        func.coalesce(func.sum(conv.visitor_message_count), 0).label("user_message_count"),
        func.coalesce(func.sum(conv.agent_message_count), 0).label("agent_message_count"),
        func.sum(
            case((and_(conv.visitor_message_count > 0, conv.agent_message_count == 0), 1), else_=0)
        ).label("unreplied_session_count"),
        func.sum(case((conv.visitor_message_count == 0, 1), else_=0)).label("visitor_silent_session_count"),
        func.avg(conv.first_human_response_seconds).label("avg_first_human_response_seconds"),
        func.sum(conv.agent_avg_response_seconds * conv.agent_response_count).label("agent_resp_num"),
        func.sum(conv.agent_response_count).label("agent_resp_den"),
        func.avg(conv.duration_seconds).label("avg_human_session_duration_seconds"),
    ]


def _final_row_to_values(row) -> dict:
    den = row.agent_resp_den
    weighted_agent = (
        float(row.agent_resp_num) / float(den)
        if row.agent_resp_num is not None and den
        else None
    )
    return {
        "final_session_count": int(row.final_session_count or 0),
        "effective_session_count": int(row.effective_session_count or 0),
        "user_message_count": int(row.user_message_count or 0),
        "agent_message_count": int(row.agent_message_count or 0),
        "unreplied_session_count": int(row.unreplied_session_count or 0),
        "visitor_silent_session_count": int(row.visitor_silent_session_count or 0),
        "avg_first_human_response_seconds": (
            float(row.avg_first_human_response_seconds)
            if row.avg_first_human_response_seconds is not None
            else None
        ),
        "avg_agent_response_seconds": weighted_agent,
        "avg_human_session_duration_seconds": (
            float(row.avg_human_session_duration_seconds)
            if row.avg_human_session_duration_seconds is not None
            else None
        ),
    }


async def _fetch_queue_access_trend(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz,
    *,
    queue_type: str,
    queue_id: int,
    report_scope: ReportScope,
) -> dict[object, dict[str, float | None]]:
    conv = Conversation
    qs = ConversationQueueSummary
    filters = _session_filters(conv, tenant_id, range_start, range_end, report_scope)
    if filters is None:
        return {}
    filters.extend([
        qs.tenant_id == tenant_id,
        qs.queue_type == queue_type,
        qs.queue_id == queue_id,
        qs.wait_duration_seconds > 0,
    ])
    bucket_key_sql = _queue_bucket_key(trend_type, tz)
    stmt = (
        select(
            bucket_key_sql.label("bkey"),
            func.count(qs.id).label("queued_session_count"),
            func.sum(case((qs.queue_result == "assigned", 1), else_=0)).label("assigned_queue_session_count"),
            func.sum(case((qs.queue_result.in_(["canceled", "timeout"]), 1), else_=0)).label("unassigned_queue_session_count"),
            func.avg(qs.wait_duration_seconds).label("avg_queue_duration_seconds"),
            func.max(qs.wait_duration_seconds).label("max_queue_duration_seconds"),
        )
        .join(conv, conv.id == qs.conversation_id)
        .where(*filters)
        .group_by(literal_column("bkey"))
    )
    rows = (await db.execute(stmt)).all()
    return {
        row.bkey: {
            "queued_session_count": int(row.queued_session_count or 0),
            "assigned_queue_session_count": int(row.assigned_queue_session_count or 0),
            "unassigned_queue_session_count": int(row.unassigned_queue_session_count or 0),
            "avg_queue_duration_seconds": (
                float(row.avg_queue_duration_seconds)
                if row.avg_queue_duration_seconds is not None
                else None
            ),
            "max_queue_duration_seconds": (
                float(row.max_queue_duration_seconds)
                if row.max_queue_duration_seconds is not None
                else None
            ),
        }
        for row in rows
    }


async def _fetch_final_queue_trend(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz,
    *,
    queue_type: str,
    queue_id: int,
    group: str,
    report_scope: ReportScope,
) -> dict[object, dict[str, float | None]]:
    conv = Conversation
    filters = _session_filters(conv, tenant_id, range_start, range_end, report_scope)
    if filters is None:
        return {}
    filters.extend([
        conv.last_assigned_queue_type == queue_type,
        conv.last_assigned_queue_id == queue_id,
    ])
    bucket_key_sql = _queue_bucket_key(trend_type, tz)
    stmt = (
        select(bucket_key_sql.label("bkey"), *_final_value_columns())
        .where(*filters)
        .group_by(literal_column("bkey"))
    )
    rows = (await db.execute(stmt)).all()
    allowed_keys = {key for key, _fmt, _level in _descriptors(group)}
    return {
        row.bkey: {
            key: value
            for key, value in _final_row_to_values(row).items()
            if key in allowed_keys
        }
        for row in rows
    }


async def _add_queue_resolution_trend_counts(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz,
    *,
    queue_type: str,
    queue_id: int,
    report_scope: ReportScope,
    settings: _SatisfactionSettings,
    out: dict[object, dict[str, float | None]],
) -> None:
    conv = Conversation
    rec = SatisfactionSurveyRecord
    filters = _satisfaction_queue_filters(
        conv,
        tenant_id,
        queue_type=queue_type,
        queue_id=queue_id,
        report_scope=report_scope,
    )
    if filters is None:
        return

    resolved = rec.service_result["resolved"].astext
    submitted_bucket = _queue_bucket_key_for_column(trend_type, tz, rec.submitted_at)
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
                rec.tenant_id == tenant_id,
                rec.config_version == settings.current_version,
                *filters,
                _submitted(rec),
                rec.submitted_at >= range_start,
                rec.submitted_at < range_end,
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


async def _add_queue_rating_trend_counts(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz,
    *,
    queue_type: str,
    queue_id: int,
    report_scope: ReportScope,
    settings: _SatisfactionSettings,
    distribution_key: str,
    result_field: str,
    options: tuple[_Option, ...],
    out: dict[object, dict[str, float | None]],
) -> None:
    if not options:
        return

    conv = Conversation
    rec = SatisfactionSurveyRecord
    filters = _satisfaction_queue_filters(
        conv,
        tenant_id,
        queue_type=queue_type,
        queue_id=queue_id,
        report_scope=report_scope,
    )
    if filters is None:
        return

    result_column = rec.service_result if result_field == "service" else rec.product_result
    option_key = result_column["option_key"].astext
    submitted_bucket = _queue_bucket_key_for_column(trend_type, tz, rec.submitted_at)
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
                rec.tenant_id == tenant_id,
                rec.config_version == settings.current_version,
                *filters,
                _submitted(rec),
                rec.submitted_at >= range_start,
                rec.submitted_at < range_end,
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


async def _fetch_queue_satisfaction_trend(
    db: AsyncSession,
    tenant_id: int,
    range_start: datetime,
    range_end: datetime,
    trend_type: TrendType,
    tz,
    *,
    queue_type: str,
    queue_id: int,
    report_scope: ReportScope,
) -> dict[object, dict[str, float | None]]:
    settings = await _satisfaction_settings(db, tenant_id)
    if not settings.enabled or not settings.has_any_type:
        return {}

    conv = Conversation
    rec = SatisfactionSurveyRecord
    filters = _satisfaction_queue_filters(
        conv,
        tenant_id,
        queue_type=queue_type,
        queue_id=queue_id,
        report_scope=report_scope,
    )
    if filters is None:
        return {}

    out: dict[object, dict[str, float | None]] = {}
    invitation_bucket = _queue_bucket_key_for_column(trend_type, tz, rec.invited_at)
    invitation_rows = (
        await db.execute(
            select(
                invitation_bucket.label("bkey"),
                func.count(rec.id).label(_SATISFACTION_INVITATION),
            )
            .select_from(rec)
            .join(conv, conv.id == rec.conversation_id)
            .where(
                rec.tenant_id == tenant_id,
                rec.config_version == settings.current_version,
                *filters,
                rec.invited_at >= range_start,
                rec.invited_at < range_end,
            )
            .group_by(literal_column("bkey"))
        )
    ).all()
    for row in invitation_rows:
        out.setdefault(row.bkey, {})[_SATISFACTION_INVITATION] = int(row.satisfaction_invitation_count or 0)

    submitted_bucket = _queue_bucket_key_for_column(trend_type, tz, rec.submitted_at)
    submitted_rows = (
        await db.execute(
            select(
                submitted_bucket.label("bkey"),
                func.count(rec.id).label(_SATISFACTION_SUBMISSION),
                func.sum(case((rec.product_result.is_not(None), 1), else_=0)).label(_PRODUCT_SATISFACTION),
            )
            .select_from(rec)
            .join(conv, conv.id == rec.conversation_id)
            .where(
                rec.tenant_id == tenant_id,
                rec.config_version == settings.current_version,
                *filters,
                _submitted(rec),
                rec.submitted_at >= range_start,
                rec.submitted_at < range_end,
            )
            .group_by(literal_column("bkey"))
        )
    ).all()
    for row in submitted_rows:
        values = out.setdefault(row.bkey, {})
        values[_SATISFACTION_SUBMISSION] = int(row.satisfaction_submission_count or 0)
        values[_PRODUCT_SATISFACTION] = (
            int(row.product_satisfaction_count or 0) if settings.product_enabled else 0
        )
    if settings.show_resolution:
        await _add_queue_resolution_trend_counts(
            db,
            tenant_id,
            range_start,
            range_end,
            trend_type,
            tz,
            queue_type=queue_type,
            queue_id=queue_id,
            report_scope=report_scope,
            settings=settings,
            out=out,
        )
    if settings.service_enabled:
        await _add_queue_rating_trend_counts(
            db,
            tenant_id,
            range_start,
            range_end,
            trend_type,
            tz,
            queue_type=queue_type,
            queue_id=queue_id,
            report_scope=report_scope,
            settings=settings,
            distribution_key=_SERVICE_DISTRIBUTION,
            result_field="service",
            options=settings.service_options,
            out=out,
        )
    if settings.product_enabled:
        await _add_queue_rating_trend_counts(
            db,
            tenant_id,
            range_start,
            range_end,
            trend_type,
            tz,
            queue_type=queue_type,
            queue_id=queue_id,
            report_scope=report_scope,
            settings=settings,
            distribution_key=_PRODUCT_DISTRIBUTION,
            result_field="product",
            options=settings.product_options,
            out=out,
        )
    return out


def _queue_bucket_key(trend_type: TrendType, tz):
    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        return _distribution_bucket_key_sql(trend_type, tz)
    return _absolute_bucket_key_sql(trend_type, tz)


def _queue_bucket_key_for_column(trend_type: TrendType, tz, column):
    if trend_type in (TrendType.HALF_HOUR, TrendType.HOUR):
        return _distribution_bucket_key_sql(trend_type, tz, column)
    return _absolute_bucket_key_sql(trend_type, tz, column)


def _combine_metrics(access: dict | None, final: dict | None, satisfaction: dict | None = None) -> QueueReportMetrics:
    access = access or {}
    final = final or {}
    satisfaction = satisfaction or {}
    queued = int(access.get("queued_session_count") or 0)
    assigned = int(access.get("assigned_queue_session_count") or 0)
    return QueueReportMetrics(
        queued_session_count=queued,
        assigned_queue_session_count=assigned,
        unassigned_queue_session_count=int(access.get("unassigned_queue_session_count") or 0),
        queue_assign_rate=(assigned / queued if queued else None),
        avg_queue_duration_seconds=access.get("avg_queue_duration_seconds"),
        max_queue_duration_seconds=access.get("max_queue_duration_seconds"),
        final_session_count=int(final.get("final_session_count") or 0),
        effective_session_count=int(final.get("effective_session_count") or 0),
        user_message_count=int(final.get("user_message_count") or 0),
        agent_message_count=int(final.get("agent_message_count") or 0),
        unreplied_session_count=int(final.get("unreplied_session_count") or 0),
        visitor_silent_session_count=int(final.get("visitor_silent_session_count") or 0),
        avg_first_human_response_seconds=final.get("avg_first_human_response_seconds"),
        avg_agent_response_seconds=final.get("avg_agent_response_seconds"),
        avg_human_session_duration_seconds=final.get("avg_human_session_duration_seconds"),
        satisfaction_invitation_count=int(satisfaction.get(_SATISFACTION_INVITATION) or 0),
        satisfaction_submission_count=int(satisfaction.get(_SATISFACTION_SUBMISSION) or 0),
        satisfaction_participation_rate=satisfaction.get(_SATISFACTION_PARTICIPATION_RATE),
        satisfaction_submission_rate=satisfaction.get(_SATISFACTION_SUBMISSION_RATE),
        product_satisfaction_count=int(satisfaction.get(_PRODUCT_SATISFACTION) or 0),
    )


def _brief_for_key(
    key: tuple[str, int],
    current: dict[tuple[str, int], _QueueInfo],
    snapshots: dict[tuple[str, int], str],
) -> QueueBrief:
    if key in current:
        return current[key].brief
    return QueueBrief(
        queue_type=key[0],  # type: ignore[arg-type]
        queue_id=key[1],
        name=snapshots.get(key) or "Unknown queue",
        status="deleted",
    )


def _fallback_info(brief: QueueBrief) -> _QueueInfo:
    return _QueueInfo(brief=brief, search_text=brief.name.lower())


def _sort_rows(rows: list[QueueOverviewRow], sort: str, order: str) -> None:
    rows.sort(key=lambda r: r.queue.name.lower())
    if sort == "queued_session_count" and order == "desc":
        rows.sort(
            key=lambda r: (
                r.metrics.avg_queue_duration_seconds is not None,
                r.metrics.avg_queue_duration_seconds or 0,
            ),
            reverse=True,
        )
        rows.sort(key=lambda r: r.metrics.queued_session_count, reverse=True)
        return
    reverse = order == "desc"
    if sort == "name":
        rows.sort(key=lambda r: r.queue.name.lower(), reverse=reverse)
        return
    if sort == "queue_type":
        rows.sort(key=lambda r: r.queue.queue_type, reverse=reverse)
        return
    if sort == "status":
        rows.sort(key=lambda r: r.queue.status, reverse=reverse)
        return
    rows.sort(
        key=lambda r: (
            getattr(r.metrics, sort) is not None,
            getattr(r.metrics, sort) or 0,
        ),
        reverse=reverse,
    )
