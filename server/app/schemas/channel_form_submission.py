"""Schemas for visitor-facing Web SDK form messages."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class PublicFormMessageConfigResponse(BaseModel):
    version: int
    config: dict[str, Any]


class PublicFormMessageSubmitRequest(BaseModel):
    version: int = Field(gt=0)
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    values: dict[str, Any] = Field(default_factory=dict)
    source: Literal[
        "outside_service_hours",
        "queue_waiting",
        "queue_full",
        "bot_handoff",
        "bot_action",
    ] = "outside_service_hours"
    conversation_public_id: str | None = Field(default=None, max_length=64)
    queue_type: Literal["employee_group"] | None = None
    queue_id: int | None = Field(default=None, gt=0)

    @field_validator("values")
    @classmethod
    def validate_values_count(cls, values: dict[str, Any]) -> dict[str, Any]:
        if len(values) > 100:
            raise ValueError("Too many form fields")
        return values


class PublicFormMessageSubmitResponse(BaseModel):
    ticket_id: int
    ticket_number: str | None = None
    success_title: str
    success_description: str
    show_ticket_number: bool
    duplicated: bool = False


class PublicFormMessageFileResponse(BaseModel):
    file_id: str
    url: str
    name: str
    size: int
    content_type: str | None = None
