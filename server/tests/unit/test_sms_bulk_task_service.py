"""
Unit tests for bulk SMS task service: permissions, state machine,
template snapshots and target management.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.sms_bulk_task import SmsBulkTask, SmsBulkTarget
from app.schemas.permission import EffectivePrincipal
from app.schemas.sms_bulk_task import SmsBulkTaskCreate, SmsBulkTaskUpdate, SmsBulkTargetCreate
from app.services.sms_bulk_task_service import SmsBulkTaskService

MANAGE = "engagement.sms_task.manage"
CREATE = "engagement.sms_task.create"

VARIABLE_DEFS = [
    {"key": "name", "label": "客户姓名", "required": True, "max_length": 30},
    {"key": "time", "label": "预约时间", "required": False, "max_length": 20},
]

FUTURE = datetime.now(timezone.utc) + timedelta(hours=2)
PAST = datetime.now(timezone.utc) - timedelta(hours=2)


def principal(permissions: list[str], user_id: int = 10, tenant_id: int = 1) -> EffectivePrincipal:
    return EffectivePrincipal(user_id=user_id, tenant_id=tenant_id, permissions=permissions, is_super_admin=False)


def task(status: str = "draft", created_by_id: int = 10, send_type: str = "immediate", scheduled_at=None) -> SmsBulkTask:
    return SmsBulkTask(
        id=1,
        tenant_id=1,
        name="八月套餐到期提醒",
        description=None,
        status=status,
        template_id=10,
        template_name="预约回访提醒",
        template_type="notify",
        sign_name="深流客服",
        provider_sign_name="深流客服",
        body="尊敬的{name}，您预约的回访时间为{time}。",
        variables=VARIABLE_DEFS,
        provider="aliyun",
        provider_template_code="SMS_123456",
        send_type=send_type,
        scheduled_at=scheduled_at,
        created_by_id=created_by_id,
        updated_by_id=created_by_id,
    )


def template_row(template_status: str = "enabled"):
    template = SimpleNamespace(
        id=10,
        name="预约回访提醒",
        type="notify",
        status=template_status,
        body="尊敬的{name}，您预约的回访时间为{time}。",
        variables=VARIABLE_DEFS,
        provider="aliyun",
        provider_template_code="SMS_123456",
    )
    signature = SimpleNamespace(name="深流客服", provider_sign_name="深流客服")
    return SimpleNamespace(id=1), template, signature


def _apply_update(db, item, payload):
    for key, value in payload.items():
        setattr(item, key, value)
    return item


def target(status: str = "pending", phone: str = "13800138000") -> SmsBulkTarget:
    return SmsBulkTarget(
        id=3,
        tenant_id=1,
        task_id=1,
        phone=phone,
        variable_values={"name": "王先生"},
        status=status,
    )


TASK_REPO_METHODS = (
    "get_by_id",
    "list_for_tenant",
    "stats_for_tasks",
    "create",
    "get_creator_name",
    "update",
    "delete",
)
TARGET_REPO_METHODS = (
    "count_for_task",
    "delete_for_task",
    "list_for_task",
    "get_by_id",
    "get_by_phone",
    "create",
    "bulk_delete_pending",
    "reset_failed_for_task",
)
GRANT_REPO_METHODS = ("get_granted_template", "list_granted_detail_for_tenant_paginated")


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _patch_repos():
    task_repo = patch("app.services.sms_bulk_task_service.SmsBulkTaskRepository").start()
    target_repo = patch("app.services.sms_bulk_task_service.SmsBulkTargetRepository").start()
    grant_repo = patch("app.services.sms_bulk_task_service.SmsTemplateGrantRepository").start()
    for name in TASK_REPO_METHODS:
        setattr(task_repo, name, AsyncMock())
    for name in TARGET_REPO_METHODS:
        setattr(target_repo, name, AsyncMock())
    for name in GRANT_REPO_METHODS:
        setattr(grant_repo, name, AsyncMock())
    return SimpleNamespace(task=task_repo, target=target_repo, grant=grant_repo)


class TestPermissions:
    @pytest.mark.asyncio
    async def test_list_tasks_without_permission_raises_forbidden(self):
        repos = _patch_repos()
        with pytest.raises(ForbiddenError):
            await SmsBulkTaskService.list_tasks(AsyncMock(), principal([]))
        repos.task.list_for_tenant.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_tasks_create_only_scopes_to_own_tasks(self):
        repos = _patch_repos()
        repos.task.list_for_tenant = AsyncMock(return_value=([], 0))
        repos.task.stats_for_tasks = AsyncMock(return_value={})

        await SmsBulkTaskService.list_tasks(AsyncMock(), principal([CREATE], user_id=42))

        assert repos.task.list_for_tenant.call_args.kwargs["created_by_id"] == 42

    @pytest.mark.asyncio
    async def test_list_tasks_manage_sees_all_tasks(self):
        repos = _patch_repos()
        repos.task.list_for_tenant = AsyncMock(return_value=([], 0))
        repos.task.stats_for_tasks = AsyncMock(return_value={})

        await SmsBulkTaskService.list_tasks(AsyncMock(), principal([MANAGE], user_id=42))

        assert repos.task.list_for_tenant.call_args.kwargs["created_by_id"] is None

    @pytest.mark.asyncio
    async def test_create_only_user_cannot_manage_others_task(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(created_by_id=99))

        with pytest.raises(NotFoundError):
            await SmsBulkTaskService.get_task(AsyncMock(), principal([CREATE], user_id=10), 1)

    @pytest.mark.asyncio
    async def test_create_task_without_create_permission_raises_forbidden(self):
        _patch_repos()
        data = SmsBulkTaskCreate(name="任务", template_id=10)
        with pytest.raises(ForbiddenError):
            await SmsBulkTaskService.create_task(AsyncMock(), principal([]), data)


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_create_task_writes_template_snapshot(self):
        repos = _patch_repos()
        repos.grant.get_granted_template = AsyncMock(return_value=template_row())
        created = task()
        repos.task.create = AsyncMock(return_value=created)
        repos.task.get_creator_name = AsyncMock(return_value="李婷")

        data = SmsBulkTaskCreate(name="八月套餐到期提醒", template_id=10)
        result = await SmsBulkTaskService.create_task(AsyncMock(), principal([CREATE]), data)

        payload = repos.task.create.call_args.args[1]
        assert payload["template_name"] == "预约回访提醒"
        assert payload["provider_template_code"] == "SMS_123456"
        assert payload["status"] == "draft"
        assert result["template_name"] == "预约回访提醒"

    @pytest.mark.asyncio
    async def test_create_task_with_disabled_template_raises_validation_error(self):
        repos = _patch_repos()
        repos.grant.get_granted_template = AsyncMock(return_value=template_row(template_status="disabled"))

        data = SmsBulkTaskCreate(name="任务", template_id=10)
        with pytest.raises(ValidationError):
            await SmsBulkTaskService.create_task(AsyncMock(), principal([CREATE]), data)

    @pytest.mark.asyncio
    async def test_create_scheduled_task_with_past_time_raises_validation_error(self):
        _patch_repos()
        data = SmsBulkTaskCreate(name="任务", template_id=10, send_type="scheduled", scheduled_at=PAST)
        with pytest.raises(ValidationError):
            await SmsBulkTaskService.create_task(AsyncMock(), principal([CREATE]), data)


class TestUpdateTask:
    @pytest.mark.asyncio
    async def test_update_sending_task_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="sending"))

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.update_task(AsyncMock(), principal([MANAGE]), 1, SmsBulkTaskUpdate(name="新名"))

    @pytest.mark.asyncio
    async def test_update_template_on_paused_task_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="paused"))

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.update_task(AsyncMock(), principal([MANAGE]), 1, SmsBulkTaskUpdate(template_id=20))

    @pytest.mark.asyncio
    async def test_update_template_on_draft_clears_targets(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="draft"))
        repos.grant.get_granted_template = AsyncMock(return_value=template_row())
        repos.task.update = AsyncMock(side_effect=lambda db, item, payload: item)
        repos.task.get_creator_name = AsyncMock(return_value=None)
        repos.target.delete_for_task = AsyncMock()

        await SmsBulkTaskService.update_task(AsyncMock(), principal([MANAGE]), 1, SmsBulkTaskUpdate(template_id=20))

        repos.target.delete_for_task.assert_awaited_once()


class TestStateMachine:
    @pytest.mark.asyncio
    async def test_publish_without_targets_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task())
        repos.target.count_for_task = AsyncMock(return_value=0)

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.publish_task(AsyncMock(), principal([MANAGE]), 1)

    @pytest.mark.asyncio
    async def test_publish_scheduled_task_with_past_time_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(send_type="scheduled", scheduled_at=PAST))
        repos.target.count_for_task = AsyncMock(return_value=5)

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.publish_task(AsyncMock(), principal([MANAGE]), 1)

    @pytest.mark.asyncio
    async def test_publish_immediate_task_enters_sending(self):
        repos = _patch_repos()
        t = task()
        repos.task.get_by_id = AsyncMock(return_value=t)
        repos.target.count_for_task = AsyncMock(return_value=5)
        repos.grant.get_granted_template = AsyncMock(return_value=template_row())
        repos.task.update = AsyncMock(side_effect=_apply_update)
        repos.task.get_creator_name = AsyncMock(return_value=None)

        result = await SmsBulkTaskService.publish_task(AsyncMock(), principal([MANAGE]), 1)

        payload = repos.task.update.call_args.args[2]
        assert payload["status"] == "sending"
        assert payload["published_at"] is not None
        assert result["status"] == "sending"

    @pytest.mark.asyncio
    async def test_publish_scheduled_task_enters_scheduled(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(send_type="scheduled", scheduled_at=FUTURE))
        repos.target.count_for_task = AsyncMock(return_value=5)
        repos.grant.get_granted_template = AsyncMock(return_value=template_row())
        repos.task.update = AsyncMock(side_effect=_apply_update)
        repos.task.get_creator_name = AsyncMock(return_value=None)

        result = await SmsBulkTaskService.publish_task(AsyncMock(), principal([MANAGE]), 1)

        assert result["status"] == "scheduled"

    @pytest.mark.asyncio
    async def test_pause_sending_task(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="sending"))
        repos.task.update = AsyncMock(side_effect=_apply_update)
        repos.task.get_creator_name = AsyncMock(return_value=None)

        result = await SmsBulkTaskService.pause_task(AsyncMock(), principal([MANAGE]), 1)

        assert result["status"] == "paused"
        assert result["pause_reason"] == "manual"

    @pytest.mark.asyncio
    async def test_pause_draft_task_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="draft"))

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.pause_task(AsyncMock(), principal([MANAGE]), 1)

    @pytest.mark.asyncio
    async def test_resume_paused_scheduled_task_returns_to_scheduled(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="paused", send_type="scheduled", scheduled_at=FUTURE))
        repos.task.update = AsyncMock(side_effect=_apply_update)
        repos.task.get_creator_name = AsyncMock(return_value=None)

        result = await SmsBulkTaskService.resume_task(AsyncMock(), principal([MANAGE]), 1)

        assert result["status"] == "scheduled"
        assert result["pause_reason"] is None

    @pytest.mark.asyncio
    async def test_resume_paused_immediate_task_returns_to_sending(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="paused"))
        repos.task.update = AsyncMock(side_effect=_apply_update)
        repos.task.get_creator_name = AsyncMock(return_value=None)

        result = await SmsBulkTaskService.resume_task(AsyncMock(), principal([MANAGE]), 1)

        assert result["status"] == "sending"

    @pytest.mark.asyncio
    async def test_archive_sending_task_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="sending"))

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.archive_task(AsyncMock(), principal([MANAGE]), 1)

    @pytest.mark.asyncio
    async def test_delete_non_draft_task_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="paused"))

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.delete_task(AsyncMock(), principal([MANAGE]), 1)

    @pytest.mark.asyncio
    async def test_delete_draft_task(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="draft"))
        repos.task.delete = AsyncMock()

        await SmsBulkTaskService.delete_task(AsyncMock(), principal([MANAGE]), 1)

        repos.task.delete.assert_awaited_once()


class TestTargets:
    @pytest.mark.asyncio
    async def test_create_target_on_sending_task_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="sending"))

        data = SmsBulkTargetCreate(phone="13800138000", variable_values={"name": "王先生"})
        with pytest.raises(ValidationError):
            await SmsBulkTaskService.create_target(AsyncMock(), principal([MANAGE]), 1, data)

    @pytest.mark.asyncio
    async def test_create_target_with_duplicate_phone_raises_conflict(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task())
        repos.target.get_by_phone = AsyncMock(return_value=target())

        data = SmsBulkTargetCreate(phone="13800138000", variable_values={"name": "王先生"})
        with pytest.raises(ConflictError):
            await SmsBulkTaskService.create_target(AsyncMock(), principal([MANAGE]), 1, data)

    @pytest.mark.asyncio
    async def test_create_target_missing_required_variable_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task())

        data = SmsBulkTargetCreate(phone="13800138000", variable_values={})
        with pytest.raises(ValidationError):
            await SmsBulkTaskService.create_target(AsyncMock(), principal([MANAGE]), 1, data)

    @pytest.mark.asyncio
    async def test_create_target_success(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task())
        repos.target.get_by_phone = AsyncMock(return_value=None)
        created = target()
        repos.target.create = AsyncMock(return_value=created)

        data = SmsBulkTargetCreate(phone="13800138000", variable_values={"name": "王先生"})
        result = await SmsBulkTaskService.create_target(AsyncMock(), principal([MANAGE]), 1, data)

        assert result["phone"] == "13800138000"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_bulk_delete_reports_skipped_non_pending(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task())
        repos.target.bulk_delete_pending = AsyncMock(return_value=2)

        result = await SmsBulkTaskService.bulk_delete_targets(AsyncMock(), principal([MANAGE]), 1, [1, 2, 3])

        assert result == {"deleted": 2, "skipped": 1}

    @pytest.mark.asyncio
    async def test_resend_failed_on_draft_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="draft"))

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.resend_failed_targets(AsyncMock(), principal([MANAGE]), 1)

    @pytest.mark.asyncio
    async def test_resend_failed_without_failed_targets_raises_validation_error(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="completed"))
        repos.target.reset_failed_for_task = AsyncMock(return_value=0)

        with pytest.raises(ValidationError):
            await SmsBulkTaskService.resend_failed_targets(AsyncMock(), principal([MANAGE]), 1)

    @pytest.mark.asyncio
    async def test_resend_failed_resets_targets(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="completed"))
        repos.target.reset_failed_for_task = AsyncMock(return_value=4)

        result = await SmsBulkTaskService.resend_failed_targets(AsyncMock(), principal([MANAGE]), 1)

        assert result == {"reset": 4}

    @pytest.mark.asyncio
    async def test_resend_failed_on_completed_task_reopens_sending(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="completed"))
        repos.target.reset_failed_for_task = AsyncMock(return_value=2)
        repos.task.update = AsyncMock(side_effect=_apply_update)

        await SmsBulkTaskService.resend_failed_targets(AsyncMock(), principal([MANAGE]), 1)

        payload = repos.task.update.call_args.args[2]
        assert payload["status"] == "sending"
        assert payload["completed_at"] is None

    @pytest.mark.asyncio
    async def test_resend_failed_on_paused_task_stays_paused(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task(status="paused"))
        repos.target.reset_failed_for_task = AsyncMock(return_value=2)

        result = await SmsBulkTaskService.resend_failed_targets(AsyncMock(), principal([MANAGE]), 1)

        assert result == {"reset": 2}
        repos.task.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_target_renders_body_snapshot(self):
        repos = _patch_repos()
        repos.task.get_by_id = AsyncMock(return_value=task())
        repos.target.get_by_id = AsyncMock(return_value=target())

        result = await SmsBulkTaskService.get_target(AsyncMock(), principal([MANAGE]), 1, 3)

        assert "王先生" in result["body_rendered"]
        assert "{name}" not in result["body_rendered"]
