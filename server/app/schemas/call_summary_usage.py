"""
Pydantic schemas for call summary usage APIs.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.base import TimestampSchema
from app.schemas.call_summary_config import CallSummaryInteractionRuleResponse
from app.schemas.fd_field_definition import FdFieldDefinitionResponse


class CallSummaryUsageFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    config_id: int
    field_definition_id: int | None = None
    field_key: str | None = None
    sort_order: int
    is_active: bool
    field_definition: FdFieldDefinitionResponse | None = None


class CallSummaryFieldValueResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    tenant_id: int | None = None
    call_record_id: int
    field_definition_id: int | None = None
    field_key: str | None = None
    value: Any = None


class CallSummaryUsageResponse(BaseModel):
    call_record_id: int
    fields: list[CallSummaryUsageFieldResponse]
    rules: list[CallSummaryInteractionRuleResponse]
    values: dict[str, Any] = Field(default_factory=dict)


class CallSummaryFieldValueUpdate(BaseModel):
    field_definition_id: int | None = None
    field_key: str | None = Field(None, max_length=64)
    value: Any = None

    @model_validator(mode="after")
    def validate_field_identifier(self):
        if self.field_definition_id is None and not self.field_key:
            raise ValueError("Either field_definition_id or field_key is required")
        return self
