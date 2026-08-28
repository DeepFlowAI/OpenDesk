"""Unit tests for outbound script validation and snapshot behavior."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.outbound_task import OutboundTask, OutboundTaskTarget, OutboundTaskTemplate
from app.schemas.outbound_task import (
    OutboundScript,
    OutboundTargetTaskContextResponse,
    OutboundTaskCreate,
    OutboundTemplateCreate,
    OutboundTemplateScriptUpdate,
    OutboundTemplateSummaryResponse,
    OutboundTemplateUpdate,
)
from app.schemas.permission import EffectivePrincipal
from app.services.outbound_task_service import OutboundTaskService


def principal(*permissions: str) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=7,
        tenant_id=1,
        permissions=list(permissions),
        is_super_admin=False,
    )


def valid_script() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "start", "type": "start", "title": "开始", "next_node_id": "question"},
            {
                "id": "question",
                "type": "branch",
                "title": "是否方便沟通",
                "content": "<p>现在方便沟通吗？</p>",
                "branches": [
                    {"id": "yes", "label": "方便", "next_node_id": "done"},
                    {"id": "no", "label": "不方便", "next_node_id": "callback"},
                ],
            },
            {"id": "done", "type": "end", "title": "结束", "content": "<p>感谢配合</p>"},
            {"id": "callback", "type": "end", "title": "约定回拨", "content": "<p>稍后联系</p>"},
        ],
    }


class TestOutboundScriptSchema:
    def test_valid_tree_is_accepted(self) -> None:
        script = OutboundScript.model_validate(valid_script())

        assert len(script.nodes) == 4

    def test_branch_without_next_step_is_rejected(self) -> None:
        payload = valid_script()
        payload["nodes"][1]["branches"][0]["next_node_id"] = "missing"

        with pytest.raises(PydanticValidationError, match="missing next step"):
            OutboundScript.model_validate(payload)

    def test_merged_branch_is_rejected(self) -> None:
        payload = valid_script()
        payload["nodes"][1]["branches"][1]["next_node_id"] = "done"

        with pytest.raises(PydanticValidationError, match="merged branches"):
            OutboundScript.model_validate(payload)

    def test_script_step_requires_meaningful_content(self) -> None:
        payload = valid_script()
        payload["nodes"].insert(
            2,
            {"id": "script", "type": "script", "title": "说明", "content": "<p> </p>", "next_node_id": "done"},
        )
        payload["nodes"][1]["branches"][0]["next_node_id"] = "script"

        with pytest.raises(PydanticValidationError, match="content is required"):
            OutboundScript.model_validate(payload)

    def test_template_summary_exposes_status_without_full_script(self) -> None:
        item = OutboundTaskTemplate(id=2, tenant_id=1, name="回访模板", fields=[], script=valid_script())

        summary = OutboundTemplateSummaryResponse.model_validate(item).model_dump()

        assert summary["has_script"] is True
        assert "script" not in summary

    def test_target_task_context_excludes_script_snapshot(self) -> None:
        task = OutboundTask(
            id=5,
            tenant_id=1,
            template_id=2,
            template_name="回访模板",
            name="八月回访",
            status="active",
            fields=[],
            script_snapshot=valid_script(),
            assignee_scope_ids=[],
        )

        context = OutboundTargetTaskContextResponse.model_validate(task).model_dump()

        assert context["has_script"] is True
        assert "script_snapshot" not in context


class TestOutboundScriptService:
    @pytest.mark.asyncio
    async def test_create_task_copies_template_script_snapshot(self) -> None:
        db = AsyncMock()
        p = principal("engagement.outbound_task.create")
        script = valid_script()
        template = OutboundTaskTemplate(id=2, tenant_id=1, name="回访模板", fields=[], script=script)
        created = OutboundTask(
            id=5,
            tenant_id=1,
            template_id=2,
            template_name=template.name,
            name="八月回访",
            status="draft",
            fields=[],
            script_snapshot=deepcopy(script),
            assignee_scope_ids=[],
            allow_self_claim=False,
            assignment_mode="manual",
            created_by_id=p.user_id,
        )

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_template = AsyncMock(return_value=template)
            repo.create_task = AsyncMock(return_value=created)
            repo.task_stats = AsyncMock(return_value={})

            await OutboundTaskService.create_task(
                db,
                p,
                OutboundTaskCreate(template_id=2, name="八月回访"),
            )

        payload = repo.create_task.await_args.args[1]
        assert payload["script_snapshot"] == script
        assert payload["script_snapshot"] is not template.script

    @pytest.mark.asyncio
    async def test_update_template_rejects_stale_version(self) -> None:
        db = AsyncMock()
        p = principal("engagement.outbound_task.template.manage")
        updated_at = datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc)
        template = OutboundTaskTemplate(
            id=2,
            tenant_id=1,
            name="回访模板",
            fields=[],
            script=valid_script(),
            updated_at=updated_at,
        )
        body = OutboundTemplateUpdate(
            name=template.name,
            fields=[],
            script=valid_script(),
            expected_updated_at=updated_at - timedelta(seconds=1),
        )

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_template = AsyncMock(return_value=template)

            with pytest.raises(ConflictError):
                await OutboundTaskService.update_template(db, p, template.id, body)

        repo.update_template.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_template_uses_atomic_version_check(self) -> None:
        db = AsyncMock()
        p = principal("engagement.outbound_task.template.manage")
        updated_at = datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc)
        template = OutboundTaskTemplate(
            id=2,
            tenant_id=1,
            name="回访模板",
            fields=[],
            script=valid_script(),
            updated_at=updated_at,
        )
        body = OutboundTemplateUpdate(
            name="新版回访模板",
            fields=[],
            script=valid_script(),
            expected_updated_at=updated_at,
        )

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_template = AsyncMock(return_value=template)
            repo.update_template_if_version = AsyncMock(return_value=template)

            result = await OutboundTaskService.update_template(db, p, template.id, body)

        assert result is template
        repo.update_template_if_version.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_my_target_script_returns_snapshot(self) -> None:
        db = AsyncMock()
        p = principal("engagement.outbound_task.execute", "call.workspace.use")
        script = valid_script()
        target = OutboundTaskTarget(id=9, tenant_id=1, task_id=5, phone_number="10086", assignee_id=p.user_id)
        task = OutboundTask(
            id=5,
            tenant_id=1,
            template_id=2,
            template_name="回访模板",
            name="八月回访",
            status="active",
            fields=[],
            script_snapshot=script,
            assignee_scope_ids=[],
        )

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=target)
            repo.get_task = AsyncMock(return_value=task)

            result = await OutboundTaskService.get_my_target_script(db, p, target.id)

        assert result == script

    @pytest.mark.asyncio
    async def test_get_my_target_script_rejects_other_assignee(self) -> None:
        db = AsyncMock()
        p = principal("engagement.outbound_task.execute", "call.workspace.use")
        target = OutboundTaskTarget(id=9, tenant_id=1, task_id=5, phone_number="10086", assignee_id=99)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=target)

            with pytest.raises(ForbiddenError):
                await OutboundTaskService.get_my_target_script(db, p, target.id)

    @pytest.mark.asyncio
    async def test_get_my_target_script_requires_snapshot(self) -> None:
        db = AsyncMock()
        p = principal("engagement.outbound_task.execute", "call.workspace.use")
        target = OutboundTaskTarget(id=9, tenant_id=1, task_id=5, phone_number="10086", assignee_id=p.user_id)
        task = OutboundTask(
            id=5,
            tenant_id=1,
            template_id=2,
            template_name="回访模板",
            name="八月回访",
            status="active",
            fields=[],
            script_snapshot=None,
            assignee_scope_ids=[],
        )

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_target = AsyncMock(return_value=target)
            repo.get_task = AsyncMock(return_value=task)

            with pytest.raises(NotFoundError):
                await OutboundTaskService.get_my_target_script(db, p, target.id)


class TestOutboundTemplateOpenApiService:
    @pytest.mark.asyncio
    async def test_create_template_for_tenant_allows_api_key_actor(self) -> None:
        db = AsyncMock()
        script = valid_script()
        created = OutboundTaskTemplate(
            id=3,
            tenant_id=11,
            name="OpenAPI 模板",
            fields=[],
            script=script,
            created_by_id=None,
            updated_by_id=None,
        )

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.create_template = AsyncMock(return_value=created)

            result = await OutboundTaskService.create_template_for_tenant(
                db,
                11,
                OutboundTemplateCreate(name="OpenAPI 模板", fields=[], script=OutboundScript.model_validate(script)),
            )

        payload = repo.create_template.await_args.args[1]
        assert result is created
        assert payload["tenant_id"] == 11
        assert payload["created_by_id"] is None
        assert payload["script"]["version"] == 1

    @pytest.mark.asyncio
    async def test_get_and_update_template_script_for_tenant(self) -> None:
        db = AsyncMock()
        script = valid_script()
        template = OutboundTaskTemplate(
            id=4,
            tenant_id=11,
            name="OpenAPI 模板",
            fields=[],
            script=None,
            updated_at=datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc),
        )
        updated = OutboundTaskTemplate(
            id=4,
            tenant_id=11,
            name="OpenAPI 模板",
            fields=[],
            script=script,
            updated_at=datetime(2026, 8, 7, 8, 5, tzinfo=timezone.utc),
        )

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_template = AsyncMock(side_effect=[template, template])
            repo.update_template = AsyncMock(return_value=updated)

            empty = await OutboundTaskService.get_template_script_for_tenant(db, 11, 4)
            result = await OutboundTaskService.update_template_script_for_tenant(
                db,
                11,
                4,
                OutboundTemplateScriptUpdate(script=OutboundScript.model_validate(script)),
            )

        assert empty.has_script is False
        assert result.has_script is True
        assert result.template_id == 4
        assert result.script is not None
        assert result.script.version == 1
        repo.update_template.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_template_for_tenant_rejects_cross_tenant(self) -> None:
        db = AsyncMock()
        template = OutboundTaskTemplate(id=4, tenant_id=99, name="其他租户", fields=[], script=None)

        with patch("app.services.outbound_task_service.OutboundTaskRepository") as repo:
            repo.get_template = AsyncMock(return_value=template)

            with pytest.raises(NotFoundError):
                await OutboundTaskService.get_template_for_tenant(db, 11, 4)
