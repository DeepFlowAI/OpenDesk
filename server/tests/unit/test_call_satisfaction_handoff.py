"""Unit tests for agent-to-satisfaction media handoff semantics."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.exceptions import ConflictError
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center.satisfaction_handoff_service import (
    CallSatisfactionHandoffService,
)
from app.services.call_satisfaction_execution_service import (
    PreparedSatisfactionExecution,
)


def _availability(available: bool = True) -> dict:
    state = {
        "available": available,
        "reason": None if available else "trigger_disabled",
        "message": None if available else "未启用",
    }
    return {
        "call_id": "customer-call",
        "agent_invite": state,
        "auto_transfer": state,
        "flow": {"id": 4, "name": "服务评价", "version_no": 3},
    }


def _prepared() -> PreparedSatisfactionExecution:
    return PreparedSatisfactionExecution(
        execution_id=81,
        tenant_id=7,
        call_record_id=22,
        call_id="customer-call",
        flow_id=4,
        flow_version_id=9,
        flow_name="服务评价",
        flow_version_no=3,
        graph={"nodes": [], "edges": []},
        settings={},
        status="preparing",
        created=True,
    )


def _orchestrator(*, start_error: Exception | None = None):
    telephony = MockTelephonyClient()
    workflow = SimpleNamespace(start=AsyncMock(side_effect=start_error))
    previous = SimpleNamespace(done=SimpleNamespace(is_set=lambda: True))
    orchestrator = SimpleNamespace(
        telephony=telephony,
        active_workflow=Mock(return_value=previous),
        install_satisfaction_workflow=Mock(return_value=workflow),
        remove_satisfaction_workflow=Mock(),
        restore_workflow=Mock(),
        finalize_agent_call=AsyncMock(),
    )
    return orchestrator, workflow, previous


@pytest.mark.asyncio
async def test_agent_invite_handoff_starts_survey_before_hanging_agent_leg() -> None:
    orchestrator, workflow, _previous = _orchestrator()
    with (
        patch.object(
            CallSatisfactionHandoffService,
            "get_availability",
            new=AsyncMock(side_effect=[_availability(), _availability()]),
        ),
        patch(
            "app.services.call_center.satisfaction_handoff_service."
            "CallControlService._resolve_current_call",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    customer_call_id="customer-call",
                    webrtc_call_id="agent-leg",
                )
            ),
        ),
        patch(
            "app.services.call_center.satisfaction_handoff_service."
            "CallSatisfactionExecutionService.prepare_managed",
            new=AsyncMock(return_value=_prepared()),
        ),
        patch(
            "app.services.call_center.orchestrator.get_orchestrator",
            return_value=orchestrator,
        ),
        patch(
            "app.services.call_center.orchestrator._get_redis_client",
            return_value=None,
        ),
        patch(
            "app.services.call_center.satisfaction_handoff_service."
            "CallTrajectoryService.append_for_call_id_best_effort",
            new=AsyncMock(),
        ),
        patch(
            "app.services.call_center.satisfaction_handoff_service._clear_legs",
            new=AsyncMock(),
        ),
    ):
        result = await CallSatisfactionHandoffService.handoff(
            tenant_id=7,
            employee_id=19,
            trigger_source="agent_invite",
        )

    assert result["ok"] is True
    workflow.start.assert_awaited_once()
    assert orchestrator.telephony.recorded == [
        (
            "call.unbridge",
            {"call_id": "customer-call", "other_call_id": "agent-leg"},
        ),
        (
            "call.hangup",
            {"call_id": "agent-leg", "reason": "satisfaction_handoff"},
        ),
    ]
    orchestrator.finalize_agent_call.assert_awaited_once_with(
        tenant_id=7,
        employee_id=19,
        call_id="customer-call",
        reason="satisfaction_started",
        mark_cdr_completed=False,
    )


@pytest.mark.asyncio
async def test_agent_invite_failure_rebridges_original_call() -> None:
    orchestrator, _workflow, previous = _orchestrator(
        start_error=RuntimeError("media failed")
    )
    mark_failed = AsyncMock(return_value="failed")
    with (
        patch.object(
            CallSatisfactionHandoffService,
            "get_availability",
            new=AsyncMock(side_effect=[_availability(), _availability()]),
        ),
        patch(
            "app.services.call_center.satisfaction_handoff_service."
            "CallControlService._resolve_current_call",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    customer_call_id="customer-call",
                    webrtc_call_id="agent-leg",
                )
            ),
        ),
        patch(
            "app.services.call_center.satisfaction_handoff_service."
            "CallSatisfactionExecutionService.prepare_managed",
            new=AsyncMock(return_value=_prepared()),
        ),
        patch(
            "app.services.call_center.satisfaction_handoff_service."
            "CallSatisfactionExecutionService.mark_failed_managed",
            new=mark_failed,
        ),
        patch(
            "app.services.call_center.orchestrator.get_orchestrator",
            return_value=orchestrator,
        ),
        patch(
            "app.services.call_center.orchestrator._get_redis_client",
            return_value=None,
        ),
    ):
        with pytest.raises(ConflictError, match="原通话已恢复"):
            await CallSatisfactionHandoffService.handoff(
                tenant_id=7,
                employee_id=19,
                trigger_source="agent_invite",
            )

    assert orchestrator.telephony.recorded[-1] == (
        "call.bridge",
        {
            "call_id": "customer-call",
            "user_call_id": "customer-call",
            "other_call_id": "agent-leg",
            "transcribe": True,
            "keepalive_on_peer_hangup": True,
        },
    )
    orchestrator.restore_workflow.assert_called_once_with(
        "customer-call", previous
    )
    mark_failed.assert_awaited_once_with(
        execution_id=81,
        reason="handoff_failed",
    )


@pytest.mark.asyncio
async def test_auto_handoff_unavailable_cleanly_skips() -> None:
    prepare = AsyncMock()
    with (
        patch.object(
            CallSatisfactionHandoffService,
            "get_availability",
            new=AsyncMock(return_value=_availability(False)),
        ),
        patch(
            "app.services.call_center.satisfaction_handoff_service."
            "CallSatisfactionExecutionService.prepare_managed",
            new=prepare,
        ),
    ):
        result = await CallSatisfactionHandoffService.handoff(
            tenant_id=7,
            employee_id=19,
            trigger_source="auto_transfer",
        )

    assert result == {
        "ok": False,
        "skipped": True,
        "reason": "trigger_disabled",
    }
    prepare.assert_not_awaited()
