"""
Consult session — single write path for host-side consult state on InCallLegs.

Telephony (bridge/hangup/tone) stays in CallControlService. This module owns:
  - explicit ConsultState (none / ringing / active)
  - mutating consult_* fields on InCallLegs
  - structured consult_transition logs

Call sites must go through ``transition`` / ``clear`` / ``replace_leg`` instead
of assigning ``legs.consult_*`` ad hoc.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.constants.call_center import ConsultState

if TYPE_CHECKING:
    from app.services.call_center.call_control_service import InCallLegs

logger = logging.getLogger(__name__)

# Legal edges for host consult state. Same-state writes are allowed (idempotent
# renew / leg replace) and logged at DEBUG.
_ALLOWED: frozenset[tuple[ConsultState, ConsultState]] = frozenset(
    {
        (ConsultState.NONE, ConsultState.RINGING),
        (ConsultState.NONE, ConsultState.ACTIVE),  # SIP may skip explicit ringing
        (ConsultState.RINGING, ConsultState.ACTIVE),
        (ConsultState.RINGING, ConsultState.NONE),
        (ConsultState.ACTIVE, ConsultState.NONE),
        (ConsultState.ACTIVE, ConsultState.ACTIVE),  # media-reconnect leg replace
        (ConsultState.RINGING, ConsultState.RINGING),
        (ConsultState.NONE, ConsultState.NONE),
    }
)


def derive_state(legs: "InCallLegs") -> ConsultState:
    """Read consult state from legs (backward compatible with pre-field data)."""
    raw = getattr(legs, "consult_state", None) or ""
    if raw:
        try:
            return ConsultState(raw)
        except ValueError:
            pass
    if legs.consult_call_id:
        return ConsultState.ACTIVE
    if legs.consult_target_employee_id or legs.consult_offer_id:
        return ConsultState.RINGING
    return ConsultState.NONE


def is_consult_active(legs: "InCallLegs") -> bool:
    """True while the host has an in-flight or live consult (for UI restore)."""
    return derive_state(legs) in {ConsultState.RINGING, ConsultState.ACTIVE}


def _log_transition(
    *,
    tenant_id: int,
    host_employee_id: int,
    from_state: ConsultState,
    to_state: ConsultState,
    reason: str,
    consult_call_id: str | None = None,
    target_employee_id: int | None = None,
    offer_id: str | None = None,
    level: int = logging.INFO,
) -> None:
    logger.log(
        level,
        "consult_transition tenant=%s host=%s from=%s to=%s "
        "consult_call_id=%s target_employee=%s offer_id=%s reason=%s",
        tenant_id,
        host_employee_id,
        from_state.value,
        to_state.value,
        consult_call_id or "-",
        target_employee_id if target_employee_id is not None else "-",
        offer_id or "-",
        reason,
    )


def apply(
    legs: "InCallLegs",
    *,
    to_state: ConsultState,
    reason: str,
    tenant_id: int,
    host_employee_id: int,
    consult_call_id: str | None = None,
    target_employee_id: int | None = None,
    offer_id: str | None = None,
    keep_target_on_clear: bool = False,
) -> ConsultState:
    """Mutate ``legs`` consult fields to ``to_state`` and emit a transition log.

    Returns the previous state. Raises ``ValueError`` on illegal transitions.
    """
    from_state = derive_state(legs)
    if (from_state, to_state) not in _ALLOWED:
        raise ValueError(
            f"illegal consult transition {from_state.value} → {to_state.value} "
            f"(reason={reason})"
        )

    if to_state is ConsultState.NONE:
        legs.consult_state = ConsultState.NONE.value
        legs.consult_call_id = None
        if not keep_target_on_clear:
            legs.consult_target_employee_id = None
            legs.consult_offer_id = None
        level = logging.INFO if from_state is not ConsultState.NONE else logging.DEBUG
        _log_transition(
            tenant_id=tenant_id,
            host_employee_id=host_employee_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            consult_call_id=consult_call_id,
            target_employee_id=target_employee_id,
            offer_id=offer_id,
            level=level,
        )
        return from_state

    if to_state is ConsultState.RINGING:
        legs.consult_state = ConsultState.RINGING.value
        if consult_call_id is not None:
            legs.consult_call_id = consult_call_id
        if target_employee_id is not None:
            legs.consult_target_employee_id = target_employee_id
        if offer_id is not None:
            legs.consult_offer_id = offer_id
    else:  # ACTIVE
        legs.consult_state = ConsultState.ACTIVE.value
        if consult_call_id is not None:
            legs.consult_call_id = consult_call_id
        if target_employee_id is not None:
            legs.consult_target_employee_id = target_employee_id
        if offer_id is not None:
            legs.consult_offer_id = offer_id

    level = (
        logging.DEBUG
        if from_state is to_state and to_state is ConsultState.ACTIVE
        else logging.INFO
    )
    _log_transition(
        tenant_id=tenant_id,
        host_employee_id=host_employee_id,
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        consult_call_id=legs.consult_call_id,
        target_employee_id=legs.consult_target_employee_id,
        offer_id=legs.consult_offer_id,
        level=level,
    )
    return from_state


async def transition(
    *,
    tenant_id: int,
    host_employee_id: int,
    to_state: ConsultState,
    reason: str,
    consult_call_id: str | None = None,
    target_employee_id: int | None = None,
    offer_id: str | None = None,
) -> "InCallLegs":
    """Load host legs, apply consult transition, persist. Single write path."""
    from app.services.call_center.call_control_service import _legs, _save_legs

    legs = await _legs(tenant_id, host_employee_id)
    apply(
        legs,
        to_state=to_state,
        reason=reason,
        tenant_id=tenant_id,
        host_employee_id=host_employee_id,
        consult_call_id=consult_call_id,
        target_employee_id=target_employee_id,
        offer_id=offer_id,
    )
    await _save_legs(tenant_id, host_employee_id, legs)
    return legs


async def clear(
    *,
    tenant_id: int,
    host_employee_id: int,
    reason: str,
    consult_call_id: str | None = None,
) -> "InCallLegs":
    """End consult on the host (NONE)."""
    return await transition(
        tenant_id=tenant_id,
        host_employee_id=host_employee_id,
        to_state=ConsultState.NONE,
        reason=reason,
        consult_call_id=consult_call_id,
    )
