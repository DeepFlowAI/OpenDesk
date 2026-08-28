"""Unit tests for custom dashboard lifecycle business rules."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.repositories.custom_dashboard_repository import CustomDashboardRepository
from app.schemas.custom_dashboard import CustomDashboardCreate, CustomDashboardUpdate
from app.services.custom_dashboard_service import CustomDashboardService
from app.services.system_settings_service import SystemSettingsService


def _dashboard(**overrides):
    values = {
        "id": 11,
        "tenant_id": 7,
        "name": "服务质量",
        "slug": "service_quality",
        "status": "draft",
        "sort_order": 1,
        "published_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _version(kind: str = "draft", **overrides):
    values = {
        "id": 21 if kind == "draft" else 22,
        "tenant_id": 7,
        "dashboard_id": 11,
        "kind": kind,
        "revision": 1,
        "name": "服务质量",
        "description": None,
        "icon": "chart-bar",
        "filters": [],
        "components": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_create_builds_initial_draft(monkeypatch):
    db = AsyncMock()
    dashboard = _dashboard()
    draft = _version()
    captured_version: dict = {}

    monkeypatch.setattr(
        CustomDashboardRepository,
        "count_for_tenant",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_max_sort_order",
        AsyncMock(return_value=3),
    )
    monkeypatch.setattr(
        CustomDashboardRepository,
        "create_dashboard",
        AsyncMock(return_value=dashboard),
    )

    async def create_version(_db, data):
        captured_version.update(data)
        return draft

    monkeypatch.setattr(CustomDashboardRepository, "create_version", create_version)

    result = await CustomDashboardService.create(
        db,
        7,
        CustomDashboardCreate(name="服务质量", slug="service_quality"),
    )

    assert result["status"] == "draft"
    assert result["draft"]["revision"] == 1
    assert captured_version["kind"] == "draft"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_changes_only_draft(monkeypatch):
    db = AsyncMock()
    dashboard = _dashboard(status="published")
    draft = _version()
    published = _version("published", name="线上名称")
    version_calls = 0

    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_by_id",
        AsyncMock(return_value=dashboard),
    )

    async def get_version(*_args, **_kwargs):
        nonlocal version_calls
        version_calls += 1
        return draft if version_calls == 1 else published

    monkeypatch.setattr(CustomDashboardRepository, "get_version", get_version)

    async def update_dashboard(_db, row, data):
        row.name = data["name"]

    async def update_version(_db, row, data):
        for key, value in data.items():
            setattr(row, key, value)

    monkeypatch.setattr(CustomDashboardRepository, "update_dashboard", update_dashboard)
    monkeypatch.setattr(CustomDashboardRepository, "update_version", update_version)

    result = await CustomDashboardService.update(
        db,
        11,
        7,
        CustomDashboardUpdate(name="草稿名称", components=[]),
    )

    assert result["draft"]["name"] == "草稿名称"
    assert result["published_revision"] == 1
    assert published.name == "线上名称"
    assert draft.revision == 2


@pytest.mark.asyncio
async def test_publish_copies_draft_into_published_slot(monkeypatch):
    db = AsyncMock()
    dashboard = _dashboard()
    draft = _version(
        components=[
            {
                "id": "metric-1",
                "title": "待处理",
                "code": "def run():\n    return {'type': 'metric', 'value': 1}",
                "x": 0,
                "y": 0,
                "w": 3,
                "h": 4,
            }
        ]
    )
    created_published = _version("published", components=draft.components)
    version_calls = 0

    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_by_id",
        AsyncMock(return_value=dashboard),
    )

    async def get_version(*_args, **_kwargs):
        nonlocal version_calls
        version_calls += 1
        return draft if version_calls == 1 else None

    monkeypatch.setattr(CustomDashboardRepository, "get_version", get_version)
    monkeypatch.setattr(
        CustomDashboardRepository,
        "count_published_components",
        AsyncMock(return_value=9),
    )
    create_version = AsyncMock(return_value=created_published)
    monkeypatch.setattr(CustomDashboardRepository, "create_version", create_version)

    async def update_dashboard(_db, row, data):
        for key, value in data.items():
            setattr(row, key, value)

    monkeypatch.setattr(CustomDashboardRepository, "update_dashboard", update_dashboard)

    result = await CustomDashboardService.publish(db, 11, 7)

    payload = create_version.await_args.args[1]
    assert payload["kind"] == "published"
    assert payload["components"] == draft.components
    assert result["status"] == "published"
    assert result["published_revision"] == 1


@pytest.mark.asyncio
async def test_publish_rejects_tenant_component_quota(monkeypatch):
    db = AsyncMock()
    dashboard = _dashboard()
    draft = _version(
        components=[
            {
                "id": "metric-1",
                "title": "待处理",
                "code": "def run():\n    return {'type': 'metric', 'value': 1}",
                "x": 0,
                "y": 0,
                "w": 3,
                "h": 4,
            }
        ]
    )
    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_by_id",
        AsyncMock(return_value=dashboard),
    )
    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_version",
        AsyncMock(return_value=draft),
    )
    monkeypatch.setattr(
        CustomDashboardRepository,
        "count_published_components",
        AsyncMock(return_value=300),
    )

    with pytest.raises(ValidationError, match="Published component quota exceeded"):
        await CustomDashboardService.publish(db, 11, 7)


@pytest.mark.asyncio
async def test_disable_rejects_draft(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_by_id",
        AsyncMock(return_value=_dashboard(status="draft")),
    )

    with pytest.raises(ConflictError, match="Draft dashboard cannot be disabled"):
        await CustomDashboardService.disable(db, 11, 7)


@pytest.mark.asyncio
async def test_workspace_detail_hides_component_code(monkeypatch):
    db = AsyncMock()
    dashboard = _dashboard(
        status="published",
        published_at=datetime.now(timezone.utc),
    )
    published = _version(
        "published",
        components=[
            {
                "id": "metric-1",
                "title": "待处理",
                "code": "def run():\n    return 1",
                "x": 0,
                "y": 0,
                "w": 3,
                "h": 4,
            }
        ],
    )
    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_by_id",
        AsyncMock(return_value=dashboard),
    )
    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_version",
        AsyncMock(return_value=published),
    )
    monkeypatch.setattr(
        SystemSettingsService,
        "get_settings",
        AsyncMock(return_value=SimpleNamespace(default_timezone="Asia/Shanghai")),
    )

    result = await CustomDashboardService.get_workspace_detail(db, 11, 7)

    assert "code" not in result["components"][0]
    assert result["components"][0]["title"] == "待处理"
