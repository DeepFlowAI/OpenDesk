"""Typed CloudEvents structured JSON envelope."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CloudEventEnvelope(BaseModel):
    """CloudEvents 1.0 envelope plus OpenDesk extension attributes."""

    model_config = ConfigDict(extra="forbid")

    specversion: Literal["1.0"] = "1.0"
    id: str
    source: str
    type: str
    subject: str | None = None
    time: datetime
    datacontenttype: Literal["application/json"] = "application/json"
    dataschema: str
    apiversion: str
    deliveryid: UUID
    test: bool
    data: dict
