"""
Pydantic schemas for ticket comments — list & create.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse, TimestampSchema


class TicketCommentAttachment(BaseModel):
    """Single attachment entry stored in `ticket_comments.attachments` JSONB.

    Mirrors the response shape of `POST /v1/upload/custom-field-file` so that
    the upload endpoint can be reused as-is on the client.
    """
    model_config = ConfigDict(extra="ignore")

    url: str = Field(..., max_length=2048)
    name: str = Field(..., max_length=512)
    size: int | None = Field(default=None, ge=0)
    content_type: str | None = Field(default=None, max_length=128)


class TicketCommentCreate(BaseModel):
    """Body for `POST /tickets/{ticket_id}/comments`.

    `body` and `attachments` cannot both be empty — checked in the service
    layer (handled there to share logic with future channels).
    """
    body: str | None = Field(default=None, max_length=50000)
    body_format: Literal["html", "markdown"] = "html"
    attachments: list[TicketCommentAttachment] | None = None


class TicketCommentResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    ticket_id: int
    author_id: int | None = None
    author_name: str | None = None
    # Filled from Employee.avatar when the author is a staff user (not stored on the row)
    author_avatar: str | None = None
    body: str | None = None
    body_format: str = "html"
    attachments: list[TicketCommentAttachment] | None = None


class TicketCommentListResponse(PaginatedResponse):
    items: list[TicketCommentResponse]
