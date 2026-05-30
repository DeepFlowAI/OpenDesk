"""
Telephony catalog schemas — aligned with Tenant Platform API contract.
"""
import ipaddress
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator


TRUNK_TYPE_VALUES = {"inbound", "outbound"}
TRUNK_STATUS_VALUES = {"enabled", "disabled"}
PHONE_STATUS_VALUES = {"available", "assigned", "disabled"}
CALL_TYPE_VALUES = ("inbound", "outbound")
CALL_TYPE_SET = set(CALL_TYPE_VALUES)
MAX_OUTBOUND_TIME_SLOTS = 10
MAX_CONCURRENCY = 1000


class OutboundTimeSlot(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        return _normalize_time(v)


def _normalize_time(value: str) -> str:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {value}, expected HH:MM")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(f"Invalid time format: {value}, expected HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time value: {value}")
    return f"{hour:02d}:{minute:02d}"


def _time_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _validate_outbound_time_slots(slots: list[OutboundTimeSlot]) -> list[dict[str, str]]:
    if len(slots) > MAX_OUTBOUND_TIME_SLOTS:
        raise ValueError(f"At most {MAX_OUTBOUND_TIME_SLOTS} outbound time slots are allowed")
    normalized: list[dict[str, str]] = []
    ranges: list[tuple[int, int]] = []
    for slot in slots:
        start = slot.start
        end = slot.end
        start_min = _time_to_minutes(start)
        end_min = _time_to_minutes(end)
        if start_min >= end_min:
            raise ValueError(f"Outbound time slot end must be after start: {start}-{end}")
        for existing_start, existing_end in ranges:
            if start_min < existing_end and end_min > existing_start:
                raise ValueError("Outbound time slots must not overlap")
        ranges.append((start_min, end_min))
        normalized.append({"start": start, "end": end})
    return normalized


class PeerEndpoint(BaseModel):
    ip: str = Field(..., min_length=1, max_length=64)
    port: int = Field(..., ge=1, le=65535)

    @field_validator("ip")
    @classmethod
    def _validate_ip_or_cidr(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("IP cannot be empty")
        try:
            if "/" in value:
                ipaddress.ip_network(value, strict=False)
            else:
                ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("Invalid IP or CIDR") from exc
        return value


class SipTrunkBase(BaseModel):
    supplier_name: str = Field(..., min_length=1, max_length=128)
    trunk_name: str = Field(..., min_length=1, max_length=128)
    trunk_types: List[str] = Field(..., min_length=1)
    remark: str | None = Field(default=None, max_length=256)
    status: str = Field(default="enabled")
    # peer_endpoints doubles as the outbound destination for trunks that
    # declare "outbound" in trunk_types — catalog_sync derives the FlowKit
    # outbound.server/port from peer_endpoints[0]. Per-call caller_id and
    # callee_prefix are sourced from the PhoneNumber row at dial time.
    peer_endpoints: List[PeerEndpoint] = Field(..., min_length=1)

    @field_validator("trunk_types")
    @classmethod
    def _validate_trunk_types(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one trunk type is required")
        invalid = [t for t in v if t not in TRUNK_TYPE_VALUES]
        if invalid:
            raise ValueError(f"Invalid trunk type: {invalid}")
        return list(dict.fromkeys(v))

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in TRUNK_STATUS_VALUES:
            raise ValueError("Invalid status")
        return v

    @model_validator(mode="after")
    def _validate_unique_endpoints(self) -> "SipTrunkBase":
        seen: set[tuple[str, int]] = set()
        for ep in self.peer_endpoints:
            key = (ep.ip, ep.port)
            if key in seen:
                raise ValueError("Duplicate IP and port combination")
            seen.add(key)
        return self


class SipTrunkCreate(SipTrunkBase):
    pass


class SipTrunkUpdate(SipTrunkBase):
    pass


class SipTrunkResponse(SipTrunkBase):
    id: str
    peer_endpoint_count: int = 0
    created_at: datetime
    updated_at: datetime


class SipTrunkListResponse(BaseModel):
    items: list[SipTrunkResponse]
    total: int
    page: int
    per_page: int
    pages: int


class SipTrunkOption(BaseModel):
    id: str
    trunk_name: str
    supplier_name: str
    status: str
    trunk_types: list[str] = Field(default_factory=list)


def _validate_call_types(value: list[str]) -> list[str]:
    if not value:
        raise ValueError("At least one call type is required")
    seen: set[str] = set()
    for item in value:
        if item not in CALL_TYPE_SET:
            raise ValueError("Invalid call type")
        seen.add(item)
    return [t for t in CALL_TYPE_VALUES if t in seen]


class PhoneNumberCreate(BaseModel):
    phone_number: str = Field(..., min_length=1, max_length=64)
    call_types: list[str] = Field(..., min_length=1)
    trunk_id: str | None = Field(default=None)
    tenant_id: str | None = Field(default=None)
    status: str = Field(default="available")
    remark: str | None = Field(default=None, max_length=256)
    concurrency: int | None = Field(default=None, ge=1, le=MAX_CONCURRENCY)
    called_number_prefix: str | None = Field(default=None, max_length=32)
    outbound_time_slots: list[OutboundTimeSlot] = Field(default_factory=list)

    @field_validator("phone_number")
    @classmethod
    def _phone_number(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Phone number is required")
        return v

    @field_validator("call_types")
    @classmethod
    def _call_types(cls, v: list[str]) -> list[str]:
        return _validate_call_types(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in PHONE_STATUS_VALUES:
            raise ValueError("Invalid status")
        return v

    @field_validator("called_number_prefix")
    @classmethod
    def _called_number_prefix(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @field_validator("outbound_time_slots")
    @classmethod
    def _outbound_time_slots(cls, v: list[OutboundTimeSlot]) -> list[OutboundTimeSlot]:
        _validate_outbound_time_slots(v)
        return v


class PhoneNumberUpdate(BaseModel):
    call_types: list[str] | None = Field(default=None, min_length=1)
    trunk_id: str | None = Field(default=None)
    tenant_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    remark: str | None = Field(default=None, max_length=256)
    concurrency: int | None = Field(default=None, ge=1, le=MAX_CONCURRENCY)
    called_number_prefix: str | None = Field(default=None, max_length=32)
    outbound_time_slots: list[OutboundTimeSlot] | None = Field(default=None)

    @field_validator("call_types")
    @classmethod
    def _call_types(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return _validate_call_types(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in PHONE_STATUS_VALUES:
            raise ValueError("Invalid status")
        return v

    @field_validator("called_number_prefix")
    @classmethod
    def _called_number_prefix(cls, v: str | None) -> str | None:
        if v is None:
            return v
        value = v.strip()
        return value or None

    @field_validator("outbound_time_slots")
    @classmethod
    def _outbound_time_slots(
        cls, v: list[OutboundTimeSlot] | None
    ) -> list[OutboundTimeSlot] | None:
        if v is None:
            return v
        _validate_outbound_time_slots(v)
        return v


class PhoneNumberResponse(BaseModel):
    id: str
    phone_number: str
    call_types: list[str] = Field(default_factory=list)
    trunk_id: str | None = None
    trunk_name: str | None = None
    supplier_name: str | None = None
    tenant_id: str | None = None
    tenant_name: str | None = None
    tenant_status: str | None = None
    status: str
    remark: str | None = None
    concurrency: int | None = None
    called_number_prefix: str | None = None
    outbound_time_slots: list[OutboundTimeSlot] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PhoneNumberListResponse(BaseModel):
    items: list[PhoneNumberResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PhoneNumberBatchPayload(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=200)
    call_types: list[str] | None = Field(default=None, min_length=1)
    trunk_id: str | None = Field(default=None)
    tenant_id: str | None = Field(default=None)
    status: str | None = Field(default=None)

    @field_validator("call_types")
    @classmethod
    def _call_types(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return _validate_call_types(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in PHONE_STATUS_VALUES:
            raise ValueError("Invalid status")
        return v


class BatchUpdateFailure(BaseModel):
    id: str
    phone_number: str | None = None
    reason: str


class BatchUpdateResponse(BaseModel):
    success_count: int
    fail_count: int
    failures: list[BatchUpdateFailure] = []
