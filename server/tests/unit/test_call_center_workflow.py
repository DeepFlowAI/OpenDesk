"""
Unit tests for the voice-flow workflow + node executors.

Uses MockTelephonyClient so we can assert which RPCs got called in what order
without touching FlowKit.
"""
import pytest

from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center.workflow import VoiceFlowWorkflow


def _graph_play_then_hangup() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "s", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
            {
                "id": "p", "type": "play", "position": {"x": 100, "y": 0},
                "data": {"prompt": {"kind": "tts", "text": "hello"}},
            },
            {"id": "h", "type": "hangup", "position": {"x": 200, "y": 0}, "data": {"pre_play": None}},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "p", "source_handle": "next"},
            {"id": "e2", "source": "p", "target": "h", "source_handle": "next"},
        ],
        "variables": [],
    }


def _graph_collect_then_condition() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "s", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
            {
                "id": "c", "type": "collect", "position": {"x": 100, "y": 0},
                "data": {
                    "prompt": {"kind": "tts", "text": "press 1"},
                    "barge_in_disabled": False,
                    "input": {
                        "mode": "single",
                        "min_digits": 1, "max_digits": 1,
                        "terminator": "#",
                        "skip_terminator_on_single": True,
                    },
                    "timeout": {"first_input_ms": 5000, "inter_digit_ms": 10000},
                    "retry": {"enabled": False, "no_input": 1, "no_match": 1},
                    "output_variable": "ui",
                },
            },
            {
                "id": "cond", "type": "condition", "position": {"x": 200, "y": 0},
                "data": {
                    "groups": [{
                        "id": "vip", "name": "VIP", "logic": "AND",
                        "conditions": [{"variable": "ui", "operator": "eq", "value": "1"}],
                    }],
                },
            },
            {"id": "h1", "type": "hangup", "position": {"x": 300, "y": 0}, "data": {"pre_play": None}},
            {"id": "h2", "type": "hangup", "position": {"x": 300, "y": 100}, "data": {"pre_play": None}},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "c", "source_handle": "next"},
            {"id": "e2", "source": "c", "target": "cond", "source_handle": "success"},
            {"id": "e3", "source": "cond", "target": "h1", "source_handle": "vip"},
            {"id": "e4", "source": "cond", "target": "h2", "source_handle": "default"},
        ],
        "variables": [],
    }


class TestWorkflow:

    @pytest.mark.asyncio
    async def test_play_then_hangup(self):
        tel = MockTelephonyClient()
        await tel.connect()
        wf = VoiceFlowWorkflow(
            call_id="call-1",
            tenant_id=1,
            graph=_graph_play_then_hangup(),
            telephony=tel,
        )
        await wf.start()
        # After start, we're waiting on call.play_end
        assert wf.done.is_set() is False
        # Simulate play_end event
        await wf.handle_event("call.play_end", {"call_id": "call-1"})
        # Workflow should call call.hangup
        assert wf.done.is_set() is True
        methods = [m for m, _ in tel.recorded]
        # Expected order: call.say (play), then call.hangup
        assert methods.index("call.say") < methods.index("call.hangup")

    @pytest.mark.asyncio
    async def test_collect_single_then_condition_vip_branch(self):
        tel = MockTelephonyClient()
        await tel.connect()
        wf = VoiceFlowWorkflow(
            call_id="c1",
            tenant_id=1,
            graph=_graph_collect_then_condition(),
            telephony=tel,
        )
        await wf.start()
        # Now waiting on call.dtmf
        await wf.handle_event("call.dtmf", {"call_id": "c1", "digit": "1"})
        # After collect → condition → h1 (VIP branch)
        assert wf.done.is_set() is True
        # Hangup was called
        assert any(m == "call.hangup" for m, _ in tel.recorded)
        # Variable was set
        assert wf.ctx.variables["ui"] == "1"

    @pytest.mark.asyncio
    async def test_collect_then_default_branch(self):
        tel = MockTelephonyClient()
        await tel.connect()
        wf = VoiceFlowWorkflow(
            call_id="c2",
            tenant_id=1,
            graph=_graph_collect_then_condition(),
            telephony=tel,
        )
        await wf.start()
        await wf.handle_event("call.dtmf", {"call_id": "c2", "digit": "9"})
        # 9 != 1 → default → h2 → hangup
        assert wf.done.is_set() is True
        assert wf.ctx.variables["ui"] == "9"
