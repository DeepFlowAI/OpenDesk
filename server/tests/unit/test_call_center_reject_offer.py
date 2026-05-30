import asyncio

import fakeredis.aioredis
import pytest

from app.libs.telephony.base import TelephonyRPCError
from app.routers.v1 import call_center
from app.schemas.call_center import AcceptOfferRequest, RejectOfferRequest
from app.services.cc_agent_resource_service import CcAgentResourceService


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.decisions: list[tuple[str, dict]] = []

    def resolve_offer(self, offer_id: str, decision: dict) -> bool:
        self.decisions.append((offer_id, decision))
        return True


class _FakeTelephony:
    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self.result = result or {}
        self.error = error

    async def webrtc_offer(self, _sdp: str) -> dict:
        if self.error is not None:
            raise self.error
        return self.result

    async def call_answer(self, _call_id: str) -> None:
        return None

    async def call_hangup(self, _call_id: str, reason: str | None = None) -> None:
        _ = reason
        return None


class _BlockingTelephony(_FakeTelephony):
    def __init__(self) -> None:
        super().__init__(result={"call_id": "webrtc-call-1", "sdp": "v=answer"})
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.offer_calls = 0

    async def webrtc_offer(self, _sdp: str) -> dict:
        self.offer_calls += 1
        self.entered.set()
        await self.release.wait()
        return self.result


async def _prepare_ringing_offer(fake_redis, *, employee_id: int = 42) -> None:
    await CcAgentResourceService.set_visible_status(
        fake_redis, tenant_id=7, employee_id=employee_id, status="ready"
    )
    await CcAgentResourceService.reserve_inbound(
        fake_redis,
        7,
        employee_id,
        call_id="call-1",
        offer_id="offer-1",
        queue_id=9,
        ttl_seconds=30,
    )
    await CcAgentResourceService.mark_ringing(
        fake_redis,
        7,
        employee_id,
        offer_id="offer-1",
        call_id="call-1",
        ttl_seconds=30,
    )


@pytest.mark.asyncio
async def test_reject_offer_requires_current_agent_owner(monkeypatch):
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    fake_orchestrator = _FakeOrchestrator()
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        lambda: fake_orchestrator,
    )
    await _prepare_ringing_offer(fake_redis)

    response = await call_center.reject_offer(
        RejectOfferRequest(offer_id="offer-1"),
        current_user={"tenant_id": 7, "user_id": 99},
        r=fake_redis,
    )

    owner_snapshot = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert response == {"ok": False, "error": "offer_expired"}
    assert fake_orchestrator.decisions == []
    assert owner_snapshot is not None
    assert owner_snapshot["offer_id"] == "offer-1"
    assert owner_snapshot["resource_state"] == "ringing"


@pytest.mark.asyncio
async def test_accept_offer_releases_and_resolves_when_webrtc_offer_fails(monkeypatch):
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    fake_orchestrator = _FakeOrchestrator()
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        lambda: fake_orchestrator,
    )
    monkeypatch.setattr(
        call_center,
        "get_telephony_client",
        lambda: _FakeTelephony(error=TelephonyRPCError(-32003, "media failed")),
    )
    await _prepare_ringing_offer(fake_redis)

    response = await call_center.accept_offer(
        AcceptOfferRequest(offer_id="offer-1", sdp="v=0"),
        current_user={"tenant_id": 7, "user_id": 42},
        db=object(),
        r=fake_redis,
    )

    snapshot = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert response.ok is False
    assert response.error == "webrtc_offer_failed: -32003"
    assert fake_orchestrator.decisions == [
        ("offer-1", {"accept": False, "reason": "webrtc_offer_failed"})
    ]
    assert snapshot is not None
    assert snapshot["resource_state"] == "idle"
    assert snapshot["last_release_reason"] == "webrtc_offer_failed"


@pytest.mark.asyncio
async def test_accept_offer_releases_and_resolves_when_kernel_returns_no_call_id(
    monkeypatch,
):
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    fake_orchestrator = _FakeOrchestrator()
    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        lambda: fake_orchestrator,
    )
    monkeypatch.setattr(
        call_center,
        "get_telephony_client",
        lambda: _FakeTelephony(result={"sdp": "v=0"}),
    )
    await _prepare_ringing_offer(fake_redis)

    response = await call_center.accept_offer(
        AcceptOfferRequest(offer_id="offer-1", sdp="v=0"),
        current_user={"tenant_id": 7, "user_id": 42},
        db=object(),
        r=fake_redis,
    )

    snapshot = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    assert response.ok is False
    assert response.error == "kernel_no_call_id"
    assert fake_orchestrator.decisions == [
        ("offer-1", {"accept": False, "reason": "kernel_no_call_id"})
    ]
    assert snapshot is not None
    assert snapshot["resource_state"] == "idle"
    assert snapshot["last_release_reason"] == "kernel_no_call_id"


@pytest.mark.asyncio
async def test_accept_offer_lock_blocks_duplicate_accept(monkeypatch):
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    fake_orchestrator = _FakeOrchestrator()
    fake_telephony = _BlockingTelephony()

    async def _upsert_session(_db, _tenant_id, _employee_id, _webrtc_call_id):
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.call_center.orchestrator.get_orchestrator",
        lambda: fake_orchestrator,
    )
    monkeypatch.setattr(call_center, "get_telephony_client", lambda: fake_telephony)
    monkeypatch.setattr(
        call_center.AgentWebRTCSessionService,
        "upsert_with_real_call_id",
        _upsert_session,
    )
    await _prepare_ringing_offer(fake_redis)

    first = asyncio.create_task(
        call_center.accept_offer(
            AcceptOfferRequest(offer_id="offer-1", sdp="v=0"),
            current_user={"tenant_id": 7, "user_id": 42},
            db=object(),
            r=fake_redis,
        )
    )
    await asyncio.wait_for(fake_telephony.entered.wait(), timeout=1)

    duplicate = await call_center.accept_offer(
        AcceptOfferRequest(offer_id="offer-1", sdp="v=0"),
        current_user={"tenant_id": 7, "user_id": 42},
        db=object(),
        r=fake_redis,
    )

    assert duplicate.ok is False
    assert duplicate.error == "offer_accept_in_progress"
    assert fake_telephony.offer_calls == 1
    assert fake_orchestrator.decisions == []

    fake_telephony.release.set()
    accepted = await asyncio.wait_for(first, timeout=1)

    snapshot = await CcAgentResourceService.get_snapshot(fake_redis, 7, 42)
    lock_value = await fake_redis.get(
        CcAgentResourceService.offer_accept_lock_key(7, "offer-1")
    )
    assert accepted.ok is True
    assert accepted.call_id == "webrtc-call-1"
    assert fake_telephony.offer_calls == 1
    assert fake_orchestrator.decisions == [
        ("offer-1", {"accept": True, "webrtc_call_id": "webrtc-call-1"})
    ]
    assert snapshot is not None
    assert snapshot["resource_state"] == "in_call"
    assert snapshot["current_call_id"] == "call-1"
    assert lock_value is None
