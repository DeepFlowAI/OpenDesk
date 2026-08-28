from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.call_center.outbound_webrtc_service import (
    OutboundCallEndedError,
    OutboundWebRTCService,
)


def _orch(*, ended=None, owner=(1, 42, "0755")):
    orch = MagicMock()
    orch._peek_outbound_originator = AsyncMock(return_value=owner)
    orch.outbound_ended_reason = AsyncMock(return_value=ended)
    orch.pair_outbound_webrtc = AsyncMock()
    return orch


@pytest.mark.asyncio
async def test_attach_returns_410_when_sip_ends_during_offer(monkeypatch):
    ended_after_offer = {"value": None}

    async def ended_reason(_call_id):
        return ended_after_offer["value"]

    orch = _orch()
    orch.outbound_ended_reason = ended_reason

    async def webrtc_offer(_sdp):
        ended_after_offer["value"] = ("busy", 486)
        return {"call_id": "rtc-1", "sdp": "answer"}

    telephony = MagicMock()
    telephony.webrtc_offer = webrtc_offer
    telephony.call_answer = AsyncMock()
    telephony.call_hangup = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        lambda: orch,
    )

    with pytest.raises(OutboundCallEndedError) as exc:
        await OutboundWebRTCService.attach(
            telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_call_id="sip-1",
            sdp="offer",
        )

    assert exc.value.status_code == 410
    assert exc.value.details == {"reason": "busy", "sip_status": 486}
    telephony.call_hangup.assert_awaited_once_with(
        "rtc-1", reason="outbound_already_ended"
    )
    orch.pair_outbound_webrtc.assert_not_awaited()
    telephony.call_answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_attach_returns_410_before_offer_when_already_ended(monkeypatch):
    orch = _orch(ended=("busy", 486))
    telephony = MagicMock()
    telephony.webrtc_offer = AsyncMock()
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        lambda: orch,
    )

    with pytest.raises(OutboundCallEndedError) as exc:
        await OutboundWebRTCService.attach(
            telephony,
            tenant_pk=1,
            employee_id=42,
            outbound_call_id="sip-1",
            sdp="offer",
        )

    assert exc.value.details["reason"] == "busy"
    telephony.webrtc_offer.assert_not_awaited()
