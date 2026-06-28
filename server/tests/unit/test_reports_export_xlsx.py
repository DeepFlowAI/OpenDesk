"""Unit tests for the reports XLSX export builder."""
from __future__ import annotations

import importlib
import zipfile
from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import app.extensions  # triggers private overlay

export_service = importlib.import_module("app.extensions.reports.services.export_service")
buckets = importlib.import_module("app.extensions.reports.lib.buckets")


def _read_zip_member(content: bytes, name: str) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read(name).decode("utf-8")


def test_builds_overview_and_trend_workbook():
    exported_at = datetime(2026, 5, 20, 14, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    content = export_service._build_xlsx([
        (
            "概览",
            export_service._overview_sheet(
                "整体报表",
                date(2026, 5, 1),
                date(2026, 5, 20),
                buckets.TrendType.HOUR,
                exported_at,
                {
                    "session_count": 2,
                    "message_count": 5,
                    "user_message_count": 2,
                    "agent_message_count": 3,
                    "avg_duration_seconds": 90,
                    "bot_session_count": 1,
                    "bot_handoff_count": 1,
                    "queued_session_count": 2,
                    "avg_queue_duration_seconds": 45,
                    "offline_message_count": 4,
                    "can_view_offline_messages": True,
                },
                include_business_metrics=True,
            ),
        ),
        (
            "趋势",
            export_service._trend_sheet(
                "整体报表",
                date(2026, 5, 1),
                date(2026, 5, 20),
                buckets.TrendType.HOUR,
                exported_at,
                [
                    {
                        "label": "10",
                        "metrics": {
                            "session_count": 2,
                            "message_count": 5,
                            "user_message_count": 2,
                            "agent_message_count": 3,
                            "avg_duration_seconds": None,
                            "bot_session_count": 1,
                            "bot_handoff_count": 1,
                            "queued_session_count": 2,
                            "avg_queue_duration_seconds": 45,
                            "offline_message_count": 4,
                            "can_view_offline_messages": True,
                        },
                    }
                ],
                include_business_metrics=True,
            ),
        ),
    ])

    assert content.startswith(b"PK")
    workbook = _read_zip_member(content, "xl/workbook.xml")
    sheet1 = _read_zip_member(content, "xl/worksheets/sheet1.xml")
    sheet2 = _read_zip_member(content, "xl/worksheets/sheet2.xml")

    assert 'name="概览"' in workbook
    assert 'name="趋势"' in workbook
    assert "会话报表" in sheet1
    assert "整体报表" in sheet1
    assert "01:30" in sheet1
    assert "机器人会话量" in sheet1
    assert "平均排队时长" in sheet1
    assert "留言数量" in sheet1
    assert "00:45" in sheet1
    assert "趋势明细" in sheet2
    assert "机器人转人工量" in sheet2
    assert "排队会话量" in sheet2
    assert "—" in sheet2


def test_overall_export_omits_offline_columns_without_permission():
    exported_at = datetime(2026, 5, 20, 14, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    sheet = export_service._overview_sheet(
        "整体报表",
        date(2026, 5, 1),
        date(2026, 5, 20),
        buckets.TrendType.HOUR,
        exported_at,
        {
            "session_count": 2,
            "message_count": 5,
            "user_message_count": 2,
            "agent_message_count": 3,
            "avg_duration_seconds": 90,
            "bot_session_count": 1,
            "bot_handoff_count": 1,
            "queued_session_count": 2,
            "avg_queue_duration_seconds": 45,
            "offline_message_count": None,
            "can_view_offline_messages": False,
        },
        include_business_metrics=True,
    )

    flattened = "\n".join(str(cell) for row in sheet for cell in row)
    assert "机器人会话量" in flattened
    assert "留言数量" not in flattened


def test_overview_sheet_includes_reception_metrics():
    exported_at = datetime(2026, 5, 20, 14, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    sheet = export_service._overview_sheet(
        "整体报表",
        date(2026, 5, 1),
        date(2026, 5, 20),
        buckets.TrendType.HOUR,
        exported_at,
        {
            "session_count": 2,
            "message_count": 5,
            "user_message_count": 2,
            "agent_message_count": 3,
            "avg_duration_seconds": 90,
            "reception_segment_count": 3,
            "reception_participated_session_count": 2,
            "reception_final_session_count": 2,
            "reception_transfer_in_count": 1,
            "reception_transfer_out_count": 1,
        },
    )

    flattened = [str(cell) for row in sheet for cell in row]
    assert "人工接待量" in flattened
    assert "转接转入量" in flattened
    assert "转接转出量" in flattened
    assert 3 in [cell for row in sheet for cell in row]


def test_employees_sheet_includes_reception_columns():
    from app.extensions.reports.schemas import EmployeeBrief, EmployeeOverviewRow, OverviewMetrics

    exported_at = datetime(2026, 5, 20, 14, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    rows = [
        EmployeeOverviewRow(
            employee=EmployeeBrief(id=1, name="Agent A", username="a", is_active=True),
            metrics=OverviewMetrics(
                session_count=5,
                reception_segment_count=7,
                reception_transfer_in_count=2,
                reception_transfer_out_count=3,
            ),
        )
    ]
    sheet = export_service._employees_sheet(
        date(2026, 5, 1),
        date(2026, 5, 20),
        exported_at,
        rows,
        q=None,
        sort="reception_segment_count",
        order="desc",
    )

    header = sheet[-2]
    assert "人工接待量" in header
    assert "转接转入量" in header
    data_row = sheet[-1]
    assert 7 in data_row


def test_safe_filename_replaces_unsupported_characters():
    filename = export_service._report_filename(
        "张/三:客服",
        date(2026, 5, 1),
        date(2026, 5, 20),
        datetime(2026, 5, 20, 14, 30, 0),
        buckets.TrendType.DAY,
    )

    assert filename.endswith(".xlsx")
    assert "/" not in filename
    assert ":" not in filename
    assert "张_三_客服" in filename
