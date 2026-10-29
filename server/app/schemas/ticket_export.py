"""Inputs for preparing and submitting a ticket export."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ticket import TicketQueryRequest


class TicketExportPrepare(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: TicketQueryRequest
    language: Literal["zh", "en"] = "zh"


class TicketExportSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared: str = Field(max_length=2_000_000)
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    fields: list[str] = Field(min_length=1, max_length=200)
