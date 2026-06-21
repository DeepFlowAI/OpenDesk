"""
Unit tests for end-user bulk import.
"""
from __future__ import annotations

from io import BytesIO
import zipfile
from unittest.mock import AsyncMock

import pytest

from app.libs.excel import build_xlsx, parse_csv, parse_spreadsheet, parse_xlsx
from app.schemas.user_import import UserImportErrorReportRequest, UserImportErrorReportRow
from app.services.user_import_service import UserImportService


def test_parse_csv_reads_headers_and_rows():
    content = "昵称,邮箱\nAlice,alice@example.com\n".encode("utf-8")
    headers, rows = parse_csv(content)
    assert headers == ["昵称", "邮箱"]
    assert rows == [["Alice", "alice@example.com"]]


def test_parse_xlsx_reads_inline_workbook():
    content = build_xlsx(["昵称", "邮箱"], [["Bob", "bob@example.com"]])
    headers, rows = parse_xlsx(content)
    assert headers == ["昵称", "邮箱"]
    assert rows == [["Bob", "bob@example.com"]]


def test_parse_spreadsheet_dispatches_by_extension():
    csv_content = "昵称\nTom\n".encode("utf-8")
    headers, rows = parse_spreadsheet(csv_content, "users.csv")
    assert headers == ["昵称"]
    assert rows == [["Tom"]]


def test_build_error_report_adds_reason_column():
    body = UserImportErrorReportRequest(
        headers=["邮箱"],
        rows=[UserImportErrorReportRow(row_number=2, values=["bad@"], error_reason="Invalid email format")],
    )
    content, filename = UserImportService.build_error_report(body, "zh")
    assert filename.endswith(".xlsx")
    with zipfile.ZipFile(BytesIO(content)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "错误原因" in sheet
    assert "Invalid email format" in sheet


def test_validate_field_value_rejects_invalid_email():
    from app.services.user_import_service import ImportColumnDef

    column = ImportColumnDef(
        field_key="email",
        field_id=None,
        header_zh="邮箱",
        header_en="Email",
        field_type="email",
        source="system",
    )
    assert UserImportService._validate_field_value(column, "not-an-email") == ["Invalid email format"]


def test_default_name_uses_email_local_part():
    assert UserImportService._default_name("alice@example.com", None, None, 2) == "alice"


@pytest.mark.asyncio
async def test_build_template_returns_workbook(monkeypatch):
    db = object()
    monkeypatch.setattr(
        UserImportService,
        "_build_import_columns",
        AsyncMock(
            return_value=[
                __import__("app.services.user_import_service", fromlist=["ImportColumnDef"]).ImportColumnDef(
                    field_key="name",
                    field_id=None,
                    header_zh="昵称",
                    header_en="Nickname",
                    field_type="single_line_text",
                    source="system",
                )
            ]
        ),
    )
    content, filename = await UserImportService.build_template(db, 1, "zh")
    assert filename.startswith("users-import-template-")
    assert content.startswith(b"PK")
