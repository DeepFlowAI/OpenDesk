"""
Unit tests for agent call-resource reset
(``CcAgentStatusService.reset_call_resource_managed``).

Key discipline (CLAUDE.md §8): no request-scoped / managed DB session may stay
open while awaiting telephony ``call_hangup``. Cleanup coverage for every stuck
call hideout lives in ``test_reset_call_state.py``.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.cc_agent_status_service as status_mod
from app.services.cc_agent_status_service import CcAgentStatusService


class SessionTracker:
    active = False
    opens = 0
    closes = 0


class FakeSessionContext:
    async def __aenter__(self):
        assert SessionTracker.active is False
        SessionTracker.active = True
        SessionTracker.opens += 1
        return SimpleNamespace(commit=AsyncMock())

    async def __aexit__(self, *_exc_info):
        SessionTracker.active = False
        SessionTracker.closes += 1


def _reset_tracker() -> None:
    SessionTracker.active = False
    SessionTracker.opens = 0
    SessionTracker.closes = 0


@pytest.mark.asyncio
async def test_managed_reset_closes_db_session_while_telephony_hangup(monkeypatch):
    """No DB session may be active while hangup is in flight."""
    _reset_tracker()
    hangup_active_states: list[bool] = []

    class _Tel:
        async def call_hangup(self, call_id: str, reason: str | None = None) -> None:
            hangup_active_states.append(SessionTracker.active)
            assert call_id == "leg-1"
            assert reason == "manual_reset"

    monkeypatch.setattr(status_mod, "AsyncSessionLocal", lambda: FakeSessionContext())

    get_active = AsyncMock(return_value={"webrtc_call_id": "leg-1"})
    close_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.agent_webrtc_session_service.AgentWebRTCSessionService.get_active",
        get_active,
    )
    monkeypatch.setattr(
        "app.services.agent_webrtc_session_service.AgentWebRTCSessionService.close",
        close_mock,
    )
    monkeypatch.setattr(
        status_mod.CallRecordRepository,
        "get_latest_active_for_agent",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        status_mod.CcAgentResourceService,
        "force_release",
        AsyncMock(),
    )
    monkeypatch.setattr(
        CcAgentStatusService,
        "get_for_employee",
        AsyncMock(return_value={"status": "ready", "employee_id": 42}),
    )

    async def _fake_clear(tenant_id: int, employee_id: int) -> None:
        return None

    monkeypatch.setattr(
        "app.services.call_center.call_control_service._clear_legs",
        _fake_clear,
    )

    result = await CcAgentStatusService.reset_call_resource_managed(
        _Tel(),
        tenant_id=8,
        employee_id=42,
        r=SimpleNamespace(),
    )

    assert result["status"] == "ready"
    assert hangup_active_states == [False]
    assert SessionTracker.opens >= 2
    assert SessionTracker.opens == SessionTracker.closes
    close_mock.assert_awaited()


@pytest.mark.asyncio
async def test_managed_reset_completes_when_hangup_raises(monkeypatch):
    """Telephony failure must not abort the reset — status still clears."""
    _reset_tracker()
    hangup_active_states: list[bool] = []

    class _Tel:
        async def call_hangup(self, call_id: str, reason: str | None = None) -> None:
            hangup_active_states.append(SessionTracker.active)
            raise RuntimeError("kernel unavailable")

    monkeypatch.setattr(status_mod, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(
        "app.services.agent_webrtc_session_service.AgentWebRTCSessionService.get_active",
        AsyncMock(return_value={"webrtc_call_id": "leg-stuck"}),
    )
    close_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.agent_webrtc_session_service.AgentWebRTCSessionService.close",
        close_mock,
    )

    active_seq = [
        SimpleNamespace(call_id="c1"),
        None,
    ]

    async def _get_latest(_db, _tenant_id, _employee_id):
        return active_seq.pop(0)

    mark_mock = AsyncMock()
    monkeypatch.setattr(
        status_mod.CallRecordRepository,
        "get_latest_active_for_agent",
        _get_latest,
    )
    monkeypatch.setattr(
        "app.services.call_record_service.CallRecordService.mark_completed",
        mark_mock,
    )

    force_mock = AsyncMock()
    monkeypatch.setattr(
        status_mod.CcAgentResourceService,
        "force_release",
        force_mock,
    )
    monkeypatch.setattr(
        CcAgentStatusService,
        "get_for_employee",
        AsyncMock(
            return_value={
                "status": "ready",
                "employee_id": 42,
                "resource_state": "idle",
                "last_release_reason": "manual_reset",
            }
        ),
    )

    cleared: list[tuple[int, int]] = []

    async def _fake_clear(tenant_id: int, employee_id: int) -> None:
        cleared.append((tenant_id, employee_id))

    monkeypatch.setattr(
        "app.services.call_center.call_control_service._clear_legs",
        _fake_clear,
    )

    result = await CcAgentStatusService.reset_call_resource_managed(
        _Tel(),
        tenant_id=8,
        employee_id=42,
        r=SimpleNamespace(),
    )

    assert hangup_active_states == [False]
    assert result["status"] == "ready"
    assert result.get("last_release_reason") == "manual_reset"
    close_mock.assert_awaited()
    assert mark_mock.await_count == 1
    assert (8, 42) in cleared
    force_mock.assert_awaited()
    assert SessionTracker.opens == SessionTracker.closes
