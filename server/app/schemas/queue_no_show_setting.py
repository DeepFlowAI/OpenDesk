"""
Queue no-show cancel setting schemas.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QueueNoShowSettingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class QueueNoShowSettingResponse(QueueNoShowSettingPayload):
    id: int | None = None
    tenant_id: int | None = None
    configured: bool
    updated_by_id: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None
