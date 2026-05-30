"""Unit tests for FlowKit recording → CDR integration."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.call_record_service import CallRecordService


def _make_row(
    *,
    call_id: str = "sip-leg-1",
    root_call_id: str | None = "root-1",
    recording_url: str | None = None,
    talk_duration_ms: int | None = 120_000,
    extra_metadata: dict | None = None,
):
    row = MagicMock()
    row.call_id = call_id
    row.root_call_id = root_call_id
    row.recording_url = recording_url
    row.talk_duration_ms = talk_duration_ms
    row.extra_metadata = extra_metadata or {}
    return row


@pytest.mark.asyncio
async def test_save_recording_by_call_id():
    db = AsyncMock()
    row = _make_row()
    with patch(
        "app.services.call_record_service.CallRecordRepository.find_by_media_call_id",
        new=AsyncMock(return_value=row),
    ), patch(
        "app.services.call_record_service.CallRecordRepository.update",
        new=AsyncMock(),
    ) as mock_update:
        saved = await CallRecordService.save_recording(
            db,
            call_id="sip-leg-1",
            url="https://bucket.oss.example/recordings/a.wav",
            partial=False,
            phase="ai",
        )
    assert saved is True
    patch_arg = mock_update.await_args.args[2]
    assert patch_arg["recording_url"] == "https://bucket.oss.example/recordings/a.wav"
    assert patch_arg["recording_duration_ms"] == 120_000
    assert patch_arg["extra_metadata"]["recording"]["phase"] == "ai"


@pytest.mark.asyncio
async def test_save_recording_by_root_call_id():
    db = AsyncMock()
    row = _make_row(call_id="sip-leg-1", root_call_id="root-1")
    with patch(
        "app.services.call_record_service.CallRecordRepository.find_by_media_call_id",
        new=AsyncMock(return_value=row),
    ), patch(
        "app.services.call_record_service.CallRecordRepository.update",
        new=AsyncMock(),
    ) as mock_update:
        saved = await CallRecordService.save_recording(
            db,
            call_id="root-1",
            url="https://bucket.oss.example/recordings/root_bridge.wav",
            phase="bridged",
        )
    assert saved is True
    assert mock_update.await_args.args[2]["extra_metadata"]["recording"]["phase"] == "bridged"


@pytest.mark.asyncio
async def test_save_recording_skips_ai_after_bridged():
    db = AsyncMock()
    row = _make_row(
        recording_url="https://bucket.oss.example/bridge.wav",
        extra_metadata={"recording": {"phase": "bridged", "partial": False}},
    )
    with patch(
        "app.services.call_record_service.CallRecordRepository.find_by_media_call_id",
        new=AsyncMock(return_value=row),
    ), patch(
        "app.services.call_record_service.CallRecordRepository.update",
        new=AsyncMock(),
    ) as mock_update:
        saved = await CallRecordService.save_recording(
            db,
            call_id="root-1",
            url="https://bucket.oss.example/ai.wav",
            phase="ai",
        )
    assert saved is False
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_save_recording_missing_cdr():
    db = AsyncMock()
    with patch(
        "app.services.call_record_service.CallRecordRepository.find_by_media_call_id",
        new=AsyncMock(return_value=None),
    ):
        saved = await CallRecordService.save_recording(
            db, call_id="unknown", url="https://example.com/x.wav",
        )
    assert saved is False


@pytest.mark.asyncio
async def test_orchestrator_on_recording_completed():
    from app.services.call_center.orchestrator import CallCenterOrchestrator
    from app.libs.telephony.base import CallEvent

    orch = CallCenterOrchestrator(telephony=AsyncMock())
    with patch(
        "app.services.call_center.orchestrator.CallRecordService.save_recording",
        new=AsyncMock(return_value=True),
    ) as mock_save, patch(
        "app.services.call_center.orchestrator.AsyncSessionLocal",
    ) as mock_session_local:
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await orch._on_recording_completed(
            CallEvent(
                method="call.recording.completed",
                data={
                    "call_id": "root-1",
                    "oss_url": "https://bucket.oss.example/r.wav",
                    "partial": True,
                    "phase": "bridged",
                    "header_patched": True,
                },
            )
        )
    mock_save.assert_awaited_once()
    kwargs = mock_save.await_args.kwargs
    assert kwargs["call_id"] == "root-1"
    assert kwargs["url"] == "https://bucket.oss.example/r.wav"
    assert kwargs["partial"] is True
    assert kwargs["phase"] == "bridged"
    assert kwargs["header_patched"] is True
