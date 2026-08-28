"""
Schemas for SIP extension management (admin) and agent call-device selection.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import PaginatedResponse


# ─────────── Admin: SIP extension management ───────────


class BoundEmployeeBrief(BaseModel):
    """Minimal identity of an agent bound to / occupying an extension."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    avatar: str | None = None


class SipExtensionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    extension_number: str = Field(min_length=2, max_length=10)
    bound_employee_ids: list[int] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not (1 <= len(normalized) <= 50):
            raise ValueError("Name must be 1-50 characters")
        return normalized

    @field_validator("extension_number")
    @classmethod
    def validate_extension_number(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.isdigit():
            raise ValueError("Extension number must contain digits only")
        if not (2 <= len(normalized) <= 10):
            raise ValueError("Extension number must be 2-10 digits")
        return normalized

    @field_validator("bound_employee_ids")
    @classmethod
    def dedupe_bound_ids(cls, value: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for emp_id in value:
            if emp_id in seen:
                continue
            seen.add(emp_id)
            out.append(emp_id)
        return out


class SipExtensionUpdate(BaseModel):
    """Edit name and/or binding set. Extension number is immutable."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    # Presence of the key means "replace the binding set" (empty list = unbind all).
    # Absence means "leave bindings unchanged".
    bound_employee_ids: list[int] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not (1 <= len(normalized) <= 50):
            raise ValueError("Name must be 1-50 characters")
        return normalized

    @field_validator("bound_employee_ids")
    @classmethod
    def dedupe_bound_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        seen: set[int] = set()
        out: list[int] = []
        for emp_id in value:
            if emp_id in seen:
                continue
            seen.add(emp_id)
            out.append(emp_id)
        return out


class SipExtensionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    extension_number: str
    sip_user_id: str
    auth_account: str
    auth_password_masked: str
    registration_status: str
    last_registered_at: datetime | None = None
    is_active: bool
    disabled_at: datetime | None = None
    bound_employee_ids: list[int] = Field(default_factory=list)
    bound_employees: list[BoundEmployeeBrief] = Field(default_factory=list)
    current_occupant_employee_id: int | None = None
    current_occupant: BoundEmployeeBrief | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SipExtensionListResponse(PaginatedResponse):
    items: list[SipExtensionResponse]


class SipRegistrationInfo(BaseModel):
    """Full registration info available to extension administrators."""

    registration_server: str
    registration_port: int | None = None
    transport: str
    sip_user_id: str
    auth_account: str
    auth_password: str | None = None
    auth_password_masked: str
    registration_status: str


class SipExtensionSecretResponse(BaseModel):
    """Create / reset-password result: the record plus one-time secret info."""

    record: SipExtensionResponse
    registration_info: SipRegistrationInfo


class BindableEmployee(BaseModel):
    """Employee eligible to be bound to a SIP extension."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    avatar: str | None = None


# ─────────── Agent: current call device ───────────


class AvailableDevice(BaseModel):
    """A device the current agent may select as their call device.

    Generic shape shared by every device type so the selector never hardcodes
    "not browser → SIP". ``extension_number`` is only set for sip_phone.
    """

    device_type: str
    name: str
    available: bool
    unavailable_reason: str | None = None
    extension_number: str | None = None
    registration_status: str | None = None
    # Shared-phone occupancy hints for the workspace selector.
    status_message: str | None = None
    current_occupant_employee_id: int | None = None
    current_occupant_name: str | None = None
    blocking_agent_name: str | None = None
    blocking_agent_count: int | None = None


class AvailableDeviceList(BaseModel):
    items: list[AvailableDevice]


class CurrentDeviceResponse(BaseModel):
    """The agent's currently selected device (None when nothing chosen yet)."""

    device_type: str | None = None
    name: str | None = None
    available: bool = False
    unavailable_reason: str | None = None
    extension_number: str | None = None
    registration_status: str | None = None
    status_message: str | None = None
    current_occupant_employee_id: int | None = None
    current_occupant_name: str | None = None
    blocking_agent_name: str | None = None
    blocking_agent_count: int | None = None


class CurrentDeviceUpdate(BaseModel):
    device_type: str = Field(min_length=1, max_length=24)
