"""Unit coverage for engagement OpenAPI authentication and task wiring."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import NotFoundError
from app.models.auto_outbound import AutoOutboundTarget, AutoOutboundTask
from app.models.outbound_task import OutboundTask, OutboundTaskTarget
from app.routers.v1.open_engagement import router
from app.repositories.auto_outbound_repository import AutoOutboundRepository
from app.repositories.outbound_task_repository import OutboundTaskRepository
from app.schemas.auto_outbound import (
    AutoOutboundTargetBulkCreateRequest,
    AutoOutboundTargetCreate,
    AutoOutboundTaskCreate,
    DailyTimeWindow,
)
from app.schemas.open_api import OpenApiContext, OpenApiTaskPrincipal
from app.schemas.outbound_task import (
    OutboundTargetBulkCreateRequest,
    OutboundTargetCreate,
    OutboundTaskCreate,
)
from app.services.auto_outbound_task_service import AutoOutboundTaskService
from app.services.outbound_task_service import OutboundTaskService


def _open_principal(tenant_id: int = 11) -> OpenApiTaskPrincipal:
    return OpenApiTaskPrincipal.from_context(
        OpenApiContext(
            tenant_id=tenant_id,
            api_key_id=7,
            api_key_name="Integration",
            api_key_version=1,
            is_active=True,
        )
    )


def test_open_api_task_principal_is_tenant_scoped_without_employee_actor() -> None:
    principal = _open_principal()

    assert principal.tenant_id == 11
    assert principal.user_id is None
    assert principal.api_key_id == 7
    assert principal.has_permission("engagement.outbound_task.manage") is True


def test_open_engagement_router_exposes_manual_and_auto_management_paths() -> None:
    operations = {
        (method, route.path)
        for route in router.routes
        for method in getattr(route, "methods", set())
    }

    expected = {
        ("GET", "/open/engagement/outbound-tasks"),
        ("POST", "/open/engagement/outbound-tasks"),
        ("PUT", "/open/engagement/outbound-tasks/{task_id}"),
        ("POST", "/open/engagement/outbound-tasks/{task_id}/publish"),
        ("POST", "/open/engagement/outbound-tasks/{task_id}/targets"),
        ("POST", "/open/engagement/outbound-tasks/{task_id}/targets/bulk"),
        ("POST", "/open/engagement/outbound-tasks/{task_id}/targets/import"),
        ("GET", "/open/engagement/outbound-tasks/{task_id}/records"),
        ("GET", "/open/engagement/auto-outbound-tasks"),
        ("POST", "/open/engagement/auto-outbound-tasks"),
        ("PUT", "/open/engagement/auto-outbound-tasks/{task_id}"),
        ("DELETE", "/open/engagement/auto-outbound-tasks/{task_id}"),
        ("POST", "/open/engagement/auto-outbound-tasks/{task_id}/start"),
        ("GET", "/open/engagement/auto-outbound-tasks/{task_id}/stats"),
        ("POST", "/open/engagement/auto-outbound-tasks/{task_id}/targets/import"),
        ("POST", "/open/engagement/auto-outbound-tasks/{task_id}/targets/bulk"),
        ("DELETE", "/open/engagement/auto-outbound-targets/{target_id}"),
        ("GET", "/open/engagement/auto-outbound-tasks/{task_id}/records"),
    }

    assert expected <= operations
    assert not any("my-outbound-targets" in path for _, path in operations)
    assert not any("agent-context" in path for _, path in operations)
    assert not any("wrapup" in path for _, path in operations)


@pytest.mark.parametrize(
    "schema",
    [OutboundTargetBulkCreateRequest, AutoOutboundTargetBulkCreateRequest],
)
def test_bulk_target_request_requires_at_least_one_target(
    schema: type[OutboundTargetBulkCreateRequest]
    | type[AutoOutboundTargetBulkCreateRequest],
) -> None:
    with pytest.raises(PydanticValidationError):
        schema(targets=[])


@pytest.mark.asyncio
async def test_open_manual_task_create_persists_no_employee_actor() -> None:
    db = AsyncMock()
    principal = _open_principal()
    template = SimpleNamespace(
        id=3,
        tenant_id=11,
        name="Customer follow-up",
        fields=[],
        script=None,
    )
    created = object()

    with (
        patch("app.services.outbound_task_service.OutboundTaskRepository") as repo,
        patch.object(
            OutboundTaskService,
            "_attach_task_stats",
            AsyncMock(return_value=["response"]),
        ),
    ):
        repo.get_template = AsyncMock(return_value=template)
        repo.create_task = AsyncMock(return_value=created)

        result = await OutboundTaskService.create_task(
            db,
            principal,
            OutboundTaskCreate(name="Open task", template_id=3),
        )

    payload = repo.create_task.await_args.args[1]
    assert result == "response"
    assert payload["tenant_id"] == 11
    assert payload["created_by_id"] is None
    assert payload["updated_by_id"] is None
    assert payload["owner_id"] is None


@pytest.mark.asyncio
async def test_open_auto_task_create_persists_no_employee_actor() -> None:
    db = AsyncMock()
    principal = _open_principal()
    template = SimpleNamespace(
        id=3,
        tenant_id=11,
        name="Auto follow-up",
        fields=[],
    )
    created = object()
    today = date(2026, 8, 13)

    with (
        patch("app.services.auto_outbound_task_service.OutboundTaskRepository") as template_repo,
        patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo,
        patch.object(
            AutoOutboundTaskService,
            "_assert_reception_refs",
            AsyncMock(),
        ),
        patch.object(
            AutoOutboundTaskService,
            "_fill_reception_target_names",
            AsyncMock(),
        ),
        patch.object(
            AutoOutboundTaskService,
            "_to_response",
            AsyncMock(return_value="response"),
        ),
    ):
        template_repo.get_template = AsyncMock(return_value=template)
        repo.create_task = AsyncMock(return_value=created)

        result = await AutoOutboundTaskService.create_task(
            db,
            principal,
            AutoOutboundTaskCreate(
                name="Open auto task",
                template_id=3,
                execution_mode="ivr",
                voice_flow_id=5,
                start_date=today,
                end_date=today,
                daily_time_windows=[
                    DailyTimeWindow(start="09:00", end="12:00"),
                    DailyTimeWindow(start="14:00", end="20:00"),
                ],
            ),
        )

    payload = repo.create_task.await_args.args[1]
    assert result == "response"
    assert payload["tenant_id"] == 11
    assert payload["created_by_id"] is None
    assert payload["updated_by_id"] is None
    assert payload["owner_id"] is None


@pytest.mark.asyncio
async def test_open_manual_task_rejects_cross_tenant_resource() -> None:
    db = AsyncMock()
    principal = _open_principal(tenant_id=11)
    task = OutboundTask(id=9, tenant_id=99, template_name="Other", name="Other")

    with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
        repo.get_task = AsyncMock(return_value=task)

        with pytest.raises(NotFoundError):
            await OutboundTaskService.get_task(db, principal, task.id)


@pytest.mark.asyncio
async def test_open_manual_targets_bulk_uses_one_tenant_scoped_repository_call() -> None:
    db = AsyncMock()
    principal = _open_principal()
    task = OutboundTask(
        id=9,
        tenant_id=11,
        template_name="Template",
        name="Task",
        status="draft",
    )
    item = OutboundTaskTarget(
        id=21,
        tenant_id=11,
        task_id=9,
        phone_number="13800138000",
        status="pending",
        field_values={},
        call_count=0,
        answered_count=0,
        total_talk_duration_ms=0,
    )

    with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
        repo.get_task = AsyncMock(return_value=task)
        repo.get_task_for_update = AsyncMock(return_value=task)
        repo.create_targets_bulk = AsyncMock(return_value=[item])

        result = await OutboundTaskService.create_targets_bulk(
            db,
            principal,
            9,
            OutboundTargetBulkCreateRequest(
                targets=[OutboundTargetCreate(phone_number="13800138000")]
            ),
        )

    rows = repo.create_targets_bulk.await_args.args[1]
    assert result.created == 1
    assert result.items[0].id == 21
    assert rows == [
        {
            "phone_number": "13800138000",
            "user_id": None,
            "assignee_id": None,
            "field_values": {},
            "tenant_id": 11,
            "task_id": 9,
        }
    ]


@pytest.mark.asyncio
async def test_open_auto_targets_bulk_matches_users_and_writes_once() -> None:
    db = AsyncMock()
    principal = _open_principal()
    task = AutoOutboundTask(id=8, tenant_id=11, name="Auto", status="draft")
    item = AutoOutboundTarget(
        id=31,
        tenant_id=11,
        task_id=8,
        phone_number="13900139000",
        user_id=41,
        status="pending",
        field_values={},
        call_count=0,
        answered_count=0,
        retry_counts={},
    )
    user = SimpleNamespace(id=41, phone="13900139000")

    with (
        patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo,
        patch("app.services.auto_outbound_task_service.UserRepository") as user_repo,
    ):
        repo.get_task = AsyncMock(return_value=task)
        repo.get_task_for_update = AsyncMock(return_value=task)
        repo.create_targets_bulk = AsyncMock(return_value=[item])
        user_repo.list_with_phone = AsyncMock(return_value=[user])
        user_repo.list_by_ids = AsyncMock(return_value=[user])

        result = await AutoOutboundTaskService.create_targets_bulk(
            db,
            principal,
            8,
            AutoOutboundTargetBulkCreateRequest(
                targets=[AutoOutboundTargetCreate(phone_number="13900139000")]
            ),
        )

    rows = repo.create_targets_bulk.await_args.args[1]
    assert result.created == 1
    assert result.items[0].user_id == 41
    assert rows[0]["tenant_id"] == 11
    assert rows[0]["task_id"] == 8
    assert rows[0]["user_id"] == 41


@pytest.mark.asyncio
async def test_bulk_repositories_flush_and_commit_without_per_item_refresh() -> None:
    manual_db = AsyncMock()
    manual_db.add_all = MagicMock()
    manual_items = await OutboundTaskRepository.create_targets_bulk(
        manual_db,
        [{"tenant_id": 11, "task_id": 9, "phone_number": "13800138000"}],
    )

    assert len(manual_items) == 1
    manual_db.add_all.assert_called_once()
    manual_db.flush.assert_awaited_once()
    manual_db.commit.assert_awaited_once()
    manual_db.refresh.assert_not_awaited()

    auto_db = AsyncMock()
    auto_db.add_all = MagicMock()
    auto_items = await AutoOutboundRepository.create_targets_bulk(
        auto_db,
        [{"tenant_id": 11, "task_id": 8, "phone_number": "13900139000"}],
    )

    assert len(auto_items) == 1
    auto_db.add_all.assert_called_once()
    auto_db.flush.assert_awaited_once()
    auto_db.commit.assert_awaited_once()
    auto_db.refresh.assert_not_awaited()
