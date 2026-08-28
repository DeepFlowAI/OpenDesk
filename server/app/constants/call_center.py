"""
Shared call-center constants: agent/resource/CDR states, Redis keys,
Socket.IO event names, and room helpers.

Business code should import from here instead of repeating string literals.
"""
from __future__ import annotations

import enum


class AgentStatus(str, enum.Enum):
    """PG agent_status.status / Redis visible_status."""

    READY = "ready"
    BUSY = "busy"
    BREAK = "break"
    AFTER_CALL_WORK = "after_call_work"
    OFFLINE = "offline"


class AgentResourceState(str, enum.Enum):
    """Redis cc:agent:resource:* resource_state."""

    IDLE = "idle"
    RESERVED = "reserved"
    RINGING = "ringing"
    IN_CALL = "in_call"
    AFTER_CALL_WORK = "after_call_work"
    UNAVAILABLE = "unavailable"


class CallLifecycleStatus(str, enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"


class CallFinalizationStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class CallSource(str, enum.Enum):
    INBOUND = "inbound"
    AGENT_DIAL = "agent_dial"
    MANUAL_OUTBOUND_TASK = "manual_outbound_task"
    AUTO_OUTBOUND = "auto_outbound"


class CallRecordingStatus(str, enum.Enum):
    NONE = "none"
    RECORDING = "recording"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ConsultState(str, enum.Enum):
    """Host-side consult lifecycle (stored on InCallLegs)."""

    NONE = "none"
    RINGING = "ringing"  # target dialing / browser ringing
    ACTIVE = "active"  # host bridged to consult target


class CcSocketEvent(str, enum.Enum):
    """Socket.IO events emitted to agent rooms (namespace=/chat)."""

    CALL_INCOMING = "cc.call_incoming"
    CALL_ANSWERED = "cc.call_answered"
    CALL_HANGUP = "cc.call_hangup"
    OUTBOUND_RINGING = "cc.outbound_ringing"
    OUTBOUND_ANSWERED = "cc.outbound_answered"
    OUTBOUND_HANGUP = "cc.outbound_hangup"
    OUTBOUND_CUSTOMER_DIALING = "cc.outbound_customer_dialing"
    CONSULT_RESULT = "cc.consult_result"
    TRANSFER_RESULT = "cc.transfer_result"
    CONFERENCE_RESULT = "cc.conference_result"
    CONFERENCE_PARTICIPANT_LEFT = "cc.conference_participant_left"
    MEDIA_RECONNECT_REQUIRED = "cc.media_reconnect_required"
    DEVICE_REGISTRATION_CHANGED = "cc.device_registration_changed"
    WEBRTC_ICE = "cc.webrtc.ice"
    TRANSCRIPT = "cc.transcript"
    WRAP_UP_STARTED = "cc.wrap_up_started"
    WRAP_UP_TIMEOUT = "cc.wrap_up_timeout"


VISIBLE_STATUSES: frozenset[str] = frozenset(s.value for s in AgentStatus)
RESOURCE_STATES: frozenset[str] = frozenset(s.value for s in AgentResourceState)
ACTIVE_RESOURCE_STATES: frozenset[str] = frozenset(
    {
        AgentResourceState.RESERVED.value,
        AgentResourceState.RINGING.value,
        AgentResourceState.IN_CALL.value,
    }
)
ACTIVE_CALL_LIFECYCLE_STATUSES: frozenset[str] = frozenset(
    {CallLifecycleStatus.ACTIVE.value}
)


def agent_socket_room(tenant_id: int, employee_id: int) -> str:
    """Socket.IO room for a workspace agent under namespace=/chat."""
    return f"agent:{tenant_id}:{employee_id}"


def embedded_call_socket_room(tenant_id: int, employee_id: int) -> str:
    """Receive-only Socket.IO room for embedded call surfaces."""
    return f"embedded-call-agent:{tenant_id}:{employee_id}"


def resource_key(tenant_id: int, employee_id: int) -> str:
    return f"cc:agent:resource:{tenant_id}:{employee_id}"


def queue_rr_key(tenant_id: int, group_id: int, channel: str = "call_center") -> str:
    return f"cc:queue:rr:{tenant_id}:group:{group_id}:{channel}"


def offer_accept_lock_key(tenant_id: int, offer_id: str) -> str:
    return f"cc:offer:accept-lock:{tenant_id}:{offer_id}"


def consult_cancel_key(offer_id: str) -> str:
    """Tombstone set when a host cancels a browser consult during RINGING.

    Closes the race where the cancel lands before the background ring task
    has registered its pending offer: the ring path checks this key before
    pushing cc.call_incoming and aborts if set.
    """
    return f"cc:consult:cancel:{offer_id}"


INCALL_LEGS_KEY_PREFIX = "cc:agent:incall"


def incall_legs_key(tenant_id: int, employee_id: int) -> str:
    return f"{INCALL_LEGS_KEY_PREFIX}:{tenant_id}:{employee_id}"


def call_owner_key(call_id: str) -> str:
    return f"cc:call:owner:{call_id}"
