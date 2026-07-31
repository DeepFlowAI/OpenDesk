"""Unit tests for consult_session — explicit consult state machine."""
from __future__ import annotations

import logging

import pytest

from app.constants.call_center import ConsultState
from app.services.call_center.call_control_service import InCallLegs
from app.services.call_center import consult_session


def test_derive_state_backward_compatible_active():
    legs = InCallLegs(consult_call_id="leg-b")
    assert consult_session.derive_state(legs) is ConsultState.ACTIVE
    assert consult_session.is_consult_active(legs)


def test_derive_state_ringing_from_target_without_leg():
    legs = InCallLegs(consult_target_employee_id=99)
    assert consult_session.derive_state(legs) is ConsultState.RINGING
    assert consult_session.is_consult_active(legs)


def test_apply_none_to_ringing_to_active_to_none(caplog):
    legs = InCallLegs()
    with caplog.at_level(logging.INFO, logger="app.services.call_center.consult_session"):
        consult_session.apply(
            legs,
            to_state=ConsultState.RINGING,
            reason="consult_start_webrtc",
            tenant_id=1,
            host_employee_id=10,
            target_employee_id=20,
        )
        assert legs.consult_state == "ringing"
        assert legs.consult_target_employee_id == 20

        consult_session.apply(
            legs,
            to_state=ConsultState.ACTIVE,
            reason="consult_webrtc_answered",
            tenant_id=1,
            host_employee_id=10,
            consult_call_id="leg-b",
            target_employee_id=20,
            offer_id="offer-1",
        )
        assert legs.consult_state == "active"
        assert legs.consult_call_id == "leg-b"

        consult_session.apply(
            legs,
            to_state=ConsultState.NONE,
            reason="consult_end",
            tenant_id=1,
            host_employee_id=10,
            consult_call_id="leg-b",
        )
        assert legs.consult_state == "none"
        assert legs.consult_call_id is None
        assert legs.consult_target_employee_id is None

    messages = [r.getMessage() for r in caplog.records if "consult_transition" in r.getMessage()]
    assert any("from=none to=ringing" in m for m in messages)
    assert any("from=ringing to=active" in m and "consult_call_id=leg-b" in m for m in messages)
    assert any("from=active to=none" in m for m in messages)


def test_illegal_transition_raises():
    legs = InCallLegs()
    # Jumping ACTIVE → RINGING is not allowed.
    consult_session.apply(
        legs,
        to_state=ConsultState.ACTIVE,
        reason="seed",
        tenant_id=1,
        host_employee_id=10,
        consult_call_id="leg-b",
    )
    with pytest.raises(ValueError, match="illegal consult transition"):
        consult_session.apply(
            legs,
            to_state=ConsultState.RINGING,
            reason="bad",
            tenant_id=1,
            host_employee_id=10,
        )


@pytest.mark.asyncio
async def test_transition_persists_via_legs_helpers(monkeypatch):
    store: dict[tuple[int, int], InCallLegs] = {}

    async def fake_legs(tenant_id: int, employee_id: int) -> InCallLegs:
        key = (tenant_id, employee_id)
        if key not in store:
            store[key] = InCallLegs()
        return store[key]

    async def fake_save(tenant_id: int, employee_id: int, legs: InCallLegs) -> None:
        store[(tenant_id, employee_id)] = legs

    monkeypatch.setattr(
        "app.services.call_center.call_control_service._legs", fake_legs
    )
    monkeypatch.setattr(
        "app.services.call_center.call_control_service._save_legs", fake_save
    )

    await consult_session.transition(
        tenant_id=7,
        host_employee_id=42,
        to_state=ConsultState.RINGING,
        reason="unit",
        target_employee_id=99,
    )
    legs = store[(7, 42)]
    assert legs.consult_state == "ringing"
    assert legs.consult_target_employee_id == 99

    await consult_session.clear(
        tenant_id=7, host_employee_id=42, reason="unit_clear"
    )
    assert store[(7, 42)].consult_state == "none"
