"""Open API schemas for call recordings."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OpenCallRecordingItem(BaseModel):
    public_id: UUID
    phase: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    download_url: str | None = None
    download_url_expires_at: datetime | None = None
    failure_reason: str | None = None


class OpenCallRecordingListResponse(BaseModel):
    call_public_id: UUID
    items: list[OpenCallRecordingItem]


class OpenCallRecordingLinkResponse(BaseModel):
    public_id: UUID
    call_public_id: UUID
    download_url: str
    download_url_expires_at: datetime
