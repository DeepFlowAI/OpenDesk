"""
Visitor session schemas.
"""
from pydantic import BaseModel, ConfigDict, Field


class VisitorSessionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    visitor_external_id: str | None = Field(default=None, min_length=1, max_length=128)
    visitor_secret: str | None = Field(default=None, min_length=1, max_length=128)
    visitor_name: str | None = Field(default=None, max_length=64)
    metadata: dict | None = None
    context_token: str | None = Field(default=None, alias="contextToken")


class VisitorSessionResponse(BaseModel):
    visitor_session_token: str
    visitor_external_id: str
    visitor_secret: str | None = None
    expires_in: int
    context_warnings: list[str] = Field(default_factory=list)


class VisitorContextSyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    context_token: str = Field(min_length=1, alias="contextToken")


class VisitorContextSyncResponse(BaseModel):
    ok: bool = True
    warnings: list[str] = Field(default_factory=list)
    customer_synced: bool = False
    session_summary_synced: bool = False
