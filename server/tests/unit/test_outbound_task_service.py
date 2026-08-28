"""
Unit tests for manual outbound task service.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.libs.excel import build_xlsx
from app.models.outbound_task import OutboundCallRecord, OutboundTask, OutboundTaskTarget, OutboundTaskTemplate
from app.models.personal_auto_outbound import PersonalAutoOutboundCall
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
    async def test_task_creator_can_read_template_for_task_creation(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.create"])
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
        active_task.fields = [{"key": "call_result", "enabled": True, "agent_editable": True}]
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

    @pytest.mark.asyncio
    async def test_create_record_redial_requires_next_follow_up_at(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        active_task = task(status="active")

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)
            repo.get_task = AsyncMock(return_value=active_task)
            repo.create_record = AsyncMock()

            with pytest.raises(ValidationError):
                await OutboundTaskService.create_record(
                    db,
                    p,
                    item.id,
                    OutboundRecordCreate(target_status="redial"),
                )

        repo.create_record.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_record_rejects_readonly_field(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        active_task = task(status="active")
        active_task.fields = [{"key": "customer_level", "enabled": True, "agent_editable": False}]

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)
            repo.get_task = AsyncMock(return_value=active_task)
            repo.create_record = AsyncMock()

            with pytest.raises(ValidationError):
                await OutboundTaskService.create_record(
                    db,
                    p,
                    item.id,
                    OutboundRecordCreate(
                        target_status="completed",
                        field_values={"customer_level": "vip"},
                    ),
                )

        repo.create_record.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_record_validates_required_field_on_merged_values(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        item.field_values = {}
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
            repo.create_record = AsyncMock()

            with pytest.raises(ValidationError):
                await OutboundTaskService.create_record(
                    db,
                    p,
                    item.id,
                    OutboundRecordCreate(target_status="completed"),
                )

        repo.create_record.assert_not_awaited()


class TestListMyTasks:
    @pytest.mark.asyncio
    async def test_list_my_tasks_requires_execute_permission(self):
        db = AsyncMock()
        p = principal([])

        with pytest.raises(ForbiddenError):
            await OutboundTaskService.list_my_tasks(db, p)

    @pytest.mark.asyncio
    async def test_list_my_tasks_returns_progress_items(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        rows = [
            {"id": 1, "name": "回访", "status": "active", "due_at": None, "my_total": 50, "my_completed": 5},
            {"id": 2, "name": "开发", "status": "paused", "due_at": None, "my_total": 40, "my_completed": 12},
        ]

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.list_my_tasks_with_progress = AsyncMock(return_value=rows)

            result = await OutboundTaskService.list_my_tasks(db, p)

        repo.list_my_tasks_with_progress.assert_awaited_once_with(db, 1, 10)
        assert result == {"items": rows}


class TestListMyTargetRecords:
    @pytest.mark.asyncio
    async def test_requires_execute_permission(self):
        db = AsyncMock()
        p = principal([])

        with pytest.raises(ForbiddenError):
            await OutboundTaskService.list_my_target_records(db, p, 3)

    @pytest.mark.asyncio
    async def test_target_not_found_raises_404(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=None)

            with pytest.raises(NotFoundError):
                await OutboundTaskService.list_my_target_records(db, p, 999)

    @pytest.mark.asyncio
    async def test_other_agents_target_raises_403(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=11)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=item)

            with pytest.raises(ForbiddenError):
                await OutboundTaskService.list_my_target_records(db, p, item.id)

    @pytest.mark.asyncio
    async def test_merges_manual_and_personal_auto_records_sorted_desc(self):
        db = AsyncMock()
        p = principal(
            ["engagement.outbound_task.execute", "call.workspace.use", "call.record.view"],
            user_id=10,
        )
        item = target(assignee_id=10)
        manual = OutboundCallRecord(
            id=11,
            tenant_id=1,
            task_id=1,
            target_id=3,
            call_record_id=9001,
            agent_id=10,
            phone_number="13800000000",
            started_at=datetime(2026, 8, 16, 6, 30, tzinfo=timezone.utc),
            duration_ms=None,
            answered=False,
            result="未接通",
            field_values={},
        )
        personal = PersonalAutoOutboundCall(
            id=52,
            tenant_id=1,
            session_id=5,
            task_id=1,
            target_id=3,
            call_record_id=8810,
            phone_number="13800000000",
            assigned_agent_id=9,
            started_at=datetime(2026, 8, 17, 2, 0, tzinfo=timezone.utc),
            answered_at=datetime(2026, 8, 17, 2, 0, 10, tzinfo=timezone.utc),
            ended_at=datetime(2026, 8, 17, 2, 5, 42, tzinfo=timezone.utc),
        )
        employee = MagicMock()
        employee.id = 9
        employee.tenant_id = 1
        employee.display_name = "李楠"
        employee.nickname = None
        employee.name = "linan"
        employee.username = "linan"

        with (
            patch("app.services.outbound_task_service.OutboundTaskRepository") as repo,
            patch("app.services.outbound_task_service.EmployeeRepository") as employee_repo,
            patch("app.services.outbound_task_service.DataScopeService") as scope_service,
        ):
            repo.get_target = AsyncMock(return_value=item)
            repo.list_records_for_target = AsyncMock(return_value=[manual])
            repo.list_personal_auto_calls_for_target = AsyncMock(return_value=[personal])
            repo.list_call_record_public_ids = AsyncMock(return_value={9001: "pub-9001"})
            employee_repo.get_by_ids = AsyncMock(return_value=[employee])
            scope_service.call_record_ids_in_scope = AsyncMock(return_value={9001})

            result = await OutboundTaskService.list_my_target_records(db, p, item.id)

        items = result["items"]
        assert [entry["id"] for entry in items] == [52, 11]
        personal_item = items[0]
        assert personal_item["source"] == "personal_auto"
        assert personal_item["answered"] is True
        assert personal_item["duration_ms"] == 332_000
        assert personal_item["agent_name"] == "李楠"
        assert personal_item["can_view_detail"] is False
        assert personal_item["call_record_public_id"] is None
        manual_item = items[1]
        assert manual_item["source"] == "manual"
        assert manual_item["result"] == "未接通"
        assert manual_item["can_view_detail"] is True
        assert manual_item["call_record_public_id"] == "pub-9001"
        repo.list_call_record_public_ids.assert_awaited_once_with(db, 1, [9001])

    @pytest.mark.asyncio
    async def test_can_view_detail_false_without_call_record_view_permission(self):
        db = AsyncMock()
        p = principal(["engagement.outbound_task.execute", "call.workspace.use"], user_id=10)
        item = target(assignee_id=10)
        manual = OutboundCallRecord(
            id=11,
            tenant_id=1,
            task_id=1,
            target_id=3,
            call_record_id=9001,
            agent_id=10,
            phone_number="13800000000",
            started_at=datetime(2026, 8, 16, 6, 30, tzinfo=timezone.utc),
            duration_ms=30_000,
            answered=True,
            result="已接通",
            field_values={},
        )

        with (
            patch("app.services.outbound_task_service.OutboundTaskRepository") as repo,
            patch("app.services.outbound_task_service.EmployeeRepository") as employee_repo,
            patch("app.services.outbound_task_service.DataScopeService") as scope_service,
        ):
            repo.get_target = AsyncMock(return_value=item)
            repo.list_records_for_target = AsyncMock(return_value=[manual])
            repo.list_personal_auto_calls_for_target = AsyncMock(return_value=[])
            repo.list_call_record_public_ids = AsyncMock(return_value={})
            employee_repo.get_by_ids = AsyncMock(return_value=[])
            scope_service.call_record_ids_in_scope = AsyncMock()

            result = await OutboundTaskService.list_my_target_records(db, p, item.id)

        assert result["items"][0]["can_view_detail"] is False
        assert result["items"][0]["call_record_public_id"] is None
        scope_service.call_record_ids_in_scope.assert_not_awaited()
