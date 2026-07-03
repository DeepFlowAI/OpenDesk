"""
Trace-coverage tests for the call-center orchestrator.

Every async task that handles a call must carry the call's trace_id + call_id
in the contextvars before emitting logs — including handlers that do NOT go
through `_route_event` (recording-completed, hangup, outbound lifecycle). A
production VoiceSpeed call showed an empty trace_id on its "Recording saved"
log because the per-call trace context wasn't applied on those paths.
"""
import logging

import pytest

from app.core.trace import (
    TraceFilter,
    build_traceparent,
    get_call_id,
    get_trace_id,
    parse_traceparent,
    set_call_id,
    set_trace_id,
)
from app.libs.telephony.base import CallEvent
from app.libs.telephony.providers.mock.client import MockTelephonyClient
from app.services.call_center import orchestrator as orch_module
from app.services.call_center.orchestrator import CallCenterOrchestrator


class _SessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_exc):
        return False


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []
        # Same filter the real stdout/OTel handlers use to stamp trace_id.
        self.addFilter(TraceFilter())

    def emit(self, record):
        self.records.append(record)


@pytest.fixture(autouse=True)
def _reset_context():
    # Each test starts from a clean trace context.
    set_trace_id(None)
    set_call_id(None)
    yield


def test_build_traceparent_round_trips():
    trace_id = "a" * 32
    tp = build_traceparent(trace_id)
    assert tp.startswith("00-")
    assert parse_traceparent(tp) == trace_id


@pytest.mark.asyncio
async def test_recording_completed_log_carries_trace_id(monkeypatch):
    """A log emitted from `_on_recording_completed` (NOT a _route_event path,
    and fired after the workflow is gone) must carry the call's trace_id."""

    trace_id = "f" * 32
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _SessionCtx())

    async def _save_recording(*_a, **_k):
        return True

    monkeypatch.setattr(
        orch_module.CallRecordService, "save_recording", _save_recording,
    )

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    # The call has ended (no workflow), but its trace mapping is still alive.
    orch._register_call_trace("media-1", trace_id, "media-1")

    handler = _CaptureHandler()
    orch_logger = logging.getLogger("app.services.call_center.orchestrator")
    orch_logger.addHandler(handler)
    orch_logger.setLevel(logging.INFO)
    try:
        await orch._on_recording_completed(
            CallEvent(
                method="call.recording.completed",
                data={"call_id": "media-1", "oss_url": "oss://rec/1.wav"},
            )
        )
    finally:
        orch_logger.removeHandler(handler)

    saved = [r for r in handler.records if "Recording saved" in r.getMessage()]
    assert saved, "expected a 'Recording saved' log line"
    assert saved[0].trace_id == trace_id
    # Contextvars are bound for the whole handler.
    assert get_trace_id() == trace_id
    assert get_call_id() == "media-1"


@pytest.mark.asyncio
async def test_bind_call_trace_prefers_live_workflow(monkeypatch):
    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())

    class _WF:
        class ctx:  # noqa: N801 - tiny stub
            variables = {"sys._trace_id": "b" * 32, "sys._trace_call_id": "root-9"}

    orch._workflows["call-9"] = _WF()  # type: ignore[assignment]
    orch.bind_call_trace("call-9")
    assert get_trace_id() == "b" * 32
    assert get_call_id() == "root-9"


@pytest.mark.asyncio
async def test_hangup_handler_binds_trace_from_map(monkeypatch):
    """`_on_hangup` does not go through _route_event; it must bind the trace."""

    trace_id = "c" * 32
    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _SessionCtx())
    monkeypatch.setattr(orch_module, "_get_redis_client", lambda: None)

    # Make the CDR lookup return nothing so the handler short-circuits quickly.
    class _NoRow:
        def scalar_one_or_none(self):
            return None

    class _DbNoRow:
        async def execute(self, _q):
            return _NoRow()

    class _SessionNoRow:
        async def __aenter__(self):
            return _DbNoRow()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(orch_module, "AsyncSessionLocal", lambda: _SessionNoRow())

    orch = CallCenterOrchestrator(telephony=MockTelephonyClient())
    orch._register_call_trace("call-7", trace_id, "call-7")

    # Avoid leaving the 300s delayed-cleanup task pending after the test.
    async def _noop_cleanup(_call_id):
        return None

    monkeypatch.setattr(orch, "_delayed_trace_cleanup", _noop_cleanup)

    await orch._on_hangup(
        CallEvent(method="call.hangup", data={"call_id": "call-7", "reason": "bye"})
    )

    assert get_trace_id() == trace_id
    assert get_call_id() == "call-7"
