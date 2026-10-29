"""Excel export service for session reports."""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from typing import Literal
from urllib.parse import quote
from xml.sax.saxutils import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.employee import Employee
from app.schemas.permission import EffectivePrincipal

from ..lib.buckets import TrendType
from ..lib.metric_groups import all_groups
from ..lib.scope import ReportScope
from ..lib.tz import get_tenant_timezone
from ..schemas import EmployeeOverviewRow, MetricFormat, OverviewMetrics, QueueOverviewRow, QueueReportMetrics
from . import employees_service, overall_service, queues_service, sessions_service

ExportScope = Literal["overall", "employees", "employee"]
QueueExportScope = Literal["list", "detail"]
CellValue = str | int | float | None

_TREND_LABELS: dict[TrendType, str] = {
    TrendType.HALF_HOUR: "半小时",
    TrendType.HOUR: "小时",
    TrendType.DAY: "日",
    TrendType.WEEK: "周",
    TrendType.MONTH: "月",
}

_SORT_LABELS = {
    "session_count": "会话数",
    "message_count": "消息数",
    "user_message_count": "用户消息数",
    "agent_message_count": "客服消息数",
    "avg_duration_seconds": "平均会话时长",
    "reception_segment_count": "人工接待量",
    "reception_participated_session_count": "参与会话数",
    "reception_final_session_count": "最终负责会话数",
    "reception_transfer_in_count": "转接转入量",
    "reception_transfer_out_count": "转接转出量",
    "name": "员工名称",
}

_QUEUE_SORT_LABELS = {
    "name": "队列名称",
    "queue_type": "队列类型",
    "status": "状态",
    "queued_session_count": "排队会话量",
    "assigned_queue_session_count": "接入排队会话量",
    "unassigned_queue_session_count": "未接入排队会话量",
    "queue_assign_rate": "排队接入率",
    "avg_queue_duration_seconds": "平均排队时长",
    "max_queue_duration_seconds": "最长排队时长",
    "final_session_count": "最终承接会话量",
    "effective_session_count": "有效会话数",
    "user_message_count": "用户消息数",
    "agent_message_count": "客服消息数",
    "unreplied_session_count": "未回复会话数",
    "visitor_silent_session_count": "客户无消息会话数",
    "avg_first_human_response_seconds": "平均首响时长",
    "avg_agent_response_seconds": "平均响应时长",
    "avg_human_session_duration_seconds": "平均会话时长",
    "satisfaction_invitation_count": "满意度邀请量",
    "satisfaction_submission_count": "满意度评价量",
    "satisfaction_participation_rate": "会话参评率",
    "satisfaction_submission_rate": "邀请提交率",
    "product_satisfaction_count": "产品评价量",
}

# Chinese labels for the grouped overall report export. The frontend localizes
# by key; the export is the only backend place that needs display text, so the
# labels live here. New groups/metrics add entries; missing keys fall back to
# the raw key.
_OVERALL_GROUP_LABELS = {
    "session_overall": "会话整体",
    "human_messages": "人工会话与消息",
    "queue_access": "排队接入",
    "service_efficiency": "服务效率",
    "satisfaction": "满意度",
}

_OVERALL_METRIC_LABELS = {
    "total_session_count": "整体会话数",
    "pure_bot_session_count": "纯机器人会话量",
    "pure_human_session_count": "纯人工会话量",
    "bot_human_session_count": "机器人+人工会话量",
    "human_involved_session_count": "包含人工会话量",
    "effective_session_count": "有效会话数",
    "visitor_message_count": "用户消息数",
    "agent_message_count": "客服消息数",
    "unreplied_session_count": "未回复会话数",
    "visitor_silent_session_count": "客户无消息会话数",
    "queued_session_count": "排队会话量",
    "assigned_queue_session_count": "接入排队会话量",
    "unassigned_queue_session_count": "未接入排队会话量",
    "avg_queue_duration_seconds": "平均排队时长",
    "max_queue_duration_seconds": "最长排队时长",
    "queue_assign_rate": "排队接入率",
    "avg_first_human_response_seconds": "平均首响时长",
    "avg_agent_response_seconds": "平均响应时长",
    "avg_human_session_duration_seconds": "平均会话时长",
    "satisfaction_invitation_count": "满意度邀请量",
    "satisfaction_submission_count": "满意度评价量",
    "satisfaction_participation_rate": "会话参评率",
    "satisfaction_submission_rate": "邀请提交率",
    "product_satisfaction_count": "产品评价量",
}

_QUEUE_METRIC_LABELS = {
    "queued_session_count": "排队会话量",
    "assigned_queue_session_count": "接入排队会话量",
    "unassigned_queue_session_count": "未接入排队会话量",
    "queue_assign_rate": "排队接入率",
    "avg_queue_duration_seconds": "平均排队时长",
    "max_queue_duration_seconds": "最长排队时长",
    "final_session_count": "最终承接会话量",
    "effective_session_count": "有效会话数",
    "user_message_count": "用户消息数",
    "agent_message_count": "客服消息数",
    "unreplied_session_count": "未回复会话数",
    "visitor_silent_session_count": "客户无消息会话数",
    "avg_first_human_response_seconds": "平均首响时长",
    "avg_agent_response_seconds": "平均响应时长",
    "avg_human_session_duration_seconds": "平均会话时长",
    "satisfaction_invitation_count": "满意度邀请量",
    "satisfaction_submission_count": "满意度评价量",
    "satisfaction_participation_rate": "会话参评率",
    "satisfaction_submission_rate": "邀请提交率",
    "product_satisfaction_count": "产品评价量",
}

_OVERALL_DISTRIBUTION_LABELS = {
    "satisfaction_resolution": "解决情况",
    "service_satisfaction_rating": "服务满意度",
    "product_satisfaction_rating": "产品满意度",
}

_RESOLUTION_SLICE_LABELS = {
    "resolved": "已解决",
    "unresolved": "未解决",
}

_DISTRIBUTION_METRIC_SEPARATOR = ":"


def _overall_group_label(key: str) -> str:
    return _OVERALL_GROUP_LABELS.get(key, key)


def _overall_metric_label(key: str, dynamic_labels: dict[str, str] | None = None) -> str:
    if dynamic_labels and key in dynamic_labels:
        return dynamic_labels[key]
    return _OVERALL_METRIC_LABELS.get(key, key)


def _distribution_metric_key(distribution_key: str, slice_key: str) -> str:
    return f"{distribution_key}{_DISTRIBUTION_METRIC_SEPARATOR}{slice_key}"


def _distribution_metric_labels(distributions: list[dict]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for distribution in distributions:
        distribution_key = str(distribution.get("key") or "")
        if not distribution_key:
            continue
        distribution_label = _OVERALL_DISTRIBUTION_LABELS.get(distribution_key, distribution_key)
        for item in distribution.get("slices") or []:
            slice_key = str(item.get("key") or "")
            if not slice_key:
                continue
            slice_label = _distribution_slice_label(distribution_key, item)
            labels[_distribution_metric_key(distribution_key, slice_key)] = f"{distribution_label}：{slice_label}"
    return labels


def _distribution_slice_label(distribution_key: str, item: dict) -> str:
    slice_key = str(item.get("key") or "")
    if distribution_key == "satisfaction_resolution":
        return _RESOLUTION_SLICE_LABELS.get(slice_key, slice_key)
    return str(item.get("label") or slice_key)


def _format_metric_value(value: float | None, fmt: str) -> CellValue:
    if value is None:
        return "—" if fmt != MetricFormat.INTEGER.value else 0
    if fmt == MetricFormat.DURATION_SECONDS.value:
        return _format_duration(value)
    if fmt == MetricFormat.PERCENT.value:
        return f"{value * 100:.1f}%"
    return int(value)


async def export_session_report(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    scope: ExportScope,
    trend_type: TrendType,
    employee_id: int | None = None,
    q: str | None = None,
    sort: str = "session_count",
    order: str = "desc",
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> tuple[bytes, str]:
    """Build an XLSX workbook and return bytes plus a safe filename."""
    now = datetime.now(get_tenant_timezone(tenant_id))

    if scope == "overall":
        return await _export_overall(
            db,
            tenant_id,
            start_date,
            end_date,
            trend_type,
            now,
            report_scope=report_scope,
            principal=principal,
        )
    if scope == "employees":
        return await _export_employees(
            db,
            tenant_id,
            start_date,
            end_date,
            now,
            q=q,
            sort=sort,
            order=order,
            report_scope=report_scope,
        )
    if scope == "employee":
        if employee_id is None:
            raise ValidationError("employee_id is required for employee export")
        return await _export_employee(
            db,
            tenant_id,
            start_date,
            end_date,
            trend_type,
            employee_id,
            now,
            report_scope=report_scope,
            principal=principal,
        )
    raise ValidationError("Unsupported export scope")


async def export_queue_report(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    *,
    scope: QueueExportScope,
    trend_type: TrendType,
    group: str | None = None,
    queue_type: str | None = None,
    queue_id: int | None = None,
    q: str | None = None,
    sort: str = "queued_session_count",
    order: str = "desc",
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> tuple[bytes, str]:
    now = datetime.now(get_tenant_timezone(tenant_id))
    if scope == "list":
        return await _export_queue_list(
            db,
            tenant_id,
            start_date,
            end_date,
            now,
            q=q,
            queue_type=queue_type,
            sort=sort,
            order=order,
            report_scope=report_scope,
            principal=principal,
        )
    if scope == "detail":
        if not queue_type or queue_id is None:
            raise ValidationError("queue_type and queue_id are required for queue detail export")
        return await _export_queue_detail(
            db,
            tenant_id,
            start_date,
            end_date,
            trend_type,
            queue_type,
            queue_id,
            now,
            group=group,
            report_scope=report_scope,
            principal=principal,
        )
    raise ValidationError("Unsupported queue export scope")


def content_disposition(filename: str) -> str:
    """Return a UTF-8 Content-Disposition header value."""
    return f"attachment; filename*=UTF-8''{quote(filename)}"


async def _export_overall(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    exported_at: datetime,
    *,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> tuple[bytes, str]:
    overview = await sessions_service.get_overview(
        db,
        tenant_id,
        start_date,
        end_date,
        report_scope=report_scope,
        principal=principal,
    )
    trend = await sessions_service.get_trend(
        db,
        tenant_id,
        start_date,
        end_date,
        trend_type,
        report_scope=report_scope,
        principal=principal,
    )
    object_name = "整体报表"
    workbook = _build_xlsx([
        ("概览", _overview_sheet(
            object_name,
            start_date,
            end_date,
            trend_type,
            exported_at,
            overview,
            include_business_metrics=True,
        )),
        ("趋势", _trend_sheet(
            object_name,
            start_date,
            end_date,
            trend_type,
            exported_at,
            trend["buckets"],
            include_business_metrics=True,
        )),
    ])
    return workbook, _report_filename(object_name, start_date, end_date, exported_at, trend_type)


async def export_overall_grouped(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    *,
    report_scope: ReportScope | None = None,
) -> tuple[bytes, str]:
    """Grouped overall report export: one overview block + one trend block per
    metric group (open to new groups without changing this function)."""
    now = datetime.now(get_tenant_timezone(tenant_id))
    object_name = "整体报表"

    summary = await overall_service.get_overall_summary(
        db, tenant_id, start_date, end_date, report_scope=report_scope
    )
    overview_sheet = _overall_overview_sheet(
        object_name, start_date, end_date, trend_type, now, summary["metrics"]
    )
    dynamic_metric_labels = _distribution_metric_labels(summary.get("distributions") or [])

    trend_blocks: list[tuple[str, list[dict]]] = []
    for group in all_groups():
        trend = await overall_service.get_overall_trend(
            db, tenant_id, start_date, end_date, trend_type,
            group=group.key, report_scope=report_scope,
        )
        trend_blocks.append((group.key, trend))
    trend_sheet = _overall_trend_sheet(
        object_name, start_date, end_date, trend_type, now, trend_blocks, dynamic_metric_labels
    )

    workbook = _build_xlsx([
        ("概览", overview_sheet),
        ("趋势", trend_sheet),
    ])
    return workbook, _report_filename(object_name, start_date, end_date, now, trend_type)


def _overall_overview_sheet(
    object_name: str,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    exported_at: datetime,
    metrics: list[dict],
) -> list[list[CellValue]]:
    rows: list[list[CellValue]] = [
        ["导出信息"],
        ["字段", "值"],
        ["报表名称", "会话报表"],
        ["报表对象", object_name],
        ["日期范围", _date_range_label(start_date, end_date)],
        ["趋势类型", _trend_label(trend_type)],
        ["导出时间", _export_time_label(exported_at)],
    ]
    # Group the flat metric list by the registry's group order; the registry is
    # the single source of truth so the export blocks match the UI groups.
    available = {m["key"]: m for m in metrics if m.get("available", True)}
    for group in all_groups():
        block = [d for d in group.descriptors if d.key in available]
        if not block:
            continue
        rows.append([])
        rows.append([_overall_group_label(group.key)])
        rows.append(["指标", "数值"])
        for descriptor in block:
            metric = available[descriptor.key]
            rows.append([
                _overall_metric_label(descriptor.key),
                _format_metric_value(metric.get("value"), metric["format"]),
            ])
    return rows


def _overall_trend_sheet(
    object_name: str,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    exported_at: datetime,
    trend_blocks: list[tuple[str, dict]],
    dynamic_metric_labels: dict[str, str] | None = None,
) -> list[list[CellValue]]:
    rows: list[list[CellValue]] = [
        ["导出信息"],
        ["字段", "值"],
        ["报表名称", "会话报表"],
        ["报表对象", object_name],
        ["日期范围", _date_range_label(start_date, end_date)],
        ["趋势类型", _trend_label(trend_type)],
        ["导出时间", _export_time_label(exported_at)],
    ]
    for group_key, trend in trend_blocks:
        descriptors = trend["metrics"]
        if not descriptors:
            continue
        rows.append([])
        rows.append([_overall_group_label(group_key)])
        rows.append(["时段", *[_overall_metric_label(d["key"], dynamic_metric_labels) for d in descriptors]])
        for bucket in trend["buckets"]:
            value_by_key = {m["key"]: m for m in bucket["metrics"]}
            row: list[CellValue] = [bucket["label"]]
            for d in descriptors:
                metric = value_by_key.get(d["key"], {})
                row.append(_format_metric_value(metric.get("value"), d["format"]))
            rows.append(row)
    return rows


async def _export_employee(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    employee_id: int,
    exported_at: datetime,
    *,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> tuple[bytes, str]:
    employee = await employees_service.get_visible_employee(
        db,
        tenant_id,
        employee_id,
        report_scope,
    )
    object_name = _employee_display_name(employee)
    overview = await sessions_service.get_overview(
        db,
        tenant_id,
        start_date,
        end_date,
        employee_id=employee_id,
        report_scope=report_scope,
        principal=principal,
    )
    trend = await sessions_service.get_trend(
        db,
        tenant_id,
        start_date,
        end_date,
        trend_type,
        employee_id=employee_id,
        report_scope=report_scope,
        principal=principal,
    )
    workbook = _build_xlsx([
        ("概览", _overview_sheet(object_name, start_date, end_date, trend_type, exported_at, overview)),
        ("趋势", _trend_sheet(object_name, start_date, end_date, trend_type, exported_at, trend["buckets"])),
    ])
    return workbook, _report_filename(object_name, start_date, end_date, exported_at, trend_type)


async def _export_employees(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    exported_at: datetime,
    *,
    q: str | None,
    sort: str,
    order: str,
    report_scope: ReportScope | None = None,
) -> tuple[bytes, str]:
    data = await employees_service.list_employees_overview(
        db,
        tenant_id,
        start_date,
        end_date,
        q=q,
        sort=sort,
        order=order,
        page=1,
        per_page=1,
        paginate=False,
        report_scope=report_scope,
    )
    rows = [EmployeeOverviewRow.model_validate(item) for item in data["items"]]
    sheet = _employees_sheet(
        start_date,
        end_date,
        exported_at,
        rows,
        q=q,
        sort=data.get("sort", sort),
        order=data.get("order", order),
    )
    workbook = _build_xlsx([("员工列表", sheet)])
    return workbook, _employees_filename(start_date, end_date, exported_at)


def _overview_sheet(
    object_name: str,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    exported_at: datetime,
    overview: dict,
    *,
    include_business_metrics: bool = False,
) -> list[list[CellValue]]:
    metrics = OverviewMetrics.model_validate(overview)
    rows: list[list[CellValue]] = [
        ["导出信息"],
        ["字段", "值"],
        ["报表名称", "会话报表"],
        ["报表对象", object_name],
        ["日期范围", _date_range_label(start_date, end_date)],
        ["趋势类型", _trend_label(trend_type)],
        ["导出时间", _export_time_label(exported_at)],
        [],
        ["概览指标"],
        ["指标", "数值", "单位"],
        ["会话数", metrics.session_count, "次"],
        ["消息数", metrics.message_count, "条"],
        ["用户消息数", metrics.user_message_count, "条"],
        ["客服消息数", metrics.agent_message_count, "条"],
        ["平均会话时长", _format_duration(metrics.avg_duration_seconds), "时长"],
        ["人工接待量", metrics.reception_segment_count, "段"],
        ["参与会话数", metrics.reception_participated_session_count, "次"],
        ["最终负责会话数", metrics.reception_final_session_count, "次"],
        ["转接转入量", metrics.reception_transfer_in_count, "次"],
        ["转接转出量", metrics.reception_transfer_out_count, "次"],
    ]
    if include_business_metrics:
        rows.extend([
            ["机器人会话量", metrics.bot_session_count, "次"],
            ["机器人转人工量", metrics.bot_handoff_count, "次"],
            ["排队会话量", metrics.queued_session_count, "次"],
            ["平均排队时长", _format_duration(metrics.avg_queue_duration_seconds), "时长"],
        ])
        if metrics.can_view_offline_messages:
            rows.append(["留言数量", metrics.offline_message_count or 0, "条"])
    return rows


def _trend_sheet(
    object_name: str,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    exported_at: datetime,
    buckets: list[dict],
    *,
    include_business_metrics: bool = False,
) -> list[list[CellValue]]:
    can_view_offline_messages = _trend_can_view_offline_messages(buckets)
    headers = ["时段", "会话数", "消息数", "用户消息数", "客服消息数", "平均会话时长"]
    if include_business_metrics:
        headers.extend(["机器人会话量", "机器人转人工量", "排队会话量", "平均排队时长"])
        if can_view_offline_messages:
            headers.append("留言数量")
    rows: list[list[CellValue]] = [
        ["导出信息"],
        ["字段", "值"],
        ["报表名称", "会话报表"],
        ["报表对象", object_name],
        ["日期范围", _date_range_label(start_date, end_date)],
        ["趋势类型", _trend_label(trend_type)],
        ["导出时间", _export_time_label(exported_at)],
        [],
        ["趋势明细"],
        headers,
    ]
    for bucket in buckets:
        metrics = OverviewMetrics.model_validate(bucket["metrics"])
        row: list[CellValue] = [
            bucket["label"],
            metrics.session_count,
            metrics.message_count,
            metrics.user_message_count,
            metrics.agent_message_count,
            _format_duration(metrics.avg_duration_seconds),
        ]
        if include_business_metrics:
            row.extend([
                metrics.bot_session_count,
                metrics.bot_handoff_count,
                metrics.queued_session_count,
                _format_duration(metrics.avg_queue_duration_seconds),
            ])
            if can_view_offline_messages:
                row.append(metrics.offline_message_count or 0)
        rows.append(row)
    return rows


def _trend_can_view_offline_messages(buckets: list[dict]) -> bool:
    if not buckets:
        return False
    metrics = OverviewMetrics.model_validate(buckets[0].get("metrics", {}))
    return metrics.can_view_offline_messages


def _employees_sheet(
    start_date: date,
    end_date: date,
    exported_at: datetime,
    rows: list[EmployeeOverviewRow],
    *,
    q: str | None,
    sort: str,
    order: str,
) -> list[list[CellValue]]:
    sheet: list[list[CellValue]] = [
        ["导出信息"],
        ["字段", "值"],
        ["报表名称", "会话报表"],
        ["报表对象", "员工报表列表"],
        ["日期范围", _date_range_label(start_date, end_date)],
        ["趋势类型", "不适用"],
        ["搜索条件", q.strip() if q and q.strip() else "全部员工"],
        ["排序条件", _sort_label(sort, order)],
        ["导出时间", _export_time_label(exported_at)],
        [],
        ["员工指标列表"],
        [
            "员工名称", "账号", "状态", "会话数", "消息数", "用户消息数", "客服消息数", "平均会话时长",
            "人工接待量", "参与会话数", "最终负责会话数", "转接转入量", "转接转出量",
        ],
    ]
    for row in rows:
        employee = row.employee
        metrics = row.metrics
        sheet.append([
            employee.display_name or employee.name or "—",
            employee.username or employee.email or "—",
            "启用" if employee.is_active else "停用",
            metrics.session_count,
            metrics.message_count,
            metrics.user_message_count,
            metrics.agent_message_count,
            _format_duration(metrics.avg_duration_seconds),
            metrics.reception_segment_count,
            metrics.reception_participated_session_count,
            metrics.reception_final_session_count,
            metrics.reception_transfer_in_count,
            metrics.reception_transfer_out_count,
        ])
    return sheet


async def _export_queue_list(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    exported_at: datetime,
    *,
    q: str | None,
    queue_type: str | None,
    sort: str,
    order: str,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> tuple[bytes, str]:
    data = await queues_service.list_queues_overview(
        db,
        tenant_id,
        start_date,
        end_date,
        q=q,
        queue_type=queue_type,
        sort=sort,
        order=order,
        page=1,
        per_page=1,
        paginate=False,
        report_scope=report_scope,
        principal=principal,
    )
    rows = [QueueOverviewRow.model_validate(item) for item in data["items"]]
    sheet = _queue_list_sheet(
        start_date,
        end_date,
        exported_at,
        rows,
        q=q,
        queue_type=queue_type,
        sort=data.get("sort", sort),
        order=data.get("order", order),
    )
    workbook = _build_xlsx([("队列列表", sheet)])
    return workbook, _queue_list_filename(start_date, end_date, exported_at)


async def _export_queue_detail(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    queue_type: str,
    queue_id: int,
    exported_at: datetime,
    *,
    group: str | None,
    report_scope: ReportScope | None = None,
    principal: EffectivePrincipal | None = None,
) -> tuple[bytes, str]:
    detail = await queues_service.get_queue_detail(
        db,
        tenant_id,
        start_date,
        end_date,
        queue_type,
        queue_id,
        report_scope=report_scope,
        principal=principal,
    )
    trend = await queues_service.get_queue_trend(
        db,
        tenant_id,
        start_date,
        end_date,
        trend_type,
        queue_type,
        queue_id,
        group=group,
        report_scope=report_scope,
        principal=principal,
    )
    object_name = detail["queue"]["name"]
    dynamic_metric_labels = _distribution_metric_labels(detail.get("distributions") or [])
    workbook = _build_xlsx([
        ("概览", _queue_detail_overview_sheet(
            object_name,
            start_date,
            end_date,
            trend_type,
            exported_at,
            detail,
        )),
        ("趋势", _queue_detail_trend_sheet(
            object_name,
            start_date,
            end_date,
            trend_type,
            exported_at,
            trend,
            dynamic_metric_labels,
        )),
    ])
    return workbook, _queue_detail_filename(object_name, start_date, end_date, exported_at, trend_type)


def _queue_list_sheet(
    start_date: date,
    end_date: date,
    exported_at: datetime,
    rows: list[QueueOverviewRow],
    *,
    q: str | None,
    queue_type: str | None,
    sort: str,
    order: str,
) -> list[list[CellValue]]:
    sheet: list[list[CellValue]] = [
        ["导出信息"],
        ["字段", "值"],
        ["报表名称", "会话报表"],
        ["报表对象", "队列报表列表"],
        ["日期范围", _date_range_label(start_date, end_date)],
        ["队列类型", _queue_type_filter_label(queue_type)],
        ["搜索条件", q.strip() if q and q.strip() else "全部队列"],
        ["排序条件", _queue_sort_label(sort, order)],
        ["导出时间", _export_time_label(exported_at)],
        [],
        ["队列指标列表"],
        [
            "队列名称", "队列类型", "状态", "排队会话量", "接入排队会话量", "未接入排队会话量",
            "排队接入率", "平均排队时长", "最长排队时长", "最终承接会话量",
        ],
    ]
    for row in rows:
        queue = row.queue
        metrics = row.metrics
        sheet.append([
            queue.name,
            _queue_type_label(queue.queue_type),
            _queue_status_label(queue.status),
            metrics.queued_session_count,
            metrics.assigned_queue_session_count,
            metrics.unassigned_queue_session_count,
            _format_metric_value(metrics.queue_assign_rate, MetricFormat.PERCENT.value),
            _format_duration(metrics.avg_queue_duration_seconds),
            _format_duration(metrics.max_queue_duration_seconds),
            metrics.final_session_count,
        ])
    return sheet


def _queue_detail_overview_sheet(
    object_name: str,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    exported_at: datetime,
    detail: dict,
) -> list[list[CellValue]]:
    queue = detail["queue"]
    metrics = QueueReportMetrics.model_validate(detail["metrics"])
    rows: list[list[CellValue]] = [
        ["导出信息"],
        ["字段", "值"],
        ["报表名称", "会话报表"],
        ["报表对象", object_name],
        ["队列类型", _queue_type_label(queue["queue_type"])],
        ["队列状态", _queue_status_label(queue["status"])],
        ["日期范围", _date_range_label(start_date, end_date)],
        ["趋势类型", _trend_label(trend_type)],
        ["导出时间", _export_time_label(exported_at)],
        [],
        ["排队接入"],
        ["指标", "数值"],
        ["排队会话量", metrics.queued_session_count],
        ["接入排队会话量", metrics.assigned_queue_session_count],
        ["未接入排队会话量", metrics.unassigned_queue_session_count],
        ["排队接入率", _format_metric_value(metrics.queue_assign_rate, MetricFormat.PERCENT.value)],
        ["平均排队时长", _format_duration(metrics.avg_queue_duration_seconds)],
        ["最长排队时长", _format_duration(metrics.max_queue_duration_seconds)],
        [],
        ["人工会话与消息"],
        ["指标", "数值"],
        ["最终承接会话量", metrics.final_session_count],
        ["有效会话数", metrics.effective_session_count],
        ["用户消息数", metrics.user_message_count],
        ["客服消息数", metrics.agent_message_count],
        ["未回复会话数", metrics.unreplied_session_count],
        ["客户无消息会话数", metrics.visitor_silent_session_count],
        [],
        ["服务效率"],
        ["指标", "数值"],
        ["平均首响时长", _format_duration(metrics.avg_first_human_response_seconds)],
        ["平均响应时长", _format_duration(metrics.avg_agent_response_seconds)],
        ["平均会话时长", _format_duration(metrics.avg_human_session_duration_seconds)],
        [],
        ["满意度"],
        ["指标", "数值"],
        ["满意度邀请量", metrics.satisfaction_invitation_count],
        ["满意度评价量", metrics.satisfaction_submission_count],
        ["会话参评率", _format_metric_value(metrics.satisfaction_participation_rate, MetricFormat.PERCENT.value)],
        ["邀请提交率", _format_metric_value(metrics.satisfaction_submission_rate, MetricFormat.PERCENT.value)],
        ["产品评价量", metrics.product_satisfaction_count],
    ]
    return rows


def _queue_detail_trend_sheet(
    object_name: str,
    start_date: date,
    end_date: date,
    trend_type: TrendType,
    exported_at: datetime,
    trend: dict,
    dynamic_metric_labels: dict[str, str] | None = None,
) -> list[list[CellValue]]:
    descriptors = trend["metrics"]
    rows: list[list[CellValue]] = [
        ["导出信息"],
        ["字段", "值"],
        ["报表名称", "会话报表"],
        ["报表对象", object_name],
        ["日期范围", _date_range_label(start_date, end_date)],
        ["趋势类型", _trend_label(trend_type)],
        ["指标组", _overall_group_label(trend["group"])],
        ["导出时间", _export_time_label(exported_at)],
        [],
        ["趋势明细"],
        ["时段", *[_queue_metric_label(d["key"], dynamic_metric_labels) for d in descriptors]],
    ]
    for bucket in trend["buckets"]:
        value_by_key = {m["key"]: m for m in bucket["metrics"]}
        row: list[CellValue] = [bucket["label"]]
        for descriptor in descriptors:
            metric = value_by_key.get(descriptor["key"], {})
            row.append(_format_metric_value(metric.get("value"), descriptor["format"]))
        rows.append(row)
    return rows


def _build_xlsx(sheets: list[tuple[str, list[list[CellValue]]]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml([name for name, _ in sheets]))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        for idx, (_, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{idx}.xml", _worksheet_xml(rows))
    return buffer.getvalue()


def _content_types_xml(sheet_count: int) -> str:
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{overrides}"
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(_sheet_name(name))}" sheetId="{idx}" r:id="rId{idx}"/>'
        for idx, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets>"
        "</workbook>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = "".join(
        f'<Relationship Id="rId{i}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{rels}"
        "</Relationships>"
    )


def _worksheet_xml(rows: list[list[CellValue]]) -> str:
    row_xml = []
    for row_idx, row in enumerate(rows, start=1):
        cells = "".join(_cell_xml(row_idx, col_idx, value) for col_idx, value in enumerate(row, start=1))
        row_xml.append(f'<row r="{row_idx}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(row_xml)}</sheetData>"
        "</worksheet>"
    )


def _cell_xml(row_idx: int, col_idx: int, value: CellValue) -> str:
    ref = f"{_column_name(col_idx)}{row_idx}"
    if value is None:
        return f'<c r="{ref}"/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, int | float):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = str(value)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return f'<c r="{ref}" t="inlineStr"><is><t{preserve}>{escape(text)}</t></is></c>'


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _sheet_name(name: str) -> str:
    return re.sub(r"[\[\]:*?/\\]", "_", name)[:31] or "Sheet"


def _date_range_label(start_date: date, end_date: date) -> str:
    return f"{start_date.isoformat()} 至 {end_date.isoformat()}"


def _trend_label(trend_type: TrendType) -> str:
    return _TREND_LABELS[trend_type]


def _sort_label(sort: str, order: str) -> str:
    direction = "升序" if order == "asc" else "倒序"
    return f"{_SORT_LABELS.get(sort, sort)}{direction}"


def _queue_sort_label(sort: str, order: str) -> str:
    direction = "升序" if order == "asc" else "倒序"
    return f"{_QUEUE_SORT_LABELS.get(sort, sort)}{direction}"


def _queue_metric_label(key: str, dynamic_labels: dict[str, str] | None = None) -> str:
    if dynamic_labels and key in dynamic_labels:
        return dynamic_labels[key]
    return _QUEUE_METRIC_LABELS.get(key, key)


def _queue_type_filter_label(queue_type: str | None) -> str:
    if not queue_type:
        return "全部队列"
    return _queue_type_label(queue_type)


def _queue_type_label(queue_type: str) -> str:
    if queue_type == "employee_group":
        return "员工组队列"
    return queue_type


def _queue_status_label(status: str) -> str:
    if status == "active":
        return "启用"
    if status == "inactive":
        return "停用"
    if status == "deleted":
        return "已删除"
    return status


def _export_time_label(exported_at: datetime) -> str:
    return exported_at.strftime("%Y-%m-%d %H:%M:%S")


def _compact_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _report_filename(
    object_name: str,
    start_date: date,
    end_date: date,
    exported_at: datetime,
    trend_type: TrendType,
) -> str:
    return _safe_filename(
        "会话报表_"
        f"{object_name}_"
        f"{_compact_date(start_date)}-{_compact_date(end_date)}_"
        f"{_trend_label(trend_type)}_"
        f"{exported_at.strftime('%Y%m%d%H%M%S')}.xlsx"
    )


def _employees_filename(start_date: date, end_date: date, exported_at: datetime) -> str:
    return _safe_filename(
        "会话报表_员工列表_"
        f"{_compact_date(start_date)}-{_compact_date(end_date)}_"
        f"{exported_at.strftime('%Y%m%d%H%M%S')}.xlsx"
    )


def _queue_list_filename(start_date: date, end_date: date, exported_at: datetime) -> str:
    return _safe_filename(
        "会话报表_队列列表_"
        f"{_compact_date(start_date)}-{_compact_date(end_date)}_"
        f"{exported_at.strftime('%Y%m%d%H%M%S')}.xlsx"
    )


def _queue_detail_filename(
    object_name: str,
    start_date: date,
    end_date: date,
    exported_at: datetime,
    trend_type: TrendType,
) -> str:
    return _safe_filename(
        "会话报表_队列报表_"
        f"{object_name}_"
        f"{_compact_date(start_date)}-{_compact_date(end_date)}_"
        f"{_trend_label(trend_type)}_"
        f"{exported_at.strftime('%Y%m%d%H%M%S')}.xlsx"
    )


def _safe_filename(value: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" .")
    return safe or "会话报表导出.xlsx"


def _employee_display_name(employee: Employee) -> str:
    return employee.display_name or employee.name or employee.username or f"员工{employee.id}"


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
