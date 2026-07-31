"""Inbound answer must not wait on caller→user phone matching.

Regression: create_for_incoming used to call identify_for_record on the
answer path; that loads every user with a phone and delayed the first
prompt by multiple seconds after FlowKit had already SIP-answered.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.libs.telephony.base import CallEvent
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.orchestrator import CallCenterOrchestrator
from app.services.call_record_service import CallRecordService


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


@pytest.mark.asyncio
async def test_inbound_answers_before_slow_user_identify(monkeypatch):
    monkeypatch.setattr(orch_module, "_RTP_WARMUP_SECONDS", 0)
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _FakeSession())

    tel = MockTelephonyClient()
    await tel.connect()
    orch = CallCenterOrchestrator(telephony=tel)
    orch._started = True

    answer_at: float | None = None
    identify_started = asyncio.Event()
    identify_finished = asyncio.Event()
    order: list[str] = []

    async def _claim(_call_id: str) -> bool:
        return True

    async def _did(_to: str) -> int:
        return 1

    async def _match(_db, _tenant_id, **_kwargs):
        rule = SimpleNamespace(
            target_type="voicespeed_agent",
            voicespeed_agent_id="agent-1",
            voicespeed_agent_name="bot",
            transfer_target=None,
        )
        return rule, None

    async def _create_cdr(*_args, **kwargs):
        assert kwargs.get("identify_user") is False
        order.append("cdr")
        return {"id": 1}

    async def _identify(_tenant_id: int, _call_id: str) -> None:
        order.append("identify_start")
        identify_started.set()
        await asyncio.sleep(0.2)
        order.append("identify_done")
        identify_finished.set()

    async def _answer(call_id: str) -> None:
        nonlocal answer_at
        order.append("answer")
        answer_at = asyncio.get_running_loop().time()
        await MockTelephonyClient.call_answer(tel, call_id)

    started = AsyncMock()

    class _FakeWorkflow:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.start = started

    monkeypatch.setattr(orch, "_claim_call", _claim)
    monkeypatch.setattr(orch, "_resolve_tenant_id_for_did", _did)
    monkeypatch.setattr(orch_module, "match_routing_rule", _match)
    monkeypatch.setattr(CallRecordService, "create_for_incoming", staticmethod(_create_cdr))
    monkeypatch.setattr(
        CallRecordService, "identify_user_for_call_managed", staticmethod(_identify)
    )
    monkeypatch.setattr(tel, "call_answer", _answer)
    monkeypatch.setattr(orch_module, "VoiceFlowWorkflow", _FakeWorkflow)

    await orch._on_incoming(
        CallEvent(
            method="call.incoming",
            data={
                "call_id": "in-1",
                "transport": "sip",
                "from": "13800138000",
                "to": "4001889250",
            },
        )
    )

    assert "answer" in order
    assert order.index("cdr") < order.index("answer")
    assert started.await_count == 1
    # Identify runs in the background and must not gate answer / workflow.start.
    assert not identify_finished.is_set()
    await asyncio.wait_for(identify_finished.wait(), timeout=1.0)
    assert order.index("answer") < order.index("identify_done")
    assert "in-1" in orch._workflows
