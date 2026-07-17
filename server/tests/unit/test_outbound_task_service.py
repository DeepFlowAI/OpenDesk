"""
Unit tests for manual outbound task service.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.libs.excel import build_xlsx
from app.models.outbound_task import OutboundTask, OutboundTaskTarget, OutboundTaskTemplate
from app.schemas.outbound_task import (
    BulkAssignRequest,
    BulkDeleteRequest,
    OutboundRecordCreate,
    OutboundTargetExecutionUpdate,
)
from app.schemas.permission import EffectivePrincipal
from app.services.outbound_task_service import OutboundTaskService


def principal(
    permissions: list[str],
    user_id: int = 10,
    tenant_id: int = 1,
) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=user_id,
        tenant_id=tenant_id,
        permissions=permissions,
        is_super_admin=False,
    )


def task(status: str = "draft", created_by_id: int = 10) -> OutboundTask:
    return OutboundTask(
        id=1,
        tenant_id=1,
        template_name="回访模板",
        name="回访任务",
        status=status,
        created_by_id=created_by_id,
        fields=[],
        assignee_scope_ids=[],
        allow_self_claim=False,
        assignment_mode="manual",
    )


def target(assignee_id: int = 10) -> OutboundTaskTarget:
    return OutboundTaskTarget(
        id=3,
        tenant_id=1,
        task_id=1,
        phone_number="13800000000",
        assignee_id=assignee_id,
        status="pending",
        field_values={"call_result": "old"},
        call_count=1,
        answered_count=0,
        total_talk_duration_ms=0,
    )


def template(tenant_id: int = 1) -> OutboundTaskTemplate:
    return OutboundTaskTemplate(
        id=2,
        tenant_id=tenant_id,
        name="回访模板",
        description=None,
        fields=[],
    )


class TestOutboundTaskService:
    @pytest.mark.asyncio
    async def test_get_template_requires_template_manage_permission(self):
        db = AsyncMock()
        p = principal([])

        with pytest.raises(ForbiddenError):
            await OutboundTaskService.get_template(db, p, 2)

    @pytest.mark.asyncio
    async def test_get_template_returns_same_tenant_template(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.template.manage"])
        item = template()

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_template = AsyncMock(return_value=item)

            result = await OutboundTaskService.get_template(db, p, item.id)

        assert result.id == item.id

    @pytest.mark.asyncio
    async def test_get_template_hides_other_tenant_template(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.template.manage"], tenant_id=1)
        item = template(tenant_id=2)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_template = AsyncMock(return_value=item)

            with pytest.raises(NotFoundError):
                await OutboundTaskService.get_template(db, p, item.id)

    @pytest.mark.asyncio
    async def test_transition_publish_without_targets_raises_validation_error(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"])
        t = task()

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.count_targets = AsyncMock(return_value=0)

            with pytest.raises(ValidationError):
                await OutboundTaskService.transition_task(db, p, t.id, "publish")

    @pytest.mark.asyncio
    async def test_creator_can_access_own_task_without_global_manage(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"], user_id=10)
        t = task(created_by_id=10)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.task_stats = AsyncMock(return_value={})

            result = await OutboundTaskService.get_task(db, p, t.id)

        assert result.id == t.id

    @pytest.mark.asyncio
    async def test_non_creator_cannot_access_task_without_global_manage(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"], user_id=11)
        t = task(created_by_id=10)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)

            with pytest.raises(NotFoundError):
                await OutboundTaskService.get_task(db, p, t.id)

    @pytest.mark.asyncio
    async def test_create_record_requires_assigned_executor(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=11)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)

            with pytest.raises(ForbiddenError):
                await OutboundTaskService.create_record(db, p, item.id, OutboundRecordCreate(target_status="completed"))

    @pytest.mark.asyncio
    async def test_create_record_updates_target_statistics(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        active_task = task(status="active")
        started_at = datetime(2026, 7, 8, 8, 0, tzinfo=timezone.utc)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)
            repo.get_task = AsyncMock(return_value=active_task)
            repo.create_record = AsyncMock(return_value=object())
            repo.update_target = AsyncMock(return_value=item)

            await OutboundTaskService.create_record(
                db,
                p,
                item.id,
                OutboundRecordCreate(
                    started_at=started_at,
                    answered=True,
                    duration_ms=30_000,
                    result="已完成",
                    target_status="completed",
                    field_values={"call_result": "done"},
                ),
            )

        repo.update_target.assert_awaited_once()
        payload = repo.update_target.await_args.args[2]
        assert payload["call_count"] == 2
        assert payload["answered_count"] == 1
        assert payload["total_talk_duration_ms"] == 30_000
        assert payload["field_values"]["call_result"] == "done"

    @pytest.mark.asyncio
    async def test_executor_updates_target_status_without_changing_call_statistics(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        active_task = task(status="active")

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)
            repo.get_task = AsyncMock(return_value=active_task)
            repo.update_target = AsyncMock(return_value=item)

            await OutboundTaskService.update_my_target(
                db,
                p,
                item.id,
                OutboundTargetExecutionUpdate(status="completed"),
            )

        repo.update_target.assert_awaited_once_with(db, item, {"status": "completed"})

    @pytest.mark.asyncio
    async def test_executor_updates_only_editable_template_fields(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        active_task = task(status="active")
        active_task.fields = [
            {"key": "call_result", "enabled": True, "agent_editable": True},
            {"key": "customer_level", "enabled": True, "agent_editable": False},
        ]

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)
            repo.get_task = AsyncMock(return_value=active_task)
            repo.update_target = AsyncMock(return_value=item)

            await OutboundTaskService.update_my_target(
                db,
                p,
                item.id,
                OutboundTargetExecutionUpdate(field_values={"call_result": "done"}),
            )

        payload = repo.update_target.await_args.args[2]
        assert payload == {"field_values": {"call_result": "done"}}

    @pytest.mark.asyncio
    async def test_executor_cannot_update_readonly_template_field(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        active_task = task(status="active")
        active_task.fields = [{"key": "customer_level", "enabled": True, "agent_editable": False}]

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)
            repo.get_task = AsyncMock(return_value=active_task)
            repo.update_target = AsyncMock()

            with pytest.raises(ValidationError):
                await OutboundTaskService.update_my_target(
                    db,
                    p,
                    item.id,
                    OutboundTargetExecutionUpdate(field_values={"customer_level": "vip"}),
                )

        repo.update_target.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_executor_cannot_bypass_required_field_validation(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        active_task = task(status="active")
        active_task.fields = [
            {
                "key": "call_result",
                "name": "外呼结果",
                "enabled": True,
                "required": True,
                "agent_editable": True,
            }
        ]

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)
            repo.get_task = AsyncMock(return_value=active_task)
            repo.update_target = AsyncMock()

            with pytest.raises(ValidationError):
                await OutboundTaskService.update_my_target(
                    db,
                    p,
                    item.id,
                    OutboundTargetExecutionUpdate(field_values={"call_result": ""}),
                )

        repo.update_target.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_executor_cannot_update_another_agents_target(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=11)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)

            with pytest.raises(ForbiddenError):
                await OutboundTaskService.update_my_target(
                    db,
                    p,
                    item.id,
                    OutboundTargetExecutionUpdate(status="completed"),
                )

    @pytest.mark.asyncio
    async def test_import_targets_maps_template_fields(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"], user_id=10)
        t = task(created_by_id=10)
        t.fields = [
            {
                "key": "ticket_no",
                "name": "工单编号",
                "field_type": "single_line_text",
                "required": True,
                "enabled": True,
            }
        ]
        content = build_xlsx(["呼叫号码", "工单编号"], [["13800000000", "T-001"]])

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.create_target = AsyncMock(return_value=target())

            result = await OutboundTaskService.import_targets(db, p, t.id, "targets.xlsx", content)

        assert result.created == 1
        repo.create_target.assert_awaited_once()
        payload = repo.create_target.await_args.args[1]
        assert payload["phone_number"] == "13800000000"
        assert payload["field_values"] == {"ticket_no": "T-001"}

    @pytest.mark.asyncio
    async def test_import_targets_reports_missing_required_template_field(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"], user_id=10)
        t = task(created_by_id=10)
        t.fields = [
            {
                "key": "ticket_no",
                "name": "工单编号",
                "field_type": "single_line_text",
                "required": True,
                "enabled": True,
            }
        ]
        content = build_xlsx(["呼叫号码", "工单编号"], [["13800000000", ""]])

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.create_target = AsyncMock(return_value=target())

            result = await OutboundTaskService.import_targets(db, p, t.id, "targets.xlsx", content)

        assert result.created == 0
        assert result.failed == 1
        assert result.errors[0].row_number == 2
        repo.create_target.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bulk_assign_allows_paused_task(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"], user_id=10)
        paused_task = task(status="paused", created_by_id=10)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=paused_task)
            repo.bulk_assign = AsyncMock(return_value=2)

            result = await OutboundTaskService.bulk_assign(
                db,
                p,
                paused_task.id,
                BulkAssignRequest(target_ids=[1, 2], assignee_id=11, overwrite=True),
            )

        assert result.updated == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_targets_allows_paused_task(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"], user_id=10)
        paused_task = task(status="paused", created_by_id=10)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=paused_task)
            repo.bulk_delete_targets = AsyncMock(return_value=2)

            result = await OutboundTaskService.bulk_delete_targets(
                db,
                p,
                paused_task.id,
                BulkDeleteRequest(target_ids=[1, 2]),
            )

        assert result.deleted == 2
        repo.bulk_delete_targets.assert_awaited_once_with(db, 1, paused_task.id, [1, 2])

    @pytest.mark.asyncio
    async def test_bulk_delete_targets_rejects_archived_task(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.manage"])
        archived_task = task(status="archived")

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=archived_task)
            repo.bulk_delete_targets = AsyncMock()

            with pytest.raises(ValidationError):
                await OutboundTaskService.bulk_delete_targets(
                    db,
                    p,
                    archived_task.id,
                    BulkDeleteRequest(target_ids=[1]),
                )

        repo.bulk_delete_targets.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bulk_delete_targets_hides_task_without_manage_access(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"], user_id=10)
        other_users_task = task(status="paused", created_by_id=11)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_task = AsyncMock(return_value=other_users_task)
            repo.bulk_delete_targets = AsyncMock()

            with pytest.raises(NotFoundError):
                await OutboundTaskService.bulk_delete_targets(
                    db,
                    p,
                    other_users_task.id,
                    BulkDeleteRequest(target_ids=[1]),
                )

        repo.bulk_delete_targets.assert_not_awaited()
