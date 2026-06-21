"""
Unit tests for user list export.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from io import BytesIO
import zipfile

import pytest

from app.core.exceptions import ValidationError
from app.libs.excel import build_xlsx
from app.schemas.user import UserExportColumn, UserExportRequest
from app.services.user_service import UserRepository, UserService


def _worksheet_text(content: bytes) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read("xl/worksheets/sheet1.xml").decode("utf-8")


def test_build_xlsx_returns_readable_workbook():
    content = build_xlsx(["用户 ID", "昵称"], [["usr_abc", "Alice"]], sheet_name="Users")

    assert content.startswith(b"PK")
    sheet = _worksheet_text(content)
    assert "用户 ID" in sheet
    assert "usr_abc" in sheet


def test_normalize_export_columns_filters_internal_id():
    columns = UserService._normalize_export_columns(
        [
            UserExportColumn(field_key="id", name="Internal ID"),
            UserExportColumn(field_key="public_id", name="用户 ID"),
            UserExportColumn(field_key="nickname", name="昵称"),
        ]
    )

    assert [column.field_key for column in columns] == ["public_id", "nickname"]


@pytest.mark.asyncio
async def test_export_users_builds_xlsx(monkeypatch):
    db = SimpleNamespace(get=AsyncMock(return_value=None))
    user = SimpleNamespace(organization_id=None)

    monkeypatch.setattr(UserService, "_get_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(UserService, "_get_field_key_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(
        UserRepository,
        "query_paginated",
        AsyncMock(return_value=([user], 1)),
    )
    monkeypatch.setattr(
        UserService,
        "_get_custom_field_option_lookup",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.services.user_service.OrganizationRepository.list_by_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        UserService,
        "_enrich_user_response",
        lambda *_args: {
            "public_id": "usr_export_00000001",
            "name": "Alice",
            "custom_fields": {},
        },
    )

    content, filename = await UserService.export_users(
        db,
        1,
        UserExportRequest(
            columns=[
                UserExportColumn(field_key="public_id", name="用户 ID"),
                UserExportColumn(field_key="name", name="昵称"),
            ]
        ),
    )

    assert filename.startswith("users-export-")
    assert filename.endswith(".xlsx")
    sheet = _worksheet_text(content)
    assert "用户 ID" in sheet
    assert "usr_export_00000001" in sheet
    assert "Alice" in sheet


@pytest.mark.asyncio
async def test_export_users_rejects_too_many_records(monkeypatch):
    db = SimpleNamespace(get=AsyncMock(return_value=None))

    monkeypatch.setattr(UserService, "_get_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(UserService, "_get_field_key_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(
        UserRepository,
        "query_paginated",
        AsyncMock(return_value=([], 5001)),
    )

    with pytest.raises(ValidationError):
        await UserService.export_users(db, 1, UserExportRequest())
