"""
Schemas for conversation file upload and access.
"""
from pydantic import BaseModel, Field


class ConversationFileUploadResponse(BaseModel):
    schema_version: int = 1
    file_id: str = Field(..., min_length=1)
    name: str
    size: int
    mime_type: str
    access_url: str


class ConversationFileAccessResponse(BaseModel):
    url: str
    expires_seconds: int
