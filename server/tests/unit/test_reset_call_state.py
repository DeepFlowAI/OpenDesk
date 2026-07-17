"""
Unit test for the one-click "reset call state" escape hatch
(POST /agent-status/me/reset). It must clean every place a stuck call can
hide — WebRTC session + kernel leg, all active call records, in-memory
conference/consult legs, and the Redis call resource — without raising.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_reset_call_state_cleans_all_sources(monkeypatch):
    from app.routers.v1 import call_center as cc_router
    import app.services.agent_webrtc_session_service as sess_mod
    import app.services.call_center.call_control_service as ccs_mod

    hangups: list[tuple] = []

    class _Tel:
        async def call_hangup(self, call_id, reason=None):
            hangups.append((call_id, reason))

    monkeypatch.setattr(cc_router, "get_telephony_client", lambda: _Tel())

    monkeypatch.setattr(
        sess_mod.AgentWebRTCSessionService,
        "get_active",
        AsyncMock(return_value={"webrtc_call_id": "leg-1"}),
    )
    close_mock = AsyncMock()
    monkeypatch.setattr(sess_mod.AgentWebRTCSessionService, "close", close_mock)

    # Two lingering active CDRs, then none.
    active_seq = [SimpleNamespace(call_id="c1"), SimpleNamespace(call_id="c2"), None]

    async def _get_latest(_db, _tenant_id, _employee_id):
        return active_seq.pop(0)

    monkeypatch.setattr(
        cc_router.CallRecordRepository, "get_latest_active_for_agent", _get_latest
    )
    mark_mock = AsyncMock()
    monkeypatch.setattr(cc_router.CallRecordService, "mark_completed", mark_mock)

    force_mock = AsyncMock()
    monkeypatch.setattr(cc_router.CcAgentResourceService, "force_release", force_mock)
    monkeypatch.setattr(
        cc_router.CcAgentStatusService,
        "get_for_employee",
        AsyncMock(return_value={"status": "ready"}),
    )
    cleared: list[tuple] = []

    async def _fake_clear(t, e):
        cleared.append((t, e))

    monkeypatch.setattr(ccs_mod, "_clear_legs", _fake_clear)

    db = SimpleNamespace(commit=AsyncMock())
    r = SimpleNamespace()

    result = await cc_router.reset_my_agent_call_resource(
        current_user={"tenant_id": 8, "user_id": 42}, db=db, r=r,
    )

    assert result == {"status": "ready"}
    # Kernel leg torn down + session closed.
    assert ("leg-1", "manual_reset") in hangups
    close_mock.assert_awaited()
    # BOTH lingering call records were closed.
    assert mark_mock.await_count == 2
    # In-memory conference/consult legs cleared + resource force-freed.
    assert (8, 42) in cleared
    force_mock.assert_awaited()


@pytest.mark.asyncio
async def test_reset_call_state_no_session_does_not_raise(monkeypatch):
    """No active session / no CDR must not 404 (close() raises NotFoundError)."""
    from app.routers.v1 import call_center as cc_router
    import app.services.agent_webrtc_session_service as sess_mod
    import app.services.call_center.call_control_service as ccs_mod

    monkeypatch.setattr(cc_router, "get_telephony_client", lambda: SimpleNamespace())
    monkeypatch.setattr(
        sess_mod.AgentWebRTCSessionService, "get_active", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        cc_router.CallRecordRepository,
        "get_latest_active_for_agent",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        cc_router.CcAgentResourceService, "force_release", AsyncMock()
    )
    monkeypatch.setattr(
        cc_router.CcAgentStatusService,
        "get_for_employee",
        AsyncMock(return_value={"status": "offline"}),
    )
    async def _noop_clear(t, e):
        return None

    monkeypatch.setattr(ccs_mod, "_clear_legs", _noop_clear)

    result = await cc_router.reset_my_agent_call_resource(
        current_user={"tenant_id": 8, "user_id": 42},
        db=SimpleNamespace(commit=AsyncMock()),
        r=SimpleNamespace(),
    )
    assert result == {"status": "offline"}
