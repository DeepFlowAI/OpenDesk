"""
Pydantic schemas for conversation minutes usage APIs
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.base import TimestampSchema
from app.schemas.cs_summary_config import CsSummaryInteractionRuleResponse
from app.schemas.fd_field_definition import FdFieldDefinitionResponse


class CsSummaryUsageFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    config_id: int
    field_definition_id: int | None = None
    field_key: str | None = None
    sort_order: int
    is_active: bool
    field_definition: FdFieldDefinitionResponse | None = None


class CsSummaryFieldValueResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    tenant_id: int | None = None
    conversation_id: int
    field_definition_id: int | None = None
    field_key: str | None = None
    value: Any = None


class CsSummaryUsageResponse(BaseModel):
    conversation_id: int
    fields: list[CsSummaryUsageFieldResponse]
    rules: list[CsSummaryInteractionRuleResponse]
    values: dict[str, Any] = Field(default_factory=dict)


class CsSummaryFieldValueUpdate(BaseModel):
    field_definition_id: int | None = None
    field_key: str | None = Field(None, max_length=64)
    value: Any = None

    @model_validator(mode="after")
    def validate_field_identifier(self):
        if self.field_definition_id is None and not self.field_key:
            raise ValueError("Either field_definition_id or field_key is required")
        return self
