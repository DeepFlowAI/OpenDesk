"""Tests for custom-dashboard field deletion protection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationError
from app.repositories.custom_dashboard_repository import CustomDashboardRepository
from app.repositories.fd_field_definition_repository import FdFieldDefinitionRepository
from app.services.custom_dashboard_service import CustomDashboardService, _contains_field_reference
from app.services.fd_field_definition_service import FdFieldDefinitionService


def test_field_reference_match_is_exact():
    assert _contains_field_reference('group_by("custom:customer_level")', "custom:customer_level")
    assert _contains_field_reference({"field_key": "custom:customer_level"}, "custom:customer_level")
    assert not _contains_field_reference("custom:customer_level_v2", "custom:customer_level")


@pytest.mark.asyncio
async def test_find_field_references_reports_draft_and_published(monkeypatch):
    dashboard = SimpleNamespace(id=3)
    rows = [
        (dashboard, SimpleNamespace(name="服务质量", kind="draft", filters=[], components=[{"code": '"custom:level"'}])),
        (dashboard, SimpleNamespace(name="服务质量", kind="published", filters=[{"field_key": "custom:level"}], components=[])),
    ]
    monkeypatch.setattr(
        CustomDashboardRepository,
        "list_versions_for_field_reference_check",
        AsyncMock(return_value=rows),
    )

    references = await CustomDashboardService.find_field_references(AsyncMock(), 7, "custom:level")

    assert [item["version_kind"] for item in references] == ["draft", "published"]


@pytest.mark.asyncio
async def test_field_delete_is_blocked_when_dashboard_references_it(monkeypatch):
    field = SimpleNamespace(
        id=9,
        tenant_id=7,
        source="custom",
        domain="shared_pool",
        applicable_modules=["ticket"],
        field_key="customer_level",
    )
    monkeypatch.setattr(FdFieldDefinitionRepository, "get_by_id", AsyncMock(return_value=field))
    delete_mock = AsyncMock()
    monkeypatch.setattr(FdFieldDefinitionRepository, "delete", delete_mock)
    monkeypatch.setattr(
        CustomDashboardService,
        "find_field_references",
        AsyncMock(return_value=[{"dashboard_id": 3, "dashboard_name": "服务质量", "version_kind": "draft"}]),
    )

    with pytest.raises(ValidationError) as exc_info:
        await FdFieldDefinitionService.delete(AsyncMock(), 9, 7)

    assert exc_info.value.details["references"][0]["dashboard_name"] == "服务质量"
    delete_mock.assert_not_awaited()
