"""Unit tests for call-report XLSX exports."""
from __future__ import annotations

import importlib
import zipfile
from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest

import app.extensions  # noqa: F401 -- load the private reports overlay
from app.schemas.permission import EffectivePrincipal

call_export = importlib.import_module("app.extensions.reports.services.call_export_service")
buckets = importlib.import_module("app.extensions.reports.lib.buckets")


def _principal(scope: str = "all") -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=7,
        tenant_id=1,
        permissions=["call.report.export"],
        data_scopes={"call_record": scope},
    )


def _worksheet_text(content: bytes, sheet_number: int = 1) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read(f"xl/worksheets/sheet{sheet_number}.xml").decode()


def test_detail_sheets_include_scope_quality_distributions_and_all_trend_groups():
    exported_at = datetime(2026, 9, 1, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    summary = {
        "metrics": [
            {"key": "call_count", "value": 3, "format": "integer", "group": "call_overview", "available": True},
            {"key": "customer_hangup_rate", "value": 0.25, "format": "percent", "group": "service_efficiency", "available": True},
        ],
        "distributions": [{
            "key": "direction", "group": "call_overview", "total": 3,
            "slices": [{"key": "inbound", "label": "inbound", "value": 2}, {"key": "outbound", "label": "outbound", "value": 1}],
        }],
        "coverage": {"status": "partial", "effective_at": "2026-08-01T00:00:00+08:00", "actual_start": "2026-08-01T00:00:00+08:00", "actual_end": "2026-09-02T00:00:00+08:00"},
        "data_quality": {"pending": 2, "failed": 0},
        "as_of": "2026-09-01T09:59:59+08:00",
    }
    trends = [
        {"group": "call_overview", "metrics": [{"key": "call_count", "format": "integer"}], "buckets": [{"label": "09:00", "metrics": [{"key": "call_count", "value": 3, "format": "integer"}]}]},
        {"group": "service_efficiency", "metrics": [{"key": "customer_hangup_rate", "format": "percent"}], "buckets": [{"label": "09:00", "metrics": [{"key": "customer_hangup_rate", "value": None, "format": "percent"}]}]},
    ]
    overview = call_export._detail_overview_rows(
        "整体报表", date(2026, 9, 1), date(2026, 9, 1), buckets.TrendType.HOUR,
        exported_at, summary, _principal("group"),
    )
    trend = call_export._trend_rows(
        "整体报表", date(2026, 9, 1), date(2026, 9, 1), buckets.TrendType.HOUR,
        exported_at, trends, summary, _principal("group"),
    )
    content = call_export.export_service._build_xlsx([("概览", overview), ("趋势", trend)])

    overview_text = _worksheet_text(content)
    trend_text = _worksheet_text(content, 2)
    assert "所在组可见通话" in overview_text
    assert "部分可用" in overview_text
    assert "处理中 2" in overview_text
    assert "呼叫方向分布" in overview_text
    assert "呼入" in overview_text
    assert "通话概览" in trend_text
    assert "服务效率" in trend_text
    assert "—" in trend_text


@pytest.mark.asyncio
async def test_queue_list_export_requests_all_rows_and_uses_fixed_columns(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_list(*args, **kwargs):
        captured.update(kwargs)
        return {
            "items": [{
                "queue": {"queue_type": "employee_group", "queue_id": 9, "name": "售后", "status": "active"},
                "metrics": {"queue_call_count": 4, "queue_entry_count": 5, "queue_answered_count": 3,
                            "queue_answer_rate": 0.6, "queue_abandoned_count": 1, "queue_abandon_rate": 0.2,
                            "avg_answer_wait_seconds": 18, "queue_service_level_20s": 0.75},
            }],
            "total": 1, "coverage": {"status": "available", "effective_at": "2026-01-01T00:00:00+08:00",
            "actual_start": "2026-09-01T00:00:00+08:00", "actual_end": "2026-09-02T00:00:00+08:00"},
            "data_quality": {}, "as_of": "2026-09-01T10:00:00+08:00",
        }

    monkeypatch.setattr(call_export.call_queues_service, "list_queues", fake_list)
    content, filename = await call_export.export_queue_list(
        object(), 1, date(2026, 9, 1), date(2026, 9, 1), q="售后", queue_type="employee_group",
        sort="queue_entry_count", order="desc", principal=_principal(),
    )

    assert captured["paginate"] is False
    assert "通话报表_队列列表_20260901-20260901_" in filename
    text = _worksheet_text(content)
    for label in ("队列", "涉及通话量", "接通率", "客户放弃率", "20 秒服务水平", "售后"):
        assert label in text


def test_detail_filename_replaces_invalid_object_name_characters():
    filename = call_export._detail_filename(
        "员工_张/三:客服", date(2026, 9, 1), date(2026, 9, 2), buckets.TrendType.DAY,
        datetime(2026, 9, 2, 11, 12, 13),
    )
    assert filename == "通话报表_员工_张_三_客服_20260901-20260902_日_20260902111213.xlsx"


def test_missing_historical_names_do_not_expose_database_ids():
    assert call_export._queue_display_name("Deleted queue #42") == "未知队列"
    assert call_export._employee_display_name({"name": "Deleted employee #17"}) == "未知员工"
