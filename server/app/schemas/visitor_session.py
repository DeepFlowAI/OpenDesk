"""
Visitor session schemas.
"""
from pydantic import BaseModel, Field


class VisitorSessionRequest(BaseModel):
    visitor_external_id: str | None = Field(default=None, min_length=1, max_length=128)
    visitor_secret: str | None = Field(default=None, min_length=1, max_length=128)
    visitor_name: str | None = Field(default=None, max_length=64)
    metadata: dict | None = None


class VisitorSessionResponse(BaseModel):
    visitor_session_token: str
    visitor_external_id: str
    visitor_secret: str | None = None
    expires_in: int
