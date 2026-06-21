"""
Agent status Pydantic schemas
"""
from pydantic import BaseModel, Field


class AgentStatusResponse(BaseModel):
    user_id: int
    status: str
    current_count: int
    max_concurrent: int


class AgentStatusUpdate(BaseModel):
    status: str


class AgentMaxConcurrentUpdate(BaseModel):
    max_concurrent: int = Field(ge=1)


class AgentStatsResponse(BaseModel):
    current_count: int
    max_concurrent: int
