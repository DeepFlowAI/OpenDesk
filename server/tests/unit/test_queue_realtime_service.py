from unittest.mock import AsyncMock

import pytest

from app.services import queue_realtime_service as qrs
from app.services.queue_realtime_service import QueueRealtimeService


@pytest.mark.asyncio
async def test_emit_queue_updated_broadcasts_to_workspace_rooms(monkeypatch):
    transport = AsyncMock()
    monkeypatch.setattr(qrs, "get_realtime_transport", lambda: transport)

    await QueueRealtimeService.emit_queue_updated(
        7,
        action="assigned",
        task_id=11,
        queue_type="employee_group",
        queue_id=3,
    )

    assert transport.emit.await_count == 2
    count_call, list_call = transport.emit.await_args_list
    count_event, payload = count_call.args
    list_event, list_payload = list_call.args
    assert count_event == "queue_count_updated"
    assert list_event == "queue_list_updated"
    assert list_payload == payload
    assert payload["action"] == "assigned"
    assert payload["task_id"] == 11
    assert payload["queue_type"] == "employee_group"
    assert payload["queue_id"] == 3
    assert "updated_at" in payload
    assert count_call.kwargs == {
        "room": "workspace:7:queue:count",
        "namespace": "/chat",
    }
    assert list_call.kwargs == {
        "room": "workspace:7:queue:list",
        "namespace": "/chat",
    }
