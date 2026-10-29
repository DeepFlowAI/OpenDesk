"""History-initiated bot replacement and shared eligibility rules."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import BusinessError
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_service import ConversationService
from app.services.offline_bot_conversation_service import OfflineBotConversationService
from app.services.visitor_web_status_service import VisitorWebStatusService


def conversation(id=1, status="bot", agent_id=None):
    return SimpleNamespace(
        id=id, public_id=f"cv_{id}", tenant_id=1, visitor_id=2, channel_id=3,
        group_id=4, agent_id=agent_id, status=status, ended_at=None, ended_by=None,
        started_at=datetime.now(timezone.utc),
        channel=SimpleNamespace(id=3, tenant_id=1, channel_type="web"),
        visitor=SimpleNamespace(external_id="visitor"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status,agent_id,count,web,expected", [
    ("bot", None, 1, "offline", "eligible"),
    ("bot", None, 1, "online", "online"),
    ("bot", None, 1, "unknown", "status_unavailable"),
    ("bot", None, 2, "offline", "multiple_active"),
    ("bot", 9, 1, "offline", "not_unassigned_bot"),
    ("handoff_pending", None, 1, "offline", "not_unassigned_bot"),
    ("queued", None, 1, "offline", "not_unassigned_bot"),
    ("active", 9, 1, "offline", "not_unassigned_bot"),
])
async def test_eligibility(monkeypatch, status, agent_id, count, web, expected):
    monkeypatch.setattr(ConversationRepository, "count_active_visitor_conversations", AsyncMock(return_value=count))
    presence = AsyncMock(return_value=web)
    monkeypatch.setattr(VisitorWebStatusService, "get_status", presence)
    result = await OfflineBotConversationService.check(
        AsyncMock(), AsyncMock(), conversation(status=status, agent_id=agent_id), source="history:7",
    )
    assert result == expected
    if count != 1 or status != "bot" or agent_id:
        presence.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["channel", "visitor", "redis"])
async def test_unknown_presence_never_eligible(monkeypatch, missing):
    bot = conversation()
    if missing != "redis":
        setattr(bot, missing, None)
    monkeypatch.setattr(ConversationRepository, "count_active_visitor_conversations", AsyncMock(return_value=1))
    monkeypatch.setattr(VisitorWebStatusService, "get_status", AsyncMock(side_effect=RuntimeError("unavailable")))
    assert await OfflineBotConversationService.check(AsyncMock(), AsyncMock(), bot, source="history:7") != "eligible"


@pytest.fixture
def history_setup(monkeypatch):
    history, bot, new = conversation(7, "closed", 8), conversation(9), conversation(10, "active", 8)
    principal = EffectivePrincipal(user_id=8, tenant_id=1, permissions=["chat.workspace.use"], group_ids=[])
    db, events = AsyncMock(), []
    db.commit.side_effect = lambda: events.append("commit")
    db.rollback.side_effect = lambda: events.append("rollback")
    monkeypatch.setattr("app.services.conversation_service.EmployeeRepository.get_by_id", AsyncMock(return_value=SimpleNamespace(max_concurrent=10)))
    monkeypatch.setattr("app.services.conversation_service.ChannelRepository.get_by_id", AsyncMock(return_value=history.channel))
    monkeypatch.setattr("app.services.conversation_service.AgentStatusService.get_status", AsyncMock(return_value={"status": "online"}))
    increment = AsyncMock(side_effect=lambda *a: events.append("count"))
    monkeypatch.setattr("app.services.conversation_service.AgentStatusService.increment_count", increment)
    lock = AsyncMock(side_effect=lambda *a, **k: events.append("lock"))
    monkeypatch.setattr(ConversationRepository, "lock_visitor_conversations", lock)
    monkeypatch.setattr(ConversationRepository, "get_by_id", AsyncMock(side_effect=lambda db, id: history if id == 7 else new))
    active = AsyncMock(return_value=bot)
    monkeypatch.setattr(ConversationRepository, "get_active_visitor_conversation", active)
    monkeypatch.setattr(ConversationRepository, "count_active_visitor_conversations", AsyncMock(return_value=1))
    monkeypatch.setattr(VisitorWebStatusService, "get_status", AsyncMock(return_value="offline"))
    async def close(db, item, ended_by, *, commit):
        assert not commit
        events.append("close")
        item.status, item.ended_by = "closed", ended_by
    end = AsyncMock(side_effect=close)
    monkeypatch.setattr(ConversationRepository, "end_conversation", end)
    create = AsyncMock(return_value=new)
    monkeypatch.setattr(ConversationRepository, "create", create)
    message = AsyncMock(return_value=SimpleNamespace(content_type="system", content="客服发起了新会话", created_at=new.started_at))
    monkeypatch.setattr(MessageRepository, "create", message)
    preview = AsyncMock()
    monkeypatch.setattr(ConversationRepository, "update_last_message", preview)
    initialize = AsyncMock()
    monkeypatch.setattr("app.services.visitor_timeout_close_service.VisitorTimeoutCloseService.initialize_for_conversation", initialize)
    emit = AsyncMock(side_effect=lambda *a, **k: events.append("notify"))
    monkeypatch.setattr(OfflineBotConversationService, "emit_closed", emit)
    monkeypatch.setattr("app.services.conversation_realtime_service.ConversationRealtimeService.emit_conversation_list_updated", AsyncMock())
    monkeypatch.setattr(ConversationService, "_workspace_conversation_item", Mock(side_effect=lambda c, **k: {"id": c.id}))
    return SimpleNamespace(**locals())


@pytest.mark.asyncio
async def test_closes_and_creates_in_one_commit(history_setup):
    s = history_setup
    result = await ConversationService.start_new_from_history(s.db, AsyncMock(), 7, s.principal)
    assert result == {"conversation": {"id": 10}, "is_new": True, "already_active": False}
    assert s.bot.status == "closed" and s.bot.ended_by == "history_start"
    assert s.history.status == "closed" and s.history.ended_by is None
    s.active.assert_awaited_once_with(s.db, tenant_id=1, visitor_id=2, channel_id=3, for_update=True)
    for method in (s.create, s.message, s.preview, s.initialize):
        assert method.await_args.kwargs["commit"] is False
    assert s.message.await_args.args[1]["metadata_"]["source_conversation_id"] == 7
    assert s.events == ["lock", "close", "commit", "count", "notify"]
    s.db.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["create", "message", "preview", "initialize", "commit"])
async def test_failure_rolls_back_without_notifications(history_setup, failure):
    s = history_setup
    method = s.db.commit if failure == "commit" else getattr(s, failure)
    method.side_effect = RuntimeError("database failed")
    with pytest.raises(RuntimeError):
        await ConversationService.start_new_from_history(s.db, AsyncMock(), 7, s.principal)
    s.db.rollback.assert_awaited_once()
    s.increment.assert_not_awaited()
    s.emit.assert_not_awaited()
    if failure != "commit":
        s.db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("web,code", [("online", "BOT_VISITOR_ONLINE"), ("unknown", "VISITOR_STATUS_UNAVAILABLE")])
async def test_conflict_has_specific_code(history_setup, monkeypatch, web, code):
    s = history_setup
    monkeypatch.setattr(VisitorWebStatusService, "get_status", AsyncMock(return_value=web))
    with pytest.raises(BusinessError) as exc:
        await ConversationService.start_new_from_history(s.db, AsyncMock(), 7, s.principal)
    assert exc.value.code == code
    s.end.assert_not_awaited()
    s.create.assert_not_awaited()
    s.db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_reuses_human_assignment_seen_after_lock(history_setup):
    s = history_setup
    s.active.return_value = s.new
    result = await ConversationService.start_new_from_history(s.db, AsyncMock(), 7, s.principal)
    assert result["already_active"] is True
    s.end.assert_not_awaited()
    s.create.assert_not_awaited()
    s.increment.assert_not_awaited()
    assert s.events == ["lock", "rollback"]


@pytest.mark.asyncio
async def test_post_commit_count_failure_still_returns_created(history_setup):
    s = history_setup
    s.increment.side_effect = RuntimeError("redis failed")
    result = await ConversationService.start_new_from_history(s.db, AsyncMock(), 7, s.principal)
    assert result["is_new"] is True
    s.db.rollback.assert_not_awaited()
    s.emit.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_history_requests_create_only_once(history_setup):
    import asyncio

    s = history_setup
    gate = asyncio.Lock()
    committed = None
    async def acquire(db, **kwargs):
        await gate.acquire()
    async def active(db, **kwargs):
        return committed or s.bot
    async def create(*args, **kwargs):
        await asyncio.sleep(0)
        return s.new
    async def commit():
        nonlocal committed
        committed = s.new
        gate.release()
    async def rollback():
        gate.release()
    s.lock.side_effect = acquire
    s.active.side_effect = active
    s.create.side_effect = create
    db1, db2 = AsyncMock(), AsyncMock()
    for db in (db1, db2):
        db.commit.side_effect = commit
        db.rollback.side_effect = rollback
    first, second = await asyncio.gather(
        ConversationService.start_new_from_history(db1, AsyncMock(), 7, s.principal),
        ConversationService.start_new_from_history(db2, AsyncMock(), 7, s.principal),
    )
    assert first["is_new"] is True and second["already_active"] is True
    s.create.assert_awaited_once()
    s.end.assert_awaited_once()
    s.increment.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,agent_id,count", [("bot", None, 2), ("handoff_pending", None, 1), ("queued", None, 1), ("active", 99, 1)])
async def test_other_active_states_are_not_closed(history_setup, monkeypatch, status, agent_id, count):
    s = history_setup
    s.bot.status, s.bot.agent_id = status, agent_id
    monkeypatch.setattr(ConversationRepository, "count_active_visitor_conversations", AsyncMock(return_value=count))
    with pytest.raises(BusinessError) as exc:
        await ConversationService.start_new_from_history(s.db, AsyncMock(), 7, s.principal)
    assert exc.value.code == "ACTIVE_CONVERSATION_EXISTS"
    s.end.assert_not_awaited()
    s.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_cross_tenant_rejected_before_cleanup(history_setup):
    s = history_setup
    s.history.tenant_id = 55
    with pytest.raises(BusinessError):
        await ConversationService.start_new_from_history(s.db, AsyncMock(), 7, s.principal)
    s.lock.assert_not_awaited()
    s.end.assert_not_awaited()


@pytest.mark.asyncio
async def test_locked_query_rechecks_replacement_after_wait():
    replacement = conversation(10, "active", 8)
    empty = Mock()
    empty.scalars.return_value.all.return_value = []
    found = Mock()
    found.scalars.return_value.all.return_value = [replacement]
    db = AsyncMock()
    db.execute.side_effect = [empty, found]
    result = await ConversationRepository.get_active_visitor_conversation(
        db, tenant_id=1, visitor_id=2, channel_id=3, for_update=True,
    )
    assert result is replacement
    assert db.execute.await_count == 2
    statement = db.execute.await_args.args[0]
    assert "FOR UPDATE" in str(statement)
    assert statement.get_execution_options()["populate_existing"] is True


@pytest.mark.asyncio
async def test_repository_writes_do_not_commit_when_owned_by_service():
    db = AsyncMock()
    db.add = Mock()
    bot = conversation()
    await ConversationRepository.end_conversation(db, bot, "history_start", commit=False)
    await ConversationRepository.create(db, {
        "public_id": "cv_test", "share_code": "CV-TEST", "tenant_id": 1,
        "visitor_id": 2, "channel_id": 3, "agent_id": 8, "status": "active",
    }, commit=False)
    await MessageRepository.create(db, {
        "tenant_id": 1, "conversation_id": 10, "sender_type": "system",
        "content_type": "system", "content": "New conversation",
    }, commit=False)
    await ConversationRepository.update_last_message(db, 10, "New conversation", bot.started_at, commit=False)
    db.commit.assert_not_awaited()
    assert bot.status == "closed" and bot.ended_by == "history_start"
    assert bot.ended_at.tzinfo is timezone.utc


@pytest.mark.asyncio
async def test_no_active_conversation_creates_without_cleanup(history_setup):
    s = history_setup
    s.active.return_value = None
    result = await ConversationService.start_new_from_history(s.db, AsyncMock(), 7, s.principal)
    assert result["is_new"] is True
    s.end.assert_not_awaited()
    s.emit.assert_not_awaited()
    s.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_ended_notifications_include_reason_and_both_namespaces(monkeypatch):
    rt = SimpleNamespace(emit=AsyncMock())
    monkeypatch.setattr("app.libs.realtime.get_realtime_transport", lambda: rt)
    await OfflineBotConversationService.emit_closed(conversation(), ended_by="history_start")
    ended_calls = [call for call in rt.emit.await_args_list if call.args[0] == "conversation_ended"]
    assert [call.kwargs["namespace"] for call in ended_calls] == ["/chat", "/visitor"]
    assert all(call.args[1]["ended_by"] == "history_start" for call in ended_calls)


@pytest.mark.asyncio
async def test_notification_failure_does_not_escape(monkeypatch):
    rt = SimpleNamespace(emit=AsyncMock(side_effect=RuntimeError("disconnected")))
    monkeypatch.setattr("app.libs.realtime.get_realtime_transport", lambda: rt)
    await OfflineBotConversationService.emit_closed(conversation(), ended_by="history_start")
