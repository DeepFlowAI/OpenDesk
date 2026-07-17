"""
In-call control schemas — hold/unhold, DTMF, transfer, consult, conference.

These endpoints all operate on the *current agent's own* active call; the
request bodies never carry a call_id (the backend resolves the agent's active
customer leg + WebRTC leg from server-side state).
"""
from typing import Literal

from pydantic import BaseModel, Field


TransferTargetType = Literal["employee", "queue", "external"]


class CallControlResult(BaseModel):
    """Generic result for an in-call control action.

    `ok` is True when the action was accepted by the media kernel. `note`
    carries a machine-readable hint (e.g. "already_ended"); `call_id` echoes
    the customer leg the action targeted when relevant.
    """

    ok: bool
    note: str | None = None
    call_id: str | None = None


class DtmfRequest(BaseModel):
    digits: str = Field(min_length=1, max_length=32, pattern=r"^[0-9*#]+$")


class TransferRequest(BaseModel):
    """Blind (direct) transfer target.

    - employee/queue: `target_id` is the internal id.
    - external: `number` is the destination phone number.
    """

    target_type: TransferTargetType
    target_id: int | None = None
    number: str | None = None


class ConsultRequest(BaseModel):
    """Start a consultation leg (customer is auto-held)."""

    target_type: Literal["employee", "external"]
    target_id: int | None = None
    number: str | None = None


class ConferenceAddRequest(BaseModel):
    """Call a new participant to (eventually) merge into a 3-way call."""

    target_type: Literal["employee", "external"]
    target_id: int | None = None
    number: str | None = None


class MuteRequest(BaseModel):
    """Record the agent's local mute state on the operation trail.

    Muting itself happens in the browser WebRTC layer (track.enabled=false);
    this only persists the state-change event for the call's operation trail.
    """

    muted: bool
