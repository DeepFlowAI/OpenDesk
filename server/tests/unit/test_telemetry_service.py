from types import SimpleNamespace

import pytest

from app.schemas.telemetry import TelemetryBatchRequest
from app.services.telemetry_service import TelemetryService


def _batch(events):
    return TelemetryBatchRequest(
        common={
            "session_id": "sess_1",
            "device_id": "dev_1",
            "url": "https://example.com/chat",
            "sdk_name": "opendesk-web",
        },
        events=events,
    )


def _channel():
    return SimpleNamespace(id=3, channel_key="od_ck_test", tenant_id=9)


@pytest.mark.asyncio
async def test_ingest_logs_flattened_frontend_event(caplog):
    body = _batch([
        {
            "name": "message_send_succeeded",
            "ts": 1760000000000,
            "request_id": "req_1",
            "props": {
                "target": "conversation",
                "ignored-key": "bad",
            },
            "metrics": {
                "duration_ms": 42,
            },
        },
    ])

    result = await TelemetryService.ingest(channel=_channel(), body=body)

    assert result.accepted == 1
    assert result.dropped == 0

    record = next(item for item in caplog.records if item.name == "app.frontend.event")
    assert record.event == "message_send_succeeded"
    assert record.channel_key == "od_ck_test"
    assert record.tenant_id == "9"
    assert record.request_id == "req_1"
    assert record.props_target == "conversation"
    assert record.metrics_duration_ms == "42"
    assert not hasattr(record, "props_ignored-key")


@pytest.mark.asyncio
async def test_ingest_app_logs_staff_auth_event(caplog):
    body = _batch([
        {
            "name": "auth_session_cleared",
            "ts": 1760000000000,
            "level": "warn",
            "props": {
                "trigger": "refresh_after_api_401",
            },
        },
    ])

    result = await TelemetryService.ingest_app(
        body=body,
        user_payload={"user_id": 7, "tenant_id": 2},
    )

    assert result.accepted == 1
    assert result.dropped == 0

    record = next(item for item in caplog.records if item.name == "app.frontend.event")
    assert record.event == "auth_session_cleared"
    assert record.source == "opendesk-web"
    assert record.tenant_id == "2"
    assert record.user_id == "7"
    assert record.props_trigger == "refresh_after_api_401"


@pytest.mark.asyncio
async def test_ingest_respects_telemetry_kill_switch(monkeypatch, caplog):
    monkeypatch.setattr("app.services.telemetry_service.settings.TELEMETRY_ENABLED", False)

    result = await TelemetryService.ingest(
        channel=_channel(),
        body=_batch([{"name": "sdk_init", "ts": 1760000000000}]),
    )

    assert result.accepted == 0
    assert result.dropped == 1
    assert not [item for item in caplog.records if item.name == "app.frontend.event"]
