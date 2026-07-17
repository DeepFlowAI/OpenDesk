"""
Schemas for public OpenAgent conversation proxy APIs.
"""
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OpenAgentChatAttachmentRequest(BaseModel):
    file_id: str = Field(..., min_length=1, max_length=512)
    type: Literal["image", "file"]
    name: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., min_length=1, max_length=128)
    size: int = Field(..., gt=0)

    @model_validator(mode="after")
    def validate_attachment_type(self) -> "OpenAgentChatAttachmentRequest":
        normalized_mime = self.mime_type.lower()
        if self.type == "image" and not normalized_mime.startswith("image/"):
            raise ValueError("Image attachment MIME type must start with image/")
        if self.type == "file" and normalized_mime.startswith("image/"):
            raise ValueError("File attachment MIME type must not be an image type")
        return self


class OpenAgentChatRequest(BaseModel):
    message: str | None = Field(default=None, max_length=5000)
    attachments: list[OpenAgentChatAttachmentRequest] = Field(default_factory=list, max_length=1)
    quoted_message_id: int | None = Field(default=None, gt=0)
    client_message_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    last_event_id: str | None = Field(default=None, max_length=128, pattern=r"^r\d+-e\d+$")
    resume: bool = False

    @model_validator(mode="after")
    def validate_message_or_attachment(self) -> "OpenAgentChatRequest":
        if not (self.message or "").strip() and not self.attachments:
            raise ValueError("Message or attachment is required")
        if self.attachments and self.quoted_message_id is not None:
            raise ValueError("Attachment messages cannot quote another message")
        return self


class HumanHandoffRequest(BaseModel):
    handoff_payload: dict[str, Any] | None = None


class OpenAgentFeedbackRequest(BaseModel):
    message_id: int = Field(..., gt=0)
    step_id: int = Field(..., gt=0)
    rating: Literal["like", "dislike"]
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment", mode="before")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        trimmed = value.strip()
        return trimmed or None


class OpenAgentFeedbackResponse(BaseModel):
    message: dict[str, Any]
    step_id: int
    rating: Literal["like", "dislike"]
    comment: str | None = None
    updated_at: str | None = None
