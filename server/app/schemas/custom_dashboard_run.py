"""Schemas for custom dashboard component execution and cancellation."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.schemas.custom_dashboard import DashboardComponentConfig, DashboardFilterConfig


class CustomDashboardRunRequest(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    page_run_id: UUID
    component_id: str = Field(min_length=1, max_length=64)
    filter_values: dict = Field(default_factory=dict)
    bypass_cache: bool = False
    component_override: DashboardComponentConfig | None = None
    filter_config_override: list[DashboardFilterConfig] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def validate_component_override(self) -> "CustomDashboardRunRequest":
        if self.component_override is not None and self.component_override.id != self.component_id:
            raise ValueError("Component override id must match component_id")
        return self


class CustomDashboardRunResponse(BaseModel):
    request_id: UUID
    status: Literal["success", "failed", "cancelled", "cooldown"]
    result: dict | None = None
    cached: bool = False
    error_code: str | None = None
    message: str | None = None
    error_line: int | None = None
    logs: str | None = None
    logs_truncated: bool = False
    query_count: int = 0
    completed_at: datetime
