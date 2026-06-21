"""
Unit tests for organization list export.
"""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
import zipfile

import pytest

from app.core.exceptions import ValidationError
from app.schemas.organization import OrganizationExportColumn, OrganizationExportRequest
from app.services.organization_service import OrganizationRepository, OrganizationService


def _worksheet_text(content: bytes) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read("xl/worksheets/sheet1.xml").decode("utf-8")


def test_normalize_export_columns_filters_internal_id():
    columns = OrganizationService._normalize_export_columns(
        [
            OrganizationExportColumn(field_key="id", name="Internal ID"),
            OrganizationExportColumn(field_key="public_id", name="组织 ID"),
            OrganizationExportColumn(field_key="__user_count", name="用户数量"),
        ]
    )

    assert [column.field_key for column in columns] == ["public_id", "__user_count"]


def test_export_cell_value_reads_user_count():
    value = OrganizationService._export_cell_value(
        {"user_count": 3},
        OrganizationExportColumn(field_key="__user_count", name="用户数量"),
        {},
    )

    assert value == "3"


@pytest.mark.asyncio
async def test_export_organizations_builds_xlsx(monkeypatch):
    db = SimpleNamespace(get=AsyncMock(return_value=None))
    organization = SimpleNamespace(id=10)

    monkeypatch.setattr(OrganizationService, "_get_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(OrganizationService, "_get_field_key_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(
        OrganizationRepository,
        "query_paginated",
        AsyncMock(return_value=([organization], 1)),
    )
    monkeypatch.setattr(
        OrganizationRepository,
        "count_users",
        AsyncMock(return_value=3),
    )
    monkeypatch.setattr(
        OrganizationService,
        "_get_custom_field_option_lookup",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        OrganizationService,
        "_enrich_response",
        lambda *_args: {
            "public_id": "org_export_00000001",
            "name": "Acme",
            "user_count": 3,
            "custom_fields": {},
        },
    )

    content, filename = await OrganizationService.export_organizations(
        db,
        1,
        OrganizationExportRequest(
            columns=[
                OrganizationExportColumn(field_key="public_id", name="组织 ID"),
                OrganizationExportColumn(field_key="name", name="名称"),
                OrganizationExportColumn(field_key="__user_count", name="用户数量"),
            ]
        ),
    )

    assert filename.startswith("organizations-export-")
    assert filename.endswith(".xlsx")
    sheet = _worksheet_text(content)
    assert "组织 ID" in sheet
    assert "org_export_00000001" in sheet
    assert "Acme" in sheet
    assert "3" in sheet


@pytest.mark.asyncio
async def test_export_organizations_rejects_too_many_records(monkeypatch):
    db = SimpleNamespace(get=AsyncMock(return_value=None))

    monkeypatch.setattr(OrganizationService, "_get_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(OrganizationService, "_get_field_key_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(
        OrganizationRepository,
        "query_paginated",
        AsyncMock(return_value=([], 5001)),
    )

    with pytest.raises(ValidationError):
        await OrganizationService.export_organizations(db, 1, OrganizationExportRequest())
