"""
Unit tests for queue no-show cancel: settings service + runtime voiding.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.queue_no_show_setting_repository import QueueNoShowSettingRepository
from app.repositories.queue_repository import QueueTaskRepository
from app.schemas.queue_no_show_setting import QueueNoShowSettingPayload
from app.services import queue_service as qs
from app.services.queue_no_show_setting_service import QueueNoShowSettingService
from app.services.queue_service import QueueTaskService
from app.services.visitor_web_status_service import VisitorWebStatusService


def _setting_row(enabled: bool = True):
    return SimpleNamespace(
        id=1,
        tenant_id=1,
        enabled=enabled,
        updated_by_id=9,
        updated_by_name="Admin",
        updated_at=None,
    )


def _conversation(*, status: str = "queued", channel_type: str = "web", external_id: str = "v1"):
    return SimpleNamespace(
        id=100,
        public_id="cv_100",
        tenant_id=1,
        status=status,
        channel_id=5,
        agent_id=None,
        visitor=SimpleNamespace(external_id=external_id),
        channel=SimpleNamespace(channel_type=channel_type),
    )


def _task(*, channel: str = "online_chat", task_type: str = "conversation", task_ref_id: str = "100"):
    return SimpleNamespace(
        id=11,
        tenant_id=1,
        channel=channel,
        task_type=task_type,
        task_ref_id=task_ref_id,
        status="queued",
    )


class TestQueueNoShowSettingService:
    @pytest.mark.asyncio
    async def test_get_current_returns_default_when_unconfigured(self):
        db = AsyncMock()
        with patch.object(QueueNoShowSettingRepository, "get_by_tenant", AsyncMock(return_value=None)):
            resp = await QueueNoShowSettingService.get_current(db, 1)
        assert resp.configured is False
        assert resp.enabled is False
        assert resp.tenant_id == 1

    @pytest.mark.asyncio
    async def test_get_current_returns_row(self):
        db = AsyncMock()
        with patch.object(QueueNoShowSettingRepository, "get_by_tenant", AsyncMock(return_value=_setting_row(True))):
            resp = await QueueNoShowSettingService.get_current(db, 1)
        assert resp.configured is True
        assert resp.enabled is True

    @pytest.mark.asyncio
    async def test_save_persists_enabled_and_actor(self):
        db = AsyncMock()
        saved = _setting_row(True)
        with patch.object(QueueNoShowSettingRepository, "save", AsyncMock(return_value=saved)) as mock_save:
            resp = await QueueNoShowSettingService.save(
                db, 1, {"user_id": 9, "display_name": "Admin"}, QueueNoShowSettingPayload(enabled=True)
            )
        assert resp.enabled is True
        args = mock_save.call_args.args
        assert args[2]["enabled"] is True
        assert args[2]["updated_by_id"] == 9
        assert args[2]["updated_by_name"] == "Admin"

    @pytest.mark.asyncio
    async def test_is_enabled(self):
        db = AsyncMock()
        with patch.object(QueueNoShowSettingRepository, "get_by_tenant", AsyncMock(return_value=None)):
            assert await QueueNoShowSettingService.is_enabled(db, 1) is False
        with patch.object(QueueNoShowSettingRepository, "get_by_tenant", AsyncMock(return_value=_setting_row(True))):
            assert await QueueNoShowSettingService.is_enabled(db, 1) is True
        with patch.object(QueueNoShowSettingRepository, "get_by_tenant", AsyncMock(return_value=_setting_row(False))):
            assert await QueueNoShowSettingService.is_enabled(db, 1) is False


class TestVoidTaskIfVisitorOffline:
    @pytest.mark.asyncio
    async def test_non_online_chat_channel_returns_false(self):
        db = AsyncMock()
        result = await QueueTaskService._void_task_if_visitor_offline(db, AsyncMock(), 1, _task(channel="call_center"))
        assert result is False

    @pytest.mark.asyncio
    async def test_setting_disabled_returns_false(self):
        db = AsyncMock()
        with patch.object(QueueNoShowSettingService, "is_enabled", AsyncMock(return_value=False)):
            result = await QueueTaskService._void_task_if_visitor_offline(db, AsyncMock(), 1, _task())
        assert result is False

    @pytest.mark.asyncio
    async def test_non_web_conversation_returns_false(self):
        db = AsyncMock()
        with patch.object(QueueNoShowSettingService, "is_enabled", AsyncMock(return_value=True)), patch.object(
            ConversationRepository, "get_by_id", AsyncMock(return_value=_conversation(channel_type="api"))
        ):
            result = await QueueTaskService._void_task_if_visitor_offline(db, AsyncMock(), 1, _task())
        assert result is False

    @pytest.mark.asyncio
    async def test_online_visitor_returns_false(self):
        db = AsyncMock()
        with patch.object(QueueNoShowSettingService, "is_enabled", AsyncMock(return_value=True)), patch.object(
            ConversationRepository, "get_by_id", AsyncMock(return_value=_conversation())
        ), patch.object(VisitorWebStatusService, "get_status", AsyncMock(return_value="online")):
            result = await QueueTaskService._void_task_if_visitor_offline(db, AsyncMock(), 1, _task())
        assert result is False

    @pytest.mark.asyncio
    async def test_offline_visitor_voids_task(self):
        db = AsyncMock()
        conv = _conversation()
        task = _task()
        with patch.object(QueueNoShowSettingService, "is_enabled", AsyncMock(return_value=True)), patch.object(
            ConversationRepository, "get_by_id", AsyncMock(return_value=conv)
        ), patch.object(VisitorWebStatusService, "get_status", AsyncMock(return_value="offline")), patch.object(
            QueueTaskRepository, "mark_terminal", AsyncMock()
        ) as mock_terminal, patch.object(
            ConversationRepository, "end_conversation", AsyncMock()
        ) as mock_end, patch.object(
            QueueTaskService, "_record_event", AsyncMock()
        ) as mock_event, patch.object(
            QueueTaskService, "_materialize_conversation_summary", AsyncMock()
        ), patch.object(
            QueueTaskService, "_emit_queue_change", AsyncMock()
        ), patch.object(
            QueueTaskService, "_emit_no_show_conversation_ended", AsyncMock()
        ):
            result = await QueueTaskService._void_task_if_visitor_offline(db, AsyncMock(), 1, task)

        assert result is True
        assert mock_terminal.call_args.args[2] == "canceled"
        assert mock_terminal.call_args.kwargs["reason"] == qs.QUEUE_NO_SHOW_REASON
        assert mock_event.call_args.args[2] == "canceled"
        assert mock_event.call_args.kwargs["reason"] == qs.QUEUE_NO_SHOW_REASON
        assert mock_end.call_args.args[2] == qs.QUEUE_NO_SHOW_ENDED_BY

    @pytest.mark.asyncio
    async def test_conversation_not_queued_returns_false(self):
        db = AsyncMock()
        with patch.object(QueueNoShowSettingService, "is_enabled", AsyncMock(return_value=True)), patch.object(
            ConversationRepository, "get_by_id", AsyncMock(return_value=_conversation(status="active"))
        ):
            result = await QueueTaskService._void_task_if_visitor_offline(db, AsyncMock(), 1, _task())
        assert result is False
