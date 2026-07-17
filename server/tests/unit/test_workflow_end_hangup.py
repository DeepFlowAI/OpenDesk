"""
A call-center workflow that ends WITHOUT bridging the caller to an agent (no
queue available, agent in wrap-up / all busy, timeout, error) must hang up the
caller's SIP leg — otherwise the caller is left in dead air. A bridged handoff
must NOT be hung up (the agent owns the call).
"""
import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center.workflow import VoiceFlowWorkflow

_GRAPH = {"nodes": [{"id": "start", "type": "start"}], "edges": []}


def _workflow(tel):
    return VoiceFlowWorkflow(call_id="c1", tenant_id=7, graph=_GRAPH, telephony=tel)


@pytest.mark.asyncio
async def test_unbridged_end_hangs_up_caller():
    tel = MockTelephonyClient()
    await tel.connect()
    wf = _workflow(tel)

    await wf._end("queue_timeout")

    methods = [(m, p.get("call_id")) for m, p in tel.recorded]
    assert ("call.hangup", "c1") in methods


@pytest.mark.asyncio
async def test_no_agent_none_reason_hangs_up_caller():
    # goto_or_end with a dangling outlet yields End() → reason None.
    tel = MockTelephonyClient()
    await tel.connect()
    wf = _workflow(tel)

    await wf._end(None)

    methods = [(m, p.get("call_id")) for m, p in tel.recorded]
    assert ("call.hangup", "c1") in methods


@pytest.mark.asyncio
async def test_bridged_end_does_not_hang_up():
    tel = MockTelephonyClient()
    await tel.connect()
    wf = _workflow(tel)

    await wf._end("bridged")

    methods = [(m, p.get("call_id")) for m, p in tel.recorded]
    assert ("call.hangup", "c1") not in methods
