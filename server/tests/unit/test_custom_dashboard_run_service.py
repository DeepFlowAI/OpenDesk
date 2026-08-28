"""Unit tests for managed-session custom dashboard run orchestration."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.libs.dashboard_sandbox.base import SandboxResult
from app.libs.dashboard_sandbox.base import SandboxExecutionError
from app.repositories.custom_dashboard_repository import CustomDashboardRepository
from app.schemas.custom_dashboard_run import CustomDashboardRunRequest
from app.schemas.permission import EffectivePrincipal
from app.services import custom_dashboard_run_service as run_module
from app.services.custom_dashboard_query_service import CustomDashboardQueryService
from app.services.custom_dashboard_resource_service import CustomDashboardResourceService
from app.services.custom_dashboard_run_service import CustomDashboardRunService
from app.services.custom_dashboard_run_service import _validate_output
from app.services.data_scope_service import DataScopeService
from app.services.system_settings_service import SystemSettingsService


class _SessionTracker:
    def __init__(self) -> None:
        self.active = 0

    def factory(self):
        tracker = self

        class Context:
            async def __aenter__(self):
                tracker.active += 1
                return AsyncMock()

            async def __aexit__(self, *_args):
                tracker.active -= 1

        return Context()


class _Lease:
    def __init__(self) -> None:
        self.released = False

    async def release(self) -> None:
        self.released = True


def test_preview_override_must_match_component_id():
    with pytest.raises(ValueError, match="override id"):
        CustomDashboardRunRequest(
            page_run_id=uuid4(),
            component_id="metric-1",
            component_override={
                "id": "metric-2",
                "title": "Other",
                "code": "def run():\n    return {'type': 'metric', 'value': 1}",
                "x": 0,
                "y": 0,
                "w": 6,
                "h": 8,
            },
        )


def test_output_rejects_html_in_chart_configuration():
    with pytest.raises(SandboxExecutionError, match="HTML"):
        _validate_output(
            {
                "type": "echarts",
                "option": {"tooltip": {"formatter": "<b>unsafe</b>"}},
            }
        )


@pytest.mark.asyncio
async def test_run_closes_db_session_while_sandbox_is_in_flight(monkeypatch):
    tracker = _SessionTracker()
    dashboard = SimpleNamespace(
        id=11,
        tenant_id=7,
        status="published",
        published_at=datetime.now(timezone.utc),
    )
    version = SimpleNamespace(
        name="服务质量",
        revision=2,
        filters=[],
        components=[
            {
                "id": "metric-1",
                "title": "待处理",
                "code": "def run():\n    return {'type': 'metric', 'value': 3}",
            }
        ],
    )
    principal = EffectivePrincipal(
        user_id=9,
        tenant_id=7,
        permissions=["ticket.workspace.view", "report.dashboard.view"],
        data_scopes={"ticket": "self"},
    )
    lease = _Lease()

    monkeypatch.setattr(run_module, "AsyncSessionLocal", tracker.factory)
    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_by_id",
        AsyncMock(return_value=dashboard),
    )
    monkeypatch.setattr(
        CustomDashboardRepository,
        "get_version",
        AsyncMock(return_value=version),
    )
    monkeypatch.setattr(
        SystemSettingsService,
        "get_settings",
        AsyncMock(return_value=SimpleNamespace(default_timezone="Asia/Shanghai")),
    )
    monkeypatch.setattr(
        CustomDashboardQueryService,
        "field_catalog_version",
        AsyncMock(return_value="catalog-v1"),
    )
    monkeypatch.setattr(
        CustomDashboardQueryService,
        "field_catalog",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        DataScopeService,
        "get_group_peer_employee_ids",
        AsyncMock(return_value=[]),
    )

    async def query_execute(*_args, **_kwargs):
        assert tracker.active == 1
        return 3

    monkeypatch.setattr(CustomDashboardQueryService, "execute", query_execute)

    monkeypatch.setattr(
        CustomDashboardResourceService,
        "is_cancelled",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        CustomDashboardResourceService,
        "is_cooling_down",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        CustomDashboardResourceService,
        "get_cache",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CustomDashboardResourceService,
        "enforce_miss_rate",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CustomDashboardResourceService,
        "acquire_execution",
        AsyncMock(return_value=lease),
    )
    monkeypatch.setattr(
        CustomDashboardResourceService,
        "consume_page_query",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CustomDashboardResourceService,
        "record_success",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        CustomDashboardResourceService,
        "set_cache",
        AsyncMock(return_value=None),
    )

    class Sandbox:
        async def execute(self, **kwargs):
            assert tracker.active == 0
            value = await kwargs["query_handler"]("count", {})
            assert tracker.active == 0
            return SandboxResult(
                output={"type": "metric", "value": value},
                query_count=1,
            )

    monkeypatch.setattr(run_module, "create_dashboard_sandbox", lambda: Sandbox())

    result = await CustomDashboardRunService.run_managed(
        AsyncMock(),
        principal,
        dashboard_id=11,
        request=CustomDashboardRunRequest(
            page_run_id=uuid4(),
            component_id="metric-1",
        ),
        preview=False,
    )

    assert result["status"] == "success"
    assert result["result"]["value"] == 3
    assert tracker.active == 0
    assert lease.released is True
