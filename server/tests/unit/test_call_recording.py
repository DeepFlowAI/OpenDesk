"""Unit tests for FlowKit recording artifact integration."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.call_record_service import CallRecordService


@pytest.mark.asyncio
async def test_save_recording_by_media_call_id() -> None:
    db = AsyncMock()
    row = SimpleNamespace(id=7, tenant_id=3, recording_status="none")
    order: list[str] = []

    async def lock(_db, record_id):
        order.append("lock")
        assert record_id == 7
        return row

    upsert = AsyncMock(side_effect=lambda *_a, **_k: order.append("upsert"))

    with patch(
        "app.services.call_record_service.CallRecordRepository.find_by_media_call_id",
        new=AsyncMock(return_value=row),
    ), patch(
        "app.services.call_record_service.CallRecordRepository.lock_by_id",
        new=lock,
    ), patch(
        "app.services.call_record_service.CallRecordingRepository.upsert",
        new=upsert,
    ), patch(
        "app.services.call_record_service.CallRecordingRepository.list_for_call",
        new=AsyncMock(return_value=[SimpleNamespace(status="completed")]),
    ), patch(
        "app.services.call_record_service.CallRecordRepository.update",
        new=AsyncMock(),
    ) as update, patch(
        "app.services.call_record_service.CallTrajectoryService.append_event",
        new=AsyncMock(),
    ):
        saved = await CallRecordService.save_recording(
            db,
            call_id="root-1",
            recording_id="rec-1",
            storage_key="recordings/rec-1.wav",
            source_event_id="flowkit:recording:rec-1",
            phase="bridged",
        )

    assert saved is True
    assert order[:2] == ["lock", "upsert"]
    assert upsert.await_args.args[1]["recording_id"] == "rec-1"
    assert upsert.await_args.args[1]["storage_key"] == "recordings/rec-1.wav"
    assert update.await_args.args[2] == {"recording_status": "completed"}


@pytest.mark.asyncio
async def test_save_recording_missing_cdr() -> None:
    with patch(
        "app.services.call_record_service.CallRecordRepository.find_by_media_call_id",
        new=AsyncMock(return_value=None),
    ):
        saved = await CallRecordService.save_recording(
            AsyncMock(),
            call_id="unknown",
            recording_id="rec-missing",
            storage_key=None,
            source_event_id="flowkit:recording:missing",
        )
    assert saved is False


@pytest.mark.asyncio
async def test_orchestrator_on_recording_completed_consumes_artifact_contract() -> None:
    from app.libs.telephony.base import CallEvent
    from app.services.call_center.orchestrator import CallCenterOrchestrator

    orchestrator = CallCenterOrchestrator(telephony=AsyncMock())
    with patch(
        "app.services.call_center.orchestrator.CallRecordService.save_recording",
        new=AsyncMock(return_value=True),
    ) as save, patch(
        "app.services.call_center.orchestrator.AsyncSessionLocal",
    ) as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await orchestrator._on_recording_completed(
            CallEvent(
                method="call.recording.completed",
                data={
                    "event_id": "flowkit:recording:rec-1",
                    "call_id": "root-1",
                    "recording_id": "rec-1",
                    "storage_key": "recordings/rec-1.wav",
                    "partial": True,
                    "phase": "bridged",
                    "duration_ms": 42_000,
                },
            )
        )

    save.assert_awaited_once()
    kwargs = save.await_args.kwargs
    assert kwargs["call_id"] == "root-1"
    assert kwargs["recording_id"] == "rec-1"
    assert kwargs["storage_key"] == "recordings/rec-1.wav"
    assert kwargs["status"] == "partial"


@pytest.mark.asyncio
async def test_recording_completed_after_call_ownership_release_is_persisted() -> None:
    from app.libs.telephony.base import CallEvent
    from app.services.call_center.orchestrator import CallCenterOrchestrator

    orchestrator = CallCenterOrchestrator(telephony=AsyncMock())
    orchestrator._owns_call = AsyncMock(return_value=False)
    with patch(
        "app.services.call_center.orchestrator.CallRecordService.save_recording",
        new=AsyncMock(return_value=True),
    ) as save, patch(
        "app.services.call_center.orchestrator.AsyncSessionLocal",
    ) as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await orchestrator._on_recording_completed(
            CallEvent(
                method="call.recording.completed",
                data={
                    "event_id": "flowkit:recording:rec-late",
                    "call_id": "ended-call",
                    "recording_id": "rec-late",
                    "storage_key": "recordings/rec-late.wav",
                },
            )
        )

    save.assert_awaited_once()
    orchestrator._owns_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_recording_completed_retries_after_deadlock(monkeypatch) -> None:
    from app.libs.telephony.base import CallEvent
    from app.services.call_center.orchestrator import CallCenterOrchestrator

    class _DeadlockDetectedError(Exception):
        sqlstate = "40P01"

    calls = {"n": 0}

    async def save(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _DeadlockDetectedError("deadlock detected")
        return True

    monkeypatch.setattr("app.db.retry.asyncio.sleep", AsyncMock())
    orchestrator = CallCenterOrchestrator(telephony=AsyncMock())
    with patch(
        "app.services.call_center.orchestrator.CallRecordService.save_recording",
        new=save,
    ), patch(
        "app.services.call_center.orchestrator.AsyncSessionLocal",
    ) as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await orchestrator._on_recording_completed(
            CallEvent(
                method="call.recording.completed",
                data={
                    "event_id": "flowkit:recording:rec-retry",
                    "call_id": "root-1",
                    "recording_id": "rec-retry",
                    "storage_key": "recordings/rec-retry.wav",
                    "phase": "bridged",
                    "partial": True,
                },
            )
        )

    assert calls["n"] == 2
