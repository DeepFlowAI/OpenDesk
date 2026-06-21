"""
Unit tests for organization bulk import.
"""
from __future__ import annotations

from io import BytesIO
import zipfile
from unittest.mock import AsyncMock

import pytest

from app.libs.excel import build_xlsx, parse_spreadsheet
from app.schemas.organization_import import (
    OrganizationImportErrorReportRequest,
    OrganizationImportErrorReportRow,
)
from app.services.organization_import_service import ImportColumnDef, OrganizationImportService


def test_parse_spreadsheet_reads_organization_csv():
    content = "名称,描述\nAcme Corp,Main vendor\n".encode("utf-8")
    headers, rows = parse_spreadsheet(content, "organizations.csv")
    assert headers == ["名称", "描述"]
    assert rows == [["Acme Corp", "Main vendor"]]


def test_build_error_report_adds_reason_column():
    body = OrganizationImportErrorReportRequest(
        headers=["名称"],
        rows=[OrganizationImportErrorReportRow(row_number=2, values=[""], error_reason="Organization name is required")],
    )
    content, filename = OrganizationImportService.build_error_report(body, "zh")
    assert filename.endswith(".xlsx")
    with zipfile.ZipFile(BytesIO(content)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "错误原因" in sheet
    assert "Organization name is required" in sheet


def test_validate_field_value_rejects_invalid_number():
    column = ImportColumnDef(
        field_key="custom_number",
        field_id=1,
        header_zh="数量",
        header_en="Count",
        field_type="number",
        source="custom",
    )
    assert OrganizationImportService._validate_field_value(column, "not-a-number") == ["Invalid number format"]


def test_duplicate_name_errors_detects_file_and_tenant_conflicts():
    seen_names: dict[str, int] = {"Acme": 2}
    existing_names = {"Globex": 10}
    errors = OrganizationImportService._duplicate_name_errors(
        row_number=3,
        row_values=["Acme", ""],
        header_to_column={0: ImportColumnDef("name", None, "名称", "Name", "single_line_text", "system")},
        name="Acme",
        seen_names=seen_names,
        existing_names=existing_names,
        locale="zh",
    )
    assert any(error.reason == "Duplicate organization name in file" for error in errors)

    errors_existing = OrganizationImportService._duplicate_name_errors(
        row_number=4,
        row_values=["Globex", ""],
        header_to_column={0: ImportColumnDef("name", None, "名称", "Name", "single_line_text", "system")},
        name="Globex",
        seen_names={},
        existing_names=existing_names,
        locale="zh",
    )
    assert any(error.reason == "Organization name already exists" for error in errors_existing)


@pytest.mark.asyncio
async def test_build_template_returns_workbook(monkeypatch):
    db = object()
    monkeypatch.setattr(
        OrganizationImportService,
        "_build_import_columns",
        AsyncMock(
            return_value=[
                ImportColumnDef(
                    field_key="name",
                    field_id=None,
                    header_zh="名称",
                    header_en="Name",
                    field_type="single_line_text",
                    source="system",
                )
            ]
        ),
    )
    content, filename = await OrganizationImportService.build_template(db, 1, "zh")
    assert filename.startswith("organizations-import-template-")
    assert content.startswith(b"PK")

    headers, rows = parse_spreadsheet(build_xlsx(["名称"], []), "template.xlsx")
    assert headers == ["名称"]
    assert rows == []
