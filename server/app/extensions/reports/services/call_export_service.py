"""XLSX exports for grouped call reports."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import TypeAlias

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService, RESOURCE_CALL_RECORD

from ..lib.buckets import TrendType
from ..lib.call_agent_metric_groups import all_groups as all_agent_groups
from ..lib.call_metric_groups import all_groups as all_overall_groups
from ..lib.call_queue_metric_groups import all_groups as all_queue_groups
from ..lib.tz import get_tenant_timezone
from ..schemas import MetricFormat
from . import call_employees_service, call_overall_service, call_queues_service, export_service

CellValue: TypeAlias = str | int | float | None

_TREND_LABELS = {
    TrendType.HALF_HOUR: "半小时", TrendType.HOUR: "小时", TrendType.DAY: "日",
    TrendType.WEEK: "周", TrendType.MONTH: "月",
}
_GROUP_LABELS = {
    "call_overview": "通话概览", "inbound_service": "呼入人工服务",
    "outbound_service": "外呼服务", "service_efficiency": "服务效率",
    "satisfaction": "满意度", "queue_flow": "队列流量",
    "queue_outcomes": "接听与流失", "queue_waiting": "等待与服务水平",
    "agent_response": "客服响应", "workload": "接待工作量",
    "offer_response": "Offer 响应", "efficiency": "处理效率",
    "collaboration": "协作流转",
}
_METRIC_LABELS = {
    "call_count": "总通话量", "inbound_call_count": "呼入量", "outbound_call_count": "呼出量",
    "active_call_count": "进行中通话量", "ended_call_count": "已结束通话量",
    "inbound_human_request_count": "请求人工量", "inbound_human_wait_count": "进入排队量",
    "inbound_agent_ringing_count": "客服振铃量", "inbound_agent_answered_count": "客服接听量",
    "inbound_human_answer_rate": "人工请求接听率", "inbound_queue_answer_rate": "排队接听率",
    "inbound_short_abandon_count": "短时放弃量", "inbound_short_abandon_rate": "短时放弃率",
    "inbound_avg_wait_seconds": "平均等待时长", "inbound_service_level_20s": "20 秒服务水平",
    "outbound_attempt_count": "外呼发起量", "outbound_customer_connected_count": "客户接通量",
    "outbound_agent_connected_count": "客服接通量", "outbound_customer_connect_rate": "客户接通率",
    "outbound_avg_customer_ring_seconds": "客户平均振铃时长", "outbound_avg_talk_seconds": "呼出平均通话时长",
    "human_served_call_count": "人工服务通话量", "total_human_talk_seconds": "人工通话总时长",
    "avg_human_talk_seconds": "人工平均通话时长", "avg_total_duration_seconds": "平均通话总时长",
    "customer_hangup_rate": "客户挂断率", "survey_triggered_count": "满意度触发量",
    "survey_answered_count": "满意度参与量", "survey_participation_rate": "满意度参与率",
    "survey_completed_count": "满意度完成量", "survey_completion_rate": "满意度完成率",
    "queue_call_count": "涉及通话量", "queue_entry_count": "入队次数",
    "first_queue_entry_count": "首次入队次数", "transfer_in_entry_count": "转入次数",
    "queue_answered_count": "接通次数", "queue_answer_rate": "接通率",
    "queue_abandoned_count": "客户放弃次数", "queue_abandon_rate": "客户放弃率",
    "queue_short_abandon_count": "短放弃量", "queue_short_abandon_rate": "短放弃率",
    "queue_timeout_count": "队列超时量", "queue_transfer_out_count": "队列转出量",
    "avg_answer_wait_seconds": "平均应答等待", "avg_abandon_wait_seconds": "平均放弃等待",
    "avg_queue_wait_seconds": "平均队列等待", "max_queue_wait_seconds": "最长队列等待",
    "queue_service_level_20s": "20 秒服务水平", "offered_call_count": "收到 Offer 的通话量",
    "offer_attempt_count": "Offer 次数", "offer_accepted_count": "Offer 接受次数",
    "offer_rejected_count": "Offer 明确拒绝次数", "offer_timeout_count": "Offer 超时次数",
    "offer_accept_rate": "Offer 接受率", "participated_call_count": "参与通话量",
    "handled_call_count": "接待通话量", "reception_segment_count": "接待段数",
    "inbound_handled_call_count": "呼入接待量", "outbound_customer_answered_count": "外呼客户接通量",
    "outbound_handled_call_count": "外呼接待量", "transfer_in_segment_count": "转入接待段数",
    "offer_timeout_rate": "Offer 超时率", "avg_offer_response_seconds": "平均 Offer 响应时长",
    "total_talk_seconds": "通话总时长", "avg_talk_seconds": "平均通话时长",
    "held_segment_count": "发生保持的接待段数", "total_hold_seconds": "客户保持总时长",
    "avg_hold_seconds": "平均保持时长", "total_after_call_work_seconds": "话后处理总时长",
    "avg_after_call_work_seconds": "平均话后处理时长", "avg_handle_seconds": "平均处理时长",
    "transfer_attempt_count": "转出尝试次数", "transfer_completed_count": "成功转出次数",
    "transfer_success_rate": "转出成功率", "transfer_failed_count": "转出失败次数",
    "consult_attempt_count": "咨询次数", "consult_connected_count": "咨询接通次数",
    "consult_success_rate": "咨询接通率", "conference_join_count": "三方参与次数",
}
_DISTRIBUTION_LABELS = {
    "direction": "呼叫方向分布", "call_source": "呼叫来源分布",
    "actual_reception_type": "实际接待类型分布", "inbound_call_result": "呼入结果分布",
    "inbound_human_funnel": "人工服务阶段漏斗", "outbound_call_source": "外呼来源分布",
    "outbound_call_result": "外呼结果分布", "call_result": "全部通话结果分布",
    "hangup_party": "挂断方分布", "hangup_stage": "结束阶段分布",
    "satisfaction_result": "满意度结果分布", "satisfaction_trigger_source": "满意度触发来源",
    "satisfaction_primary_option": "首个作答选项分布", "queue_exit_result": "离队结果分布",
    "queue_wait_duration": "等待时长分布", "offer_result": "Offer 结果分布",
    "reception_entry_reason": "接待进入原因分布", "handle_duration": "处理时长分布",
    "reception_end_reason": "接待结束原因分布",
}
_ENUM_LABELS = {
    "inbound": "呼入", "outbound": "外呼", "agent_dial": "客服拨号",
    "manual_outbound_task": "手动外呼任务", "auto_outbound": "自动外呼", "ivr": "IVR",
    "bot": "机器人", "agent": "人工客服", "bot_agent": "机器人转人工", "not_formed": "未形成接待",
    "agent_answered": "客服已接听", "customer_short_abandon": "客户短时放弃",
    "agent_no_answer": "客服未接听", "customer_no_answer": "客户未接听", "customer_busy": "客户忙线",
    "customer_unreachable": "客户不可达", "provider_answer_unconfirmed": "振铃超时，供应商未确认接听",
    "provider_temporarily_unavailable": "供应商返回暂时无法接通",
    "invalid_number": "号码无效", "ivr_customer_hangup": "客户在 IVR 挂断",
    "bot_customer_hangup": "客户在机器人阶段挂断", "bot_completed": "机器人完成",
    "canceled": "已取消", "failed": "失败", "customer": "客户", "supervisor": "班长",
    "system": "系统", "carrier": "运营商", "unknown": "未知", "pre_route": "路由前",
    "customer_ringing": "客户振铃", "agent_waiting": "客服等待", "agent_ringing": "客服振铃",
    "in_call": "通话中", "completed": "完成", "partial": "部分完成", "unanswered": "未作答",
    "not_surveyed": "未调查", "post_call": "通话后", "during_call": "通话中",
    "auto_transfer": "自动转满意度", "agent_invite": "客服邀请", "other": "其他",
    "answered": "已接通", "abandoned": "已放弃", "timeout": "已超时", "transfer_out": "已转出",
    "accepted": "已接受", "rejected": "已拒绝", "bridge_failed": "桥接失败",
    "0_5s": "0–5 秒", "5_20s": ">5–20 秒", "20_60s": ">20–60 秒",
    "60_180s": ">60–180 秒", "over_180s": ">180 秒", "initial": "首次接入",
    "agent_transfer": "客服转入", "queue_transfer": "队列转入", "supervisor_takeover": "主管接管",
    "0_1m": "0–1 分钟", "1_3m": ">1–3 分钟", "3_5m": ">3–5 分钟",
    "5_10m": ">5–10 分钟", "over_10m": ">10 分钟", "call_ended": "通话结束",
    "transfer_completed": "成功转出", "agent_exit": "客服退出", "system_error": "系统异常",
}
_QUEUE_SORT_LABELS = {key: label for key, label in _METRIC_LABELS.items()}
_QUEUE_SORT_LABELS.update({"name": "队列", "queue_type": "类型", "status": "状态"})
_EMPLOYEE_SORT_LABELS = {key: label for key, label in _METRIC_LABELS.items()}
_EMPLOYEE_SORT_LABELS.update({"name": "员工", "status": "状态"})


async def export_overall(db: AsyncSession, tenant_id: int, start: date, end: date, trend: TrendType,
                         principal: EffectivePrincipal) -> tuple[bytes, str]:
    exported_at = datetime.now(get_tenant_timezone(tenant_id))
    summary = await call_overall_service.get_overall_summary(db, tenant_id, start, end, principal=principal)
    trends = []
    for group in all_overall_groups():
        trends.append(await call_overall_service.get_overall_trend(
            db, tenant_id, start, end, trend, group=group.key, principal=principal
        ))
    sheets = [
        ("概览", _detail_overview_rows("整体报表", start, end, trend, exported_at, summary, principal)),
        ("趋势", _trend_rows("整体报表", start, end, trend, exported_at, trends, summary, principal)),
    ]
    return export_service._build_xlsx(sheets), _detail_filename("整体报表", start, end, trend, exported_at)


async def export_queue_list(db: AsyncSession, tenant_id: int, start: date, end: date, *, q: str | None,
                            queue_type: str, sort: str, order: str,
                            principal: EffectivePrincipal) -> tuple[bytes, str]:
    exported_at = datetime.now(get_tenant_timezone(tenant_id))
    data = await call_queues_service.list_queues(
        db, tenant_id, start, end, principal=principal, q=q, queue_type=queue_type,
        sort=sort, order=order, page=1, per_page=100, paginate=False,
    )
    rows = _common_rows("队列列表", start, end, None, exported_at, data, principal)
    rows.extend([
        ["搜索条件", q.strip() if q and q.strip() else "全部队列"],
        ["队列类型", _queue_type_filter_label(queue_type)],
        ["排序条件", _sort_label(sort, order, _QUEUE_SORT_LABELS)],
        ["匹配队列数", data["total"]], [], ["队列列表"],
        ["队列", "类型", "状态", "涉及通话量", "入队次数", "接通次数", "接通率",
         "客户放弃次数", "客户放弃率", "平均应答等待", "20 秒服务水平"],
    ])
    for item in data["items"]:
        queue, metrics = item["queue"], item["metrics"]
        rows.append([
            _queue_display_name(queue.get("name")), _queue_type_label(queue["queue_type"]), _status_label(queue["status"]),
            metrics["queue_call_count"], metrics["queue_entry_count"], metrics["queue_answered_count"],
            _format_value(metrics["queue_answer_rate"], MetricFormat.PERCENT.value), metrics["queue_abandoned_count"],
            _format_value(metrics["queue_abandon_rate"], MetricFormat.PERCENT.value),
            _format_value(metrics["avg_answer_wait_seconds"], MetricFormat.DURATION_SECONDS.value),
            _format_value(metrics["queue_service_level_20s"], MetricFormat.PERCENT.value),
        ])
    filename = _list_filename("队列列表", start, end, exported_at)
    return export_service._build_xlsx([("队列列表", rows)]), filename


async def export_queue_detail(db: AsyncSession, tenant_id: int, start: date, end: date, trend: TrendType,
                              queue_type: str, queue_id: int,
                              principal: EffectivePrincipal) -> tuple[bytes, str]:
    exported_at = datetime.now(get_tenant_timezone(tenant_id))
    summary = await call_queues_service.get_queue_summary(
        db, tenant_id, start, end, queue_type, queue_id, principal=principal
    )
    trends = []
    for group in all_queue_groups():
        trends.append(await call_queues_service.get_queue_trend(
            db, tenant_id, start, end, queue_type, queue_id, trend, group=group.key, principal=principal
        ))
    name = _queue_display_name(summary["queue"].get("name"))
    object_rows = [["队列名称", name], ["队列类型", _queue_type_label(summary["queue"]["queue_type"])],
                   ["队列状态", _status_label(summary["queue"]["status"])]]
    sheets = [
        ("概览", _detail_overview_rows(name, start, end, trend, exported_at, summary, principal, object_rows)),
        ("趋势", _trend_rows(name, start, end, trend, exported_at, trends, summary, principal)),
    ]
    return export_service._build_xlsx(sheets), _detail_filename(f"队列_{name}", start, end, trend, exported_at)


async def export_employee_list(db: AsyncSession, tenant_id: int, start: date, end: date, *, q: str | None,
                               group_id: int | None, status: str, sort: str, order: str,
                               principal: EffectivePrincipal) -> tuple[bytes, str]:
    exported_at = datetime.now(get_tenant_timezone(tenant_id))
    data = await call_employees_service.list_employees_overview(
        db, tenant_id, start, end, principal=principal, q=q, group_id=group_id, status=status,
        sort=sort, order=order, page=1, per_page=100, paginate=False,
    )
    group_name = (
        await call_employees_service.get_employee_group_name(db, tenant_id, group_id)
        if group_id is not None else None
    )
    rows = _common_rows("员工列表", start, end, None, exported_at, data, principal)
    rows.extend([
        ["搜索条件", q.strip() if q and q.strip() else "全部员工"],
        ["当前员工组", group_name or ("未知员工组" if group_id is not None else "全部员工组")],
        ["员工状态", _employee_status_filter_label(status)],
        ["排序条件", _sort_label(sort, order, _EMPLOYEE_SORT_LABELS)],
        ["匹配员工数", data["total"]], [], ["员工列表"],
        ["员工", "账号 / 邮箱", "状态", "参与通话量", "接待通话量", "接待段数", "呼入接待量",
         "外呼发起量", "外呼客户接通量", "Offer 接受率", "平均通话时长", "平均处理时长", "成功转出次数"],
    ])
    for item in data["items"]:
        employee, metrics = item["employee"], item["metrics"]
        rows.append([
            _employee_display_name(employee),
            "—" if employee["status"] == "deleted" else employee.get("username") or employee.get("email") or "—",
            _status_label(employee["status"]), metrics["participated_call_count"], metrics["handled_call_count"],
            metrics["reception_segment_count"], metrics["inbound_handled_call_count"], metrics["outbound_attempt_count"],
            metrics["outbound_customer_answered_count"], _format_value(metrics["offer_accept_rate"], MetricFormat.PERCENT.value),
            _format_value(metrics["avg_talk_seconds"], MetricFormat.DURATION_SECONDS.value),
            _format_value(metrics["avg_handle_seconds"], MetricFormat.DURATION_SECONDS.value), metrics["transfer_completed_count"],
        ])
    return export_service._build_xlsx([("员工列表", rows)]), _list_filename("员工列表", start, end, exported_at)


async def export_employee_detail(db: AsyncSession, tenant_id: int, start: date, end: date, trend: TrendType,
                                 employee_id: int, principal: EffectivePrincipal) -> tuple[bytes, str]:
    exported_at = datetime.now(get_tenant_timezone(tenant_id))
    summary = await call_employees_service.get_employee_summary(
        db, tenant_id, start, end, employee_id, principal=principal
    )
    trends = []
    for group in all_agent_groups():
        trends.append(await call_employees_service.get_employee_trend(
            db, tenant_id, start, end, employee_id, trend, group=group.key, principal=principal
        ))
    employee = summary["employee"]
    name = _employee_display_name(employee)
    object_rows = [["员工名称", name],
                   ["账号 / 邮箱", "—" if employee["status"] == "deleted" else employee.get("username") or employee.get("email") or "—"],
                   ["员工状态", _status_label(employee["status"])],
                   ["当前员工组", "、".join(summary.get("group_names") or []) or "—"]]
    sheets = [
        ("概览", _detail_overview_rows(name, start, end, trend, exported_at, summary, principal, object_rows)),
        ("趋势", _trend_rows(name, start, end, trend, exported_at, trends, summary, principal)),
    ]
    return export_service._build_xlsx(sheets), _detail_filename(f"员工_{name}", start, end, trend, exported_at)


def content_disposition(filename: str) -> str:
    return export_service.content_disposition(filename)


def _detail_overview_rows(object_name: str, start: date, end: date, trend: TrendType,
                          exported_at: datetime, summary: dict, principal: EffectivePrincipal,
                          object_rows: list[list[CellValue]] | None = None) -> list[list[CellValue]]:
    rows = _common_rows(object_name, start, end, trend, exported_at, summary, principal)
    if object_rows:
        rows.extend([[], ["对象信息"], ["字段", "值"], *object_rows])
    metrics_by_group: dict[str, list[dict]] = {}
    for metric in summary.get("metrics") or []:
        metrics_by_group.setdefault(metric.get("group") or "", []).append(metric)
    for group, metrics in metrics_by_group.items():
        rows.extend([[], [_GROUP_LABELS.get(group, group)], ["指标", "数值", "格式"]])
        rows.extend([_METRIC_LABELS.get(metric["key"], metric["key"]),
                     _format_value(metric.get("value"), metric["format"]), _format_label(metric["format"])]
                    for metric in metrics if metric.get("available", True))
        for distribution in [item for item in summary.get("distributions") or [] if item.get("group") == group]:
            rows.extend([[], [_DISTRIBUTION_LABELS.get(distribution["key"], distribution["key"])],
                         ["分布项", "数量", "占比"]])
            total = distribution.get("total") or 0
            for item in distribution.get("slices") or []:
                ratio = item["value"] / total if total else None
                rows.append([_ENUM_LABELS.get(item["key"], item.get("label") or "未知"), item["value"],
                             _format_value(ratio, MetricFormat.PERCENT.value)])
    if summary.get("coverage", {}).get("status") == "unavailable":
        rows.extend([[], ["所选时间内暂无可用的报表历史数据"]])
    return rows


def _trend_rows(object_name: str, start: date, end: date, trend: TrendType, exported_at: datetime,
                trends: list[dict], summary: dict, principal: EffectivePrincipal) -> list[list[CellValue]]:
    rows = _common_rows(object_name, start, end, trend, exported_at, summary, principal)
    for block in trends:
        descriptors = block.get("metrics") or []
        rows.extend([[], [_GROUP_LABELS.get(block["group"], block["group"])],
                     ["时段", *[_METRIC_LABELS.get(item["key"], item["key"]) for item in descriptors]]])
        for bucket in block.get("buckets") or []:
            values = {item["key"]: item for item in bucket.get("metrics") or []}
            rows.append([bucket["label"], *[
                _format_value(values.get(item["key"], {}).get("value"), item["format"])
                for item in descriptors
            ]])
    return rows


def _common_rows(object_name: str, start: date, end: date, trend: TrendType | None, exported_at: datetime,
                 result: dict, principal: EffectivePrincipal) -> list[list[CellValue]]:
    coverage = result.get("coverage") or {}
    return [["导出信息"], ["字段", "值"], ["报表名称", "通话报表"], ["报表对象", object_name],
            ["日期范围", f"{start.isoformat()} 至 {end.isoformat()}"],
            ["趋势类型", _TREND_LABELS[trend] if trend else "不适用"],
            ["数据截至时间", _format_datetime(result.get("as_of"))],
            ["导出时间", exported_at.strftime("%Y-%m-%d %H:%M:%S")],
            ["数据范围说明", _scope_label(principal)],
            ["历史覆盖状态", _coverage_label(coverage.get("status"))],
            ["完整数据起点", _format_datetime(coverage.get("effective_at"))],
            ["实际统计范围", _actual_range_label(coverage)],
            ["数据质量摘要", _quality_label(result.get("data_quality") or {})]]


def _format_value(value: float | int | None, format_key: str) -> CellValue:
    if value is None:
        return "—" if format_key != MetricFormat.INTEGER.value else 0
    if format_key == MetricFormat.PERCENT.value:
        return f"{float(value) * 100:.1f}%"
    if format_key == MetricFormat.DURATION_SECONDS.value:
        return export_service._format_duration(float(value))
    return int(value)


def _format_label(value: str) -> str:
    return {"integer": "整数", "percent": "百分比", "duration_seconds": "时长"}.get(value, value)


def _scope_label(principal: EffectivePrincipal) -> str:
    return {"all": "全部可见通话", "group": "所在组可见通话", "self": "本人可见通话"}.get(
        DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD), "本人可见通话"
    )


def _coverage_label(status: str | None) -> str:
    return {"available": "完整可用", "partial": "部分可用", "unavailable": "不可用"}.get(status or "", "不可用")


def _quality_label(quality: dict) -> str:
    labels = {"pending": "处理中", "processing": "处理中", "incomplete": "不完整", "failed": "失败",
              "satisfaction_pending": "满意度待生成", "reception_incomplete": "接待事实不完整",
              "offer_incomplete": "Offer 事实不完整", "after_call_work_incomplete": "话后处理事实不完整"}
    parts = [f"{labels.get(key, key)} {value}" for key, value in quality.items() if value]
    return "；".join(parts) if parts else "无异常"


def _format_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def _actual_range_label(coverage: dict) -> str:
    if not coverage.get("actual_start") or not coverage.get("actual_end"):
        return "—"
    return f"{_format_datetime(coverage['actual_start'])} 至 {_format_datetime(coverage['actual_end'])}"


def _sort_label(sort: str, order: str, labels: dict[str, str]) -> str:
    return f"{labels.get(sort, sort)}{'升序' if order == 'asc' else '倒序'}"


def _queue_type_label(value: str) -> str:
    return {"employee_group": "员工组队列", "employee": "客服直连队列"}.get(value, "未知")


def _queue_type_filter_label(value: str) -> str:
    return "全部队列" if value in {"", "all"} else _queue_type_label(value)


def _status_label(value: str) -> str:
    return {"active": "启用", "inactive": "停用", "deleted": "已删除"}.get(value, "未知")


def _queue_display_name(value: str | None) -> str:
    if not value or re.fullmatch(r"(?:Deleted|Unknown) queue(?: #\d+)?", value, re.IGNORECASE):
        return "未知队列"
    return value


def _employee_display_name(employee: dict) -> str:
    value = employee.get("display_name") or employee.get("name")
    if not value or re.fullmatch(r"(?:Deleted )?employee #\d+", value, re.IGNORECASE):
        return "未知员工"
    return value


def _employee_status_filter_label(value: str) -> str:
    return "全部状态" if value in {"", "all"} else _status_label(value)


def _detail_filename(object_name: str, start: date, end: date, trend: TrendType, exported_at: datetime) -> str:
    return export_service._safe_filename(
        f"通话报表_{object_name}_{start:%Y%m%d}-{end:%Y%m%d}_{_TREND_LABELS[trend]}_{exported_at:%Y%m%d%H%M%S}.xlsx"
    )


def _list_filename(object_name: str, start: date, end: date, exported_at: datetime) -> str:
    return export_service._safe_filename(
        f"通话报表_{object_name}_{start:%Y%m%d}-{end:%Y%m%d}_{exported_at:%Y%m%d%H%M%S}.xlsx"
    )
