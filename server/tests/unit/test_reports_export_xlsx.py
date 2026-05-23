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
                },
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
                        },
                    }
                ],
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
    assert "趋势明细" in sheet2
    assert "—" in sheet2


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
