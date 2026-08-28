"""
Unit tests for the bulk SMS send engine: scheduled start, batch claim,
channel submit, auto-pause, completion, stale sweep and receipt linkage.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.libs.sms.base import SmsSendResult
from app.models.sms_bulk_task import SmsBulkTask, SmsBulkTarget
from app.services.sms_bulk_send_service import SmsBulkSendService

NOW = datetime.now(timezone.utc)


class _SessionTracker:
    """Tracks open/close of AsyncSessionLocal so tests can prove the channel
    call happens while no DB session is held."""

    def __init__(self):
        self.open_count = 0
        self.max_open_during_channel = 0

    def new_session(self):
        tracker = self

        class _Session:
            def __init__(self):
                self.commit = AsyncMock()

            async def __aenter__(self):
                tracker.open_count += 1
                return self

            async def __aexit__(self, *exc):
                tracker.open_count -= 1
                return False

        return _Session()


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _patch_session_local(tracker: _SessionTracker):
    patch(
        "app.services.sms_bulk_send_service.AsyncSessionLocal",
        side_effect=lambda: tracker.new_session(),
    ).start()


def _patch_repos():
    task_repo = patch("app.services.sms_bulk_send_service.SmsBulkTaskRepository").start()
    target_repo = patch("app.services.sms_bulk_send_service.SmsBulkTargetRepository").start()
    record_repo = patch("app.services.sms_bulk_send_service.SmsSendRecordRepository").start()
    for name in ("list_due_scheduled", "start_scheduled_task", "list_sending_task_ids", "complete_if_finished", "get_by_id", "get_status", "update"):
        setattr(task_repo, name, AsyncMock())
    for name in (
        "sweep_stale_claimed",
        "claim_pending_targets",
        "release_task_claimed",
        "mark_submitted",
        "mark_failed",
        "bind_send_record",
    ):
        setattr(target_repo, name, AsyncMock())
    record_repo.create = AsyncMock()
    record_repo.update_send_result = AsyncMock()
    task_repo.list_due_scheduled.return_value = []
    task_repo.list_sending_task_ids.return_value = []
    task_repo.get_status.return_value = "sending"
    target_repo.sweep_stale_claimed.return_value = 0
    target_repo.claim_pending_targets.return_value = []
    task_repo.complete_if_finished.return_value = False
    return SimpleNamespace(task=task_repo, target=target_repo, record=record_repo)


def _task() -> SmsBulkTask:
    return SmsBulkTask(
        id=1,
        tenant_id=1,
        name="八月套餐到期提醒",
        status="sending",
        template_id=10,
        template_name="预约回访提醒",
        template_type="notify",
        sign_name="深流客服",
        provider_sign_name="深流客服",
        body="尊敬的{name}，您预约的回访时间为{time}。",
        variables=[{"key": "name", "label": "客户姓名", "required": True}],
        provider="aliyun",
        provider_template_code="SMS_123456",
        send_type="immediate",
        created_by_id=10,
        updated_by_id=10,
    )


def _target(target_id: int, phone: str) -> SmsBulkTarget:
    return SmsBulkTarget(
        id=target_id,
        tenant_id=1,
        task_id=1,
        phone=phone,
        variable_values={"name": "王先生"},
        status="sending",
        claimed_at=NOW,
    )


def _client(success: bool = True, biz_id: str = "BIZ-1"):
    client = SimpleNamespace()
    client.send_sms = AsyncMock(
        return_value=SmsSendResult(success=success, biz_id=biz_id if success else None,
                                   error_code=None if success else "isv.BUSINESS_LIMIT_CONTROL",
                                   error_message=None if success else "触发流控")
    )
    return client


class TestRunTick:
    @pytest.mark.asyncio
    async def test_due_scheduled_task_starts(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_due_scheduled.return_value = [7]
        repos.task.start_scheduled_task.return_value = True

        stats = await SmsBulkSendService.run_tick()

        assert stats["started"] == 1
        repos.task.start_scheduled_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_claimed_targets_swept(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.target.sweep_stale_claimed.return_value = 3

        stats = await SmsBulkSendService.run_tick()

        assert stats["swept"] == 3
        stale_before = repos.target.sweep_stale_claimed.call_args.kwargs["stale_before"]
        assert stale_before < NOW - timedelta(seconds=200)

    @pytest.mark.asyncio
    async def test_send_success_marks_submitted(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_sending_task_ids.return_value = [1]
        repos.task.get_by_id.return_value = _task()
        repos.target.claim_pending_targets.return_value = [_target(11, "13800138000")]
        repos.record.create.side_effect = lambda db, payload: SimpleNamespace(id=99)
        patch("app.services.sms_bulk_send_service.get_sms_client", return_value=_client(True)).start()

        stats = await SmsBulkSendService.run_tick()

        assert stats["sent"] == 1
        record_payload = repos.record.create.call_args.args[1]
        assert record_payload["source"] == "bulk"
        assert record_payload["bulk_task_id"] == 1
        assert record_payload["employee_id"] == 10
        assert record_payload["body_snapshot"] == "尊敬的王先生，您预约的回访时间为{time}。"
        repos.target.bind_send_record.assert_awaited_once()
        repos.target.mark_submitted.assert_awaited_once()
        repos.target.mark_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_call_runs_without_db_session(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_sending_task_ids.return_value = [1]
        repos.task.get_by_id.return_value = _task()
        repos.target.claim_pending_targets.return_value = [_target(11, "13800138000")]
        repos.record.create.side_effect = lambda db, payload: SimpleNamespace(id=99)

        client = _client(True)
        original_send = client.send_sms

        async def send_and_observe(**kwargs):
            tracker.max_open_during_channel = tracker.open_count
            return await original_send(**kwargs)

        client.send_sms = send_and_observe
        patch("app.services.sms_bulk_send_service.get_sms_client", return_value=client).start()

        await SmsBulkSendService.run_tick()

        assert tracker.max_open_during_channel == 0

    @pytest.mark.asyncio
    async def test_send_failure_marks_failed(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_sending_task_ids.return_value = [1]
        repos.task.get_by_id.return_value = _task()
        repos.target.claim_pending_targets.return_value = [_target(11, "13800138000")]
        repos.record.create.side_effect = lambda db, payload: SimpleNamespace(id=99)
        patch("app.services.sms_bulk_send_service.get_sms_client", return_value=_client(False)).start()

        stats = await SmsBulkSendService.run_tick()

        assert stats["failed"] == 1
        repos.target.mark_failed.assert_awaited_once()
        fail_kwargs = repos.target.mark_failed.call_args.kwargs
        assert "isv.BUSINESS_LIMIT_CONTROL" in fail_kwargs["fail_reason"]
        repos.target.mark_submitted.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_exception_marks_failed(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_sending_task_ids.return_value = [1]
        repos.task.get_by_id.return_value = _task()
        repos.target.claim_pending_targets.return_value = [_target(11, "13800138000")]
        repos.record.create.side_effect = lambda db, payload: SimpleNamespace(id=99)
        client = SimpleNamespace()
        client.send_sms = AsyncMock(side_effect=RuntimeError("connection reset"))
        patch("app.services.sms_bulk_send_service.get_sms_client", return_value=client).start()

        stats = await SmsBulkSendService.run_tick()

        assert stats["failed"] == 1
        fail_kwargs = repos.target.mark_failed.call_args.kwargs
        assert "INTERNAL" in fail_kwargs["fail_reason"]

    @pytest.mark.asyncio
    async def test_consecutive_failures_auto_pause(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_sending_task_ids.return_value = [1]
        repos.task.get_by_id.return_value = _task()
        repos.target.claim_pending_targets.return_value = [
            _target(11 + i, f"138001380{i:02d}") for i in range(5)
        ]
        repos.record.create.side_effect = lambda db, payload: SimpleNamespace(id=99)
        patch("app.services.sms_bulk_send_service.get_sms_client", return_value=_client(False)).start()
        patch(
            "app.services.sms_bulk_send_service.settings.SMS_BULK_SEND_AUTO_PAUSE_CONSECUTIVE_FAILURES", 3
        ).start()

        stats = await SmsBulkSendService.run_tick()

        assert stats["auto_paused"] == 1
        assert stats["failed"] == 3  # stops at the threshold, remaining targets untouched
        repos.target.release_task_claimed.assert_awaited_once()
        update_payload = repos.task.update.call_args.args[2]
        assert update_payload["status"] == "paused"
        assert update_payload["pause_reason"] == "channel_error"

    @pytest.mark.asyncio
    async def test_task_completes_when_no_open_targets(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_sending_task_ids.return_value = [1]
        repos.task.get_by_id.return_value = _task()
        repos.target.claim_pending_targets.return_value = []
        repos.task.complete_if_finished.return_value = True

        stats = await SmsBulkSendService.run_tick()

        assert stats["completed"] == 1

    @pytest.mark.asyncio
    async def test_channel_timeout_marks_failed(self):
        import asyncio

        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_sending_task_ids.return_value = [1]
        repos.task.get_by_id.return_value = _task()
        repos.target.claim_pending_targets.return_value = [_target(11, "13800138000")]
        repos.record.create.side_effect = lambda db, payload: SimpleNamespace(id=99)

        async def hang(**kwargs):
            await asyncio.sleep(10)

        client = SimpleNamespace()
        client.send_sms = hang
        patch("app.services.sms_bulk_send_service.get_sms_client", return_value=client).start()
        patch("app.services.sms_bulk_send_service.settings.SMS_BULK_SEND_TIMEOUT_SECONDS", 0.01).start()

        stats = await SmsBulkSendService.run_tick()

        assert stats["failed"] == 1
        fail_kwargs = repos.target.mark_failed.call_args.kwargs
        assert "TIMEOUT" in fail_kwargs["fail_reason"]

    @pytest.mark.asyncio
    async def test_mid_batch_pause_stops_and_releases_claim(self):
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        repos.task.list_sending_task_ids.return_value = [1]
        repos.task.get_by_id.return_value = _task()
        repos.target.claim_pending_targets.return_value = [
            _target(11 + i, f"138001380{i:02d}") for i in range(3)
        ]
        # Task was paused between claim and first send.
        repos.task.get_status.return_value = "paused"
        patch("app.services.sms_bulk_send_service.get_sms_client", return_value=_client(True)).start()

        stats = await SmsBulkSendService.run_tick()

        assert stats["sent"] == 0
        assert stats["failed"] == 0
        repos.record.create.assert_not_called()
        repos.target.release_task_claimed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_sweep_floor_covers_worst_case_batch(self):
        """claimed rows must outlive batch_size * per-call timeout."""
        tracker = _SessionTracker()
        _patch_session_local(tracker)
        repos = _patch_repos()
        patch("app.services.sms_bulk_send_service.settings.SMS_BULK_SEND_CLAIM_STALE_SECONDS", 60).start()
        patch("app.services.sms_bulk_send_service.settings.SMS_BULK_SEND_BATCH_SIZE", 50).start()
        patch("app.services.sms_bulk_send_service.settings.SMS_BULK_SEND_TIMEOUT_SECONDS", 30).start()

        await SmsBulkSendService.run_tick()

        stale_before = repos.target.sweep_stale_claimed.call_args.kwargs["stale_before"]
        # floor = 50 * 30 + 60 = 1560s, overriding the configured 60s
        assert stale_before < NOW - timedelta(seconds=1500)


class TestClaimPendingTargets:
    @pytest.mark.asyncio
    async def test_claim_uses_for_update_skip_locked(self):
        """Concurrent workers must never receive the same pending row."""
        from unittest.mock import MagicMock

        from app.repositories.sms_bulk_task_repository import SmsBulkTargetRepository

        target = _target(11, "13800138000")
        target.status = "pending"
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [target]
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        claimed = await SmsBulkTargetRepository.claim_pending_targets(db, task_id=1, limit=10, now=NOW)

        assert claimed == [target]
        assert target.status == "sending"
        assert target.claimed_at == NOW
        db.commit.assert_awaited_once()
        stmt = db.execute.await_args.args[0]
        assert stmt._for_update_arg is not None
        assert stmt._for_update_arg.skip_locked is True

    @pytest.mark.asyncio
    async def test_claim_empty_result_skips_commit(self):
        from unittest.mock import MagicMock

        from app.repositories.sms_bulk_task_repository import SmsBulkTargetRepository

        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        claimed = await SmsBulkTargetRepository.claim_pending_targets(db, task_id=1, limit=10, now=NOW)

        assert claimed == []
        db.commit.assert_not_awaited()
