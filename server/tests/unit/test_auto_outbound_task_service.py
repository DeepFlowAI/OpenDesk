"""
Unit tests for auto outbound task service.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.libs.excel import build_xlsx
from app.models.auto_outbound import AutoOutboundTarget, AutoOutboundTask
from app.models.outbound_task import OutboundTaskTemplate
from app.models.user import User
from app.schemas.auto_outbound import (
    AutoOutboundTargetCreate,
    AutoOutboundTargetUpdate,
    AutoOutboundTaskCreate,
    AutoOutboundTaskUpdate,
)
from app.schemas.permission import EffectivePrincipal
from app.services.auto_outbound_task_service import (
    AutoOutboundTaskService,
    is_out_of_daily_window,
)
from app.services.auto_outbound_event_service import AutoOutboundEventService


@pytest.fixture(autouse=True)
def _task_event_defaults(monkeypatch):
    """Keep existing task tests focused on task rules; event contracts have dedicated tests."""
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundEventService.actor_snapshot",
        AsyncMock(return_value={"type": "employee", "name": "Agent"}),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundEventService.emit_task_event",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.auto_outbound_task_service.AutoOutboundEventService.emit_business_record_event",
        AsyncMock(return_value=[]),
    )


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


def template(tenant_id: int = 1) -> OutboundTaskTemplate:
    return OutboundTaskTemplate(
        id=2,
        tenant_id=tenant_id,
        name="回访模板",
        description=None,
        fields=[{"key": "note", "name": "备注", "field_type": "single_line_text", "required": False, "enabled": True}],
    )


def task(
    status: str = "draft",
    created_by_id: int = 10,
    execution_mode: str = "ivr",
    auto_pause_reason: str | None = None,
    auto_resume_on_target_append: bool = False,
) -> AutoOutboundTask:
    return AutoOutboundTask(
        id=1,
        tenant_id=1,
        name="自动回访",
        template_id=2,
        template_name="回访模板",
        fields=[{"key": "note", "name": "备注", "field_type": "single_line_text", "required": False, "enabled": True}],
        status=status,
        auto_pause_reason=auto_pause_reason,
        auto_resume_on_target_append=auto_resume_on_target_append,
        execution_mode=execution_mode,
        voice_flow_id=10,
        voice_flow_name="回访流程",
        owner_id=created_by_id,
        created_by_id=created_by_id,
        updated_by_id=created_by_id,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        daily_time_windows=[{"start": "09:00", "end": "12:00"}, {"start": "14:00", "end": "20:00"}],
        caller_number_id="pn_1",
        max_concurrency=10,
        retry_policy={"no_answer": {"max_retries": 2, "interval_minutes": 120}},
        daily_per_number_limit=3,
        wrapup_seconds=60,
    )


def create_payload(**overrides) -> AutoOutboundTaskCreate:
    payload = {
        "name": "自动回访",
        "template_id": 2,
        "execution_mode": "ivr",
        "voice_flow_id": 10,
        "voice_flow_name": "回访流程",
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 31),
        "daily_time_windows": [{"start": "09:00", "end": "12:00"}],
        "caller_number_id": "pn_1",
    }
    payload.update(overrides)
    return AutoOutboundTaskCreate(**payload)


class TestOutOfWindow:
    def test_inside_window(self):
        now = datetime(2026, 8, 7, 10, 30)
        assert is_out_of_daily_window([{"start": "09:00", "end": "12:00"}], now=now) is False

    def test_outside_window(self):
        now = datetime(2026, 8, 7, 13, 0)
        assert is_out_of_daily_window([{"start": "09:00", "end": "12:00"}], now=now) is True

    def test_empty_windows_are_out(self):
        assert is_out_of_daily_window([], now=datetime(2026, 8, 7, 10, 0)) is True


class TestAutoOutboundBusinessRecordEvents:
    @pytest.mark.asyncio
    async def test_target_field_change_emits_updated_in_same_transaction(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        current_task = task(status="active")
        target = AutoOutboundTarget(
            id=10,
            tenant_id=1,
            task_id=1,
            phone_number="13800138000",
            status="pending",
            field_values={"note": "old"},
            call_count=0,
            answered_count=0,
            retry_counts={},
        )
        updated = AutoOutboundTarget(
            id=10,
            tenant_id=1,
            task_id=1,
            phone_number="13800138000",
            status="pending",
            field_values={"note": "new"},
            call_count=0,
            answered_count=0,
            retry_counts={},
        )

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_target = AsyncMock(return_value=target)
            repo.get_task = AsyncMock(return_value=current_task)
            repo.update_target = AsyncMock(return_value=updated)
            result = await AutoOutboundTaskService.update_target(
                db,
                p,
                target.id,
                AutoOutboundTargetUpdate(field_values={"note": "new"}),
            )

        assert result.field_values == {"note": "new"}
        assert repo.update_target.await_args.kwargs["commit"] is False
        event = AutoOutboundEventService.emit_business_record_event
        event.assert_awaited_once()
        assert event.await_args.kwargs["event_type"] == (
            "auto_outbound.business_record.updated"
        )
        assert event.await_args.kwargs["keys"] == ["note"]
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_same_target_fields_do_not_write_or_emit(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        current_task = task(status="active")
        target = AutoOutboundTarget(
            id=10,
            tenant_id=1,
            task_id=1,
            phone_number="13800138000",
            status="pending",
            field_values={"note": "same"},
            call_count=0,
            answered_count=0,
            retry_counts={},
        )

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_target = AsyncMock(return_value=target)
            repo.get_task = AsyncMock(return_value=current_task)
            repo.update_target = AsyncMock()
            result = await AutoOutboundTaskService.update_target(
                db,
                p,
                target.id,
                AutoOutboundTargetUpdate(field_values={"note": "same"}),
            )

        assert result is target
        repo.update_target.assert_not_awaited()
        AutoOutboundEventService.emit_business_record_event.assert_not_awaited()
        db.commit.assert_not_awaited()


class TestAutoOutboundPermissions:
    @pytest.mark.asyncio
    async def test_list_requires_manage_or_create(self):
        db = AsyncMock()
        with pytest.raises(ForbiddenError):
            await AutoOutboundTaskService.list_tasks(db, principal([]), 1, 20)

    @pytest.mark.asyncio
    async def test_create_requires_create_permission(self):
        db = AsyncMock()
        with pytest.raises(ForbiddenError):
            await AutoOutboundTaskService.create_task(
                db, principal(["engagement.auto_outbound_task.manage"]), create_payload()
            )

    @pytest.mark.asyncio
    async def test_creator_can_access_own_task(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"], user_id=10)
        t = task(created_by_id=10)

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.task_stats = AsyncMock(return_value={})
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                result = await AutoOutboundTaskService.get_task(db, p, t.id)

        assert result.id == t.id

    @pytest.mark.asyncio
    async def test_non_creator_without_manage_gets_not_found(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"], user_id=11)
        t = task(created_by_id=10)

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            with pytest.raises(NotFoundError):
                await AutoOutboundTaskService.get_task(db, p, t.id)

    @pytest.mark.asyncio
    async def test_manage_can_access_any_task(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"], user_id=99)
        t = task(created_by_id=10)

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.task_stats = AsyncMock(return_value={})
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                result = await AutoOutboundTaskService.get_task(db, p, t.id)

        assert result.id == t.id


class TestAutoOutboundStateMachine:
    @pytest.mark.asyncio
    async def test_start_without_targets_raises(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        t = task()

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.count_targets = AsyncMock(return_value=0)
            with pytest.raises(ValidationError, match="import outbound targets"):
                await AutoOutboundTaskService.start_task(db, p, t.id)

    @pytest.mark.asyncio
    async def test_start_active_task(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        t = task(status="draft")
        updated = task(status="active")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.count_targets = AsyncMock(return_value=3)
            repo.update_task = AsyncMock(return_value=updated)
            repo.task_stats = AsyncMock(return_value={1: {"total_targets": 3}})
            with patch.object(
                AutoOutboundTaskService,
                "_assert_caller_number_available",
                new=AsyncMock(),
            ), patch.object(
                AutoOutboundTaskService,
                "_assert_reception_refs",
                new=AsyncMock(),
            ):
                with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                    emp.get_by_ids = AsyncMock(return_value=[])
                    result = await AutoOutboundTaskService.start_task(db, p, t.id)

        assert result.status == "active"
        repo.update_task.assert_awaited()
        assert repo.update_task.await_args.kwargs["commit"] is False
        event = AutoOutboundEventService.emit_task_event
        event.assert_awaited_once()
        assert event.await_args.kwargs["event_type"] == "auto_outbound.task.started"
        assert event.await_args.kwargs["previous_status"] == "draft"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_same_value_update_does_not_emit_event_or_commit(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        current = task(status="paused")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=current)
            repo.update_task = AsyncMock()
            repo.task_stats = AsyncMock(return_value={})
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                result = await AutoOutboundTaskService.update_task(
                    db,
                    p,
                    current.id,
                    AutoOutboundTaskUpdate(name=current.name),
                )

        assert result.name == current.name
        repo.update_task.assert_not_awaited()
        AutoOutboundEventService.emit_task_event.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_snapshots_event_before_deleting_task(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        draft = task(status="draft")
        operations: list[str] = []

        async def emit(*_args, **_kwargs):
            operations.append("event")
            return []

        async def delete(*_args, **_kwargs):
            operations.append("delete")

        async def commit():
            operations.append("commit")

        AutoOutboundEventService.emit_task_event.side_effect = emit
        db.commit.side_effect = commit
        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=draft)
            repo.delete_task = AsyncMock(side_effect=delete)
            await AutoOutboundTaskService.delete_task(db, p, draft.id)

        assert operations == ["event", "delete", "commit"]
        assert repo.delete_task.await_args.kwargs["commit"] is False
        assert AutoOutboundEventService.emit_task_event.await_args.kwargs["event_type"] == (
            "auto_outbound.task.deleted"
        )

    @pytest.mark.asyncio
    async def test_pause_resume_archive_delete_transitions(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])

        active = task(status="active")
        paused = task(status="paused")
        archived = task(status="archived")
        draft = task(status="draft")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=active)
            repo.update_task = AsyncMock(return_value=paused)
            repo.task_stats = AsyncMock(return_value={})
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                result = await AutoOutboundTaskService.pause_task(db, p, active.id)
            assert result.status == "paused"

            repo.get_task = AsyncMock(return_value=paused)
            repo.count_targets = AsyncMock(return_value=1)
            repo.count_targets_by_status = AsyncMock(return_value=1)
            repo.update_task = AsyncMock(return_value=active)
            with patch.object(
                AutoOutboundTaskService,
                "_assert_caller_number_available",
                new=AsyncMock(),
            ), patch.object(
                AutoOutboundTaskService,
                "_assert_reception_refs",
                new=AsyncMock(),
            ):
                with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                    emp.get_by_ids = AsyncMock(return_value=[])
                    result = await AutoOutboundTaskService.resume_task(db, p, paused.id)
            assert result.status == "active"
            # Resume clears the auto-pause reason.
            assert repo.update_task.await_args.args[2]["auto_pause_reason"] is None

            repo.get_task = AsyncMock(return_value=paused)
            repo.update_task = AsyncMock(return_value=archived)
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                result = await AutoOutboundTaskService.archive_task(db, p, paused.id)
            assert result.status == "archived"

            repo.get_task = AsyncMock(return_value=draft)
            repo.delete_task = AsyncMock()
            await AutoOutboundTaskService.delete_task(db, p, draft.id)
            repo.delete_task.assert_awaited()

            repo.get_task = AsyncMock(return_value=active)
            with pytest.raises(ValidationError, match="draft"):
                await AutoOutboundTaskService.delete_task(db, p, active.id)

    @pytest.mark.asyncio
    async def test_resume_without_pending_targets_raises(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task(status="paused", auto_pause_reason="queue_finished")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.count_targets_by_status = AsyncMock(return_value=0)
            with pytest.raises(ValidationError, match="Add pending numbers before resuming"):
                await AutoOutboundTaskService.resume_task(db, p, t.id)

    @pytest.mark.asyncio
    async def test_resume_completed_task_raises_ended(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task(status="completed")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            with pytest.raises(ValidationError, match="has ended and cannot be resumed"):
                await AutoOutboundTaskService.resume_task(db, p, t.id)

    @pytest.mark.asyncio
    async def test_resume_with_redial_pending_target_succeeds(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        paused = task(status="paused", auto_pause_reason="queue_finished")
        active = task(status="active")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=paused)
            repo.count_targets_by_status = AsyncMock(return_value=1)
            repo.update_task = AsyncMock(return_value=active)
            repo.task_stats = AsyncMock(return_value={})
            with patch.object(
                AutoOutboundTaskService,
                "_assert_caller_number_available",
                new=AsyncMock(),
            ), patch.object(
                AutoOutboundTaskService,
                "_assert_reception_refs",
                new=AsyncMock(),
            ):
                with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                    emp.get_by_ids = AsyncMock(return_value=[])
                    result = await AutoOutboundTaskService.resume_task(db, p, paused.id)

        assert result.status == "active"
        repo.count_targets_by_status.assert_awaited_once()
        assert repo.count_targets_by_status.await_args.kwargs["statuses"] == ["pending", "redial_pending"]

    @pytest.mark.asyncio
    async def test_cannot_change_mode_after_start(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task(status="active")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            with pytest.raises(ValidationError, match="cannot be changed after start"):
                await AutoOutboundTaskService.update_task(
                    db,
                    p,
                    t.id,
                    AutoOutboundTaskUpdate(execution_mode="bot"),
                )

    @pytest.mark.asyncio
    async def test_paused_can_update_name_only(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task(status="paused")
        updated = task(status="paused")
        updated.name = "新名称"

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.update_task = AsyncMock(return_value=updated)
            repo.task_stats = AsyncMock(return_value={})
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                result = await AutoOutboundTaskService.update_task(
                    db, p, t.id, AutoOutboundTaskUpdate(name="新名称")
                )

        assert result.name == "新名称"
        payload = repo.update_task.await_args.args[2]
        assert payload["name"] == "新名称"
        assert "execution_mode" not in payload

    @pytest.mark.asyncio
    async def test_paused_reject_pacing_mode_change(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task(status="paused", execution_mode="agent")
        t.voice_flow_id = None
        t.voice_flow_name = None
        t.queue_id = 3
        t.pacing_mode = "progressive"

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            with pytest.raises(ValidationError, match="cannot be changed after start"):
                await AutoOutboundTaskService.update_task(
                    db, p, t.id, AutoOutboundTaskUpdate(pacing_mode="ratio", dial_ratio=2, abandon_prompt="hangup")
                )

    @pytest.mark.asyncio
    async def test_paused_same_execution_mode_is_ignored(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task(status="paused")
        updated = task(status="paused")
        updated.name = "自动回访-改"

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.update_task = AsyncMock(return_value=updated)
            repo.task_stats = AsyncMock(return_value={})
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                await AutoOutboundTaskService.update_task(
                    db,
                    p,
                    t.id,
                    AutoOutboundTaskUpdate(name="自动回访-改", execution_mode="ivr"),
                )

        payload = repo.update_task.await_args.args[2]
        assert payload["name"] == "自动回访-改"
        assert "execution_mode" not in payload


class TestAutoOutboundCreateAndImport:
    @pytest.mark.asyncio
    async def test_create_copies_template_fields(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        tpl = template()
        created = task()

        with patch("app.services.auto_outbound_task_service.OutboundTaskRepository") as tpl_repo:
            tpl_repo.get_template = AsyncMock(return_value=tpl)
            with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
                repo.create_task = AsyncMock(return_value=created)
                with patch.object(
                    AutoOutboundTaskService, "_assert_reception_refs", new=AsyncMock()
                ), patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                    emp.get_by_ids = AsyncMock(return_value=[])
                    await AutoOutboundTaskService.create_task(db, p, create_payload())

                payload = repo.create_task.await_args.args[1]
                assert payload["template_name"] == "回访模板"
                assert payload["fields"][0]["key"] == "note"
                assert payload["status"] == "draft"
                assert payload["auto_resume_on_target_append"] is False

    @pytest.mark.asyncio
    async def test_create_task_orm_payload_keeps_date_and_decimal(self):
        """Regression: mode=json must not leave str/float for DATE/NUMERIC columns."""
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        tpl = template()
        created = task(execution_mode="agent")
        created.voice_flow_id = None
        created.voice_flow_name = None
        created.queue_id = 3
        created.pacing_mode = "predictive"
        created.dial_intensity = Decimal("1.50")
        created.abandon_rate_limit = Decimal("0.0300")
        created.abandon_prompt = "hangup"
        created.start_date = date(2026, 8, 7)
        data = create_payload(
            execution_mode="agent",
            voice_flow_id=None,
            voice_flow_name=None,
            queue_id=3,
            pacing_mode="predictive",
            dial_intensity=Decimal("1.50"),
            abandon_rate_limit=Decimal("0.0300"),
            abandon_prompt="hangup",
            start_date=date(2026, 8, 7),
            end_date=date(2026, 8, 31),
        )

        with patch("app.services.auto_outbound_task_service.OutboundTaskRepository") as tpl_repo:
            tpl_repo.get_template = AsyncMock(return_value=tpl)
            with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
                repo.create_task = AsyncMock(return_value=created)
                with patch.object(
                    AutoOutboundTaskService, "_assert_reception_refs", new=AsyncMock()
                ), patch.object(
                    AutoOutboundTaskService,
                    "_resolve_reception_target_names",
                    new=AsyncMock(return_value={created.id: "销售队列"}),
                ), patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                    emp.get_by_ids = AsyncMock(return_value=[])
                    await AutoOutboundTaskService.create_task(db, p, data)

                payload = repo.create_task.await_args.args[1]
                assert isinstance(payload["start_date"], date)
                assert isinstance(payload["end_date"], date)
                assert payload["start_date"] == date(2026, 8, 7)
                assert payload["end_date"] == date(2026, 8, 31)
                assert isinstance(payload["dial_intensity"], Decimal)
                assert payload["dial_intensity"] == Decimal("1.50")
                assert isinstance(payload["abandon_rate_limit"], Decimal)
                assert payload["abandon_rate_limit"] == Decimal("0.0300")
                # JSONB fields remain json-compatible dicts
                assert isinstance(payload["daily_time_windows"], list)
                assert isinstance(payload["daily_time_windows"][0], dict)

    @pytest.mark.asyncio
    async def test_update_task_orm_payload_keeps_date_and_decimal(self):
        """Regression: update path restores date/Decimal only for fields that are set."""
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task(status="draft", execution_mode="agent")
        t.voice_flow_id = None
        t.voice_flow_name = None
        t.queue_id = 3
        t.pacing_mode = "predictive"
        t.dial_intensity = Decimal("1.20")
        t.abandon_rate_limit = Decimal("0.0200")
        t.abandon_prompt = "hangup"
        updated = task(status="draft", execution_mode="agent")
        updated.voice_flow_id = None
        updated.voice_flow_name = None
        updated.queue_id = 3
        updated.pacing_mode = "predictive"
        updated.dial_intensity = Decimal("2.25")
        updated.abandon_rate_limit = Decimal("0.0500")
        updated.abandon_prompt = "hangup"
        data = AutoOutboundTaskUpdate(
            start_date=date(2026, 8, 7),
            end_date=date(2026, 9, 1),
            dial_intensity=Decimal("2.25"),
            abandon_rate_limit=Decimal("0.0500"),
        )

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.update_task = AsyncMock(return_value=updated)
            repo.task_stats = AsyncMock(return_value={})
            with patch.object(
                AutoOutboundTaskService, "_assert_reception_refs", new=AsyncMock()
            ), patch.object(
                AutoOutboundTaskService,
                "_resolve_reception_target_names",
                new=AsyncMock(return_value={updated.id: "销售队列"}),
            ), patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                await AutoOutboundTaskService.update_task(db, p, t.id, data)

            payload = repo.update_task.await_args.args[2]
            assert isinstance(payload["start_date"], date)
            assert isinstance(payload["end_date"], date)
            assert payload["start_date"] == date(2026, 8, 7)
            assert payload["end_date"] == date(2026, 9, 1)
            assert isinstance(payload["dial_intensity"], Decimal)
            assert payload["dial_intensity"] == Decimal("2.25")
            assert isinstance(payload["abandon_rate_limit"], Decimal)
            assert payload["abandon_rate_limit"] == Decimal("0.0500")
            assert "name" not in payload

    @pytest.mark.asyncio
    async def test_import_matches_user_and_skips_rate_limited(self):
        db = AsyncMock()
        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=pending_result)
        p = principal(["engagement.auto_outbound_task.create"])
        t = task(status="draft")
        matched_user = User(
            id=77,
            tenant_id=1,
            public_id="u77",
            external_id="e77",
            name="张三",
            phone="13800000000",
        )

        content = build_xlsx(
            ["phone_number", "备注"],
            [
                ["13800000000", "ok"],
                ["13900000000", "rate"],
                ["", "bad"],
            ],
        )

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_task_for_update = AsyncMock(return_value=t)
            repo.count_records_for_numbers_on_day = AsyncMock(
                return_value={"13900000000": 3}
            )
            repo.create_targets_bulk = AsyncMock(return_value=[MagicMock()])
            with patch("app.services.auto_outbound_task_service.UserRepository") as user_repo:
                user_repo.list_with_phone = AsyncMock(return_value=[matched_user])
                user_repo.list_by_ids = AsyncMock(return_value=[matched_user])
                result = await AutoOutboundTaskService.import_targets(
                    db, p, t.id, "targets.xlsx", content
                )

        assert result.total == 3
        assert result.created == 1
        assert result.skipped_rate_limited == 1
        assert result.failed == 1
        bulk_rows = repo.create_targets_bulk.await_args.args[1]
        assert len(bulk_rows) == 1
        assert bulk_rows[0]["user_id"] == 77
        assert bulk_rows[0]["phone_number"] == "13800000000"

    @pytest.mark.asyncio
    async def test_create_target_matches_user_when_missing(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        t = task()
        matched_user = User(
            id=88,
            tenant_id=1,
            public_id="u88",
            external_id="e88",
            name="李四",
            phone="+86 138-0000-0001",
        )

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_task_for_update = AsyncMock(return_value=t)
            repo.create_target = AsyncMock(
                return_value=AutoOutboundTarget(
                    id=9,
                    tenant_id=1,
                    task_id=1,
                    phone_number="13800000001",
                    user_id=88,
                    status="pending",
                    field_values={},
                    call_count=0,
                    answered_count=0,
                    retry_counts={},
                )
            )
            with patch("app.services.auto_outbound_task_service.UserRepository") as user_repo:
                user_repo.list_with_phone = AsyncMock(return_value=[matched_user])
                user_repo.list_by_ids = AsyncMock(return_value=[matched_user])
                await AutoOutboundTaskService.create_target(
                    db,
                    p,
                    t.id,
                    AutoOutboundTargetCreate(phone_number="13800000001"),
                )

        payload = repo.create_target.await_args.args[1]
        assert payload["user_id"] == 88
        assert repo.create_target.await_args.kwargs["commit"] is False


class TestAutoResumeAfterTargetAppend:
    @staticmethod
    def _updating_task(task_row: AutoOutboundTask):
        async def update(_db, item, payload, *, commit=True):
            for key, value in payload.items():
                setattr(item, key, value)
            return item

        return AsyncMock(side_effect=update)

    @pytest.mark.asyncio
    async def test_queue_finished_task_resumes_and_emits_system_event(self):
        db = AsyncMock()
        paused = task(
            status="paused",
            auto_pause_reason="queue_finished",
            auto_resume_on_target_append=True,
        )
        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo, patch(
            "app.services.auto_outbound.tenant_time.resolve_tenant_timezone",
            new=AsyncMock(return_value=ZoneInfo("Asia/Shanghai")),
        ):
            repo.get_task_for_update = AsyncMock(return_value=paused)
            repo.count_targets_by_status = AsyncMock(return_value=1)
            repo.update_task = self._updating_task(paused)

            resumed = await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, paused.id
            )

        assert resumed is True
        assert paused.status == "active"
        assert paused.auto_pause_reason is None
        event = AutoOutboundEventService.emit_task_event.await_args.kwargs
        assert event["event_type"] == "auto_outbound.task.resumed"
        assert event["actor"] == {"type": "system"}
        assert event["reason"] == "targets_appended_auto_resume"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reason", [None, "dial_service_unavailable"])
    async def test_manual_or_dial_failure_pause_does_not_resume(self, reason):
        db = AsyncMock()
        paused = task(
            status="paused",
            auto_pause_reason=reason,
            auto_resume_on_target_append=True,
        )
        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task_for_update = AsyncMock(return_value=paused)
            repo.count_targets_by_status = AsyncMock()
            resumed = await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, paused.id
            )

        assert resumed is False
        repo.count_targets_by_status.assert_not_awaited()
        AutoOutboundEventService.emit_task_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_setting_does_not_resume(self):
        db = AsyncMock()
        paused = task(
            status="paused",
            auto_pause_reason="queue_finished",
            auto_resume_on_target_append=False,
        )
        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task_for_update = AsyncMock(return_value=paused)
            repo.count_targets_by_status = AsyncMock()
            resumed = await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, paused.id
            )

        assert resumed is False
        repo.count_targets_by_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_concurrent_checks_emit_only_one_resume_event(self):
        db = AsyncMock()
        paused = task(
            status="paused",
            auto_pause_reason="queue_finished",
            auto_resume_on_target_append=True,
        )
        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo, patch(
            "app.services.auto_outbound.tenant_time.resolve_tenant_timezone",
            new=AsyncMock(return_value=ZoneInfo("Asia/Shanghai")),
        ):
            repo.get_task_for_update = AsyncMock(return_value=paused)
            repo.count_targets_by_status = AsyncMock(return_value=1)
            repo.update_task = self._updating_task(paused)

            first = await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, paused.id
            )
            second = await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, paused.id
            )

        assert (first, second) == (True, False)
        assert AutoOutboundEventService.emit_task_event.await_count == 1

    @pytest.mark.asyncio
    async def test_expired_task_completes_instead_of_resuming(self):
        db = AsyncMock()
        paused = task(
            status="paused",
            auto_pause_reason="queue_finished",
            auto_resume_on_target_append=True,
        )
        paused.end_date = date(2000, 1, 1)
        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo, patch(
            "app.services.auto_outbound.tenant_time.resolve_tenant_timezone",
            new=AsyncMock(return_value=ZoneInfo("Asia/Shanghai")),
        ):
            repo.get_task_for_update = AsyncMock(return_value=paused)
            repo.count_targets_by_status = AsyncMock(return_value=0)
            repo.update_task = self._updating_task(paused)

            resumed = await AutoOutboundTaskService._maybe_auto_resume_after_target_append(
                db, paused.id
            )

        assert resumed is False
        assert paused.status == "completed"
        event = AutoOutboundEventService.emit_task_event.await_args.kwargs
        assert event["event_type"] == "auto_outbound.task.completed"
        assert event["reason"] == "schedule_ended"

    @pytest.mark.asyncio
    async def test_enabling_setting_on_paused_task_runs_resume_gate(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        paused = task(
            status="paused",
            auto_pause_reason="queue_finished",
            auto_resume_on_target_append=False,
        )
        updated = task(
            status="paused",
            auto_pause_reason="queue_finished",
            auto_resume_on_target_append=True,
        )
        gate = AsyncMock(return_value=True)
        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo, patch.object(
            AutoOutboundTaskService,
            "_maybe_auto_resume_after_target_append",
            new=gate,
        ), patch("app.services.auto_outbound_task_service.EmployeeRepository") as employee_repo:
            repo.get_task = AsyncMock(return_value=paused)
            repo.update_task = AsyncMock(return_value=updated)
            repo.task_stats = AsyncMock(return_value={})
            employee_repo.get_by_ids = AsyncMock(return_value=[])
            await AutoOutboundTaskService.update_task(
                db,
                p,
                paused.id,
                AutoOutboundTaskUpdate(auto_resume_on_target_append=True),
            )

        gate.assert_awaited_once_with(db, paused.id)

    @pytest.mark.asyncio
    async def test_import_without_valid_new_targets_does_not_run_resume_gate(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        paused = task(
            status="paused",
            auto_pause_reason="queue_finished",
            auto_resume_on_target_append=True,
        )
        gate = AsyncMock(return_value=True)
        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo, patch.object(
            AutoOutboundTaskService,
            "_maybe_auto_resume_after_target_append",
            new=gate,
        ), patch("app.services.auto_outbound_task_service.UserRepository") as user_repo:
            repo.get_task = AsyncMock(return_value=paused)
            repo.count_records_for_numbers_on_day = AsyncMock(return_value={})
            repo.create_targets_bulk = AsyncMock()
            user_repo.list_with_phone = AsyncMock(return_value=[])
            result = await AutoOutboundTaskService.import_targets(
                db,
                p,
                paused.id,
                "targets.xlsx",
                build_xlsx(["phone_number"], [[""]]),
            )

        assert result.created == 0
        assert result.task_auto_resumed is False
        gate.assert_not_awaited()
        repo.create_targets_bulk.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_and_import_reject_completed_task(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task(status="completed")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            with pytest.raises(ValidationError, match="Completed tasks cannot accept new targets"):
                await AutoOutboundTaskService.create_target(
                    db, p, t.id, AutoOutboundTargetCreate(phone_number="13800000001")
                )
            with pytest.raises(ValidationError, match="Completed tasks cannot accept new targets"):
                await AutoOutboundTaskService.import_targets(
                    db, p, t.id, "targets.xlsx", build_xlsx(["phone_number"], [["13800000001"]])
                )

    @pytest.mark.asyncio
    async def test_create_target_clears_invalid_user_id(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        t = task()

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_task_for_update = AsyncMock(return_value=t)
            repo.create_target = AsyncMock(
                return_value=AutoOutboundTarget(
                    id=9,
                    tenant_id=1,
                    task_id=1,
                    phone_number="13800000001",
                    user_id=None,
                    status="pending",
                    field_values={},
                    call_count=0,
                    answered_count=0,
                    retry_counts={},
                )
            )
            with patch("app.services.auto_outbound_task_service.UserRepository") as user_repo:
                user_repo.list_by_ids = AsyncMock(return_value=[])
                await AutoOutboundTaskService.create_target(
                    db,
                    p,
                    t.id,
                    AutoOutboundTargetCreate(phone_number="13800000001", user_id=999),
                )

        payload = repo.create_target.await_args.args[1]
        assert payload["user_id"] is None

    @pytest.mark.asyncio
    async def test_start_rejects_unavailable_caller_number(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        t = task()

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.count_targets = AsyncMock(return_value=1)
            with patch.object(
                AutoOutboundTaskService,
                "_assert_caller_number_available",
                new=AsyncMock(side_effect=ValidationError("Caller number is disabled or not allowed for outbound")),
            ):
                with pytest.raises(ValidationError, match="Caller number"):
                    await AutoOutboundTaskService.start_task(db, p, t.id)


class TestAutoOutboundAgentContext:
    @pytest.mark.asyncio
    async def test_requires_workspace_permission(self):
        db = AsyncMock()
        with pytest.raises(ForbiddenError):
            await AutoOutboundTaskService.get_agent_context(
                db, principal(["engagement.auto_outbound_task.manage"]), 1
            )

    @pytest.mark.asyncio
    async def test_agent_with_workspace_use_can_access(self):
        db = AsyncMock()
        p = principal(["call.workspace.use"], user_id=77)
        t = task()
        t.fields = [
            {
                "key": "note",
                "name": "备注",
                "field_type": "single_line_text",
                "required": False,
                "enabled": True,
                "agent_editable": True,
            }
        ]

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            result = await AutoOutboundTaskService.get_agent_context(db, p, t.id)

        assert result.task_id == t.id
        assert result.task_name == t.name
        assert result.template_name == t.template_name
        assert result.wrapup_seconds == 60
        assert result.record is None
        assert len(result.fields) == 1
        assert result.fields[0].agent_editable is True

    @pytest.mark.asyncio
    async def test_record_by_call_record_id(self):
        db = AsyncMock()
        p = principal(["call.workspace.use"], user_id=77)
        t = task()
        record = MagicMock(
            id=100,
            target_id=10,
            call_record_id=555,
            phone_number="13800138000",
            agent_id=77,
            reception_result={"assigned": True},
        )
        target = MagicMock(id=10, field_values={"note": "预填"})

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_record_by_call_record_id = AsyncMock(return_value=record)
            repo.get_target = AsyncMock(return_value=target)
            repo.list_agent_records_for_phone = AsyncMock()
            result = await AutoOutboundTaskService.get_agent_context(
                db, p, t.id, call_record_id=555, phone_number="13800138000"
            )

        assert result.record is not None
        assert result.record.id == 100
        assert result.record.target_id == 10
        assert result.record.field_values["note"] == "预填"
        repo.list_agent_records_for_phone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_record_by_call_record_id_rejects_other_agent(self):
        db = AsyncMock()
        p = principal(["call.workspace.use"], user_id=77)
        t = task()
        record = MagicMock(
            id=100,
            target_id=10,
            call_record_id=555,
            agent_id=88,
            reception_result={"assigned": True},
        )

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_record_by_call_record_id = AsyncMock(return_value=record)
            with pytest.raises(ForbiddenError):
                await AutoOutboundTaskService.get_agent_context(
                    db, p, t.id, call_record_id=555
                )

    @pytest.mark.asyncio
    async def test_record_by_call_record_id_manage_can_view_others(self):
        db = AsyncMock()
        p = principal(["call.workspace.use", "engagement.auto_outbound_task.manage"], user_id=77)
        t = task()
        record = MagicMock(
            id=100,
            target_id=10,
            call_record_id=555,
            agent_id=88,
            reception_result={"assigned": True},
        )
        target = MagicMock(id=10, field_values={})

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_record_by_call_record_id = AsyncMock(return_value=record)
            repo.get_target = AsyncMock(return_value=target)
            result = await AutoOutboundTaskService.get_agent_context(
                db, p, t.id, call_record_id=555
            )

        assert result.record is not None
        assert result.record.id == 100

    @pytest.mark.asyncio
    async def test_record_fallback_phone_and_agent(self):
        db = AsyncMock()
        p = principal(["call.workspace.use"], user_id=77)
        t = task()
        submitted = MagicMock(
            id=98,
            target_id=10,
            phone_number="13800138000",
            agent_id=77,
            reception_result={"submitted_by": 77, "field_values": {"note": "done"}},
        )
        open_record = MagicMock(
            id=99,
            target_id=11,
            phone_number="13800138000",
            agent_id=77,
            reception_result={"assigned": True, "agent_id": 77},
        )
        target = MagicMock(id=11, field_values={"level": "A"})

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_record_by_call_record_id = AsyncMock(return_value=None)
            repo.list_agent_records_for_phone = AsyncMock(return_value=[submitted, open_record])
            repo.get_target = AsyncMock(return_value=target)
            result = await AutoOutboundTaskService.get_agent_context(
                db, p, t.id, phone_number="13800138000"
            )

        assert result.record is not None
        assert result.record.id == 99
        assert result.record.field_values["level"] == "A"

    @pytest.mark.asyncio
    async def test_record_fallback_phone_uses_latest_submitted_record(self):
        db = AsyncMock()
        p = principal(["call.workspace.use"], user_id=77)
        t = task()
        submitted = MagicMock(
            id=98,
            target_id=10,
            phone_number="13800138000",
            agent_id=77,
            reception_result={
                "submitted_by": 77,
                "field_values": {"note": "done"},
            },
        )
        target = MagicMock(id=10, field_values={"level": "A"})

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_record_by_call_record_id = AsyncMock(return_value=None)
            repo.list_agent_records_for_phone = AsyncMock(return_value=[submitted])
            repo.get_target = AsyncMock(return_value=target)
            result = await AutoOutboundTaskService.get_agent_context(
                db, p, t.id, phone_number="13800138000"
            )

        assert result.record is not None
        assert result.record.id == 98
        assert result.record.field_values == {"level": "A", "note": "done"}

    @pytest.mark.asyncio
    async def test_record_null_when_no_match(self):
        db = AsyncMock()
        p = principal(["call.workspace.use"], user_id=77)
        t = task()

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.get_record_by_call_record_id = AsyncMock(return_value=None)
            repo.list_agent_records_for_phone = AsyncMock(return_value=[])
            result = await AutoOutboundTaskService.get_agent_context(
                db, p, t.id, call_record_id=1, phone_number="10086"
            )

        assert result.record is None


class TestCallerNumberTenantScope:
    @pytest.mark.asyncio
    async def test_rejects_cross_tenant_number(self):
        db = AsyncMock()
        number = MagicMock(call_types=["outbound"], status="available", tenant_id="other")
        tenant = MagicMock(tenant_id="mine")
        db.get = AsyncMock(side_effect=[number, tenant])

        with pytest.raises(ValidationError, match="Caller number"):
            await AutoOutboundTaskService._assert_caller_number_available(db, 1, "pn_1")

    @pytest.mark.asyncio
    async def test_allows_global_number(self):
        db = AsyncMock()
        number = MagicMock(call_types=["outbound"], status="available", tenant_id=None)
        db.get = AsyncMock(return_value=number)

        await AutoOutboundTaskService._assert_caller_number_available(db, 1, "pn_1")
        assert db.get.await_count == 1

    @pytest.mark.asyncio
    async def test_allows_same_tenant_number(self):
        db = AsyncMock()
        number = MagicMock(call_types=["outbound"], status="available", tenant_id="acme")
        tenant = MagicMock(tenant_id="acme")
        db.get = AsyncMock(side_effect=[number, tenant])

        await AutoOutboundTaskService._assert_caller_number_available(db, 1, "pn_1")


class TestTaskStatsAndRecords:
    @pytest.mark.asyncio
    async def test_build_task_stats_computes_rates_and_concurrency(self):
        with patch.object(
            AutoOutboundTaskService, "_current_concurrency", new=AsyncMock(return_value=4)
        ):
            stats = await AutoOutboundTaskService._build_task_stats(
                1,
                {
                    "total_targets": 10,
                    "finished_targets": 3,
                    "call_count": 8,
                    "answered_count": 4,
                    "transfer_count": 2,
                    "abandon_count": 1,
                },
            )
        assert stats.answer_rate == 0.5
        assert stats.abandon_rate == 0.25
        assert stats.current_concurrency == 4
        assert stats.transfer_count == 2

    @pytest.mark.asyncio
    async def test_build_task_stats_redis_unavailable_is_none(self):
        with patch.object(
            AutoOutboundTaskService, "_current_concurrency", new=AsyncMock(return_value=None)
        ):
            stats = await AutoOutboundTaskService._build_task_stats(
                1, {"call_count": 0, "answered_count": 0, "abandon_count": 0}
            )
        assert stats.answer_rate is None
        assert stats.abandon_rate is None
        assert stats.current_concurrency is None

    @pytest.mark.asyncio
    async def test_list_records_fills_agent_name(self):
        from types import SimpleNamespace

        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task()
        record = SimpleNamespace(
            id=1,
            tenant_id=1,
            task_id=1,
            target_id=9,
            call_record_id=None,
            phone_number="13800138000",
            attempt_no=1,
            started_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
            answered_at=None,
            ended_at=None,
            duration_ms=0,
            terminal_state=None,
            reception_type="agent",
            agent_id=77,
            reception_result=None,
            fail_reason=None,
            created_at=None,
            updated_at=None,
        )
        employee = SimpleNamespace(id=77, name="坐席甲")

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.list_records = AsyncMock(return_value=([record], 1))
            repo.list_call_record_public_ids = AsyncMock(return_value={})
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[employee])
                result = await AutoOutboundTaskService.list_records(db, p, t.id, 1, 20)

        assert result["items"][0].agent_name == "坐席甲"

    @pytest.mark.asyncio
    async def test_list_records_fills_call_record_public_id(self):
        from types import SimpleNamespace
        from uuid import UUID

        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        t = task()
        public_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        record = SimpleNamespace(
            id=1,
            tenant_id=1,
            task_id=1,
            target_id=9,
            call_record_id=88,
            phone_number="13800138000",
            attempt_no=1,
            started_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
            answered_at=None,
            ended_at=None,
            duration_ms=0,
            terminal_state=None,
            reception_type="agent",
            agent_id=None,
            reception_result=None,
            fail_reason=None,
            created_at=None,
            updated_at=None,
        )

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.get_task = AsyncMock(return_value=t)
            repo.list_records = AsyncMock(return_value=([record], 1))
            repo.list_call_record_public_ids = AsyncMock(return_value={88: str(public_id)})
            with patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                result = await AutoOutboundTaskService.list_records(db, p, t.id, 1, 20)

        assert result["items"][0].call_record_id == 88
        assert result["items"][0].call_record_public_id == str(public_id)


class TestReceptionTargetName:
    @pytest.mark.asyncio
    async def test_create_ivr_fills_voice_flow_name(self):
        from types import SimpleNamespace

        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        tpl = template()
        created = task()
        created.voice_flow_name = "回访流程"
        data = create_payload(voice_flow_name=None)

        with patch("app.services.auto_outbound_task_service.OutboundTaskRepository") as tpl_repo:
            tpl_repo.get_template = AsyncMock(return_value=tpl)
            with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
                repo.create_task = AsyncMock(return_value=created)
                with patch.object(
                    AutoOutboundTaskService, "_assert_reception_refs", new=AsyncMock()
                ), patch(
                    "app.services.auto_outbound_task_service.VoiceFlowRepository"
                ) as vf_repo, patch(
                    "app.services.auto_outbound_task_service.EmployeeRepository"
                ) as emp:
                    vf_repo.get_by_id = AsyncMock(
                        return_value=SimpleNamespace(id=10, name="回访流程")
                    )
                    emp.get_by_ids = AsyncMock(return_value=[])
                    await AutoOutboundTaskService.create_task(db, p, data)

                payload = repo.create_task.await_args.args[1]
                assert payload["voice_flow_name"] == "回访流程"

    @pytest.mark.asyncio
    async def test_create_bot_fills_voicespeed_agent_name(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.create"])
        tpl = template()
        created = task(execution_mode="bot")
        created.voice_flow_id = None
        created.voice_flow_name = None
        created.voicespeed_agent_id = "vs_1"
        created.voicespeed_agent_name = "智能回访"
        created.transfer_queue_id = 5
        data = create_payload(
            execution_mode="bot",
            voice_flow_id=None,
            voice_flow_name=None,
            voicespeed_agent_id="vs_1",
            voicespeed_agent_name=None,
            transfer_queue_id=5,
        )

        with patch("app.services.auto_outbound_task_service.OutboundTaskRepository") as tpl_repo:
            tpl_repo.get_template = AsyncMock(return_value=tpl)
            with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
                repo.create_task = AsyncMock(return_value=created)
                with patch.object(
                    AutoOutboundTaskService, "_assert_reception_refs", new=AsyncMock()
                ), patch.object(
                    AutoOutboundTaskService,
                    "_lookup_voicespeed_agent_name",
                    new=AsyncMock(return_value="智能回访"),
                ), patch(
                    "app.services.auto_outbound_task_service.EmployeeRepository"
                ) as emp:
                    emp.get_by_ids = AsyncMock(return_value=[])
                    await AutoOutboundTaskService.create_task(db, p, data)

                payload = repo.create_task.await_args.args[1]
                assert payload["voicespeed_agent_name"] == "智能回访"

    @pytest.mark.asyncio
    async def test_resolve_names_for_ivr_bot_agent_modes(self):
        from types import SimpleNamespace

        db = AsyncMock()
        ivr = task(execution_mode="ivr")
        ivr.id = 1
        ivr.voice_flow_id = 14
        ivr.voice_flow_name = None

        bot = task(execution_mode="bot")
        bot.id = 2
        bot.voice_flow_id = None
        bot.voice_flow_name = None
        bot.voicespeed_agent_id = "vs_9"
        bot.voicespeed_agent_name = None
        bot.transfer_queue_id = 5

        agent = task(execution_mode="agent")
        agent.id = 3
        agent.voice_flow_id = None
        agent.voice_flow_name = None
        agent.queue_id = 7

        with patch(
            "app.services.auto_outbound_task_service.VoiceFlowRepository"
        ) as vf_repo, patch(
            "app.services.auto_outbound_task_service.EmployeeGroupRepository"
        ) as group_repo, patch.object(
            AutoOutboundTaskService,
            "_voicespeed_agent_name_map",
            new=AsyncMock(return_value={"vs_9": "外呼机器人"}),
        ):
            vf_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=14, name="IVR流程A"))
            group_repo.get_by_id = AsyncMock(
                return_value=SimpleNamespace(id=7, tenant_id=1, name="一线接待队列")
            )
            names = await AutoOutboundTaskService._resolve_reception_target_names(
                db, 1, [ivr, bot, agent]
            )

        assert names[1] == "IVR流程A"
        assert names[2] == "外呼机器人"
        assert names[3] == "一线接待队列"

    @pytest.mark.asyncio
    async def test_list_tasks_returns_reception_target_name(self):
        db = AsyncMock()
        p = principal(["engagement.auto_outbound_task.manage"])
        ivr = task(execution_mode="ivr")
        ivr.id = 11
        ivr.voice_flow_name = None
        agent = task(execution_mode="agent")
        agent.id = 12
        agent.voice_flow_id = None
        agent.voice_flow_name = None
        agent.queue_id = 7

        with patch("app.services.auto_outbound_task_service.AutoOutboundRepository") as repo:
            repo.list_tasks = AsyncMock(return_value=([ivr, agent], 2))
            repo.task_stats = AsyncMock(return_value={})
            with patch.object(
                AutoOutboundTaskService,
                "_resolve_reception_target_names",
                new=AsyncMock(return_value={11: "回访流程", 12: "销售队列"}),
            ), patch("app.services.auto_outbound_task_service.EmployeeRepository") as emp:
                emp.get_by_ids = AsyncMock(return_value=[])
                result = await AutoOutboundTaskService.list_tasks(db, p, 1, 20)

        assert result["items"][0].reception_target_name == "回访流程"
        assert result["items"][1].reception_target_name == "销售队列"
